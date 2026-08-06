import os
import sys
import re
import shutil
import subprocess
import yaml
import json
import hashlib
import requests
import urllib.parse
import random
import time
import threading
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor

# =====================================================================
# CONTRATOS DE SERVICIO (DATACLASSES)
# =====================================================================

@dataclass(frozen=True)
class DocumentoTarget:
    """Input inicial del documento detectado en los feeds/fichas"""
    url_origen: str
    descripcion: str
    tipo_sugerido: str  # 'PCA', 'PPT', 'Anexo', 'Otro'
    tamano_estimated_bytes: Optional[int] = None

@dataclass(frozen=True)
class ExtraccionResult:
    """Output garantizado del procesamiento de un documento"""
    exito: bool
    texto: str
    metodo: str                # 'pymupdf', 'tesseract', 'ninguno'
    num_paginas: int
    paginas_ocr: int
    idioma_detectado: str       # 'es', 'ca', 'desconocido'
    version_reglas: int         # Versión del motor de clasificación/extracción utilizado
    tiempo_procesamiento_ms: int
    error_detalle: Optional[str] = None

# =====================================================================
# JERARQUÍA DE ERRORES ESTRUCTURADOS
# =====================================================================

class LectorException(Exception):
    """Excepción base para la Capa 4 (Lector Documental)"""
    pass

class NetworkError(LectorException):
    """Errores de conexión, DNS, timeouts o códigos de estado HTTP incorrectos"""
    pass

class FormatError(LectorException):
    """PDFs corruptos, cifrados o archivos que no cumplen con la firma mágica %PDF"""
    pass

class ExtractionError(LectorException):
    """Fallo al acceder a las páginas de texto o fallo interno del parser PyMuPDF"""
    pass

class OCRError(LectorException):
    """Fallo por falta del binario Tesseract o error al invocar la API de OCR"""
    pass

# =====================================================================
# MOTOR DEL LECTOR DOCUMENTAL
# =====================================================================

class Lector:
    """
    Clase responsable de la descarga, extracción de texto, clasificación
    y OCR de los pliegos y anexos de las licitaciones (Capa 4).
    """
    
    VERSION_REGLAS = 1

    def __init__(self, db_memoria=None, config_dir: str = "config", run_id: int = 9999):
        self.db = db_memoria
        self.config_dir = config_dir
        self.run_id = run_id
        
        self.config = self._cargar_configuracion()
        
        # Atributos de estado del bootstrap
        self.dependencias_ok = False
        self.ocr_estado = "ocr_ausente"  # ocr_disponible, ocr_parcial, ocr_ausente
        self.tesseract_path_bin = None
        self.tesseract_version = ""
        self.tesseract_idiomas = []
        self.modo_ocr_diferido = False
        
        # Logs de inicialización
        self.inicializado = False
        
        # Estructuras para Backpressure Dinámica por Host
        self.host_cooldowns = {}
        self.cooldown_lock = threading.Lock()

        # Estructura de Métricas compartida para monitoreo
        self.metrics = {
            "success": 0,
            "failed": 0,
            "bypass": 0,
            "duplicate": 0,
            "bytes": 0,
            "latencies": []
        }
        self.metrics_lock = threading.Lock()

    def _cargar_configuracion(self) -> Dict[str, Any]:
        """Carga la configuración global lector_config desde lector.yaml o usa defaults"""
        path = os.path.join(self.config_dir, "lector.yaml")
        
        default_config = {
            "descargas": {
                "max_concurrentes": 3,
                "throttling_segundos": 2.0,
                "timeout_segundos": 30.0,
                "max_reintentos": 3,
                "ignorar_extensiones": [".zip", ".dwg", ".xlsx", ".docx", ".rar"]
            },
            "extraccion": {
                "min_caracteres_pagina_digital": 100,
                "idiomas_ocr": "spa+cat",
                "reglas_version": self.VERSION_REGLAS
            },
            "modo_diferido_ocr": False,
            "simulacion_dry_run": False
        }
        
        if not os.path.exists(path):
            return default_config
            
        try:
            with open(path, "r", encoding="utf-8") as f:
                loaded = yaml.safe_load(f) or {}
                # Fusionar diccionarios de forma segura
                for k, v in loaded.items():
                    if isinstance(v, dict) and k in default_config:
                        default_config[k].update(v)
                    else:
                        default_config[k] = v
                return default_config
        except Exception as e:
            print(f"[!] Lector: Error cargando config/lector.yaml: {e}. Usando valores por defecto.")
            return default_config

    def registrar_log_JSONL(self, action: str, expediente_id: Optional[str] = None, reason: Optional[str] = None, duration_ms: Optional[int] = None):
        """Registra un evento estructurado JSONL. Delega en la Capa 3 si está disponible, o escribe a pipeline.jsonl directamente."""
        if self.db:
            try:
                self.db.registrar_log_json(
                    run_id=self.run_id,
                    action=action,
                    expediente_id=expediente_id,
                    reason=reason,
                    duration_ms=duration_ms,
                    updated_by="lector"
                )
                return
            except Exception:
                pass
                
        # Fallback a escritura directa en pipeline.jsonl si no hay DB
        log_path = os.path.join("data", "pipeline.jsonl")
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        entry = {
            "timestamp": timestamp,
            "run_id": self.run_id,
            "action": action,
            "updated_by": "lector"
        }
        if expediente_id:
            entry["expediente_id"] = expediente_id
        if reason:
            entry["reason"] = reason
        if duration_ms is not None:
            entry["duration_ms"] = duration_ms
            
        try:
            os.makedirs("data", exist_ok=True)
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception as e:
            print(f"[!] Error al escribir log de inicialización en caliente: {e}")

    # =====================================================================
    # 🧱 1. VALIDACIÓN DE DEPENDENCIAS Y BOOTSTRAP
    # =====================================================================

    def ejecutar_bootstrap(self) -> bool:
        """
        Ejecuta la inicialización determinista del entorno documental (Paso 1).
        Verifica dependencias de Python, busca el binario Tesseract OCR, inicializa
        las carpetas físicas y verifica permisos de escritura.
        """
        self.registrar_log_JSONL(action="bootstrap_start")
        print("[~] [lector] Ejecutando bootstrap de inicialización documental...")
        
        # 1. Validar dependencias de Python
        self.dependencias_ok = self._validar_dependencias_python()
        
        # 2. Autodetectar Tesseract OCR
        self._autodetectar_tesseract()
        
        # 3. Validar carpetas locales de almacenamiento
        directorios_escribibles = self._inicializar_directorios()
        
        # 4. Cargar configuraciones de simulación
        if self.config.get("simulacion_dry_run") or self.config.get("modo_diferido_ocr"):
            self.modo_ocr_diferido = True
            
        # 5. Healthcheck final del Paso 1
        healthcheck_exito = self._ejecutar_healthcheck(directorios_escribibles)
        
        if healthcheck_exito:
            self.inicializado = True
            self.registrar_log_JSONL(
                action="bootstrap_completed", 
                reason=f"Modo: {'degradado' if not self.dependencias_ok else 'normal'} | OCR: {self.ocr_estado} | Diferido: {'SÍ' if self.modo_ocr_diferido else 'NO'}"
            )
            print("[+] [lector] Bootstrap del Lector finalizado con éxito.")
        else:
            self.registrar_log_JSONL(action="bootstrap_failed", reason="Healthcheck no superado")
            print("[-] [lector] Bootstrap del Lector fallido.")
            
        return self.inicializado

    def _validar_dependencias_python(self) -> bool:
        """Valida que los módulos de Python críticos estén disponibles e importables."""
        librerias_criticas = {
            "fitz": "PyMuPDF (lectura nativa)",
            "PIL": "Pillow (imágenes para OCR)",
            "bs4": "beautifulsoup4 (scraping)",
            "langdetect": "langdetect (detección idioma)"
        }
        
        faltantes = []
        info_versiones = []
        
        for lib, desc in librerias_criticas.items():
            try:
                mod = __import__(lib)
                version = "N/A"
                if hasattr(mod, "__version__"):
                    version = mod.__version__
                elif lib == "fitz" and hasattr(mod, "VersionBind"): # PyMuPDF versión
                    version = getattr(mod, "VersionBind", "N/A")
                info_versiones.append(f"{lib}: {version}")
            except ImportError:
                faltantes.append(lib)
                
        if faltantes:
            reason_str = f"Librerías ausentes: {', '.join(faltantes)}"
            self.registrar_log_JSONL(action="dep_missing", reason=reason_str)
            print(f"[!] [lector] Advertencia: Modo degradado activo. {reason_str}")
            return False
            
        self.registrar_log_JSONL(action="dep_validated", reason=" | ".join(info_versiones))
        return True

    def _autodetectar_tesseract(self):
        """Implementa la autodetección robusta de Tesseract OCR en Windows/sistema."""
        # 1. Rutas del PATH
        path_bin = shutil.which("tesseract")
        
        # 2. Rutas por defecto en Windows
        rutas_windows = [
            r"C:\Program Files\Tesseract-OCR\tesseract.exe",
            r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
            os.path.expandvars(r"%LOCALAPPDATA%\Tesseract-OCR\tesseract.exe"),
            os.path.expandvars(r"%PROGRAMFILES%\Tesseract-OCR\tesseract.exe")
        ]
        
        # 3. Ruta de configuración
        config_path = self.config.get("extraccion", {}).get("tesseract_path")
        if config_path:
            rutas_windows.insert(0, config_path)
            
        if not path_bin:
            for ruta in rutas_windows:
                if os.path.isfile(ruta):
                    path_bin = ruta
                    break
                    
        if not path_bin:
            self.ocr_estado = "ocr_ausente"
            self.modo_ocr_diferido = True
            self.registrar_log_JSONL(action="ocr_missing", reason="Binario Tesseract no localizado. Modo diferido activado.")
            print("[!] [lector] Tesseract OCR no detectado en el sistema. Los escaneos se diferirán.")
            return

        self.tesseract_path_bin = path_bin
        
        # Obtener versión e idiomas de Tesseract
        try:
            # Obtener versión
            result_ver = subprocess.run([path_bin, "--version"], capture_output=True, text=True, timeout=5)
            version_match = result_ver.stdout.split("\n")[0] if result_ver.returncode == 0 else ""
            self.tesseract_version = version_match.strip()
            
            # Obtener idiomas
            result_langs = subprocess.run([path_bin, "--list-langs"], capture_output=True, text=True, timeout=5)
            if result_langs.returncode == 0:
                lines = result_langs.stdout.strip().split("\n")
                # Las primeras líneas de list-langs suelen ser informativas, las de idiomas están al final
                self.tesseract_idiomas = [lang.strip() for lang in lines[1:] if lang.strip()]
            
            # Validar soporte de spa+cat
            soporta_spa = "spa" in self.tesseract_idiomas
            soporta_cat = "cat" in self.tesseract_idiomas
            
            if soporta_spa and soporta_cat:
                self.ocr_estado = "ocr_disponible"
                print(f"[+] [lector] Tesseract OCR detectado y verificado (versión: {self.tesseract_version.split(' ')[0]}).")
            else:
                self.ocr_estado = "ocr_parcial"
                faltan = []
                if not soporta_spa: faltan.append("spa")
                if not soporta_cat: faltan.append("cat")
                print(f"[!] [lector] Tesseract OCR parcial. Faltan diccionarios de idioma: {', '.join(faltan)}.")
                
            self.registrar_log_JSONL(
                action="ocr_status",
                reason=f"Estado: {self.ocr_estado} | Version: {self.tesseract_version.split(' ')[0]} | Idiomas: {','.join(self.tesseract_idiomas)}"
            )
            
        except (subprocess.SubprocessError, OSError) as e:
            self.ocr_estado = "ocr_ausente"
            self.modo_ocr_diferido = True
            self.registrar_log_JSONL(action="ocr_missing", reason=f"Fallo al validar Tesseract binario: {e}")
            print(f"[!] [lector] Error de ejecución de Tesseract. Activado modo OCR diferido: {e}")

    def _inicializar_directorios(self) -> bool:
        """Inicializa físicamente las carpetas de almacenamiento y valida permisos de escritura."""
        db_dir = "data"
        if self.db and hasattr(self.db, "db_path"):
            db_dir = os.path.dirname(self.db.db_path) or "data"
            
        carpetas = {
            "pliegos": os.path.join(db_dir, "pliegos"),
            "logs_docs": os.path.join(db_dir, "logs", "documentos")
        }
        
        errores_creacion = []
        verificaciones_ok = True
        
        for clave, ruta in carpetas.items():
            if not os.path.exists(ruta):
                try:
                    os.makedirs(ruta, exist_ok=True)
                    self.registrar_log_JSONL(action="dir_created", reason=f"Directorio creado: {ruta}")
                    print(f"[+] [lector] Directorio estructurado creado: {ruta}")
                except Exception as e:
                    errores_creacion.append(f"{ruta} ({e})")
                    verificaciones_ok = False
                    continue
            
            # Verificación preventiva de permisos de escritura
            test_file = os.path.join(ruta, ".write_test")
            try:
                with open(test_file, "w") as f:
                    f.write("write_test")
                os.remove(test_file)
            except Exception as e:
                errores_creacion.append(f"Sin escritura en {ruta} ({e})")
                verificaciones_ok = False
                
        if not verificaciones_ok:
            reason_str = f"Errores en directorios: {'; '.join(errores_creacion)}"
            self.registrar_log_JSONL(action="dir_error", reason=reason_str)
            print(f"[-] [lector] Error crítico en sistema de ficheros: {reason_str}")
        else:
            self.registrar_log_JSONL(action="dir_status", reason=f"Rutas de pliegos inicializadas y escribibles.")
            
        return verificaciones_ok

    def _ejecutar_healthcheck(self, directorios_ok: bool) -> bool:
        """Ejecuta una inspección final del estado documental antes de habilitar el Lector."""
        # Un fallo en directorios es un bloqueante duro
        if not directorios_ok:
            return False
            
        # Conexión opcional a la BD
        db_conectada = True
        if self.db:
            try:
                with self.db.conectar() as conn:
                    conn.execute("SELECT 1;")
            except Exception:
                db_conectada = False
                
            print("[!] [lector] Advertencia: Base de datos no conectada o inaccesible.")
            # Si no hay base de datos, el lector operará de manera local o simulada pero no interrumpe el bootstrap
            
        return True

    def _path_for_document(self, expediente_id: str, lote_numero: int, titulo: str, tipo: str, sha_short: str) -> tuple:
        """
        Calcula la ruta física segmentada para guardar el documento.
        Estructura: data/documents/{primeros_4_char_expediente}/{expediente_id}/{lote_numero}/
        Crea los directorios necesarios.
        Retorna (final_path, temp_path).
        """
        db_dir = "data"
        if self.db and hasattr(self.db, "db_path"):
            db_dir = os.path.dirname(self.db.db_path) or "data"
            
        # Normalizar caracteres problemáticos del expediente_id para rutas de Windows
        exp_clean = re.sub(r'[\\/*?:"<>|]', '_', expediente_id).strip()
        prefix = exp_clean[:4] if len(exp_clean) >= 4 else "MISC"
        
        dir_path = os.path.join(db_dir, "documents", prefix, exp_clean, str(lote_numero))
        os.makedirs(dir_path, exist_ok=True)
        
        # Sanitizar título del documento
        titulo_clean = re.sub(r'[\\/*?:"<>|\s]', '_', titulo).strip()
        # Limitar longitud para evitar pasarse del límite de OS (260 char en Windows)
        titulo_clean = titulo_clean[:60]
        
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M")
        filename = f"{tipo}_{titulo_clean}_{timestamp}_{sha_short}.pdf"
        
        final_path = os.path.join(dir_path, filename)
        temp_path = final_path + ".part"
        
        return final_path, temp_path

    def _descargar_documento_hilo(self, doc: Dict[str, Any], domain_semaphores: Dict[str, threading.Semaphore]) -> None:
        """
        Método ejecutor por hilo que gestiona la descarga física, verificación e integridad de un documento.
        """
        doc_id = doc["id"]
        exp_id = doc["expediente_id"]
        url = doc["url"]
        tipo = doc["tipo"]
        titulo = doc["titulo"]
        hash_publico = doc["hash_documento"]
        intentos_previos = doc["intentos"] or 0
        
        try:
            parsed_url = urllib.parse.urlparse(url)
            domain = parsed_url.netloc or "desconocido"
        except Exception:
            domain = "desconocido"
            
        sem = domain_semaphores.get(domain)
        if not sem:
            sem = threading.Semaphore(2)
            domain_semaphores[domain] = sem
            
        with sem:
            # 0. Pre-deduplicación basada en hash de metadatos de feed (evita red)
            if hash_publico:
                try:
                    doc_existente = self.db.obtener_documento_descargado_por_hash_feed(hash_publico)
                except Exception as e:
                    print(f"[!] [lector] Error comprobando pre-deduplicación por hash: {e}")
                    doc_existente = None
                    
                if doc_existente:
                    local_path_existente = doc_existente["local_path"]
                    sha256_existente = doc_existente["sha256"]
                    mida_existente = doc_existente["mida_bytes"]
                    
                    sql_dup = """
                    UPDATE documentos
                    SET estado = 'DESCARGADO', local_path = ?, sha256 = ?, mida_bytes = ?, intentos = 1, error_detalle = 'DUPLICADO_HISTORICO_FEED', updated_at = ?
                    WHERE id = ?;
                    """
                    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                    try:
                        with self.db.db_lock():
                            with self.db.conectar() as conn:
                                with conn:
                                    conn.execute(sql_dup, (local_path_existente, sha256_existente, mida_existente, now_str, doc_id))
                        self.registrar_log_JSONL(action="doc_download_bypass", expediente_id=exp_id, reason=f"ID: {doc_id} | Hash: {hash_publico[:12]} | Copiado de: {local_path_existente}")
                        print(f"[~] [lector] Documento ID {doc_id} pre-deduplicado instantáneamente por hash de feed.")
                        with self.metrics_lock:
                            self.metrics["bypass"] += 1
                        return
                    except Exception as e:
                        print(f"[!] [lector] Fallo al guardar pre-deduplicación del hash en BD para ID {doc_id}: {e}")
            
            # Verificar cooldown cooperativo de backpressure
            with self.cooldown_lock:
                cooldown_fin = self.host_cooldowns.get(domain, 0.0)
                delay_restante = cooldown_fin - time.time()
                
            if delay_restante > 0:
                print(f"[~] [lector] Backpressure activa para {domain}. Esperando {delay_restante:.2f}s antes de intentar...")
                time.sleep(delay_restante)
                
            # 1. Marcar estado como DESCARGANDO
            self.db.actualizar_estado_documento(doc_id, "DESCARGANDO")
            self.registrar_log_JSONL(action="doc_download_started", expediente_id=exp_id, reason=f"ID: {doc_id} | Titulo: {titulo} | Intento: {intentos_previos+1}")
            
            sha_short = hash_publico[:8] if hash_publico else "unknown"
            lote_numero = 1
            
            final_path, temp_path = self._path_for_document(exp_id, lote_numero, titulo, tipo, sha_short)
            
            intentos = intentos_previos
            max_reintentos = self.config["descargas"].get("max_reintentos", 3)
            timeout = self.config["descargas"].get("timeout_segundos", 30.0)
            
            # User-Agent de cortesía
            headers = {
                "User-Agent": "Antigravity Incoop Tender Downloader/1.2 (+mailto:controller@incoop.org)",
                "Accept": "application/pdf, */*"
            }
            
            exito = False
            error_msg = ""
            
            while intentos < max_reintentos and not exito:
                intentos += 1
                try:
                    if intentos > 1:
                        delay = 1.0 * (2 ** (intentos - 1)) + random.uniform(0.1, 0.5)
                        time.sleep(delay)
                        
                    t0 = time.time()
                    resp = requests.get(url, headers=headers, stream=True, timeout=timeout)
                    
                    if resp.status_code == 429:
                        retry_after = resp.headers.get("Retry-After")
                        cooldown = int(retry_after) if retry_after and retry_after.isdigit() else 30
                        
                        # Activar cooldown dinámico cooperativo
                        with self.cooldown_lock:
                            self.host_cooldowns[domain] = time.time() + cooldown
                            
                        print(f"[!] [lector] Rate limit 429 para {domain}. Activado cooldown colectivo de {cooldown}s...")
                        time.sleep(cooldown)
                        raise NetworkError(f"HTTP 429 Rate Limit (Retry-After: {cooldown}s)")
                        
                    if resp.status_code != 200:
                        raise NetworkError(f"HTTP Status Code {resp.status_code}")
                        
                    # Descarga en chunks escribiendo a temp_path y calculando SHA256 simultáneamente
                    sha256_calc = hashlib.sha256()
                    mida_bytes = 0
                    
                    with open(temp_path, "wb") as f_part:
                        for chunk in resp.iter_content(chunk_size=64*1024):
                            if chunk:
                                f_part.write(chunk)
                                sha256_calc.update(chunk)
                                mida_bytes += len(chunk)
                                
                    latencia_ms = int((time.time() - t0) * 1000)
                    
                    # Comprobaciones de contenido
                    if mida_bytes < 1024:
                        raise FormatError(f"Fichero descargado demasiado pequeño ({mida_bytes} bytes). Probablemente error HTML.")
                        
                    with open(temp_path, "rb") as f_check:
                        magic = f_check.read(5)
                    if not magic.startswith(b"%PDF-"):
                        ext = os.path.splitext(titulo.lower())[1]
                        is_non_pdf = ext in [".docx", ".doc", ".xml", ".zip", ".xlsx", ".xls", ".rar", ".7z"] or not url.lower().endswith(".pdf")
                        if is_non_pdf:
                            self.db.actualizar_estado_documento(doc_id, "OMITIDO_FORMATO_NO_PDF", error_detalle=f"Formato no PDF ({ext or 'desconocido'})")
                            if os.path.exists(temp_path):
                                try:
                                    os.remove(temp_path)
                                except Exception:
                                    pass
                            self.registrar_log_JSONL(action="doc_download_skipped_format", expediente_id=exp_id, reason=f"ID: {doc_id} | Titulo: {titulo} | Ext: {ext}")
                            print(f"[~] [lector] Documento ID {doc_id} omitido limpiamente (formato no PDF: {ext or 'desconocido'}).")
                            with self.metrics_lock:
                                self.metrics["skipped_format"] += 1
                            return
                        else:
                            raise FormatError("Firma mágica inválida. El fichero no es un PDF nativo.")
                        
                    sha256_hex = sha256_calc.hexdigest()
                    
                    # Comprobar duplicado en base de datos
                    if self.db.documento_sha256_existe(sha256_hex, doc_id):
                        self.db.actualizar_estado_documento(doc_id, "DESCARGADO", error_detalle="DUPLICADO_FISICO")
                        if os.path.exists(temp_path):
                            os.remove(temp_path)
                        self.registrar_log_JSONL(action="doc_download_duplicate", expediente_id=exp_id, reason=f"ID: {doc_id} | Hash: {sha256_hex[:12]}")
                        print(f"[~] [lector] Documento ID {doc_id} marcado como duplicado físico.")
                        with self.metrics_lock:
                            self.metrics["duplicate"] += 1
                        return
                        
                    # Mover a definitivo de forma atómica
                    if os.path.exists(final_path):
                        os.remove(final_path)
                    os.replace(temp_path, final_path)
                    
                    # Generar Sidecar JSON
                    sidecar_path = final_path + ".meta.json"
                    sidecar_data = {
                        "sha256": sha256_hex,
                        "mida_bytes": mida_bytes,
                        "downloaded_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                        "source_url": url,
                        "http_status": resp.status_code,
                        "content_type": resp.headers.get("Content-Type", "application/pdf")
                    }
                    with open(sidecar_path, "w", encoding="utf-8") as f_side:
                        json.dump(sidecar_data, f_side, indent=2)
                        
                    # Registrar éxito en base de datos
                    self.db.registrar_descarga_exitosa(doc_id, final_path, sha256_hex, mida_bytes)
                    self.registrar_log_JSONL(action="doc_download_succeeded", expediente_id=exp_id, reason=f"ID: {doc_id} | Ruta: {final_path} | Hash: {sha256_hex[:8]}", duration_ms=latencia_ms)
                    print(f"[+] [lector] Documento ID {doc_id} descargado y validado en: {final_path}")
                    
                    with self.metrics_lock:
                        self.metrics["success"] += 1
                        self.metrics["bytes"] += mida_bytes
                        self.metrics["latencies"].append(latencia_ms)
                    exito = True
                    
                except Exception as e:
                    error_msg = str(e)
                    print(f"[!] [lector] Error intentando descargar ID {doc_id} (Intento {intentos}/{max_reintentos}): {e}")
                    if os.path.exists(temp_path):
                        try:
                            os.remove(temp_path)
                        except Exception:
                            pass
                            
            if not exito:
                self.db.registrar_intento_fallido(doc_id, error_msg, intentos)
                self.registrar_log_JSONL(action="doc_download_failed", expediente_id=exp_id, reason=f"ID: {doc_id} | Fallos: {intentos} | Error: {error_msg}")
                print(f"[-] [lector] Descarga fallida definitiva para ID {doc_id} tras {intentos} intentos: {error_msg}")
                with self.metrics_lock:
                    self.metrics["failed"] += 1

    def ejecutar_descargas(self) -> None:
        """
        Orquesta la descarga concurrente de todos los documentos en estado DETECTADO
        o con descargas previas fallidas e intentos pendientes.
        """
        if not self.db:
            print("[!] [lector] No se puede ejecutar descargas. Base de datos no conectada.")
            return
            
        docs_pendientes = self.db.obtener_documentos_pendientes()
        if not docs_pendientes:
            print("[~] [lector] No se encontraron documentos pendientes de descarga.")
            return
            
        print(f"[~] [lector] Iniciando descarga concurrente de {len(docs_pendientes)} documentos...")
        
        # Agrupar y crear semáforos por dominio
        domain_semaphores = {}
        for doc in docs_pendientes:
            url = doc["url"]
            try:
                parsed_url = urllib.parse.urlparse(url)
                domain = parsed_url.netloc or "desconocido"
            except Exception:
                domain = "desconocido"
            if domain not in domain_semaphores:
                domain_semaphores[domain] = threading.Semaphore(2)
                
        # Reiniciar métricas antes del pool
        with self.metrics_lock:
            self.metrics = {"success": 0, "failed": 0, "bypass": 0, "duplicate": 0, "skipped_format": 0, "bytes": 0, "latencies": []}
            
        max_workers = self.config["descargas"].get("max_concurrentes", 6)
        
        # Mezclar de forma aleatoria para equilibrar la carga entre dominios
        random.shuffle(docs_pendientes)
        
        t_start = time.time()
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            for doc in docs_pendientes:
                executor.submit(self._descargar_documento_hilo, doc, domain_semaphores)
                
        duration_total = time.time() - t_start
        print(f"[+] [lector] Finalizada la ejecución del descargador de documentos.")
        
        # Consolidar y reportar métricas
        total_procesados = len(docs_pendientes)
        latencias = self.metrics["latencies"]
        avg_latency = int(sum(latencias) / len(latencias)) if latencias else 0
        total_mb = round(self.metrics["bytes"] / (1024 * 1024), 2)
        
        summary_reason = (
            f"Procesados: {total_procesados} | Exito: {self.metrics['success']} | "
            f"Bypass: {self.metrics['bypass']} | Duplicado: {self.metrics['duplicate']} | "
            f"FormatOmitido: {self.metrics['skipped_format']} | Fallo: {self.metrics['failed']} | "
            f"Tamaño: {total_mb} MB | Latencia media: {avg_latency}ms"
        )
        self.registrar_log_JSONL(action="run_downloads_summary", reason=summary_reason, duration_ms=int(duration_total * 1000))
        
        # Generar CSV consolidado en data/reports
        db_dir = "data"
        if self.db and hasattr(self.db, "db_path"):
            db_dir = os.path.dirname(self.db.db_path) or "data"
        report_dir = os.path.join(db_dir, "reports")
        os.makedirs(report_dir, exist_ok=True)
        report_csv = os.path.join(report_dir, "downloads_summary.csv")
        
        write_header = not os.path.exists(report_csv)
        try:
            with open(report_csv, "a", encoding="utf-8") as f_csv:
                if write_header:
                    f_csv.write("timestamp,run_id,total,success,bypass,duplicate,skipped_format,failed,size_mb,avg_latency_ms\n")
                now_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                f_csv.write(
                    f"{now_str},{self.run_id},{total_procesados},{self.metrics['success']},"
                    f"{self.metrics['bypass']},{self.metrics['duplicate']},{self.metrics['skipped_format']},"
                    f"{self.metrics['failed']},{total_mb},{avg_latency}\n"
                )
            print(f"[+] [lector] Reporte operativo consolidado CSV escrito en: {report_csv}")
        except Exception as e:
            print(f"[!] [lector] Error al generar reporte CSV consolidado: {e}")

    def ejecutar_purga_obsoletos(self, dias_retencion: int = 90) -> int:
        """
        Elimina físicamente los archivos PDF y sidecars correspondientes a expedientes soft-deleted
        o cuya fecha de ingesta supere los dias_retencion establecidos.
        Pasa el estado en BD a PURGADO.
        Devuelve el número de documentos purgados.
        """
        if not self.db:
            print("[!] [lector] No se puede ejecutar purga. Base de datos no conectada.")
            return 0
            
        docs_purga = self.db.obtener_documentos_para_purga(dias_retencion)
        if not docs_purga:
            print("[~] [lector] No se encontraron documentos que requieran purga por retención.")
            return 0
            
        print(f"[~] [lector] Iniciando purga física de {len(docs_purga)} documentos (> {dias_retencion} días o inactivos)...")
        
        doc_ids = []
        purgados_conteo = 0
        
        for doc in docs_purga:
            doc_id = doc["id"]
            pdf_path = doc["local_path"]
            doc_ids.append(doc_id)
            
            # Borrar PDF físico
            if pdf_path and os.path.exists(pdf_path):
                try:
                    os.remove(pdf_path)
                    purgados_conteo += 1
                    # Borrar sidecar JSON si existe
                    sidecar_path = pdf_path + ".meta.json"
                    if os.path.exists(sidecar_path):
                        os.remove(sidecar_path)
                    print(f"  [+] Purgado físico: {doc['titulo']} ({pdf_path})")
                except Exception as e:
                    print(f"  [!] Error borrando archivo {pdf_path}: {e}")
                    
        # Actualizar base de datos
        if doc_ids:
            try:
                self.db.marcar_documentos_como_purgados(doc_ids)
                self.registrar_log_JSONL(action="purge_completed", reason=f"Purgados: {len(doc_ids)} | Eliminados en disco: {purgados_conteo}")
                print(f"[+] [lector] Purga completada de {len(doc_ids)} documentos en base de datos.")
            except Exception as e:
                print(f"[!] Error al actualizar estados de purga en BD: {e}")
                
        return purgados_conteo

    def extraer_texto_pdf_nativo(self, local_path: str) -> ExtraccionResult:
        """
        Extrae texto nativo (vectorial) de un PDF página a página usando PyMuPDF (fitz).
        Detecta si el documento es escaneado (densidad de caracteres < 50/página) e identifica el idioma.
        """
        t0 = time.perf_counter()
        if not local_path or not os.path.exists(local_path):
            return ExtraccionResult(
                exito=False,
                texto="",
                metodo="ninguno",
                num_paginas=0,
                paginas_ocr=0,
                idioma_detectado="desconocido",
                version_reglas=self.VERSION_REGLAS,
                tiempo_procesamiento_ms=0,
                error_detalle="Archivo físico no encontrado"
            )

        try:
            import fitz
            doc = fitz.open(local_path)
            num_paginas = len(doc)
            paginas_texto = []
            paginas_escaneadas = 0

            for i in range(num_paginas):
                page = doc[i]
                page_text = page.get_text("text") or ""
                page_text_clean = page_text.strip()

                if len(page_text_clean) < 50:
                    paginas_escaneadas += 1
                
                paginas_texto.append(page_text)

            doc.close()

            texto_completo = "\n--- PAGINA --- \n".join(paginas_texto)
            texto_limpio = re.sub(r'\n{3,}', '\n\n', texto_completo).strip()

            # Detección de idioma
            idioma = self.detectar_idioma_texto(texto_limpio)

            duracion_ms = int((time.perf_counter() - t0) * 1000)

            # Si más del 50% de las páginas son escaneadas o la densidad total es muy baja
            if num_paginas > 0 and (paginas_escaneadas / num_paginas > 0.5 or len(texto_limpio) < 100):
                return ExtraccionResult(
                    exito=True,
                    texto=texto_limpio,
                    metodo="pymupdf",
                    num_paginas=num_paginas,
                    paginas_ocr=paginas_escaneadas,
                    idioma_detectado=idioma,
                    version_reglas=self.VERSION_REGLAS,
                    tiempo_procesamiento_ms=duracion_ms,
                    error_detalle="OCR_REQUERIDO"
                )

            return ExtraccionResult(
                exito=True,
                texto=texto_limpio,
                metodo="pymupdf",
                num_paginas=num_paginas,
                paginas_ocr=0,
                idioma_detectado=idioma,
                version_reglas=self.VERSION_REGLAS,
                tiempo_procesamiento_ms=duracion_ms,
                error_detalle=None
            )

        except Exception as e:
            duracion_ms = int((time.perf_counter() - t0) * 1000)
            return ExtraccionResult(
                exito=False,
                texto="",
                metodo="ninguno",
                num_paginas=0,
                paginas_ocr=0,
                idioma_detectado="desconocido",
                version_reglas=self.VERSION_REGLAS,
                tiempo_procesamiento_ms=duracion_ms,
                error_detalle=str(e)
            )

    def detectar_idioma_texto(self, texto: str) -> str:
        """Detecta el idioma principal del texto (es/ca/desconocido) usando langdetect."""
        if not texto or len(texto.strip()) < 30:
            return "desconocido"
        try:
            from langdetect import detect
            muestra = texto[:1000]
            code = detect(muestra)
            if code in ['es', 'ca', 'en']:
                return code
            return code
        except Exception:
            return "desconocido"

    def procesar_extraccion_texto_lote(self) -> None:
        """
        Orquesta la extracción de texto nativo con PyMuPDF para todos los documentos en estado DESCARGADO.
        """
        if not self.db:
            print("[!] [lector] No se puede ejecutar extracción. Base de datos no conectada.")
            return

        docs = self.db.obtener_documentos_para_extraccion()
        if not docs:
            print("[~] [lector] No hay documentos en estado DESCARGADO listos para extracción de texto.")
            return

        print(f"[~] [lector] Iniciando extracción de texto nativo (PyMuPDF) en {len(docs)} documentos...")
        self.registrar_log_JSONL(action="doc_extraction_batch_start", reason=f"Candidatos: {len(docs)}")

        exitos = 0
        ocr_flagged = 0
        errores = 0
        total_paginas = 0
        idiomas_map = {}

        t_start = time.perf_counter()

        for doc in docs:
            doc_id = doc["id"]
            exp_id = doc["expediente_id"]
            local_path = doc["local_path"]
            titulo = doc["titulo"]

            resultado = self.extraer_texto_pdf_nativo(local_path)
            total_paginas += resultado.num_paginas

            if resultado.exito:
                idioma = resultado.idioma_detectado
                idiomas_map[idioma] = idiomas_map.get(idioma, 0) + 1

                if resultado.error_detalle == "OCR_REQUERIDO":
                    estado_final = "OCR_REQUERIDO"
                    ocr_flagged += 1
                    self.db.guardar_resultado_extraccion_texto(
                        doc_id=doc_id,
                        estado=estado_final,
                        texto_extraido=resultado.texto,
                        metodo=resultado.metodo,
                        idioma=idioma,
                        version_reglas=resultado.version_reglas,
                        error_detalle="Escaneado o densidad de texto baja (<50 chars/pag)"
                    )
                    self.registrar_log_JSONL(
                        action="doc_ocr_flagged",
                        expediente_id=exp_id,
                        reason=f"ID: {doc_id} | Paginas: {resultado.num_paginas} | Paginas OCR: {resultado.paginas_ocr}",
                        duration_ms=resultado.tiempo_procesamiento_ms
                    )
                    print(f"[~] [lector] Documento ID {doc_id} ('{titulo[:30]}') requiere OCR (Paso 5).")
                else:
                    estado_final = "TEXTO_EXTRAIDO"
                    exitos += 1
                    self.db.guardar_resultado_extraccion_texto(
                        doc_id=doc_id,
                        estado=estado_final,
                        texto_extraido=resultado.texto,
                        metodo=resultado.metodo,
                        idioma=idioma,
                        version_reglas=resultado.version_reglas,
                        error_detalle=None
                    )
                    self.registrar_log_JSONL(
                        action="doc_text_extracted_native",
                        expediente_id=exp_id,
                        reason=f"ID: {doc_id} | Chars: {len(resultado.texto)} | Idioma: {idioma} | Paginas: {resultado.num_paginas}",
                        duration_ms=resultado.tiempo_procesamiento_ms
                    )
                    print(f"[+] [lector] Texto nativo extraído para ID {doc_id} ('{titulo[:30]}') [{len(resultado.texto)} chars, idioma: {idioma}].")
            else:
                errores += 1
                self.db.guardar_resultado_extraccion_texto(
                    doc_id=doc_id,
                    estado="ERROR_EXTRACCION",
                    texto_extraido=None,
                    metodo="ninguno",
                    idioma="desconocido",
                    version_reglas=self.VERSION_REGLAS,
                    error_detalle=resultado.error_detalle
                )
                self.registrar_log_JSONL(
                    action="doc_extraction_failed",
                    expediente_id=exp_id,
                    reason=f"ID: {doc_id} | Error: {resultado.error_detalle}"
                )
                print(f"[!] [lector] Fallo en la extracción de texto para ID {doc_id}: {resultado.error_detalle}")

        total_duration_ms = int((time.perf_counter() - t_start) * 1000)
        ms_per_page = round(total_duration_ms / total_paginas, 2) if total_paginas > 0 else 0

        summary = (
            f"Procesados: {len(docs)} | Exitosos (PyMuPDF): {exitos} | "
            f"Requiere OCR: {ocr_flagged} | Errores: {errores} | "
            f"Idiomas: {idiomas_map} | Paginas: {total_paginas} ({ms_per_page}ms/pag)"
        )
        self.registrar_log_JSONL(action="doc_extraction_batch_completed", reason=summary, duration_ms=total_duration_ms)

        print("\n" + "=" * 85)
        print(f" RESUMEN EXTRACCIÓN DE TEXTO NATIVO (PASO 4) ".center(85, "="))
        print(f"Documentos analizados: {len(docs)}")
        print(f"  [+] Texto vectorial extraído (PyMuPDF): {exitos}")
        print(f"  [~] Escaneados marcados para OCR (Paso 5): {ocr_flagged}")
        print(f"  [-] Errores de extracción: {errores}")
        print(f"  [Lang] Distribución de idiomas: {idiomas_map}")
        print(f"  [Time] Páginas analizadas: {total_paginas} (Velocidad: {ms_per_page} ms/pág)")
        print("=" * 85 + "\n")

    def ejecutar_ocr_pdf_diferido(self, local_path: str, texto_previo: str = "") -> ExtraccionResult:
        """
        Ejecuta OCR sobre las páginas escaneadas de un PDF usando PyMuPDF pixmap + pytesseract / Tesseract CLI.
        Si Tesseract no está instalado en el sistema, entra en modo degradado (OCR_DIFERIDO).
        """
        t0 = time.perf_counter()
        if not local_path or not os.path.exists(local_path):
            return ExtraccionResult(
                exito=False,
                texto=texto_previo or "",
                metodo="ninguno",
                num_paginas=0,
                paginas_ocr=0,
                idioma_detectado="desconocido",
                version_reglas=self.VERSION_REGLAS,
                tiempo_procesamiento_ms=0,
                error_detalle="Archivo físico no encontrado"
            )

        # Modo Degradado: si Tesseract no está instalado/disponible
        if not self.tesseract_path_bin or self.ocr_estado == "ocr_ausente":
            duracion_ms = int((time.perf_counter() - t0) * 1000)
            return ExtraccionResult(
                exito=True,
                texto=texto_previo or "",
                metodo="pymupdf_vectorial_previo",
                num_paginas=0,
                paginas_ocr=0,
                idioma_detectado=self.detectar_idioma_texto(texto_previo),
                version_reglas=self.VERSION_REGLAS,
                tiempo_procesamiento_ms=duracion_ms,
                error_detalle="OCR_DIFERIDO_TESSERACT_NO_INSTALADO"
            )

        try:
            import fitz
            from PIL import Image
            import io

            doc = fitz.open(local_path)
            num_paginas = len(doc)
            paginas_texto = []
            paginas_ocr_count = 0

            langs = "cat+spa" if "cat" in self.tesseract_idiomas else "spa"

            for i in range(num_paginas):
                page = doc[i]
                page_text_native = page.get_text("text") or ""
                
                # Si la página tiene densidad de texto muy baja (<50 chars), renderizar a imagen y procesar con OCR
                if len(page_text_native.strip()) < 50:
                    pix = page.get_pixmap(dpi=200)
                    img_bytes = pix.tobytes("png")
                    img = Image.open(io.BytesIO(img_bytes))

                    try:
                        import pytesseract
                        if self.tesseract_path_bin:
                            pytesseract.pytesseract.tesseract_cmd = self.tesseract_path_bin
                        ocr_text = pytesseract.image_to_string(img, lang=langs)
                    except Exception:
                        cmd = [self.tesseract_path_bin, "stdin", "stdout", "-l", langs]
                        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                        out, _ = proc.communicate(input=img_bytes)
                        ocr_text = out.decode("utf-8", errors="ignore")

                    paginas_texto.append(ocr_text)
                    paginas_ocr_count += 1
                else:
                    paginas_texto.append(page_text_native)

            doc.close()

            texto_completo = "\n--- PAGINA (OCR) --- \n".join(paginas_texto)
            texto_limpio = re.sub(r'\n{3,}', '\n\n', texto_completo).strip()

            idioma = self.detectar_idioma_texto(texto_limpio)
            duracion_ms = int((time.perf_counter() - t0) * 1000)

            return ExtraccionResult(
                exito=True,
                texto=texto_limpio,
                metodo="tesseract",
                num_paginas=num_paginas,
                paginas_ocr=paginas_ocr_count,
                idioma_detectado=idioma,
                version_reglas=self.VERSION_REGLAS,
                tiempo_procesamiento_ms=duracion_ms,
                error_detalle=None
            )

        except Exception as e:
            duracion_ms = int((time.perf_counter() - t0) * 1000)
            return ExtraccionResult(
                exito=False,
                texto=texto_previo or "",
                metodo="ninguno",
                num_paginas=0,
                paginas_ocr=0,
                idioma_detectado="desconocido",
                version_reglas=self.VERSION_REGLAS,
                tiempo_procesamiento_ms=duracion_ms,
                error_detalle=str(e)
            )

    def procesar_ocr_diferido_lote(self) -> None:
        """
        Orquesta el procesamiento OCR para todos los documentos marcados como OCR_REQUERIDO.
        Si Tesseract no está disponible, opera en modo degradado de forma transparente.
        """
        if not self.db:
            print("[!] [lector] No se puede ejecutar OCR. Base de datos no conectada.")
            return

        docs = self.db.obtener_documentos_para_ocr()
        if not docs:
            print("[~] [lector] No hay documentos en estado OCR_REQUERIDO para procesar.")
            return

        print(f"[~] [lector] Iniciando motor de OCR diferido en {len(docs)} documentos...")
        self.registrar_log_JSONL(action="doc_ocr_batch_start", reason=f"Candidatos: {len(docs)}")

        exitos = 0
        diferidos = 0
        errores = 0
        total_paginas_ocr = 0

        t_start = time.perf_counter()

        for doc in docs:
            doc_id = doc["id"]
            exp_id = doc["expediente_id"]
            local_path = doc["local_path"]
            titulo = doc["titulo"]
            texto_previo = doc.get("texto_extraido") or ""

            self.registrar_log_JSONL(action="doc_ocr_started", expediente_id=exp_id, reason=f"ID: {doc_id} | Titulo: {titulo}")
            resultado = self.ejecutar_ocr_pdf_diferido(local_path, texto_previo=texto_previo)
            total_paginas_ocr += resultado.paginas_ocr

            if resultado.exito:
                if resultado.error_detalle == "OCR_DIFERIDO_TESSERACT_NO_INSTALADO":
                    diferidos += 1
                    self.db.guardar_resultado_extraccion_texto(
                        doc_id=doc_id,
                        estado="OCR_DIFERIDO",
                        texto_extraido=resultado.texto,
                        metodo=resultado.metodo,
                        idioma=resultado.idioma_detectado,
                        version_reglas=resultado.version_reglas,
                        error_detalle="Tesseract no instalado en sistema (Modo Degradado)"
                    )
                    self.registrar_log_JSONL(
                        action="doc_ocr_degraded",
                        expediente_id=exp_id,
                        reason=f"ID: {doc_id} | Motivo: Tesseract no disponible | Texto previo conservado"
                    )
                    print(f"[~] [lector] Documento ID {doc_id} ('{titulo[:30]}') pasado a OCR_DIFERIDO (Modo degradado: Tesseract no instalado).")
                else:
                    exitos += 1
                    self.db.guardar_resultado_extraccion_texto(
                        doc_id=doc_id,
                        estado="TEXTO_EXTRAIDO",
                        texto_extraido=resultado.texto,
                        metodo=resultado.metodo,
                        idioma=resultado.idioma_detectado,
                        version_reglas=resultado.version_reglas,
                        error_detalle=None
                    )
                    self.registrar_log_JSONL(
                        action="doc_ocr_succeeded",
                        expediente_id=exp_id,
                        reason=f"ID: {doc_id} | Paginas OCR: {resultado.paginas_ocr} | Idioma: {resultado.idioma_detectado}",
                        duration_ms=resultado.tiempo_procesamiento_ms
                    )
                    print(f"[+] [lector] OCR Tesseract completado con éxito para ID {doc_id} ('{titulo[:30]}') [{resultado.paginas_ocr} pág. reconocidas].")
            else:
                errores += 1
                self.db.guardar_resultado_extraccion_texto(
                    doc_id=doc_id,
                    estado="ERROR_OCR",
                    texto_extraido=texto_previo,
                    metodo="ninguno",
                    idioma="desconocido",
                    version_reglas=self.VERSION_REGLAS,
                    error_detalle=resultado.error_detalle
                )
                self.registrar_log_JSONL(
                    action="doc_ocr_failed",
                    expediente_id=exp_id,
                    reason=f"ID: {doc_id} | Error: {resultado.error_detalle}"
                )
                print(f"[!] [lector] Fallo al ejecutar OCR sobre ID {doc_id}: {resultado.error_detalle}")

        total_duration_ms = int((time.perf_counter() - t_start) * 1000)
        summary = (
            f"Procesados: {len(docs)} | OCR Exitoso: {exitos} | "
            f"Diferidos (Sin Tesseract): {diferidos} | Errores: {errores} | "
            f"Paginas OCR: {total_paginas_ocr}"
        )
        self.registrar_log_JSONL(action="doc_ocr_batch_completed", reason=summary, duration_ms=total_duration_ms)

        print("\n" + "=" * 85)
        print(f" RESUMEN MOTOR DE OCR DIFERIDO (PASO 5) ".center(85, "="))
        print(f"Documentos escaneados analizados: {len(docs)}")
        print(f"  [+] Reconocidos con Tesseract (spa+cat): {exitos}")
        print(f"  [~] Diferidos por Modo Degradado: {diferidos}")
        print(f"  [-] Errores de OCR: {errores}")
        print(f"  [Time] Páginas rasterizadas a 200 DPI: {total_paginas_ocr}")
        print("=" * 85 + "\n")




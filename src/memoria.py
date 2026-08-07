import os
import sqlite3
import zoneinfo
import hashlib
import json
import time
import random
import shutil
import threading
from datetime import datetime, timezone, timedelta
from pathlib import Path
from contextlib import contextmanager
from typing import Dict, Any, List, Optional, Tuple

# La definición canónica vive en el paquete raíz. Se reexporta aquí porque
# `src/api/dependencies.py` ya importaba PROJECT_ROOT desde este módulo.
from src import (
    ESTADOS_OPERATIVOS_VALIDOS,
    PROJECT_ROOT,
    normalizar_estado_operativo,
    ruta_proyecto,
    ruta_datos,
)

# =====================================================================
# HELPER DE VERIFICACIÓN DE PID Y PROCESOS
# =====================================================================

def es_pid_activo(pid: int) -> bool:
    """
    Verifica si un Process ID (PID) está activo en el sistema operativo.
    Compatibilidad en Windows y POSIX sin librerías externas.
    """
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError as e:
        if getattr(e, 'winerror', None) == 5 or getattr(e, 'errno', None) == 13:
            return True
        return False
    except Exception:
        return False

# =====================================================================
# HELPER DE NORMALIZACIÓN DE FECHAS
# =====================================================================

def normalizar_fecha_utc(fecha_str: str) -> str:
    """
    Normaliza una fecha string (con o sin offset de zona horaria) a formato ISO 8601 UTC (YYYY-MM-DDTHH:MM:SSZ).
    Asume que las fechas sin zona horaria están en hora peninsular española (Europe/Madrid).
    """
    if not fecha_str or fecha_str == "N/A":
        return "N/A"
    
    fecha_str = fecha_str.strip()
    try:
        # Caso 1: Tiene zona horaria/offset explícito (+xx:xx o Z)
        if "+" in fecha_str or fecha_str.endswith("Z") or ("-" in fecha_str[10:]):
            val = fecha_str
            if val.endswith("Z"):
                val = val[:-1] + "+00:00"
            dt = datetime.fromisoformat(val)
            return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        
        # Caso 2: Sin zona horaria (como la API de Socrata)
        val_clean = fecha_str.split(".")[0].replace("T", " ")
        try:
            dt = datetime.strptime(val_clean, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            dt = datetime.strptime(val_clean, "%Y-%m-%d")
        
        try:
            tz_madrid = zoneinfo.ZoneInfo("Europe/Madrid")
            dt = dt.replace(tzinfo=tz_madrid)
            return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        except Exception:
            # Fallback robusto en caso de que zoneinfo no tenga la BD de zonas horarias instalada
            mes = dt.month
            dia = dt.day
            is_verano = False
            if 3 < mes < 10:
                is_verano = True
            elif mes == 3:
                is_verano = (dia >= 25)
            elif mes == 10:
                is_verano = (dia < 25)
            
            offset = 2 if is_verano else 1
            dt = dt - timedelta(hours=offset)
            dt = dt.replace(tzinfo=timezone.utc)
            return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    except Exception:
        return fecha_str

# =====================================================================
# HELPER DE RASTRO DE CAMBIOS DE ESTADO (H-31)
# =====================================================================

#: Marca que identifica una entrada de cambio de estado dentro de `expedientes.log_cambios`.
#: El formato es estable a propósito: la invariante de memoria comercial del Paso 6 —qué
#: expedientes NO pueden eliminarse jamás— tiene que poder responder "¿este lote llegó
#: alguna vez a Presentada?", y este rastro es la única evidencia que quedará.
MARCA_LOG_ESTADO = "ESTADO"


def entrada_log_cambio_estado(lote_numero: int, anterior: str, nuevo: str, autor: str = "user") -> str:
    """Compone una línea de rastro para un cambio de estado operativo.

    Por qué existe (H-31): hasta la Capa 9 no quedaba ninguna constancia de por qué estados
    había pasado un lote. `lotes.updated_at`/`updated_by` no sirven —el Radar los sobreescribe
    en cada reingesta mientras la licitación siga en el feed— y `log_cambios` sólo recogía
    cambios de fecha límite y ausencias. El escenario que el propio contrato de la Capa 9 pone
    como ejemplo, "un lote puede estar hoy en Inactiva habiendo pasado por Presentada", ocurre
    de verdad: `soft_delete_obsoletos()` reescribe el estado sin dejar constancia de cuál era.
    Sin este rastro, un lote con negocio invertido pero sin costes registrados sería
    indistinguible de una `Nueva` caducada, y por tanto elegible para eliminación física.
    """
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    anterior_txt = normalizar_estado_operativo(anterior) or "?"
    nuevo_txt = normalizar_estado_operativo(nuevo) or "?"
    return (
        f"[{timestamp}] [{autor}] {MARCA_LOG_ESTADO} lote {lote_numero}: "
        f"'{anterior_txt}' -> '{nuevo_txt}'"
    )


def anexar_log_cambios(cursor, expediente_id: str, entrada: str) -> None:
    """Añade una entrada al histórico del expediente sin perder lo ya escrito.

    Se concatena en SQL (`log_cambios || ?`) en vez de leer-modificar-escribir para que la
    escritura sea atómica respecto a la fila y no pise lo que otra operación haya anexado.
    """
    cursor.execute(
        "UPDATE expedientes SET log_cambios = COALESCE(log_cambios, '') || ? WHERE id = ?;",
        (f"\n{entrada}", expediente_id),
    )


# =====================================================================
# HELPER DE NORMALIZACIÓN Y CÁLCULO DE HASH
# =====================================================================

def calcular_feed_hash(licitacion: Dict[str, Any]) -> str:
    """
    Calcula de forma determinista el hash SHA256 del contenido público de la licitación
    para detectar cambios semánticos y evitar escrituras redundantes.
    """
    titulo = (licitacion.get("titulo") or "").strip().lower()
    vec = f"{float(licitacion.get('vec', 0.0)):.2f}"
    pbl = f"{float(licitacion.get('importe', 0.0)):.2f}"
    fecha_limite = (licitacion.get("fecha_limite") or "").strip().lower()
    proc = (licitacion.get("procedimiento_codigo") or "").strip().lower()
    tipo = (licitacion.get("tipo_contrato_codigo") or "").strip().lower()
    
    # CPVs ordenados para evitar variaciones por cambios de orden en el XML
    cpvs = sorted([str(c).strip().lower() for c in licitacion.get("cpvs", [])])
    cpvs_str = ",".join(cpvs)
    
    payload = f"{titulo}|{vec}|{pbl}|{fecha_limite}|{proc}|{tipo}|{cpvs_str}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()

# =====================================================================
# CONSTANTES DDL - ESQUEMA DE BASE DE DATOS (ESQUEMA COMPLETO v6)
# =====================================================================

# Versión única del esquema. Antes vivía duplicada —como literal en el INSERT inicial y
# como atributo de clase—, de modo que una base recién creada podía nacer declarando una
# versión distinta de la que el código esperaba y disparar una migración sobre un esquema
# que ya estaba al día. Ahora sólo hay una fuente.
ESQUEMA_VERSION_ACTUAL = 6

SQL_CREATE_METADATA = """
CREATE TABLE IF NOT EXISTS metadata (
    version INTEGER NOT NULL
);
"""

SQL_INSERT_INITIAL_VERSION = f"""
INSERT INTO metadata (version) VALUES ({ESQUEMA_VERSION_ACTUAL});
"""

# ---------------------------------------------------------------------
# Vocabulario canónico de los estados de archivado (H-27)
#
# El enum de la API declara estos estados capitalizados, como todos los demás
# ("Nueva", "Estudiando"...), pero el Radar los escribía en minúsculas. Dos grafías
# del mismo estado en la misma columna. No rompía nada porque `estado_operativo` está
# tipado como `str` y las comparaciones del Radar bajan a minúsculas — el sistema era
# coherente por accidente—, pero la Capa 9 debe seleccionar lo archivado y comprobar
# por qué estados pasó cada lote: ahí un falso negativo significa borrar lo que no se
# debía. La grafía canónica es la capitalizada.
ESTADO_INACTIVA = "Inactiva"
ESTADO_ANULADA_ADMINISTRACION = "Anulada_Administracion"

# Comparaciones siempre en minúsculas, para tolerar filas escritas antes de la
# normalización de v6 y no volver a depender de la grafía almacenada.
ESTADOS_ARCHIVADOS_NORMALIZADOS = ("inactiva", "anulada_administracion")

SQL_CREATE_EXPEDIENTES = """
CREATE TABLE IF NOT EXISTS expedientes (
    id TEXT PRIMARY KEY,
    titulo TEXT NOT NULL,
    organo TEXT,
    localidad TEXT,
    nuts TEXT,
    procedimiento TEXT,
    tipo_contrato TEXT,
    urgente INTEGER DEFAULT 0,
    fuente TEXT,
    link TEXT,
    fecha_publicacion TEXT,
    fecha_limite TEXT,
    fecha_ingesta TEXT NOT NULL,
    alerta_modificacion INTEGER DEFAULT 0,
    log_cambios TEXT DEFAULT '',
    last_seen_feed TEXT,
    feed_hash TEXT,
    -- Ciclo de vida (Capa 9, esquema v6). Hasta v5 sólo `lotes` tenía borrado lógico, así
    -- que un expediente entero no podía archivarse. Ver `.agents/CONTRATO_CAPA_9.md`.
    deleted_at TEXT,
    deleted_reason TEXT
);
"""

SQL_CREATE_LOTES = """
CREATE TABLE IF NOT EXISTS lotes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    expediente_id TEXT NOT NULL,
    lote_numero INTEGER NOT NULL DEFAULT 1,
    titulo_lote TEXT,
    cpvs TEXT,
    pbl REAL DEFAULT 0.0,
    vec REAL DEFAULT 0.0,
    garantia_definitiva REAL DEFAULT 0.0,
    subrogacion INTEGER DEFAULT 0,
    revision_precios INTEGER DEFAULT 0,
    dias_restantes INTEGER,
    score_total INTEGER DEFAULT 0,
    motivos_scoring TEXT,
    sector TEXT,
    prioridad TEXT DEFAULT 'Media',
    pmp_dias INTEGER DEFAULT 30,
    ratio_prorrogas REAL DEFAULT 1.0,
    estado_operativo TEXT DEFAULT 'Nueva',
    notes_usuario TEXT DEFAULT '', -- Mantenemos alias/columnas manuales
    notas_usuario TEXT DEFAULT '',
    empresa_adjudicataria TEXT,
    importe_adjudicacion REAL,
    dinero_en_la_mesa REAL,
    horas_internas_invertidas INTEGER DEFAULT 0,
    costes_externos REAL DEFAULT 0.0,
    importe_garantia_retenida REAL DEFAULT 0.0,
    fecha_devolucion_garantia TEXT,
    deleted_at TEXT,
    deleted_reason TEXT,
    -- Versión del contrato de scoring bajo la que se puntuó este lote (esquema v6).
    -- Lección del borrado de la beta (Paso D10): los datos de julio hubo que tirarlos
    -- porque estaban puntuados con la lógica anterior al Bloque 2 y convivían con los
    -- nuevos en esta misma tabla, sin nada que permitiera distinguirlos.
    version_scoring TEXT,
    updated_by TEXT DEFAULT 'radar',
    updated_at TEXT,
    FOREIGN KEY (expediente_id) REFERENCES expedientes(id) ON DELETE RESTRICT,
    UNIQUE(expediente_id, lote_numero)
);
"""

SQL_CREATE_EJECUCIONES = """
CREATE TABLE IF NOT EXISTS ejecuciones (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    start_time TEXT NOT NULL,
    end_time TEXT,
    estado TEXT NOT NULL,
    -- Métricas de la corrida (esquema v6). Hasta v5 esta tabla sólo guardaba cuándo
    -- empezó y acabó una ejecución, de modo que no permitía responder a "¿qué encontró
    -- la prospección del martes?". Las escribe el pipeline; el Paso 3 sólo crea el sitio.
    expedientes_nuevos INTEGER DEFAULT 0,
    expedientes_actualizados INTEGER DEFAULT 0,
    lotes_evaluados INTEGER DEFAULT 0,
    documentos_descargados INTEGER DEFAULT 0,
    analisis_realizados INTEGER DEFAULT 0,
    alertas_generadas INTEGER DEFAULT 0,
    errores INTEGER DEFAULT 0,
    version_scoring TEXT,
    version_politica_retencion TEXT
);
"""

SQL_CREATE_PURGAS = """
CREATE TABLE IF NOT EXISTS purgas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ejecutada_at TEXT NOT NULL,
    -- ARCHIVADO | DOCUMENTAL | ELIMINACION
    tipo TEXT NOT NULL,
    -- 'pipeline' cuando la dispara la política; 'usuario' cuando la pide una persona.
    solicitada_por TEXT NOT NULL,
    version_politica TEXT NOT NULL,
    documentos_purgados INTEGER DEFAULT 0,
    bytes_liberados INTEGER DEFAULT 0,
    expedientes_archivados INTEGER DEFAULT 0,
    expedientes_eliminados INTEGER DEFAULT 0,
    -- Lo que la invariante de memoria comercial impidió borrar. Se cuenta a propósito:
    -- una purga que bloquea mucho es una señal, no un fallo.
    bloqueados INTEGER DEFAULT 0,
    backup_asociado TEXT,
    -- COMPLETADA | ABORTADA | DEGRADADA
    resultado TEXT NOT NULL,
    detalle TEXT
);
"""

SQL_CREATE_DOCUMENTOS = """
CREATE TABLE IF NOT EXISTS documentos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    expediente_id TEXT NOT NULL,
    titulo TEXT NOT NULL,
    url TEXT NOT NULL,
    tipo TEXT NOT NULL, -- 'PCA', 'PPT', 'Anexo', 'Otro'
    hash_documento TEXT NOT NULL,
    local_path TEXT,
    estado TEXT NOT NULL DEFAULT 'DETECTADO', -- DETECTADO, DESCARGANDO, DESCARGADO, PROCESADO, ERROR_DESCARGA, OCR_PENDIENTE, ERROR_EXTRACCION
    sha256 TEXT,
    mida_bytes INTEGER,
    idioma TEXT,
    metodo_extraccion TEXT, -- 'pymupdf', 'tesseract', 'ninguno'
    texto_extraido TEXT,
    version_reglas INTEGER,
    error_detalle TEXT,
    intentos INTEGER DEFAULT 0,
    last_attempt_at TEXT,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (expediente_id) REFERENCES expedientes(id) ON DELETE RESTRICT,
    UNIQUE(expediente_id, hash_documento)
);
"""

SQL_CREATE_ANALISIS_SEMANTICO = """
CREATE TABLE IF NOT EXISTS analisis_semantico (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    expediente_id TEXT NOT NULL,
    subrogacion_detectada INTEGER DEFAULT 0,
    subrogacion_num_trabajadores INTEGER,
    subrogacion_convenio TEXT,
    subrogacion_desglose_completo INTEGER DEFAULT 0,
    subrogacion_coste_anual REAL,
    subrogacion_riesgo TEXT DEFAULT 'MEDIO',
    revision_precios_permitida INTEGER DEFAULT 0,
    revision_precios_formula TEXT,
    revision_precios_art_103 INTEGER DEFAULT 0,
    revision_precios_obs TEXT,
    criterios_peso_formulas INTEGER DEFAULT 50,
    criterios_peso_juicio_valor INTEGER DEFAULT 50,
    criterios_requiere_memoria INTEGER DEFAULT 1,
    criterios_desglose_json TEXT,
    dictamen_recomendacion TEXT DEFAULT 'REVISAR_RIESGO',
    dictamen_motivos_json TEXT,
    dictamen_ajuste_score INTEGER DEFAULT 0,
    dictamen_resumen TEXT,
    raw_dto_json TEXT NOT NULL,
    version_esquema INTEGER DEFAULT 1,
    modelo_llm TEXT,
    prompt_tokens INTEGER DEFAULT 0,
    completion_tokens INTEGER DEFAULT 0,
    tiempo_procesamiento_seg REAL DEFAULT 0.0,
    estado_analisis TEXT NOT NULL DEFAULT 'COMPLETADO',
    error_detalle TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (expediente_id) REFERENCES expedientes(id) ON DELETE RESTRICT,
    UNIQUE(expediente_id)
);
"""

SQL_CREATE_BOLETINES_ALERTAS = """
CREATE TABLE IF NOT EXISTS boletines_alertas (
    id_alerta TEXT PRIMARY KEY,
    fuente TEXT NOT NULL,
    num_boletin TEXT NOT NULL,
    fecha_publicacion TEXT NOT NULL,
    organo_emisor TEXT NOT NULL,
    municipio TEXT,
    titulo_anuncio TEXT NOT NULL,
    seccion_boletin TEXT,
    url_anuncio TEXT,
    url_pdf TEXT,
    texto_sumario TEXT,
    score_temprano INTEGER DEFAULT 0,
    motivos_score TEXT,
    categoria_fase_temprana TEXT DEFAULT 'OTROS',
    dictamen_ia_json TEXT,
    estado_operativo TEXT NOT NULL DEFAULT 'NUEVA_FASE_TEMPRANA',
    expediente_licitacion_vinculado TEXT,
    notas_usuario TEXT DEFAULT '',
    fecha_ingesta TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (expediente_licitacion_vinculado) REFERENCES expedientes(id) ON DELETE SET NULL
);
"""

SQL_CREATE_INDICES = [
    "CREATE INDEX IF NOT EXISTS idx_expedientes_last_seen ON expedientes(last_seen_feed);",
    "CREATE INDEX IF NOT EXISTS idx_lotes_expediente_estado ON lotes(expediente_id, estado_operativo);",
    "CREATE INDEX IF NOT EXISTS idx_expedientes_hash ON expedientes(feed_hash);",
    "CREATE INDEX IF NOT EXISTS idx_lotes_estado ON lotes(estado_operativo);",
    "CREATE INDEX IF NOT EXISTS idx_lotes_fecha_garantia ON lotes(fecha_devolucion_garantia);",
    "CREATE INDEX IF NOT EXISTS idx_documentos_exp_estado ON documentos(expediente_id, estado);",
    "CREATE INDEX IF NOT EXISTS idx_documentos_estado_fecha ON documentos(estado, updated_at);",
    "CREATE INDEX IF NOT EXISTS idx_analisis_semantico_exp ON analisis_semantico(expediente_id);",
    "CREATE INDEX IF NOT EXISTS idx_analisis_semantico_estado ON analisis_semantico(estado_analisis);",
    "CREATE INDEX IF NOT EXISTS idx_boletines_fuente_fecha ON boletines_alertas(fuente, fecha_publicacion);",
    "CREATE INDEX IF NOT EXISTS idx_boletines_estado ON boletines_alertas(estado_operativo);",
    "CREATE INDEX IF NOT EXISTS idx_boletines_expediente ON boletines_alertas(expediente_licitacion_vinculado);",
    # Esquema v6 — Capa 9
    "CREATE INDEX IF NOT EXISTS idx_expedientes_deleted_at ON expedientes(deleted_at);",
    "CREATE INDEX IF NOT EXISTS idx_purgas_fecha_tipo ON purgas(ejecutada_at, tipo);"
]


# =====================================================================
# DDL DE VISTAS ANALÍTICAS (SQL VIEWS v2)
# =====================================================================

# La vista NO filtra por `deleted_at` (H-30, corregido en la Capa 9, Paso 4). Lo hacía, y
# eso convertía el archivado en destrucción de indicadores: en el momento en que el
# Depurador archivara un lote `Adjudicada` o `Perdida` —tal como se decidió que haría—,
# ese lote dejaría de contar como ganado o perdido. Ganadas y perdidas caerían a cero y la
# tasa de éxito quedaría en blanco, sin haberse borrado un solo dato.
#
# El contrato de la Capa 9 es explícito: lo archivado "sigue en la base y sigue contando en
# los KPIs históricos". La memoria comercial cuenta esté archivada o no; el archivado
# gobierna qué se ve en el canal principal, no qué ha ocurrido. `vista_analisis_CAC` ya se
# comportaba así, de modo que las dos vistas discrepaban sobre qué es la población histórica.
SQL_CREATE_VIEW_WIN_RATE = """
CREATE VIEW IF NOT EXISTS vista_win_rate AS
SELECT 
    COALESCE(COUNT(CASE WHEN LOWER(estado_operativo) IN ('adjudicada', 'adjudicada_incoop') OR LOWER(empresa_adjudicataria) LIKE '%incoop%' THEN 1 END), 0) AS ganadas,
    COALESCE(COUNT(CASE WHEN LOWER(estado_operativo) IN ('perdida', 'adjudicada_competencia') OR (LOWER(empresa_adjudicataria) NOT LIKE '%incoop%' AND empresa_adjudicataria IS NOT NULL) THEN 1 END), 0) AS perdidas,
    COALESCE(COUNT(CASE WHEN LOWER(estado_operativo) = 'presentada' THEN 1 END), 0) AS pendientes_resolucion,
    COALESCE(COUNT(CASE WHEN LOWER(estado_operativo) IN ('adjudicada', 'adjudicada_incoop', 'perdida', 'adjudicada_competencia', 'presentada') THEN 1 END), 0) AS total_presentadas,
    ROUND(
        CAST(COALESCE(COUNT(CASE WHEN LOWER(estado_operativo) IN ('adjudicada', 'adjudicada_incoop') OR LOWER(empresa_adjudicataria) LIKE '%incoop%' THEN 1 END), 0) AS REAL) /
        NULLIF(COALESCE(COUNT(CASE WHEN LOWER(estado_operativo) IN ('adjudicada', 'adjudicada_incoop', 'perdida', 'adjudicada_competencia', 'presentada') THEN 1 END), 0), 0) * 100,
        2
    ) AS tasa_exito_porcentaje
FROM lotes;
"""

SQL_CREATE_VIEW_ANALISIS_CAC_TEMPLATE = """
CREATE VIEW IF NOT EXISTS vista_analisis_CAC AS
SELECT 
    expediente_id,
    lote_numero,
    titulo_lote,
    estado_operativo,
    horas_internas_invertidas,
    costes_externos,
    (horas_internas_invertidas * {tarifa_hora}) + costes_externos AS coste_adquisicion_total,
    pbl AS importe_licitacion_pbl,
    importe_adjudicacion,
    CASE 
        WHEN LOWER(estado_operativo) IN ('adjudicada', 'adjudicada_incoop') THEN COALESCE(importe_adjudicacion, pbl)
        ELSE 0.0
    END AS retorno_adjudicado,
    CASE 
        WHEN LOWER(estado_operativo) IN ('adjudicada', 'adjudicada_incoop') THEN COALESCE(importe_adjudicacion, pbl) - ((horas_internas_invertidas * {tarifa_hora}) + costes_externos)
        ELSE -((horas_internas_invertidas * {tarifa_hora}) + costes_externos)
    END AS retorno_neto
FROM lotes;
"""

SQL_CREATE_VIEW_GARANTIAS_ACTIVAS = """
CREATE VIEW IF NOT EXISTS vista_garantias_activas AS
SELECT 
    expediente_id,
    lote_numero,
    titulo_lote,
    pbl,
    importe_garantia_retenida,
    fecha_devolucion_garantia,
    strftime('%Y-%m-%d', datetime('now')) AS fecha_consulta_actual,
    CAST(julianday(fecha_devolucion_garantia) - julianday('now') AS INTEGER) AS dias_para_devolucion
FROM lotes
WHERE LOWER(estado_operativo) IN ('adjudicada', 'adjudicada_incoop') 
  AND importe_garantia_retenida > 0.0
ORDER BY fecha_devolucion_garantia ASC;
"""

SQL_CREATE_VIEW_GARANTIAS_POR_MES = """
CREATE VIEW IF NOT EXISTS vista_garantias_por_mes AS
SELECT 
    strftime('%Y-%m', fecha_devolucion_garantia) AS mes_devolucion,
    COUNT(*) AS cantidad_avales,
    ROUND(SUM(importe_garantia_retenida), 2) AS total_garantias_retenidas
FROM lotes
WHERE LOWER(estado_operativo) IN ('adjudicada', 'adjudicada_incoop') 
  AND importe_garantia_retenida > 0.0
  AND fecha_devolucion_garantia IS NOT NULL
GROUP BY strftime('%Y-%m', fecha_devolucion_garantia)
ORDER BY mes_devolucion ASC;
"""

SQL_CREATE_VIEW_ALERTAS_TEMPRANAS = """
CREATE VIEW IF NOT EXISTS vista_alertas_tempranas AS
SELECT 
    id_alerta,
    fuente,
    num_boletin,
    fecha_publicacion,
    organo_emisor,
    municipio,
    titulo_anuncio,
    categoria_fase_temprana,
    score_temprano,
    estado_operativo,
    expediente_licitacion_vinculado,
    fecha_ingesta
FROM boletines_alertas
ORDER BY fecha_publicacion DESC;
"""

# =====================================================================
# CLASE MEMORIA - PERSISTENCIA Y TRAZABILIDAD
# =====================================================================

class Memoria:
    """
    Clase responsable del almacenamiento, persistencia y trazabilidad de las licitaciones.
    Soporta control de duplicados (hash), control de concurrencia (locks),
    migración automática y segura del esquema (v5), blindaje de datos de usuario,
    vistas analíticas dinámicas y backups transaccionales en caliente catalogados.
    """
    # Fuente única: ver ESQUEMA_VERSION_ACTUAL arriba. No duplicar el número aquí.
    ESQUEMA_VERSION = ESQUEMA_VERSION_ACTUAL


    def __init__(self, db_path: Optional[str] = None):
        env_path = os.getenv("DB_PATH_INCOOP")
        raw_path = env_path or db_path or ruta_datos("licitaciones.db")
        if not os.path.isabs(raw_path):
            raw_path = str((PROJECT_ROOT / raw_path).resolve())
        self.db_path = raw_path
        self.db_write_lock = threading.Lock()

        # El directorio de almacenamiento se garantiza aquí, no al conectar. `setup_db()`
        # adquiere el cerrojo de migración ANTES de abrir la primera conexión, así que en una
        # instalación nueva —donde `data/` no existe, porque está excluida de Git— fallaba con
        # FileNotFoundError al crear el .lock. Es decir: un clon limpio del repositorio no
        # podía arrancar el sistema.
        db_dir = os.path.dirname(self.db_path)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)

    @contextmanager
    def conectar(self):
        """
        Context manager para gestionar de forma segura las conexiones a SQLite.
        Habilita el modo de diario WAL y la verificación de claves foráneas.
        Asegura que la conexión siempre se cierre al finalizar.
        """
        db_dir = os.path.dirname(self.db_path)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)

        conn = sqlite3.connect(self.db_path, timeout=30.0)
        try:
            conn.execute("PRAGMA busy_timeout=30000;")
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA foreign_keys=ON;")
            yield conn
        except Exception as e:
            raise e
        finally:
            conn.close()

    def _motivo_lock_huerfano(self, lock_path: str, ttl: float) -> Optional[str]:
        """
        Decide si un cerrojo existente puede reclamarse. Devuelve el motivo textual si
        es huérfano, o None si debe respetarse.

        Lee el fichero y lo cierra antes de devolver el control: el borrado es
        responsabilidad del llamante, porque Windows no permite borrar un fichero
        mientras siga abierto.
        """
        try:
            with open(lock_path, "r", encoding="utf-8") as f_lock:
                content = f_lock.read().strip()
        except FileNotFoundError:
            return None  # Ya no existe: el llamante reintentará y lo creará.
        except OSError:
            content = ""

        lock_pid = None
        lock_time = None
        if content:
            try:
                data = json.loads(content)
                lock_pid = data.get("pid")
                lock_time = data.get("created_at")
            except (ValueError, AttributeError):
                pass  # Contenido corrupto: se trata como cerrojo ilegible más abajo.

        # 1. El proceso propietario ya no existe.
        if lock_pid is not None:
            try:
                pid_int = int(lock_pid)
            except (TypeError, ValueError):
                pid_int = None
            if pid_int and not es_pid_activo(pid_int):
                return f"PID {pid_int} inactivo"

        # 2. El propietario sigue vivo pero el cerrojo ha superado su TTL.
        if lock_time is not None:
            try:
                antiguedad = time.time() - float(lock_time)
            except (TypeError, ValueError):
                antiguedad = None
            if antiguedad is not None:
                return f"TTL superado ({antiguedad:.0f}s > {ttl:.0f}s)" if antiguedad > ttl else None

        # 3. Cerrojo ilegible: sin PID ni fecha utilizables. Ocurre cuando un proceso
        # muere entre crear el fichero y escribir el payload. Se caduca por la fecha de
        # modificación del propio fichero, nunca de inmediato: un cerrojo ilegible pero
        # reciente puede ser un proceso sano que aún no ha terminado de escribirlo.
        try:
            antiguedad = time.time() - os.path.getmtime(lock_path)
        except OSError:
            return None
        if antiguedad > ttl:
            return f"cerrojo ilegible con {antiguedad:.0f}s de antigüedad (TTL {ttl:.0f}s)"
        return None

    @contextmanager
    def db_lock(self, timeout: float = 10.0, ttl: float = 600.0, lock_suffix: str = ".lock"):
        """
        Context manager que adquiere un lock exclusivo en memoria (hilos)
        y posteriormente a nivel de sistema de archivos (procesos).
        Escribe un payload JSON {"pid": ..., "created_at": ...} y limpia automáticamente
        locks huérfanos por PID inactivo o superación del TTL (600s).
        """
        lock_path = self.db_path + lock_suffix
        adquirido_fs = False
        fd = None
        start_time = time.time()
        
        # 1. Adquirir lock en memoria para evitar contención de disco local
        with self.db_write_lock:
            # 2. Adquirir lock a nivel de sistema de archivos
            while time.time() - start_time < timeout:
                try:
                    fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                    payload = json.dumps({"pid": os.getpid(), "created_at": time.time()}).encode("utf-8")
                    os.write(fd, payload)
                    adquirido_fs = True
                    break
                except FileExistsError:
                    # La decisión se toma con el fichero ya cerrado y el borrado ocurre
                    # después: en Windows os.remove() falla con WinError 32 si queda un
                    # handle abierto, y el lock huérfano no se reclamaba jamás.
                    motivo = self._motivo_lock_huerfano(lock_path, ttl)

                    if motivo is not None:
                        try:
                            os.remove(lock_path)
                        except FileNotFoundError:
                            pass  # Otro proceso lo reclamó primero: reintentar sin más.
                        except OSError as e_rm:
                            # No se pudo borrar (permisos, handle vivo). Se espera y se
                            # reintenta; el estado sigue siendo distinguible porque el
                            # bucle acabará lanzando RuntimeError si nunca se libera.
                            print(f"[!] No se pudo reclamar el cerrojo huérfano ({lock_path}): {e_rm}")
                            time.sleep(random.uniform(0.05, 0.15))
                            continue
                        else:
                            # Borrar el cerrojo de otro proceso es destructivo: debe dejar rastro.
                            self.registrar_log_json(
                                run_id=0,
                                action="DB_LOCK_HUERFANO_RECLAMADO",
                                reason=f"{lock_path}: {motivo}",
                                updated_by="memoria"
                            )
                        continue  # Reintentar inmediatamente adquirir el lock

                    time.sleep(random.uniform(0.05, 0.15))

            if not adquirido_fs:
                raise RuntimeError(
                    f"No se pudo adquirir el lock de base de datos a nivel de disco ({lock_path}) tras {timeout}s."
                )
                
            try:
                yield
            finally:
                if fd is not None:
                    try:
                        os.close(fd)
                    except Exception:
                        pass
                    try:
                        if os.path.exists(lock_path):
                            os.remove(lock_path)
                    except Exception:
                        pass

    def _crear_backup_migracion(self) -> str:
        backup_path = self.db_path + ".mig_backup"
        if os.path.exists(backup_path):
            try:
                os.remove(backup_path)
            except Exception:
                pass
        
        conn_src = sqlite3.connect(self.db_path, timeout=30.0)
        conn_src.execute("PRAGMA busy_timeout=30000;")
        conn_dst = sqlite3.connect(backup_path, timeout=30.0)
        conn_dst.execute("PRAGMA busy_timeout=30000;")
        try:
            conn_src.backup(conn_dst)
        finally:
            conn_dst.close()
            conn_src.close()
        return backup_path

    def _restaurar_backup_migracion(self, backup_path: str) -> None:
        if not os.path.exists(backup_path):
            return
        
        conn_src = sqlite3.connect(backup_path, timeout=30.0)
        conn_src.execute("PRAGMA busy_timeout=30000;")
        conn_dst = sqlite3.connect(self.db_path, timeout=30.0)
        conn_dst.execute("PRAGMA busy_timeout=30000;")
        try:
            conn_src.backup(conn_dst)
        finally:
            conn_dst.close()
            conn_src.close()
            
        try:
            os.remove(backup_path)
        except Exception:
            pass

    def setup_db(self) -> None:
        """
        Inicializa la base de datos si no existe, o verifica/migra el esquema de forma idempotente
        y segura si ya existe (realizando un backup antes). Recrea las vistas analíticas.
        Utiliza un lock físico de exclusión mutua para evitar colisiones de concurrencia en la migración.
        """
        lock_path = self.db_path + ".lock"
        adquirido = False
        fd = None
        
        # Intentar adquirir lock
        for intencion in range(5):
            try:
                fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                adquirido = True
                break
            except FileExistsError:
                time.sleep(1.0)
                
        if not adquirido:
            raise RuntimeError(
                "No se pudo adquirir el lock de migración de base de datos. "
                "Hay otro proceso ejecutando setup_db() de forma concurrente."
            )

        try:
            # Si no existe base de datos física, la creamos limpia en v5
            if not os.path.exists(self.db_path):
                with self.conectar() as conn:
                    with conn:
                        conn.execute(SQL_CREATE_METADATA)
                        conn.execute(SQL_INSERT_INITIAL_VERSION)
                        conn.execute(SQL_CREATE_EXPEDIENTES)
                        conn.execute(SQL_CREATE_LOTES)
                        conn.execute(SQL_CREATE_EJECUCIONES)
                        conn.execute(SQL_CREATE_DOCUMENTOS)
                        conn.execute(SQL_CREATE_ANALISIS_SEMANTICO)
                        conn.execute(SQL_CREATE_BOLETINES_ALERTAS)
                        conn.execute(SQL_CREATE_PURGAS)
                        for query in SQL_CREATE_INDICES:
                            conn.execute(query)
                print(f"[+] Base de datos nueva inicializada correctamente en esquema v{self.ESQUEMA_VERSION}.")
            else:
                # Si ya existe, abrimos y verificamos la versión
                with self.conectar() as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        "SELECT name FROM sqlite_master WHERE type='table' AND name='metadata';"
                    )
                    tabla_metadata_existe = cursor.fetchone() is not None

                    if not tabla_metadata_existe:
                        with conn:
                            conn.execute(SQL_CREATE_METADATA)
                            conn.execute(SQL_INSERT_INITIAL_VERSION)
                            conn.execute(SQL_CREATE_EXPEDIENTES)
                            conn.execute(SQL_CREATE_LOTES)
                            conn.execute(SQL_CREATE_EJECUCIONES)
                            conn.execute(SQL_CREATE_DOCUMENTOS)
                            conn.execute(SQL_CREATE_ANALISIS_SEMANTICO)
                            conn.execute(SQL_CREATE_BOLETINES_ALERTAS)
                            for query in SQL_CREATE_INDICES:
                                conn.execute(query)
                        print(f"[+] Esquema v{self.ESQUEMA_VERSION} inicializado (BD física previa sin metadata).")
                    else:
                        cursor.execute("SELECT version FROM metadata LIMIT 1;")
                        row = cursor.fetchone()
                        version_actual = row[0] if row else 0

                        print(f"[~] Base de datos existente. Versión actual en BD: {version_actual} | Versión esperada: {self.ESQUEMA_VERSION}")

                        if version_actual < self.ESQUEMA_VERSION:
                            print(f"[~] Iniciando backup preventivo antes de migrar...")
                            backup_file = self._crear_backup_migracion()
                            try:
                                with self.conectar() as conn_mig:
                                    cursor_mig = conn_mig.cursor()
                                    
                                    def _columna_existe(tabla, columna):
                                        cursor_mig.execute(f"PRAGMA table_info({tabla});")
                                        return any(c[1] == columna for c in cursor_mig.fetchall())

                                    with conn_mig:
                                        # Migración a v2
                                        if version_actual < 2:
                                            if not _columna_existe("expedientes", "last_seen_feed"):
                                                conn_mig.execute("ALTER TABLE expedientes ADD COLUMN last_seen_feed TEXT;")
                                            if not _columna_existe("expedientes", "feed_hash"):
                                                conn_mig.execute("ALTER TABLE expedientes ADD COLUMN feed_hash TEXT;")
                                            
                                            if not _columna_existe("lotes", "deleted_at"):
                                                conn_mig.execute("ALTER TABLE lotes ADD COLUMN deleted_at TEXT;")
                                            if not _columna_existe("lotes", "deleted_reason"):
                                                conn_mig.execute("ALTER TABLE lotes ADD COLUMN deleted_reason TEXT;")
                                            if not _columna_existe("lotes", "updated_by"):
                                                conn_mig.execute("ALTER TABLE lotes ADD COLUMN updated_by TEXT DEFAULT 'radar';")
                                            if not _columna_existe("lotes", "updated_at"):
                                                conn_mig.execute("ALTER TABLE lotes ADD COLUMN updated_at TEXT;")
                                            
                                            conn_mig.execute(SQL_CREATE_EJECUCIONES)
                                        
                                        # Migración a v3
                                        if version_actual < 3:
                                            conn_mig.execute(SQL_CREATE_DOCUMENTOS)

                                        # Migración a v4
                                        if version_actual < 4:
                                            conn_mig.execute(SQL_CREATE_ANALISIS_SEMANTICO)

                                        # Migración a v5
                                        if version_actual < 5:
                                            conn_mig.execute(SQL_CREATE_BOLETINES_ALERTAS)

                                        # Migración a v6 — Capa 9: ciclo de vida del dato
                                        if version_actual < 6:
                                            # Borrado lógico a nivel de expediente. Hasta v5
                                            # sólo lo tenían los lotes.
                                            if not _columna_existe("expedientes", "deleted_at"):
                                                conn_mig.execute("ALTER TABLE expedientes ADD COLUMN deleted_at TEXT;")
                                            if not _columna_existe("expedientes", "deleted_reason"):
                                                conn_mig.execute("ALTER TABLE expedientes ADD COLUMN deleted_reason TEXT;")

                                            # Generación de scoring con la que se puntuó el lote.
                                            if not _columna_existe("lotes", "version_scoring"):
                                                conn_mig.execute("ALTER TABLE lotes ADD COLUMN version_scoring TEXT;")

                                            # Métricas de la corrida. `ejecuciones` puede no
                                            # existir si se viene de un esquema anterior a v2,
                                            # y ALTER TABLE sobre una tabla ausente aborta la
                                            # migración entera: se garantiza primero. Si la
                                            # crea aquí, nace ya con las columnas v6 y los
                                            # ALTER de abajo se saltan solos.
                                            conn_mig.execute(SQL_CREATE_EJECUCIONES)
                                            for columna, tipo in (
                                                ("expedientes_nuevos", "INTEGER DEFAULT 0"),
                                                ("expedientes_actualizados", "INTEGER DEFAULT 0"),
                                                ("lotes_evaluados", "INTEGER DEFAULT 0"),
                                                ("documentos_descargados", "INTEGER DEFAULT 0"),
                                                ("analisis_realizados", "INTEGER DEFAULT 0"),
                                                ("alertas_generadas", "INTEGER DEFAULT 0"),
                                                ("errores", "INTEGER DEFAULT 0"),
                                                ("version_scoring", "TEXT"),
                                                ("version_politica_retencion", "TEXT"),
                                            ):
                                                if not _columna_existe("ejecuciones", columna):
                                                    conn_mig.execute(
                                                        f"ALTER TABLE ejecuciones ADD COLUMN {columna} {tipo};"
                                                    )

                                            conn_mig.execute(SQL_CREATE_PURGAS)

                                            # H-27: normalización de las dos grafías del estado
                                            # archivado. Se hace aquí, con copia previa ya
                                            # tomada, porque a partir de v6 la Capa 9 compara
                                            # estados para decidir qué puede borrarse.
                                            conn_mig.execute(
                                                "UPDATE lotes SET estado_operativo = ? "
                                                "WHERE LOWER(estado_operativo) = 'inactiva';",
                                                (ESTADO_INACTIVA,)
                                            )
                                            conn_mig.execute(
                                                "UPDATE lotes SET estado_operativo = ? "
                                                "WHERE LOWER(estado_operativo) = 'anulada_administracion';",
                                                (ESTADO_ANULADA_ADMINISTRACION,)
                                            )


                                        # Re-crear índices (v2, v3, v4 y v5)
                                        for query in SQL_CREATE_INDICES:
                                            try:
                                                conn_mig.execute(query)
                                            except sqlite3.OperationalError:
                                                pass

                                            
                                        conn_mig.execute("UPDATE metadata SET version = ?;", (self.ESQUEMA_VERSION,))
                                
                                if os.path.exists(backup_file):
                                    os.remove(backup_file)
                                print(f"[+] Migración a v{self.ESQUEMA_VERSION} completada con éxito.")

                            except Exception as e:
                                print(f"[!] Error crítico durante la migración: {e}. Restaurando backup preventivo...")
                                self._restaurar_backup_migracion(backup_file)
                                raise e

                        elif version_actual > self.ESQUEMA_VERSION:
                            raise ValueError(
                                f"La base de datos tiene una versión de esquema superior ({version_actual}) "
                                f"a la compatible con este código ({self.ESQUEMA_VERSION}). Por favor, actualiza el software."
                            )
                        else:
                            # Asegurar de forma preventiva que existan las nuevas columnas de descargas
                            with self.conectar() as conn_check:
                                cursor_check = conn_check.cursor()
                                def _columna_existe_conn(tabla, columna):
                                    cursor_check.execute(f"PRAGMA table_info({tabla});")
                                    return any(c[1] == columna for c in cursor_check.fetchall())
                                
                                with conn_check:
                                    if not _columna_existe_conn("documentos", "intentos"):
                                        conn_check.execute("ALTER TABLE documentos ADD COLUMN intentos INTEGER DEFAULT 0;")
                                    if not _columna_existe_conn("documentos", "last_attempt_at"):
                                        conn_check.execute("ALTER TABLE documentos ADD COLUMN last_attempt_at TEXT;")
                            print("[+] La base de datos está actualizada a la versión esperada.")
        finally:
            if fd is not None:
                try:
                    os.close(fd)
                except Exception:
                    pass
            if adquirido:
                try:
                    os.remove(lock_path)
                except Exception:
                    pass

        # --- RECREACIÓN DE VISTAS ANALÍTICAS CON TARIFA CONFIGURABLE ---
        tarifa_hora = 35.0
        yaml_path = ruta_proyecto("config/perfil_incoop.yaml")
        if os.path.exists(yaml_path):
            try:
                import yaml
                with open(yaml_path, "r", encoding="utf-8") as fy:
                    config_data = yaml.safe_load(fy)
                    if config_data and "tarifa_cac_hora" in config_data:
                        tarifa_hora = float(config_data["tarifa_cac_hora"])
            except Exception as e:
                print(f"[!] Advertencia al leer config/perfil_incoop.yaml, usando tarifa CAC por defecto de 35.0: {e}")

        with self.conectar() as conn:
            with conn:
                # Limpiar vistas analíticas previas
                conn.execute("DROP VIEW IF EXISTS vista_win_rate;")
                conn.execute("DROP VIEW IF EXISTS vista_analisis_CAC;")
                conn.execute("DROP VIEW IF EXISTS vista_garantias_activas;")
                conn.execute("DROP VIEW IF EXISTS vista_garantias_por_mes;")
                conn.execute("DROP VIEW IF EXISTS vista_alertas_tempranas;")
                
                # Crear vistas
                conn.execute(SQL_CREATE_VIEW_WIN_RATE)
                
                sql_cac_dinamica = SQL_CREATE_VIEW_ANALISIS_CAC_TEMPLATE.format(tarifa_hora=tarifa_hora)
                conn.execute(sql_cac_dinamica)
                
                conn.execute(SQL_CREATE_VIEW_GARANTIAS_ACTIVAS)
                conn.execute(SQL_CREATE_VIEW_GARANTIAS_POR_MES)
                conn.execute(SQL_CREATE_VIEW_ALERTAS_TEMPRANAS)
                
                # Asegurar índices para las vistas
                conn.execute("CREATE INDEX IF NOT EXISTS idx_lotes_estado ON lotes(estado_operativo);")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_lotes_fecha_garantia ON lotes(fecha_devolucion_garantia);")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_boletines_estado ON boletines_alertas(estado_operativo);")
        print(f"[+] Vistas analíticas y de tesorería recreadas (Tarifa horaria CAC: {tarifa_hora} EUR/h).")


    # =====================================================================
    # MOTOR DE LOCKS LÓGICOS DE CONCURRENCIA
    # =====================================================================

    def iniciar_ejecucion(self) -> int:
        """
        Intenta adquirir el lock de inicio de ejecución.
        Si hay una ejecución activa hace menos de 6 horas, lanza RuntimeError.
        Si la ejecución tiene más de 6 horas, se reapropia de ella, marcándola como FAILED por timeout.
        Devuelve el ID de la nueva ejecución creada.
        """
        now_utc = datetime.now(timezone.utc)
        now_str = now_utc.strftime("%Y-%m-%dT%H:%M:%SZ")

        with self.conectar() as conn:
            cursor = conn.cursor()
            
            # Comprobar la última ejecución RUNNING
            cursor.execute(
                "SELECT id, start_time FROM ejecuciones WHERE estado = 'RUNNING' ORDER BY id DESC LIMIT 1;"
            )
            row = cursor.fetchone()
            
            if row:
                run_id, start_str = row
                try:
                    start_time = datetime.strptime(start_str, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
                    diferencia = now_utc - start_time
                    horas = diferencia.total_seconds() / 3600.0
                    
                    if horas < 6.0:
                        raise RuntimeError(
                            f"Ya existe una ejecución en curso (ID: {run_id}) iniciada hace {horas:.1f} horas. "
                            "Ejecución paralela del radar abortada."
                        )
                    else:
                        # Reapropiación de lock por timeout (6 horas)
                        with conn:
                            cursor.execute(
                                "UPDATE ejecuciones SET estado = 'FAILED', end_time = ? WHERE id = ?;",
                                (now_str, run_id)
                            )
                        print(f"[!] [radar] Reapropiación de lock. Ejecución huérfana ID: {run_id} cerrada por timeout.")
                except Exception as e:
                    if "Ejecución paralela del radar abortada" in str(e):
                        raise e

            # Adquirir nuevo lock
            with conn:
                cursor.execute(
                    "INSERT INTO ejecuciones (start_time, estado) VALUES (?, 'RUNNING');",
                    (now_str,)
                )
                nueva_id = cursor.lastrowid
            return nueva_id

    def finalizar_ejecucion(self, ejecucion_id: int, exito: bool = True) -> None:
        """
        Cierra la ejecución activa liberando el lock lógico.
        """
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        estado = "COMPLETED" if exito else "FAILED"
        
        with self.conectar() as conn:
            with conn:
                conn.execute(
                    "UPDATE ejecuciones SET estado = ?, end_time = ? WHERE id = ?;",
                    (estado, now_str, ejecucion_id)
                )

    #: Columnas de métricas que `ejecuciones` admite (esquema v6). La lista blanca evita
    #: que un nombre de columna llegue interpolado desde fuera y, sobre todo, que una
    #: métrica mal escrita se pierda en silencio: se rechaza con un error explícito.
    METRICAS_EJECUCION_VALIDAS = (
        "expedientes_nuevos",
        "expedientes_actualizados",
        "lotes_evaluados",
        "documentos_descargados",
        "analisis_realizados",
        "alertas_generadas",
        "errores",
        "version_scoring",
        "version_politica_retencion",
    )

    def registrar_metricas_ejecucion(self, ejecucion_id: int, **metricas) -> None:
        """
        Persiste las métricas de una corrida en la tabla `ejecuciones` (esquema v6).

        Hasta ahora estas cifras se imprimían por terminal y se perdían: la tabla sólo sabía
        cuándo empezó y acabó cada ejecución, de modo que no había forma de responder a
        "¿qué encontró la prospección del martes?". El Paso 3 creó las columnas; aquí se
        pueblan por primera vez.

        Los valores a `None` se omiten, para no pisar con nulos lo que otra fase ya escribió.
        """
        campos = {k: v for k, v in metricas.items() if v is not None}
        if not campos:
            return

        desconocidas = set(campos) - set(self.METRICAS_EJECUCION_VALIDAS)
        if desconocidas:
            raise ValueError(
                f"Métricas de ejecución desconocidas: {', '.join(sorted(desconocidas))}. "
                f"Válidas: {', '.join(self.METRICAS_EJECUCION_VALIDAS)}."
            )

        asignaciones = ", ".join(f"{campo} = :{campo}" for campo in campos)
        parametros = dict(campos)
        parametros["ejecucion_id"] = ejecucion_id

        with self.conectar() as conn:
            with conn:
                conn.execute(
                    f"UPDATE ejecuciones SET {asignaciones} WHERE id = :ejecucion_id;",
                    parametros
                )

    def contar_documentos_descargados_desde(self, desde_utc: str) -> int:
        """
        Documentos que quedaron descargados o procesados durante la corrida en curso.

        Se cuenta contra la base y no con un contador en memoria porque la descarga es
        multihilo y resiliente: un documento puede reintentarse, diferirse a OCR o fallar,
        y lo que interesa registrar es cuántos acabaron realmente en disco. `DETECTADO` no
        cuenta: detectar una URL no es haberla descargado.
        """
        with self.conectar() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT COUNT(*) FROM documentos "
                "WHERE updated_at >= ? AND estado IN ('DESCARGADO', 'PROCESADO');",
                (desde_utc,)
            )
            return cursor.fetchone()[0]

    def registrar_purga(
        self,
        tipo: str,
        solicitada_por: str,
        version_politica: str,
        resultado: str,
        documentos_purgados: int = 0,
        bytes_liberados: int = 0,
        expedientes_archivados: int = 0,
        expedientes_eliminados: int = 0,
        bloqueados: int = 0,
        backup_asociado: Optional[str] = None,
        detalle: Optional[str] = None,
        conn: Optional[sqlite3.Connection] = None,
    ) -> int:
        """
        Registra una operación del Depurador en la tabla de auditoría `purgas` (esquema v6).

        Se registran también las abortadas y las degradadas: "nada se purga en silencio"
        incluye, sobre todo, lo que se intentó y no salió. `conn` permite escribir dentro de
        la misma transacción que la operación auditada, para que el rastro y el hecho no
        puedan quedar desacoplados.
        """
        sql = """
        INSERT INTO purgas (
            ejecutada_at, tipo, solicitada_por, version_politica,
            documentos_purgados, bytes_liberados, expedientes_archivados,
            expedientes_eliminados, bloqueados, backup_asociado, resultado, detalle
        ) VALUES (
            :ejecutada_at, :tipo, :solicitada_por, :version_politica,
            :documentos_purgados, :bytes_liberados, :expedientes_archivados,
            :expedientes_eliminados, :bloqueados, :backup_asociado, :resultado, :detalle
        );
        """
        parametros = {
            "ejecutada_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "tipo": tipo,
            "solicitada_por": solicitada_por,
            "version_politica": version_politica,
            "documentos_purgados": documentos_purgados,
            "bytes_liberados": bytes_liberados,
            "expedientes_archivados": expedientes_archivados,
            "expedientes_eliminados": expedientes_eliminados,
            "bloqueados": bloqueados,
            "backup_asociado": backup_asociado,
            "resultado": resultado,
            "detalle": detalle,
        }

        if conn is not None:
            return conn.execute(sql, parametros).lastrowid

        with self.conectar() as c:
            with c:
                return c.execute(sql, parametros).lastrowid

    # =====================================================================
    # UPSERT DE INGESTA CON DETECCION DE CAMBIOS POR HASH
    # =====================================================================

    def upsert_oportunidad(self, licitacion: Dict[str, Any], evaluacion: Dict[str, Any]) -> None:
        """
        Inserta o actualiza un expediente y su Lote 1 de forma atómica.
        Utiliza feed_hash para omitir escrituras pesadas si el payload público no ha cambiado.
        """
        expediente_id = licitacion.get("id")
        nuevo_hash = calcular_feed_hash(licitacion)
        timestamp_now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        # 1. Recuperar valores previos de la base de datos de forma transaccional
        fecha_limite_previa = None
        log_cambios_previo = ""
        alerta_modificacion_previa = 0
        vec_previo = None
        estado_operativo_previo = "Nueva"
        hash_previo = None
        existe_previo = False

        with self.conectar() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT fecha_limite, log_cambios, alerta_modificacion, feed_hash FROM expedientes WHERE id = ?;",
                (expediente_id,)
            )
            row_exp = cursor.fetchone()
            if row_exp:
                existe_previo = True
                fecha_limite_previa, log_cambios_previo, alerta_modificacion_previa, hash_previo = row_exp
                if log_cambios_previo is None:
                    log_cambios_previo = ""

                cursor.execute(
                    "SELECT vec, estado_operativo FROM lotes WHERE expediente_id = ? AND lote_numero = 1;",
                    (expediente_id,)
                )
                row_lote = cursor.fetchone()
                if row_lote:
                    vec_previo, estado_operativo_previo = row_lote

        # Caso Optimización: El hash coincide (Hit)
        if existe_previo and hash_previo == nuevo_hash:
            with self.conectar() as conn:
                with conn:
                    conn.execute(
                        "UPDATE expedientes SET last_seen_feed = ? WHERE id = ?;",
                        (timestamp_now, expediente_id)
                    )
            return

        # 2. Normalizar fechas a UTC
        fecha_pub_utc = normalizar_fecha_utc(licitacion.get("fecha_publicacion", ""))
        fecha_lim_utc = normalizar_fecha_utc(licitacion.get("fecha_limite", ""))

        # 3. Detectar rectificaciones públicas
        alerta_modificacion = alerta_modificacion_previa
        log_cambios = log_cambios_previo
        
        if existe_previo:
            cambios = []
            fl_prev_utc = normalizar_fecha_utc(fecha_limite_previa)
            if fl_prev_utc != "N/A" and fecha_lim_utc != "N/A" and fl_prev_utc != fecha_lim_utc:
                cambios.append(f"Fecha límite modificada de {fl_prev_utc} a {fecha_lim_utc}")
            
            vec_nuevo = float(licitacion.get("vec", 0.0))
            if vec_previo is not None and abs(vec_previo - vec_nuevo) > 0.01:
                cambios.append(f"VEC modificado de {vec_previo:,.2f} EUR a {vec_nuevo:,.2f} EUR")
            
            if cambios and estado_operativo_previo.lower() != "nueva":
                alerta_modificacion = 1
                timestamp_log = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
                entrada_log = f"[{timestamp_log}] [radar] " + " | ".join(cambios)
                log_cambios = log_cambios + "\n" + entrada_log if log_cambios else entrada_log

        # Serializar cpvs y motivos
        cpvs_serialized = ",".join(licitacion.get("cpvs", []))
        motivos_serialized = " | ".join(evaluacion.get("motivos", []))

        datos_expediente = {
            "id": expediente_id,
            "titulo": licitacion.get("titulo"),
            "organo": licitacion.get("organo"),
            "localidad": licitacion.get("localidad"),
            "nuts": licitacion.get("country_subentity_code"),
            "procedimiento": licitacion.get("procedimiento_codigo"),
            "tipo_contrato": licitacion.get("tipo_contrato_codigo"),
            "urgente": 1 if licitacion.get("urgente") else 0,
            "fuente": licitacion.get("fuente"),
            "link": licitacion.get("link"),
            "fecha_publicacion": fecha_pub_utc,
            "fecha_limite": fecha_lim_utc,
            "alerta_modificacion": alerta_modificacion,
            "log_cambios": log_cambios,
            "last_seen_feed": timestamp_now,
            "feed_hash": nuevo_hash
        }

        datos_lote = {
            "expediente_id": expediente_id,
            "lote_numero": 1,
            "titulo_lote": licitacion.get("titulo"),
            "cpvs": cpvs_serialized,
            "pbl": licitacion.get("importe", 0.0),
            "vec": licitacion.get("vec", 0.0),
            "garantia_definitiva": evaluacion.get("garantia_estimada", 0.0),
            "subrogacion": 1 if evaluacion.get("subrogacion_detectada") else 0,
            "revision_precios": 1 if evaluacion.get("revision_precios_detectada") else 0,
            "dias_restantes": evaluacion.get("dias_restantes"),
            "score_total": evaluacion.get("score", 0),
            "motivos_scoring": motivos_serialized,
            "sector": evaluacion.get("sector_detectado"),
            "prioridad": evaluacion.get("prioridad", "Media"),
            "pmp_dias": evaluacion.get("pmp_detectado", 30),
            "ratio_prorrogas": evaluacion.get("ratio_prorrogas", 1.0),
            # Generación de scoring con la que se puntuó (esquema v6, lección del Paso D10).
            "version_scoring": evaluacion.get("version_scoring"),
            "updated_by": "radar",
            "updated_at": timestamp_now
        }

        sql_upsert_expediente = """
        INSERT INTO expedientes (
            id, titulo, organo, localidad, nuts, procedimiento, tipo_contrato,
            urgente, fuente, link, fecha_publicacion, fecha_limite, fecha_ingesta,
            alerta_modificacion, log_cambios, last_seen_feed, feed_hash
        ) VALUES (
            :id, :titulo, :organo, :localidad, :nuts, :procedimiento, :tipo_contrato,
            :urgente, :fuente, :link, :fecha_publicacion, :fecha_limite, :last_seen_feed,
            :alerta_modificacion, :log_cambios, :last_seen_feed, :feed_hash
        ) ON CONFLICT(id) DO UPDATE SET
            titulo = excluded.titulo,
            organo = excluded.organo,
            localidad = excluded.localidad,
            nuts = excluded.nuts,
            procedimiento = excluded.procedimiento,
            tipo_contrato = excluded.tipo_contrato,
            urgente = excluded.urgente,
            link = excluded.link,
            fecha_publicacion = excluded.fecha_publicacion,
            fecha_limite = excluded.fecha_limite,
            alerta_modificacion = excluded.alerta_modificacion,
            log_cambios = excluded.log_cambios,
            last_seen_feed = excluded.last_seen_feed,
            feed_hash = excluded.feed_hash;
        """

        sql_upsert_lote = """
        INSERT INTO lotes (
            expediente_id, lote_numero, titulo_lote, cpvs, pbl, vec,
            garantia_definitiva, subrogacion, revision_precios, dias_restantes,
            score_total, motivos_scoring, sector, prioridad, pmp_dias, ratio_prorrogas,
            version_scoring, updated_by, updated_at
        ) VALUES (
            :expediente_id, :lote_numero, :titulo_lote, :cpvs, :pbl, :vec,
            :garantia_definitiva, :subrogacion, :revision_precios, :dias_restantes,
            :score_total, :motivos_scoring, :sector, :prioridad, :pmp_dias, :ratio_prorrogas,
            :version_scoring, :updated_by, :updated_at
        ) ON CONFLICT(expediente_id, lote_numero) DO UPDATE SET
            titulo_lote = excluded.titulo_lote,
            cpvs = excluded.cpvs,
            pbl = excluded.pbl,
            vec = excluded.vec,
            garantia_definitiva = excluded.garantia_definitiva,
            subrogacion = excluded.subrogacion,
            revision_precios = excluded.revision_precios,
            dias_restantes = excluded.dias_restantes,
            score_total = excluded.score_total,
            motivos_scoring = excluded.motivos_scoring,
            sector = excluded.sector,
            prioridad = excluded.prioridad,
            pmp_dias = excluded.pmp_dias,
            ratio_prorrogas = excluded.ratio_prorrogas,
            version_scoring = excluded.version_scoring,
            updated_by = excluded.updated_by,
            updated_at = excluded.updated_at;
        """

        with self.conectar() as conn:
            with conn:
                conn.execute(sql_upsert_expediente, datos_expediente)
                conn.execute(sql_upsert_lote, datos_lote)

    # =====================================================================
    # SOFT DELETE OPERATIVO POR TIMESTAMPS
    # =====================================================================

    def soft_delete_obsoletos(self, ejecucion_start_utc: str) -> None:
        """
        Aplica borrado lógico a los expedientes ausentes en la ejecución actual.
        Utiliza el last_seen_feed comparado con el timestamp de inicio de la ejecución.
        """
        fecha_actual_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        with self.conectar() as conn:
            cursor = conn.cursor()
            
            cursor.execute(
                "SELECT id, fecha_limite FROM expedientes WHERE last_seen_feed < ? OR last_seen_feed IS NULL;",
                (ejecucion_start_utc,)
            )
            obsoletos = cursor.fetchall()
            
            if not obsoletos:
                return

            with conn:
                for exp_id, fecha_limite in obsoletos:
                    cursor.execute(
                        "SELECT id, lote_numero, estado_operativo FROM lotes WHERE expediente_id = ?;",
                        (exp_id,)
                    )
                    lotes = cursor.fetchall()
                    
                    for lote_id, lote_numero, estado_op in lotes:
                        if normalizar_estado_operativo(estado_op) == "nueva":
                            cursor.execute(
                                "UPDATE lotes SET estado_operativo = ?, deleted_at = ?, deleted_reason = ?, updated_by = 'radar', updated_at = ? WHERE id = ?;",
                                (ESTADO_INACTIVA, fecha_actual_utc, "Ausente en el feed de licitaciones vigentes (Expirado)", fecha_actual_utc, lote_id)
                            )
                            cursor.execute(
                                "UPDATE expedientes SET log_cambios = COALESCE(log_cambios, '') || ? WHERE id = ?;",
                                (f"\n[{fecha_actual_utc}] [radar] Estado cambiado de 'Nueva' a '{ESTADO_INACTIVA}' (Ausente en feed)", exp_id)
                            )
                            # Rastro estructurado además del literario (H-31): el Paso 6
                            # tendrá que responder por qué estados pasó este lote.
                            anexar_log_cambios(
                                cursor, exp_id,
                                entrada_log_cambio_estado(lote_numero, estado_op, ESTADO_INACTIVA, autor="radar")
                            )
                        elif normalizar_estado_operativo(estado_op) not in ESTADOS_ARCHIVADOS_NORMALIZADOS:
                            if fecha_limite and fecha_limite != "N/A" and fecha_limite > fecha_actual_utc:
                                cursor.execute(
                                    "UPDATE lotes SET estado_operativo = ?, deleted_at = ?, deleted_reason = ?, updated_by = 'radar', updated_at = ? WHERE id = ?;",
                                    (ESTADO_ANULADA_ADMINISTRACION, fecha_actual_utc, "Ausente en feed antes de la fecha límite (Posible anulación)", fecha_actual_utc, lote_id)
                                )
                                cursor.execute(
                                    "UPDATE expedientes SET alerta_modificacion = 1, log_cambios = COALESCE(log_cambios, '') || ? WHERE id = ?;",
                                    (f"\n[{fecha_actual_utc}] [radar] [ALERTA] Licitación ausente del feed antes de su vencimiento. Posible anulación.", exp_id)
                                )
                                # Esta es la rama que el contrato de la Capa 9 cita como
                                # ejemplo: un lote puede acabar en `Anulada_Administracion`
                                # habiendo pasado por `Presentada`. Hasta ahora el estado
                                # anterior se perdía aquí, y con él la prueba de que hubo
                                # negocio invertido.
                                anexar_log_cambios(
                                    cursor, exp_id,
                                    entrada_log_cambio_estado(
                                        lote_numero, estado_op, ESTADO_ANULADA_ADMINISTRACION, autor="radar"
                                    )
                                )

    # =====================================================================
    # MÉTODOS DAO - ACTUALIZACIONES MANUALES POR EL EQUIPO
    # =====================================================================

    def actualizar_estado_lote(self, expediente_id: str, lote_numero: int, estado: str) -> None:
        """
        Actualiza el estado operativo comercial de un lote específico por el usuario.
        Aplica normalización higiénica en minúsculas y sin espacios.

        Deja rastro del cambio en `expedientes.log_cambios` (H-31). No es cosmético: es la
        única evidencia de que alguien invirtió criterio en este lote, y de ella depende la
        invariante que impide eliminar memoria comercial.
        """
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        estado_clean = normalizar_estado_operativo(estado)
        with self.conectar() as conn:
            with conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT estado_operativo FROM lotes WHERE expediente_id = ? AND lote_numero = ?;",
                    (expediente_id, lote_numero)
                )
                fila = cursor.fetchone()
                estado_anterior = fila[0] if fila else None

                cursor.execute(
                    "UPDATE lotes SET estado_operativo = ?, updated_by = 'user', updated_at = ? WHERE expediente_id = ? AND lote_numero = ?;",
                    (estado_clean, now_str, expediente_id, lote_numero)
                )

                # Sólo se anota si hubo cambio real: reafirmar el estado actual no es
                # información, y llenaría el histórico de ruido.
                if fila and normalizar_estado_operativo(estado_anterior) != estado_clean:
                    anexar_log_cambios(
                        cursor, expediente_id,
                        entrada_log_cambio_estado(lote_numero, estado_anterior, estado_clean, autor="user")
                    )

    def registrar_costes_CAC(self, expediente_id: str, lote_numero: int, horas: int, costes_externos: float) -> None:
        """
        Registra costes de adquisición (CAC) asociados al estudio/oferta del lote.
        """
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        with self.conectar() as conn:
            with conn:
                conn.execute(
                    "UPDATE lotes SET horas_internas_invertidas = ?, costes_externos = ?, updated_by = 'user', updated_at = ? WHERE expediente_id = ? AND lote_numero = ?;",
                    (horas, costes_externos, now_str, expediente_id, lote_numero)
                )

    def actualizar_notas_usuario(self, expediente_id: str, lote_numero: int, notas: str) -> None:
        """
        Inserta o actualiza las notas internas redactadas por el equipo de Incoop.
        """
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        with self.conectar() as conn:
            with conn:
                conn.execute(
                    "UPDATE lotes SET notas_usuario = ?, updated_by = 'user', updated_at = ? WHERE expediente_id = ? AND lote_numero = ?;",
                    (notas.strip(), now_str, expediente_id, lote_numero)
                )

    def registrar_cierre_adjudicacion(self, expediente_id: str, lote_numero: int, empresa: str, importe: float, dinero_mesa: float) -> None:
        """
        Registra la información de cierre tras la adjudicación (inteligencia competitiva).
        Aplica normalización higiénica al adjudicatario.
        """
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        empresa_clean = empresa.strip().lower() if empresa else None
        with self.conectar() as conn:
            with conn:
                conn.execute(
                    "UPDATE lotes SET empresa_adjudicataria = ?, importe_adjudicacion = ?, dinero_en_la_mesa = ?, updated_by = 'user', updated_at = ? WHERE expediente_id = ? AND lote_numero = ?;",
                    (empresa_clean, importe, dinero_mesa, now_str, expediente_id, lote_numero)
                )

    def registrar_garantia(self, expediente_id: str, lote_numero: int, importe_garantia: float, fecha_devolucion: str) -> None:
        """
        Registra el importe de aval definitivo depositado y la fecha estimada de retorno (Working Capital).
        Valida estrictamente que la fecha cumpla con el formato ISO 'YYYY-MM-DD'.
        """
        if fecha_devolucion and fecha_devolucion != "N/A":
            try:
                datetime.strptime(fecha_devolucion.strip(), "%Y-%m-%d")
            except ValueError:
                raise ValueError(
                    f"Formato de fecha de devolución '{fecha_devolucion}' inválido. "
                    "Debe cumplir estrictamente con el formato ISO 'YYYY-MM-DD'."
                )
                
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        with self.conectar() as conn:
            with conn:
                conn.execute(
                    "UPDATE lotes SET importe_garantia_retenida = ?, fecha_devolucion_garantia = ?, updated_by = 'user', updated_at = ? WHERE expediente_id = ? AND lote_numero = ?;",
                    (importe_garantia, fecha_devolucion.strip(), now_str, expediente_id, lote_numero)
                )

    def registrar_log_json(self, run_id: int, action: str, expediente_id: Optional[str] = None, reason: Optional[str] = None, duration_ms: Optional[int] = None, updated_by: str = "radar") -> None:
        """
        Registra un evento clave en formato JSON Lines (JSONL) en data/pipeline.jsonl para auditoría y observabilidad.
        """
        log_dir = os.path.dirname(self.db_path)
        if not log_dir:
            log_dir = ruta_datos()
        if not os.path.exists(log_dir):
            os.makedirs(log_dir, exist_ok=True)
        log_path = os.path.join(log_dir, "pipeline.jsonl")
        
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        log_entry = {
            "timestamp": timestamp,
            "run_id": run_id,
            "action": action,
            "updated_by": updated_by
        }
        if expediente_id:
            log_entry["expediente_id"] = expediente_id
        if reason:
            log_entry["reason"] = reason
        if duration_ms is not None:
            log_entry["duration_ms"] = duration_ms
            
        try:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
        except Exception as e:
            print(f"[!] Error al escribir log estructurado JSONL: {e}")

    def upsert_oportunidades_batch(self, oportunidades: List[tuple], run_id: int, batch_size: int = 200) -> Dict[str, int]:
        """
        Ingesta de forma eficiente un conjunto de licitaciones y evaluaciones en chunks/lotes,
        evitando abrir y cerrar conexiones SQLite por cada elemento.
        Devuelve métricas de hits, misses y errores.
        """
        # `nuevos` y `actualizados` desglosan los misses: un miss es una escritura, pero no
        # es lo mismo descubrir un expediente que ver cambiar uno que ya se conocía. Los
        # hits no son ninguna de las dos cosas —el hash coincide, no ha cambiado nada—, así
        # que no se suman a ningún lado. Alimentan las métricas de `ejecuciones` (v6).
        estadisticas = {"hits": 0, "misses": 0, "errores": 0, "nuevos": 0, "actualizados": 0}
        if not oportunidades:
            return estadisticas

        timestamp_now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        sql_upsert_expediente = """
        INSERT INTO expedientes (
            id, titulo, organo, localidad, nuts, procedimiento, tipo_contrato,
            urgente, fuente, link, fecha_publicacion, fecha_limite, fecha_ingesta,
            alerta_modificacion, log_cambios, last_seen_feed, feed_hash
        ) VALUES (
            :id, :titulo, :organo, :localidad, :nuts, :procedimiento, :tipo_contrato,
            :urgente, :fuente, :link, :fecha_publicacion, :fecha_limite, :last_seen_feed,
            :alerta_modificacion, :log_cambios, :last_seen_feed, :feed_hash
        ) ON CONFLICT(id) DO UPDATE SET
            titulo = excluded.titulo,
            organo = excluded.organo,
            localidad = excluded.localidad,
            nuts = excluded.nuts,
            procedimiento = excluded.procedimiento,
            tipo_contrato = excluded.tipo_contrato,
            urgente = excluded.urgente,
            link = excluded.link,
            fecha_publicacion = excluded.fecha_publicacion,
            fecha_limite = excluded.fecha_limite,
            alerta_modificacion = excluded.alerta_modificacion,
            log_cambios = excluded.log_cambios,
            last_seen_feed = excluded.last_seen_feed,
            feed_hash = excluded.feed_hash;
        """

        sql_upsert_lote = """
        INSERT INTO lotes (
            expediente_id, lote_numero, titulo_lote, cpvs, pbl, vec,
            garantia_definitiva, subrogacion, revision_precios, dias_restantes,
            score_total, motivos_scoring, sector, prioridad, pmp_dias, ratio_prorrogas,
            version_scoring, updated_by, updated_at
        ) VALUES (
            :expediente_id, :lote_numero, :titulo_lote, :cpvs, :pbl, :vec,
            :garantia_definitiva, :subrogacion, :revision_precios, :dias_restantes,
            :score_total, :motivos_scoring, :sector, :prioridad, :pmp_dias, :ratio_prorrogas,
            :version_scoring, :updated_by, :updated_at
        ) ON CONFLICT(expediente_id, lote_numero) DO UPDATE SET
            titulo_lote = excluded.titulo_lote,
            cpvs = excluded.cpvs,
            pbl = excluded.pbl,
            vec = excluded.vec,
            garantia_definitiva = excluded.garantia_definitiva,
            subrogacion = excluded.subrogacion,
            revision_precios = excluded.revision_precios,
            dias_restantes = excluded.dias_restantes,
            score_total = excluded.score_total,
            motivos_scoring = excluded.motivos_scoring,
            sector = excluded.sector,
            prioridad = excluded.prioridad,
            pmp_dias = excluded.pmp_dias,
            ratio_prorrogas = excluded.ratio_prorrogas,
            version_scoring = excluded.version_scoring,
            updated_by = excluded.updated_by,
            updated_at = excluded.updated_at;
        """

        # Procesar en chunks
        for idx in range(0, len(oportunidades), batch_size):
            chunk = oportunidades[idx:idx + batch_size]
            
            with self.conectar() as conn:
                with conn: # Transacción atómica corta por chunk
                    cursor = conn.cursor()
                    
                    for lic, eval_data in chunk:
                        expediente_id = lic.get("id")
                        start_time_perf = time.perf_counter()
                        
                        try:
                            nuevo_hash = calcular_feed_hash(lic)
                            
                            # 1. Recuperar valores previos de la base de datos
                            cursor.execute(
                                "SELECT fecha_limite, log_cambios, alerta_modificacion, feed_hash FROM expedientes WHERE id = ?;",
                                (expediente_id,)
                            )
                            row_exp = cursor.fetchone()
                            
                            existe_previo = False
                            hash_previo = None
                            fecha_limite_previa = None
                            log_cambios_previo = ""
                            alerta_modificacion_previa = 0
                            vec_previo = None
                            estado_operativo_previo = "Nueva"
                            
                            if row_exp:
                                existe_previo = True
                                fecha_limite_previa, log_cambios_previo, alerta_modificacion_previa, hash_previo = row_exp
                                if log_cambios_previo is None:
                                    log_cambios_previo = ""

                                cursor.execute(
                                    "SELECT vec, estado_operativo FROM lotes WHERE expediente_id = ? AND lote_numero = 1;",
                                    (expediente_id,)
                                )
                                row_lote = cursor.fetchone()
                                if row_lote:
                                    vec_previo, estado_operativo_previo = row_lote
                            
                            duration_ms = int((time.perf_counter() - start_time_perf) * 1000)
                            
                            # Caso Optimización: El hash coincide (Hit)
                            if existe_previo and hash_previo == nuevo_hash:
                                cursor.execute(
                                    "UPDATE expedientes SET last_seen_feed = ? WHERE id = ?;",
                                    (timestamp_now, expediente_id)
                                )
                                estadisticas["hits"] += 1
                                self.registrar_log_json(
                                    run_id=run_id, action="upsert_hit", expediente_id=expediente_id,
                                    reason="hash_identical", duration_ms=duration_ms
                                )
                                continue

                            # Caso Escritura: El hash difiere o es nueva (Miss)
                            fecha_pub_utc = normalizar_fecha_utc(lic.get("fecha_publicacion", ""))
                            fecha_lim_utc = normalizar_fecha_utc(lic.get("fecha_limite", ""))

                            alerta_modificacion = alerta_modificacion_previa
                            log_cambios = log_cambios_previo
                            
                            if existe_previo:
                                cambios = []
                                fl_prev_utc = normalizar_fecha_utc(fecha_limite_previa)
                                if fl_prev_utc != "N/A" and fecha_lim_utc != "N/A" and fl_prev_utc != fecha_lim_utc:
                                    cambios.append(f"Fecha límite modificada de {fl_prev_utc} a {fecha_lim_utc}")
                                
                                vec_nuevo = float(lic.get("vec", 0.0))
                                if vec_previo is not None and abs(vec_previo - vec_nuevo) > 0.01:
                                    cambios.append(f"VEC modificado de {vec_previo:,.2f} EUR a {vec_nuevo:,.2f} EUR")
                                
                                if cambios and estado_operativo_previo.lower() != "nueva":
                                    alerta_modificacion = 1
                                    timestamp_log = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
                                    entrada_log = f"[{timestamp_log}] [radar] " + " | ".join(cambios)
                                    log_cambios = log_cambios + "\n" + entrada_log if log_cambios else entrada_log

                            cpvs_serialized = ",".join(lic.get("cpvs", []))
                            motivos_serialized = " | ".join(eval_data.get("motivos", []))

                            datos_expediente = {
                                "id": expediente_id,
                                "titulo": lic.get("titulo"),
                                "organo": lic.get("organo"),
                                "localidad": lic.get("localidad"),
                                "nuts": lic.get("country_subentity_code"),
                                "procedimiento": lic.get("procedimiento_codigo"),
                                "tipo_contrato": lic.get("tipo_contrato_codigo"),
                                "urgente": 1 if lic.get("urgente") else 0,
                                "fuente": lic.get("fuente"),
                                "link": lic.get("link"),
                                "fecha_publicacion": fecha_pub_utc,
                                "fecha_limite": fecha_lim_utc,
                                "alerta_modificacion": alerta_modificacion,
                                "log_cambios": log_cambios,
                                "last_seen_feed": timestamp_now,
                                "feed_hash": nuevo_hash
                            }

                            datos_lote = {
                                "expediente_id": expediente_id,
                                "lote_numero": 1,
                                "titulo_lote": lic.get("titulo"),
                                "cpvs": cpvs_serialized,
                                "pbl": lic.get("importe", 0.0),
                                "vec": lic.get("vec", 0.0),
                                "garantia_definitiva": eval_data.get("garantia_estimada", 0.0),
                                "subrogacion": 1 if eval_data.get("subrogacion_detectada") else 0,
                                "revision_precios": 1 if eval_data.get("revision_precios_detectada") else 0,
                                "dias_restantes": eval_data.get("dias_restantes"),
                                "score_total": eval_data.get("score", 0),
                                "motivos_scoring": motivos_serialized,
                                "sector": eval_data.get("sector_detectado"),
                                "prioridad": eval_data.get("prioridad", "Media"),
                                "pmp_dias": eval_data.get("pmp_detectado", 30),
                                "ratio_prorrogas": eval_data.get("ratio_prorrogas", 1.0),
                                "version_scoring": eval_data.get("version_scoring"),
                                "updated_by": "radar",
                                "updated_at": timestamp_now
                            }

                            cursor.execute(sql_upsert_expediente, datos_expediente)
                            cursor.execute(sql_upsert_lote, datos_lote)
                            
                            duration_ms = int((time.perf_counter() - start_time_perf) * 1000)
                            estadisticas["misses"] += 1
                            estadisticas["actualizados" if existe_previo else "nuevos"] += 1
                            self.registrar_log_json(
                                run_id=run_id, action="upsert_miss", expediente_id=expediente_id,
                                reason="hash_changed" if existe_previo else "new_expediente",
                                duration_ms=duration_ms
                            )

                        except Exception as e:
                            estadisticas["errores"] += 1
                            duration_ms = int((time.perf_counter() - start_time_perf) * 1000)
                            self.registrar_log_json(
                                run_id=run_id, action="upsert_error", expediente_id=expediente_id,
                                reason=str(e), duration_ms=duration_ms
                            )
                            print(f"[!] Error al ingestar expediente {expediente_id}: {e}")

        return estadisticas

    # =====================================================================
    # SISTEMA DE COPÌAS DE SEGURIDAD EN CALIENTE (BACKUP API) Y CATÁLOGO
    # =====================================================================

    def realizar_backup(self, run_id: int, custom_dest_dir: Optional[str] = None) -> str:
        """
        Realiza una copia de seguridad atómica en caliente utilizando la API .backup() de SQLite.
        Utiliza una extensión temporal (.tmp) y renombra atómicamente a (.bak) tras pasar un Smoke Test de consistencia.
        Genera checksum SHA256 y registra la entrada en backups_catalog.jsonl.
        """
        start_time = time.perf_counter()
        
        # 1. Definir rutas y directorios
        db_dir = os.path.dirname(self.db_path)
        if not db_dir:
            db_dir = ruta_datos()
        backups_dir = os.path.join(db_dir, "backups") if not custom_dest_dir else custom_dest_dir
        
        os.makedirs(backups_dir, exist_ok=True)
        
        now_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        final_filename = f"licitaciones_{now_str}.db.bak"
        tmp_filename = f"licitaciones_{now_str}.db.tmp"
        
        final_path = os.path.join(backups_dir, final_filename)
        tmp_path = os.path.join(backups_dir, tmp_filename)
        
        # 2. Comprobar espacio libre defensivo (Debe haber al menos 2x del tamaño de la base de datos libre)
        if os.path.exists(self.db_path):
            db_size = os.path.getsize(self.db_path)
            # shutil.disk_usage devuelve (total, used, free)
            try:
                free_space = shutil.disk_usage(backups_dir).free
                if free_space < (db_size * 2):
                    raise IOError(
                        f"Espacio en disco insuficiente para el backup. "
                        f"Requerido estimado: {db_size * 2} bytes | Libre disponible: {free_space} bytes."
                    )
            except Exception as e:
                if isinstance(e, IOError):
                    raise e
                # Si falla shutil.disk_usage (por ej. en algunos entornos acotados), procedemos con precaución
                pass
        
        # 3. Realizar backup atómico al archivo temporal (.tmp)
        conn_dst = None
        try:
            with self.conectar() as conn_src:
                conn_dst = sqlite3.connect(tmp_path, timeout=30.0)
                conn_dst.execute("PRAGMA busy_timeout=30000;")
                # Volcado nativo
                conn_src.backup(conn_dst)
                conn_dst.close()
                conn_dst = None
                
            # 4. Smoke Test de Consistencia: Abrir el temporal en modo Lectura y validar
            conn_test = sqlite3.connect(tmp_path, timeout=30.0)
            conn_test.execute("PRAGMA busy_timeout=30000;")
            cursor_test = conn_test.cursor()
            try:
                cursor_test.execute("SELECT COUNT(*) FROM expedientes;")
                conteo_exp = cursor_test.fetchone()[0]
                cursor_test.execute("SELECT COUNT(*) FROM lotes;")
                conteo_lotes = cursor_test.fetchone()[0]
                # Validar lectura de vistas
                cursor_test.execute("SELECT * FROM vista_win_rate;")
                cursor_test.fetchone()
            except Exception as e_smoke:
                raise ValueError(f"Smoke Test fallido sobre el backup temporal: {e_smoke}")
            finally:
                conn_test.close()
                
            # 5. Renombrado atómico a (.bak)
            if os.path.exists(final_path):
                os.remove(final_path)
            os.rename(tmp_path, final_path)
            
            # 6. Calcular Checksum SHA256 del archivo definitivo
            sha256_hash = hashlib.sha256()
            with open(final_path, "rb") as f_bytes:
                for byte_block in iter(lambda: f_bytes.read(4096), b""):
                    sha256_hash.update(byte_block)
            checksum = sha256_hash.hexdigest()
            
            duration_ms = int((time.perf_counter() - start_time) * 1000)
            size_bytes = os.path.getsize(final_path)
            
            # 7. Catalogar el backup en backups_catalog.jsonl
            catalog_path = os.path.join(backups_dir, "backups_catalog.jsonl")
            timestamp_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            
            catalog_entry = {
                "timestamp": timestamp_iso,
                "run_id": run_id,
                "file_path": final_path,
                "file_name": final_filename,
                "checksum_sha256": checksum,
                "size_bytes": size_bytes,
                "duration_ms": duration_ms,
                "status": "success",
                "user": "radar"
            }
            
            with open(catalog_path, "a", encoding="utf-8") as f_cat:
                f_cat.write(json.dumps(catalog_entry, ensure_ascii=False) + "\n")
                
            self.registrar_log_json(
                run_id=run_id, action="backup_success",
                reason=f"File: {final_filename} | Checksum: {checksum[:8]}...",
                duration_ms=duration_ms
            )
            return final_path
            
        except Exception as e:
            # En caso de error, limpiar temporal si existiera
            if os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass
            self.registrar_log_json(
                run_id=run_id, action="backup_failed",
                reason=str(e), duration_ms=int((time.perf_counter() - start_time) * 1000)
            )
            raise e
        finally:
            if conn_dst:
                try:
                    conn_dst.close()
                except Exception:
                    pass

    def rotar_backups(self, custom_dest_dir: Optional[str] = None, dias_retencion: int = 7) -> int:
        """
        Escanea el directorio de backups, elimina físicamente los archivos .bak con antigüedad
        superior a los días de retención y limpia su historial del catálogo de forma atómica.
        """
        db_dir = os.path.dirname(self.db_path)
        if not db_dir:
            db_dir = ruta_datos()
        backups_dir = os.path.join(db_dir, "backups") if not custom_dest_dir else custom_dest_dir
        
        if not os.path.exists(backups_dir):
            return 0
            
        ahora_utc = datetime.now(timezone.utc)
        limite_tiempo = ahora_utc - timedelta(days=dias_retencion)
        
        archivos_eliminados = []
        purgados = 0
        
        # 1. Escanear directorio buscando archivos que sigan el patrón licitaciones_*.db.bak
        for filename in os.listdir(backups_dir):
            if filename.startswith("licitaciones_") and filename.endswith(".db.bak"):
                file_path = os.path.join(backups_dir, filename)
                
                # Parsear fecha desde el nombre del archivo (licitaciones_YYYYMMDD_HHMMSS.db.bak)
                partes = filename.split("_")
                if len(partes) >= 3:
                    fecha_str = partes[1] # YYYYMMDD
                    hora_str = partes[2].split(".")[0] # HHMMSS
                    try:
                        file_dt = datetime.strptime(f"{fecha_str}_{hora_str}", "%Y%m%d_%H%M%S").replace(tzinfo=timezone.utc)
                        if file_dt < limite_tiempo:
                            # Eliminar archivo físico
                            if os.path.exists(file_path):
                                os.remove(file_path)
                            archivos_eliminados.append(filename)
                            purgados += 1
                    except Exception:
                        pass
                        
        # 2. Limpiar atómicamente el catálogo backups_catalog.jsonl
        catalog_path = os.path.join(backups_dir, "backups_catalog.jsonl")
        if os.path.exists(catalog_path) and archivos_eliminados:
            tmp_catalog_path = catalog_path + ".tmp"
            try:
                # Leer catálogo y descartar líneas obsoletas
                lineas_conservar = []
                with open(catalog_path, "r", encoding="utf-8") as f_cat:
                    for line in f_cat:
                        if line.strip():
                            data = json.loads(line.strip())
                            if data.get("file_name") not in archivos_eliminados:
                                lineas_conservar.append(line)
                                
                # Escribir atómicamente en archivo temporal y renombrar
                with open(tmp_catalog_path, "w", encoding="utf-8") as f_tmp:
                    for line in lineas_conservar:
                        f_tmp.write(line)
                        
                os.replace(tmp_catalog_path, catalog_path)
            except Exception as e:
                # Limpiar temporal si falló
                if os.path.exists(tmp_catalog_path):
                    try:
                        os.remove(tmp_catalog_path)
                    except Exception:
                        pass
    def registrar_documento_detectado(self, expediente_id: str, doc: Dict[str, Any]) -> bool:
        """
        Registra un documento detectado por el radar en la base de datos (esquema v3).
        Evita la regresión de estado (no sobrescribe si el documento ya está descargado/procesado).
        Devuelve True si se insertó o actualizó en estado DETECTADO, False en caso contrario.
        """
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        
        sql = """
        INSERT INTO documentos (
            expediente_id, titulo, url, tipo, hash_documento, estado, updated_at
        ) VALUES (
            :expediente_id, :titulo, :url, :tipo, :hash_documento, 'DETECTADO', :updated_at
        ) ON CONFLICT(expediente_id, hash_documento) DO UPDATE SET
            url = excluded.url,
            updated_at = excluded.updated_at
        WHERE documentos.estado IN ('DETECTADO', 'ERROR_DESCARGA');
        """
        
        params = {
            "expediente_id": expediente_id,
            "titulo": doc["titulo"].strip(),
            "url": doc["url"].strip(),
            "tipo": doc["tipo"].strip(),
            "hash_documento": doc["hash"].strip(),
            "updated_at": now_str
        }
        
        with self.db_lock():
            with self.conectar() as conn:
                with conn:
                    cursor = conn.cursor()
                    cursor.execute(sql, params)
                    return cursor.rowcount > 0

    def obtener_documentos_pendientes(self) -> List[Dict[str, Any]]:
        """
        Devuelve los documentos que están en estado DETECTADO o ERROR_DESCARGA con intentos < 3.
        """
        sql = """
        SELECT id, expediente_id, titulo, url, tipo, hash_documento, intentos
        FROM documentos
        WHERE estado IN ('DETECTADO', 'ERROR_DESCARGA') AND intentos < 3;
        """
        with self.conectar() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(sql)
            return [dict(row) for row in cursor.fetchall()]

    def actualizar_estado_documento(self, doc_id: int, estado: str, error_detalle: Optional[str] = None) -> None:
        """
        Actualiza genéricamente el estado de un documento en la base de datos de forma segura.
        """
        sql = """
        UPDATE documentos
        SET estado = ?, error_detalle = ?, updated_at = ?
        WHERE id = ?;
        """
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        with self.db_lock():
            with self.conectar() as conn:
                with conn:
                    conn.execute(sql, (estado, error_detalle, now_str, doc_id))

    def registrar_descarga_exitosa(self, doc_id: int, local_path: str, sha256: str, mida_bytes: int) -> None:
        """
        Registra la descarga física exitosa de un documento.
        """
        sql = """
        UPDATE documentos
        SET estado = 'DESCARGADO', local_path = ?, sha256 = ?, mida_bytes = ?, intentos = intentos + 1, error_detalle = NULL, updated_at = ?
        WHERE id = ?;
        """
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        with self.db_lock():
            with self.conectar() as conn:
                with conn:
                    conn.execute(sql, (local_path, sha256, mida_bytes, now_str, doc_id))

    def registrar_intento_fallido(self, doc_id: int, error_detalle: str, intentos: int) -> None:
        """
        Registra un intento de descarga fallido e incrementa el contador.
        """
        sql = """
        UPDATE documentos
        SET estado = 'ERROR_DESCARGA', intentos = ?, last_attempt_at = ?, error_detalle = ?, updated_at = ?
        WHERE id = ?;
        """
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        with self.db_lock():
            with self.conectar() as conn:
                with conn:
                    conn.execute(sql, (intentos, now_str, error_detalle, now_str, doc_id))

    def documento_sha256_existe(self, sha256: str, excluir_id: int) -> bool:
        """
        Comprueba si ya existe otro documento en estado DESCARGADO con el mismo sha256.
        """
        sql = """
        SELECT id FROM documentos
        WHERE sha256 = ? AND id != ? AND estado = 'DESCARGADO';
        """
        with self.conectar() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, (sha256, excluir_id))
            return cursor.fetchone() is not None

    def obtener_documento_descargado_por_hash_feed(self, hash_documento: str) -> Optional[Dict[str, Any]]:
        """
        Busca si ya existe algún documento en estado DESCARGADO que tenga el mismo hash_documento original del feed.
        Permite la pre-deduplicación directa sin llamar a internet.
        """
        sql = """
        SELECT local_path, sha256, mida_bytes
        FROM documentos
        WHERE hash_documento = ? AND estado = 'DESCARGADO' AND local_path IS NOT NULL
        LIMIT 1;
        """
        with self.conectar() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(sql, (hash_documento,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def obtener_documentos_para_purga(self, dias_retencion: int) -> List[Dict[str, Any]]:
        """
        Busca documentos descargados asociados a expedientes inactivos (lotes inactivos)
        o cuya fecha de ingesta supere los dias_retencion establecidos.
        """
        sql = """
        SELECT d.id, d.local_path, d.titulo
        FROM documentos d
        JOIN expedientes e ON d.expediente_id = e.id
        WHERE d.estado = 'DESCARGADO' AND d.local_path IS NOT NULL
          AND (
            NOT EXISTS (
              SELECT 1 FROM lotes l
              -- LOWER() y no el literal: hasta v6 convivieron dos grafías del mismo
              -- estado (H-27), y esta consulta dependía de que el Radar escribiera en
              -- minúsculas. Comparar normalizado la hace indiferente a la grafía
              -- almacenada, también en bases migradas desde v5.
              WHERE l.expediente_id = e.id
                AND LOWER(l.estado_operativo) NOT IN ('inactiva', 'anulada_administracion')
            )
            OR datetime(e.fecha_ingesta) <= datetime('now', ?)
          );
        """
        # Formato de modificador de tiempo para SQLite: '-90 days'
        modifier = f"-{dias_retencion} days"
        with self.conectar() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(sql, (modifier,))
            return [dict(row) for row in cursor.fetchall()]

    def marcar_documentos_como_purgados(self, doc_ids: List[int]) -> None:
        """
        Pasa el estado de los documentos a PURGADO y limpia sus rutas físicas y metadatos de almacenamiento.
        """
        if not doc_ids:
            return
            
        placeholders = ",".join("?" for _ in doc_ids)
        sql = f"""
        UPDATE documentos
        SET estado = 'PURGADO', local_path = NULL, error_detalle = 'PURGADO_HISTORICO', updated_at = ?
        WHERE id IN ({placeholders});
        """
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        with self.db_lock():
            with self.conectar() as conn:
                with conn:
                    conn.execute(sql, [now_str] + doc_ids)

    def obtener_documentos_para_extraccion(self) -> List[Dict[str, Any]]:
        """
        Devuelve los documentos que están en estado DESCARGADO y tienen local_path válido en disco.
        """
        sql = """
        SELECT id, expediente_id, titulo, url, tipo, local_path, sha256
        FROM documentos
        WHERE estado = 'DESCARGADO' AND local_path IS NOT NULL;
        """
        with self.conectar() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(sql)
            return [dict(row) for row in cursor.fetchall()]

    def guardar_resultado_extraccion_texto(
        self,
        doc_id: int,
        estado: str,
        texto_extraido: Optional[str],
        metodo: str,
        idioma: Optional[str],
        version_reglas: int,
        error_detalle: Optional[str] = None
    ) -> None:
        """
        Guarda los resultados de la extracción de texto nativo (PyMuPDF) u OCR en la base de datos.
        """
        sql = """
        UPDATE documentos
        SET estado = ?, texto_extraido = ?, metodo_extraccion = ?, idioma = ?, version_reglas = ?, error_detalle = ?, updated_at = ?
        WHERE id = ?;
        """
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        with self.db_lock():
            with self.conectar() as conn:
                with conn:
                    conn.execute(sql, (estado, texto_extraido, metodo, idioma, version_reglas, error_detalle, now_str, doc_id))

    def obtener_documentos_para_ocr(self) -> List[Dict[str, Any]]:
        """
        Devuelve los documentos que están en estado OCR_REQUERIDO y tienen local_path válido en disco.
        """
        sql = """
        SELECT id, expediente_id, titulo, url, tipo, local_path, sha256, texto_extraido
        FROM documentos
        WHERE estado = 'OCR_REQUERIDO' AND local_path IS NOT NULL;
        """
        with self.conectar() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(sql)
            return [dict(row) for row in cursor.fetchall()]

    # =====================================================================
    # MÉTODOS DAO - ANÁLISIS SEMÁNTICO DE LICITACIONES (ESQUEMA v4)
    # =====================================================================

    def guardar_analisis_semantico(
        self,
        expediente_id: str,
        dto: Any,
        metadatos: Optional[Dict[str, Any]] = None,
        run_id: Optional[int] = None
    ) -> bool:
        """
        Guarda o actualiza de forma atómica y determinista el análisis semántico de una licitación en SQLite (Esquema v4).
        Registra el evento correspondiente en data/pipeline.jsonl.
        """
        if metadatos is None:
            metadatos = {}

        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        # Serialización de campos DTO
        criterios_desglose_json = json.dumps(getattr(dto.criterios, "criterios_desglose", []), ensure_ascii=False)
        dictamen_motivos_json = json.dumps(getattr(dto.dictamen, "motivos", []), ensure_ascii=False)
        raw_dto_json = dto.to_json() if hasattr(dto, "to_json") else json.dumps(dto, ensure_ascii=False)

        datos = {
            "expediente_id": expediente_id,
            "subrogacion_detectada": 1 if getattr(dto.subrogacion, "detectada", False) else 0,
            "subrogacion_num_trabajadores": getattr(dto.subrogacion, "num_trabajadores", None),
            "subrogacion_convenio": getattr(dto.subrogacion, "convenio_colectivo", None),
            "subrogacion_desglose_completo": 1 if getattr(dto.subrogacion, "desglose_salarial_completo", False) else 0,
            "subrogacion_coste_anual": getattr(dto.subrogacion, "coste_estimado_anual", None),
            "subrogacion_riesgo": getattr(dto.subrogacion, "riesgo_evaluado", "MEDIO"),
            "revision_precios_permitida": 1 if getattr(dto.revision_precios, "permitida", False) else 0,
            "revision_precios_formula": getattr(dto.revision_precios, "formula_detectada", None),
            "revision_precios_art_103": 1 if getattr(dto.revision_precios, "art_103_aplica", False) else 0,
            "revision_precios_obs": getattr(dto.revision_precios, "observaciones", None),
            "criterios_peso_formulas": getattr(dto.criterios, "peso_precio_formulas", 50),
            "criterios_peso_juicio_valor": getattr(dto.criterios, "peso_juicio_valor", 50),
            "criterios_requiere_memoria": 1 if getattr(dto.criterios, "requiere_memoria_tecnica", True) else 0,
            "criterios_desglose_json": criterios_desglose_json,
            "dictamen_recomendacion": getattr(dto.dictamen, "recomendacion", "REVISAR_RIESGO"),
            "dictamen_motivos_json": dictamen_motivos_json,
            "dictamen_ajuste_score": getattr(dto.dictamen, "ajuste_score", 0),
            "dictamen_resumen": getattr(dto.dictamen, "resumen_ejecutivo", ""),
            "raw_dto_json": raw_dto_json,
            "version_esquema": getattr(dto, "version_esquema", 1),
            "modelo_llm": str(metadatos.get("modelo_llm", "desconocido")),
            "prompt_tokens": int(metadatos.get("prompt_tokens", 0)),
            "completion_tokens": int(metadatos.get("completion_tokens", 0)),
            "tiempo_procesamiento_seg": float(metadatos.get("tiempo_procesamiento_seg", 0.0)),
            "estado_analisis": str(metadatos.get("estado_analisis", "COMPLETADO")).upper(),
            "error_detalle": str(metadatos.get("error_detalle")) if metadatos.get("error_detalle") else None,
            "updated_at": now_str
        }

        sql = """
        INSERT INTO analisis_semantico (
            expediente_id, subrogacion_detectada, subrogacion_num_trabajadores, subrogacion_convenio,
            subrogacion_desglose_completo, subrogacion_coste_anual, subrogacion_riesgo,
            revision_precios_permitida, revision_precios_formula, revision_precios_art_103, revision_precios_obs,
            criterios_peso_formulas, criterios_peso_juicio_valor, criterios_requiere_memoria, criterios_desglose_json,
            dictamen_recomendacion, dictamen_motivos_json, dictamen_ajuste_score, dictamen_resumen,
            raw_dto_json, version_esquema, modelo_llm, prompt_tokens, completion_tokens,
            tiempo_procesamiento_seg, estado_analisis, error_detalle, created_at, updated_at
        ) VALUES (
            :expediente_id, :subrogacion_detectada, :subrogacion_num_trabajadores, :subrogacion_convenio,
            :subrogacion_desglose_completo, :subrogacion_coste_anual, :subrogacion_riesgo,
            :revision_precios_permitida, :revision_precios_formula, :revision_precios_art_103, :revision_precios_obs,
            :criterios_peso_formulas, :criterios_peso_juicio_valor, :criterios_requiere_memoria, :criterios_desglose_json,
            :dictamen_recomendacion, :dictamen_motivos_json, :dictamen_ajuste_score, :dictamen_resumen,
            :raw_dto_json, :version_esquema, :modelo_llm, :prompt_tokens, :completion_tokens,
            :tiempo_procesamiento_seg, :estado_analisis, :error_detalle, :updated_at, :updated_at
        ) ON CONFLICT(expediente_id) DO UPDATE SET
            subrogacion_detectada = excluded.subrogacion_detectada,
            subrogacion_num_trabajadores = excluded.subrogacion_num_trabajadores,
            subrogacion_convenio = excluded.subrogacion_convenio,
            subrogacion_desglose_completo = excluded.subrogacion_desglose_completo,
            subrogacion_coste_anual = excluded.subrogacion_coste_anual,
            subrogacion_riesgo = excluded.subrogacion_riesgo,
            revision_precios_permitida = excluded.revision_precios_permitida,
            revision_precios_formula = excluded.revision_precios_formula,
            revision_precios_art_103 = excluded.revision_precios_art_103,
            revision_precios_obs = excluded.revision_precios_obs,
            criterios_peso_formulas = excluded.criterios_peso_formulas,
            criterios_peso_juicio_valor = excluded.criterios_peso_juicio_valor,
            criterios_requiere_memoria = excluded.criterios_requiere_memoria,
            criterios_desglose_json = excluded.criterios_desglose_json,
            dictamen_recomendacion = excluded.dictamen_recomendacion,
            dictamen_motivos_json = excluded.dictamen_motivos_json,
            dictamen_ajuste_score = excluded.dictamen_ajuste_score,
            dictamen_resumen = excluded.dictamen_resumen,
            raw_dto_json = excluded.raw_dto_json,
            version_esquema = excluded.version_esquema,
            modelo_llm = excluded.modelo_llm,
            prompt_tokens = excluded.prompt_tokens,
            completion_tokens = excluded.completion_tokens,
            tiempo_procesamiento_seg = excluded.tiempo_procesamiento_seg,
            estado_analisis = excluded.estado_analisis,
            error_detalle = excluded.error_detalle,
            updated_at = excluded.updated_at;
        """

        with self.db_lock():
            with self.conectar() as conn:
                with conn:
                    conn.execute(sql, datos)

        rec_val = getattr(dto.dictamen, "recomendacion", "N/A") if hasattr(dto, "dictamen") else "N/A"
        self.registrar_log_json(
            run_id=run_id or 0,
            action="guardar_analisis_semantico",
            expediente_id=expediente_id,
            reason=f"estado:{datos['estado_analisis']}|rec:{rec_val}",
            updated_by="analista_ia"
        )
        return True

    def obtener_analisis_semantico(self, expediente_id: str) -> Optional[Any]:
        """
        Recupera y reconstruye una instancia de AnalisisSemanticoDTO para el expediente_id indicado.
        Retorna None si no existe análisis registrado.
        """
        from src.analista import AnalisisSemanticoDTO
        sql = "SELECT raw_dto_json FROM analisis_semantico WHERE expediente_id = ?;"
        with self.conectar() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, (expediente_id,))
            row = cursor.fetchone()
            if not row or not row[0]:
                return None
            # Relectura desde BD: tolerante. Un registro histórico corrupto se degrada
            # a un DTO marcado en vez de impedir la lectura del expediente completo.
            return AnalisisSemanticoDTO.from_json(row[0], estricto=False)

    def obtener_analisis_semantico_raw(self, expediente_id: str) -> Optional[Dict[str, Any]]:
        """
        Devuelve el registro completo de la tabla analisis_semantico como un diccionario.
        """
        sql = "SELECT * FROM analisis_semantico WHERE expediente_id = ?;"
        with self.conectar() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(sql, (expediente_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def obtener_datos_completos_expediente(self, expediente_id: str) -> Dict[str, Any]:
        """
        Devuelve el texto ensamblado de los documentos procesados de un expediente,
        junto con su score cuantitativo e información de presupuesto.
        """
        sql_docs = """
        SELECT titulo, texto_extraido, idioma
        FROM documentos
        WHERE expediente_id = ? AND estado = 'PROCESADO' AND texto_extraido IS NOT NULL;
        """
        sql_lote = """
        SELECT e.titulo, l.pbl, l.score_total
        FROM expedientes e
        LEFT JOIN lotes l ON l.expediente_id = e.id
        WHERE e.id = ?;
        """
        with self.conectar() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute(sql_docs, (expediente_id,))
            docs = cursor.fetchall()
            
            cursor.execute(sql_lote, (expediente_id,))
            lote_row = cursor.fetchone()
            
        textos = []
        idiomas = []
        for d in docs:
            txt = d["texto_extraido"] or ""
            if txt.strip():
                textos.append(f"--- DOCUMENTO: {d['titulo']} ---\n{txt}")
                if d["idioma"]:
                    idiomas.append(d["idioma"])

        texto_completo = "\n\n".join(textos)
        idioma_principal = idiomas[0] if idiomas else "es"
        
        score_cuantitativo = float(lote_row["score_total"]) if lote_row and lote_row["score_total"] is not None else 50.0
        titulo = lote_row["titulo"] if lote_row and lote_row["titulo"] else expediente_id
        pbl = float(lote_row["pbl"]) if lote_row and lote_row["pbl"] is not None else 0.0

        return {
            "expediente_id": expediente_id,
            "titulo": titulo,
            "pbl": pbl,
            "texto_pliego": texto_completo,
            "score_cuantitativo": score_cuantitativo,
            "idioma": idioma_principal
        }

    def listar_expedientes_pendientes_analisis(self, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Obtiene los expedientes que tienen documentos en estado 'PROCESADO' (texto extraído/OCR),
        pero que aún no tienen un registro en la tabla analisis_semantico (o cuyo estado es 'PENDIENTE').
        """
        sql = """
        SELECT DISTINCT e.id, e.titulo, e.organo, e.fecha_limite
        FROM expedientes e
        JOIN documentos d ON d.expediente_id = e.id
        LEFT JOIN analisis_semantico a ON a.expediente_id = e.id
        WHERE d.estado = 'PROCESADO'
          AND (a.expediente_id IS NULL OR a.estado_analisis = 'PENDIENTE')
        LIMIT ?;
        """
        with self.conectar() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(sql, (limit,))
            return [dict(row) for row in cursor.fetchall()]

    def healthcheck_memoria(self) -> Dict[str, Any]:
        """
        Ejecuta un autodiagnóstico determinista de la base de datos (Regla 6).
        Verifica conectividad, integridad, versión del esquema y presencia de tablas críticas.
        """
        resultado = {
            "status": "OK",
            "db_path": self.db_path,
            "version_esperada": self.ESQUEMA_VERSION,
            "version_actual": None,
            "quick_check": "FAILED",
            "tablas_detectadas": [],
            "error": None
        }

        try:
            with self.conectar() as conn:
                cursor = conn.cursor()
                cursor.execute("PRAGMA quick_check;")
                qc = cursor.fetchone()
                resultado["quick_check"] = qc[0] if qc else "UNKNOWN"

                cursor.execute("SELECT version FROM metadata LIMIT 1;")
                ver_row = cursor.fetchone()
                resultado["version_actual"] = ver_row[0] if ver_row else 0

                cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
                tablas = [r[0] for r in cursor.fetchall()]
                resultado["tablas_detectadas"] = tablas

                tablas_requeridas = ["metadata", "expedientes", "lotes", "ejecuciones", "documentos", "analisis_semantico", "boletines_alertas"]
                faltantes = [t for t in tablas_requeridas if t not in tablas]

                if faltantes:
                    resultado["status"] = "ERROR"
                    resultado["error"] = f"Tablas requeridas ausentes: {faltantes}"
                elif resultado["version_actual"] != self.ESQUEMA_VERSION:
                    resultado["status"] = "DEGRADADO"
                    resultado["error"] = f"Desfase de esquema: {resultado['version_actual']} vs {self.ESQUEMA_VERSION}"
                elif resultado["quick_check"] != "ok":
                    resultado["status"] = "CORRUPTO"
                    resultado["error"] = f"Fallo en PRAGMA quick_check: {resultado['quick_check']}"

        except Exception as e:
            resultado["status"] = "CRITICAL"
            resultado["error"] = str(e)

        return resultado

    # =====================================================================
    # MÉTODOS DAO — CAPA 6: EL CENTINELA DE BOLETINES
    # =====================================================================

    def guardar_alerta_boletin(self, alerta) -> bool:
        """
        Guarda o actualiza (UPSERT) una alerta de boletín en la tabla boletines_alertas.
        Si la alerta ya existe (mismo id_alerta SHA256), actualiza los datos pero preserva las notas manuales del usuario.
        """
        sql = """
        INSERT INTO boletines_alertas (
            id_alerta, fuente, num_boletin, fecha_publicacion, organo_emisor,
            municipio, titulo_anuncio, seccion_boletin, url_anuncio, url_pdf,
            texto_sumario, score_temprano, motivos_score, categoria_fase_temprana,
            dictamen_ia_json, estado_operativo, expediente_licitacion_vinculado,
            notas_usuario, fecha_ingesta, updated_at
        ) VALUES (
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
        )
        ON CONFLICT(id_alerta) DO UPDATE SET
            fuente = excluded.fuente,
            num_boletin = excluded.num_boletin,
            fecha_publicacion = excluded.fecha_publicacion,
            organo_emisor = excluded.organo_emisor,
            municipio = excluded.municipio,
            titulo_anuncio = excluded.titulo_anuncio,
            seccion_boletin = excluded.seccion_boletin,
            url_anuncio = excluded.url_anuncio,
            url_pdf = excluded.url_pdf,
            texto_sumario = excluded.texto_sumario,
            score_temprano = excluded.score_temprano,
            motivos_score = excluded.motivos_score,
            categoria_fase_temprana = excluded.categoria_fase_temprana,
            dictamen_ia_json = excluded.dictamen_ia_json,
            -- Blindaje de la decisión humana: lo que ha decidido una persona desde el Cockpit
            -- no puede ser sobrescrito por una reejecución del pipeline. DESCARTADA_TEMPRANA
            -- se añade aquí porque, al empezar a persistirse los descartes automáticos, una
            -- alerta rechazada a mano volvería a su estado de reglas en la siguiente pasada.
            estado_operativo = CASE
                WHEN boletines_alertas.estado_operativo IN ('CONVERTIDA_A_LICITACION', 'EN_ESTUDIO_PROACTIVO', 'DESCARTADA_TEMPRANA')
                THEN boletines_alertas.estado_operativo
                ELSE excluded.estado_operativo
            END,
            expediente_licitacion_vinculado = COALESCE(boletines_alertas.expediente_licitacion_vinculado, excluded.expediente_licitacion_vinculado),
            notas_usuario = CASE 
                WHEN boletines_alertas.notas_usuario IS NOT NULL AND boletines_alertas.notas_usuario != '' 
                THEN boletines_alertas.notas_usuario 
                ELSE excluded.notas_usuario 
            END,
            updated_at = excluded.updated_at;
        """
        motivos_str = json.dumps(alerta.motivos_score, ensure_ascii=False) if alerta.motivos_score else "[]"
        dictamen_json = alerta.dictamen_ia.to_json() if alerta.dictamen_ia else None
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        dictamen_categoria = "OTROS"
        if alerta.dictamen_ia and alerta.dictamen_ia.categoria_fase_temprana:
            dictamen_categoria = alerta.dictamen_ia.categoria_fase_temprana

        params = (
            alerta.id_alerta,
            alerta.fuente,
            alerta.num_boletin,
            alerta.fecha_publicacion,
            alerta.organo_emisor,
            alerta.municipio,
            alerta.titulo_anuncio,
            alerta.seccion_boletin,
            alerta.url_anuncio,
            alerta.url_pdf,
            alerta.texto_sumario,
            alerta.score_temprano,
            motivos_str,
            dictamen_categoria,
            dictamen_json,
            alerta.estado_operativo,
            alerta.expediente_licitacion_vinculado,
            alerta.notas_usuario or "",
            alerta.fecha_ingesta,
            now_str
        )

        with self.conectar() as conn:
            with conn:
                conn.execute(sql, params)
        return True

    def obtener_alerta_boletin(self, id_alerta: str):
        """
        Recupera una alerta de boletín por su identificador único (id_alerta SHA256).
        """
        from src.centinela import AlertaBoletinDTO, DictamenCentinelaDTO
        sql = "SELECT * FROM boletines_alertas WHERE id_alerta = ?;"
        with self.conectar() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(sql, (id_alerta,))
            row = cursor.fetchone()
            if not row:
                return None
            
            row_dict = dict(row)
            if row_dict.get("motivos_score"):
                try:
                    row_dict["motivos_score"] = json.loads(row_dict["motivos_score"])
                except Exception:
                    row_dict["motivos_score"] = []
            
            if row_dict.get("dictamen_ia_json"):
                try:
                    row_dict["dictamen_ia"] = DictamenCentinelaDTO.from_json(row_dict["dictamen_ia_json"])
                except Exception:
                    row_dict["dictamen_ia"] = None

            return AlertaBoletinDTO.from_dict(row_dict)

    def listar_alertas_tempranas(
        self,
        estado: Optional[str] = None,
        fuente: Optional[str] = None,
        limite: int = 50,
        incluir_descartadas: bool = False
    ):
        """
        Devuelve una lista de AlertaBoletinDTO filtrada opcionalmente por estado y fuente.

        Las alertas descartadas por reglas se persisten para poder auditarlas y reevaluarlas,
        pero **no forman parte del canal principal**: se excluyen salvo que se pidan por su
        estado explícito o con `incluir_descartadas=True`.
        """
        from src.centinela import AlertaBoletinDTO, DictamenCentinelaDTO
        where_clauses = []
        params = []

        if estado:
            where_clauses.append("estado_operativo = ?")
            params.append(estado)
        elif not incluir_descartadas:
            where_clauses.append("estado_operativo != 'DESCARTADA_POR_REGLAS'")
        if fuente:
            where_clauses.append("fuente = ?")
            params.append(fuente.upper())

        sql = "SELECT * FROM boletines_alertas"
        if where_clauses:
            sql += " WHERE " + " AND ".join(where_clauses)
        sql += " ORDER BY fecha_publicacion DESC LIMIT ?;"
        params.append(limite)

        with self.conectar() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(sql, params)
            rows = cursor.fetchall()
            
            alertas = []
            for r in rows:
                row_dict = dict(r)
                if row_dict.get("motivos_score"):
                    try:
                        row_dict["motivos_score"] = json.loads(row_dict["motivos_score"])
                    except Exception:
                        row_dict["motivos_score"] = []
                if row_dict.get("dictamen_ia_json"):
                    try:
                        row_dict["dictamen_ia"] = DictamenCentinelaDTO.from_json(row_dict["dictamen_ia_json"])
                    except Exception:
                        row_dict["dictamen_ia"] = None
                alertas.append(AlertaBoletinDTO.from_dict(row_dict))
            return alertas

    def vincular_alerta_a_expediente(self, id_alerta: str, expediente_id: str) -> bool:
        """
        Vincular una alerta de boletín a una licitación formal en PSCP/PCSP y transicionar
        su estado a 'CONVERTIDA_A_LICITACION'.
        """
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        sql = """
        UPDATE boletines_alertas 
        SET expediente_licitacion_vinculado = ?,
            estado_operativo = 'CONVERTIDA_A_LICITACION',
            updated_at = ?
        WHERE id_alerta = ?;
        """
        with self.conectar() as conn:
            with conn:
                cursor = conn.execute(sql, (expediente_id, now_str, id_alerta))
                return cursor.rowcount > 0

    def actualizar_estado_alerta_boletin(
        self,
        id_alerta: str,
        nuevo_estado: str,
        notas: Optional[str] = None
    ) -> bool:
        """
        Actualiza el estado operativo de una alerta dentro de la Máquina de Estados y sus notas.
        """
        from src.centinela import ESTADOS_BOLETIN_VALIDOS, BoletinDTOValidationError
        nuevo_estado = nuevo_estado.upper()
        if nuevo_estado not in ESTADOS_BOLETIN_VALIDOS:
            raise BoletinDTOValidationError(f"Estado no válido: '{nuevo_estado}'")

        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        if notas is not None:
            sql = """
            UPDATE boletines_alertas 
            SET estado_operativo = ?,
                notas_usuario = ?,
                updated_at = ?
            WHERE id_alerta = ?;
            """
            params = (nuevo_estado, notas, now_str, id_alerta)
        else:
            sql = """
            UPDATE boletines_alertas 
            SET estado_operativo = ?,
                updated_at = ?
            WHERE id_alerta = ?;
            """
            params = (nuevo_estado, now_str, id_alerta)

        with self.conectar() as conn:
            with conn:
                cursor = conn.execute(sql, params)
                return cursor.rowcount > 0

    def obtener_resumen_kpis(self, conn: Optional[sqlite3.Connection] = None) -> Dict[str, Any]:
        """
        Obtiene un resumen estructurado de las métricas de negocio agregadas (KPIs) para la API y Cockpit Visual.
        """
        def _ejecutar_kpis(c: sqlite3.Connection) -> Dict[str, Any]:
            cur = c.cursor()
            
            # Total expedientes vivos. La tabla `expedientes` no tiene `deleted_at`: el
            # archivado lógico vive en `lotes`, así que un expediente cuyos lotes están todos
            # archivados es un expediente archivado. Un COUNT(*) plano los seguía contando y
            # el Cockpit mostraba "51 Expedientes" sobre un desglose que sólo sumaba 22 lotes.
            # Es el mismo defecto de poblaciones mezcladas que H-08, en el último contador
            # que se le escapó a aquella corrección.
            cur.execute("""
                SELECT COUNT(DISTINCT expediente_id) FROM lotes WHERE deleted_at IS NULL;
            """)
            total_exp = cur.fetchone()[0] or 0
            
            # Total lotes
            cur.execute("SELECT COUNT(*) FROM lotes WHERE deleted_at IS NULL;")
            total_lotes = cur.fetchone()[0] or 0
            
            # Todas las métricas de conversión proceden de la misma vista y de la
            # misma población (lotes no archivados). Antes se mezclaba esta consulta
            # con una vista sin filtro de soft-delete y el win rate era imposible.
            cur.execute("""
                SELECT ganadas, perdidas, pendientes_resolucion, tasa_exito_porcentaje
                FROM vista_win_rate;
            """)
            row_wr = cur.fetchone() or (0, 0, 0, 0.0)
            ganadas = row_wr[0] or 0
            perdidas = row_wr[1] or 0
            presentadas = row_wr[2] or 0
            win_rate = float(row_wr[3] or 0.0)
            cur.execute("""
                SELECT
                    COUNT(CASE WHEN LOWER(estado_operativo) IN ('nueva', 'estudiando') THEN 1 END),
                    COALESCE(SUM(pbl), 0.0)
                FROM lotes WHERE deleted_at IS NULL;
            """)
            estudio, volumen_pbl = cur.fetchone()
            estudio = estudio or 0
            volumen_pbl = float(volumen_pbl or 0.0)
            
            # Avales / Garantías retenidas de la vista
            cur.execute("SELECT COALESCE(SUM(importe_garantia_retenida), 0.0) FROM vista_garantias_activas;")
            row_gar = cur.fetchone()
            garantias = float(row_gar[0]) if (row_gar and row_gar[0] is not None) else 0.0
            
            # Alertas tempranas activas
            cur.execute("""
                SELECT COUNT(*) FROM boletines_alertas 
                WHERE UPPER(estado_operativo) IN ('NUEVA_FASE_TEMPRANA', 'EN_ESTUDIO_PROACTIVO');
            """)
            alertas_activas = cur.fetchone()[0] or 0
            
            return {
                "total_expedientes": total_exp,
                "total_lotes": total_lotes,
                "licitaciones_estudio": estudio,
                "licitaciones_presentadas": presentadas,
                "licitaciones_ganadas": ganadas,
                "licitaciones_perdidas": perdidas,
                "win_rate_porcentaje": win_rate,
                "volumen_total_pbl": volumen_pbl,
                "capital_garantias_retenidas": garantias,
                "alertas_tempranas_activas": alertas_activas
            }

        if conn is not None:
            return _ejecutar_kpis(conn)
        else:
            with self.conectar() as c:
                return _ejecutar_kpis(c)

    def listar_expedientes_paginados(
        self,
        page: int = 1,
        limit: int = 10,
        search: Optional[str] = None,
        min_score: Optional[int] = None,
        pmp_max: Optional[int] = None,
        subrogacion_critica: Optional[bool] = None,
        estado: Optional[str] = None,
        incluir_archivadas: bool = False,
        conn: Optional[sqlite3.Connection] = None
    ) -> Tuple[List[Dict[str, Any]], int]:
        """
        Devuelve una lista paginada de expedientes con sus lotes asociados y el recuento total coincidentes.

        `incluir_archivadas` es la única vía para llegar desde la interfaz a lo que el
        Depurador sacó del canal principal (H-32). Por defecto es `False`: el Funnel es la
        tabla con la que se decide a qué concurso presentarse y no debe arrastrar histórico.
        Mismo criterio y mismo patrón que el filtro de auditoría que el Paso D5/D9 añadió al
        Centinela para las alertas descartadas por reglas.
        """
        def _ejecutar_listar(c: sqlite3.Connection):
            c.row_factory = sqlite3.Row
            cur = c.cursor()

            where_clauses = ["1=1"]
            params: List[Any] = []

            if search:
                term = f"%{search.strip().lower()}%"
                where_clauses.append("(LOWER(e.id) LIKE ? OR LOWER(e.titulo) LIKE ? OR LOWER(e.organo) LIKE ? OR LOWER(COALESCE(e.localidad, '')) LIKE ?)")
                params.extend([term, term, term, term])

            if min_score is not None:
                where_clauses.append("COALESCE(sub.max_score, 0) >= ?")
                params.append(min_score)

            if pmp_max is not None:
                where_clauses.append("COALESCE(sub.max_pmp, 0) <= ?")
                params.append(pmp_max)

            if subrogacion_critica is not None:
                val_sub = 1 if subrogacion_critica else 0
                where_clauses.append("COALESCE(sub.has_subrogacion, 0) = ?")
                params.append(val_sub)

            if estado:
                where_clauses.append("LOWER(sub.estado_operativo) = ?")
                params.append(estado.strip().lower())

            where_str = " AND ".join(where_clauses)

            # El filtro de vivos se aplica salvo que se pidan expresamente las archivadas.
            # `archivada` viaja hasta la fila para que la pantalla pueda marcarla: una fila
            # archivada mezclada sin distintivo con las vivas induciría a decidir sobre algo
            # que ya está fuera del canal (Convención C3).
            filtro_vivos = "" if incluir_archivadas else "WHERE deleted_at IS NULL"
            sub_lotes = f"""
                SELECT
                    expediente_id,
                    MAX(score_total) AS max_score,
                    MAX(pmp_dias) AS max_pmp,
                    MAX(CASE WHEN subrogacion = 1 THEN 1 ELSE 0 END) AS has_subrogacion,
                    MIN(estado_operativo) AS estado_operativo,
                    MIN(CASE WHEN deleted_at IS NULL THEN 0 ELSE 1 END) AS archivada
                FROM lotes
                {filtro_vivos}
                GROUP BY expediente_id
            """

            # JOIN interno, no LEFT: la subconsulta ya filtra `deleted_at IS NULL`, pero un
            # LEFT JOIN dejaba pasar igualmente los expedientes sin ningún lote vivo, con
            # todos los campos de `sub` a NULL. Resultado: el Funnel listaba los 29
            # expedientes archivados junto a los 22 vivos, como filas fantasma de "0 € y
            # 0 pts" —porque el join de lotes sí los excluía— y una de ellas arrastraba un
            # score de 115, de la escala anterior al Bloque 2. La tabla con la que se decide
            # a qué concurso presentarse mostraba más del doble de expedientes de los reales.
            count_sql = f"""
                SELECT COUNT(DISTINCT e.id)
                FROM expedientes e
                JOIN ({sub_lotes}) sub ON e.id = sub.expediente_id
                WHERE {where_str};
            """
            cur.execute(count_sql, params)
            total_count = cur.fetchone()[0] or 0

            if total_count == 0:
                return [], 0

            offset = (page - 1) * limit
            data_sql = f"""
                SELECT 
                    e.id, e.titulo, e.organo, e.localidad, e.nuts, e.procedimiento,
                    e.urgente, e.fuente, e.link, e.fecha_publicacion, e.fecha_limite,
                    e.fecha_ingesta, e.alerta_modificacion, e.log_cambios,
                    e.deleted_at, e.deleted_reason,
                    COALESCE(sub.max_score, 0) AS score_maximo,
                    COALESCE(sub.archivada, 0) AS archivada
                FROM expedientes e
                JOIN ({sub_lotes}) sub ON e.id = sub.expediente_id
                WHERE {where_str}
                ORDER BY e.fecha_publicacion DESC, e.id DESC
                LIMIT ? OFFSET ?;
            """
            cur.execute(data_sql, params + [limit, offset])
            rows_exp = cur.fetchall()

            expedientes = []
            exp_map = {}
            for row in rows_exp:
                exp_dict = dict(row)
                exp_dict["lotes"] = []
                exp_dict["analisis_semantico"] = None
                expedientes.append(exp_dict)
                exp_map[exp_dict["id"]] = exp_dict

            if exp_map:
                exp_ids = list(exp_map.keys())
                placeholders = ",".join("?" * len(exp_ids))

                # Batch Query 1: Lotes en una única llamada SQL. Respeta el mismo criterio
                # que la subconsulta de arriba; si no, un expediente traído por
                # `incluir_archivadas` llegaría a la pantalla sin ningún lote dentro.
                filtro_lotes = "" if incluir_archivadas else "AND deleted_at IS NULL"
                lotes_sql = f"""
                    SELECT * FROM lotes
                    WHERE expediente_id IN ({placeholders}) {filtro_lotes}
                    ORDER BY expediente_id, lote_numero ASC;
                """
                cur.execute(lotes_sql, exp_ids)
                for rl in cur.fetchall():
                    lote_dict = dict(rl)
                    exp_id = lote_dict["expediente_id"]
                    if exp_id in exp_map:
                        exp_map[exp_id]["lotes"].append(lote_dict)

                # Batch Query 2: Análisis Semántico en una única llamada SQL.
                # Se incluye `estado_analisis` para que el Cockpit pueda advertir en el
                # propio listado qué dictámenes NO proceden de una lectura real del pliego.
                sem_sql = f"""
                    SELECT expediente_id, dictamen_recomendacion, subrogacion_detectada, subrogacion_riesgo,
                           revision_precios_permitida, criterios_peso_formulas, criterios_peso_juicio_valor,
                           dictamen_resumen, estado_analisis, modelo_llm, error_detalle
                    FROM analisis_semantico
                    WHERE expediente_id IN ({placeholders});
                """
                cur.execute(sem_sql, exp_ids)
                for rs in cur.fetchall():
                    sem_dict = dict(rs)
                    exp_id = sem_dict.pop("expediente_id")
                    sem_dict["modo_degradado"] = (
                        str(sem_dict.get("estado_analisis") or "").upper() != "COMPLETADO"
                    )
                    if exp_id in exp_map:
                        exp_map[exp_id]["analisis_semantico"] = sem_dict

            return expedientes, total_count

        if conn is not None:
            return _ejecutar_listar(conn)
        else:
            with self.conectar() as c:
                return _ejecutar_listar(c)

    def obtener_expediente_completo(
        self,
        expediente_id: str,
        conn: Optional[sqlite3.Connection] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Recupera un expediente completo por su ID con sus lotes y dictamen semántico.
        """
        def _ejecutar_obtener(c: sqlite3.Connection):
            c.row_factory = sqlite3.Row
            cur = c.cursor()

            cur.execute("""
                SELECT 
                    e.id, e.titulo, e.organo, e.localidad, e.nuts, e.procedimiento,
                    e.urgente, e.fuente, e.link, e.fecha_publicacion, e.fecha_limite,
                    e.fecha_ingesta, e.alerta_modificacion, e.log_cambios,
                    e.deleted_at, e.deleted_reason,
                    (SELECT COALESCE(MAX(score_total), 0) FROM lotes WHERE expediente_id = e.id) AS score_maximo
                FROM expedientes e
                WHERE e.id = ?;
            """, (expediente_id,))
            row_exp = cur.fetchone()
            if not row_exp:
                return None

            exp_dict = dict(row_exp)

            # La ficha muestra TODOS los lotes, archivados incluidos (H-32). Antes filtraba
            # por `deleted_at`, de modo que la ficha de un expediente archivado se abría con
            # la lista de lotes vacía: no había nada que mirar ni sobre lo que decidir.
            # Cada lote viaja con su `deleted_at` y su `deleted_reason` para que el Cockpit
            # pueda distinguirlo — mostrarlo sin distintivo sería peor que no mostrarlo
            # (Convención C3).
            #
            # `score_maximo` pasa a calcularse sobre todos los lotes por la misma razón: si
            # sólo contara los vivos, la ficha de un expediente archivado anunciaría "0 pts"
            # sobre lotes que se puntuaron en su día.
            cur.execute("""
                SELECT * FROM lotes
                WHERE expediente_id = ?
                ORDER BY lote_numero ASC;
            """, (expediente_id,))
            rows_lotes = cur.fetchall()
            exp_dict["lotes"] = [dict(r) for r in rows_lotes]

            # `estado_analisis`, `modelo_llm` y `error_detalle` se exponen para que el
            # Cockpit pueda distinguir un dictamen real de uno emitido en modo degradado.
            cur.execute("""
                SELECT dictamen_recomendacion, subrogacion_detectada, subrogacion_riesgo,
                       revision_precios_permitida, criterios_peso_formulas, criterios_peso_juicio_valor,
                       dictamen_resumen, estado_analisis, modelo_llm, error_detalle, raw_dto_json, updated_at
                FROM analisis_semantico
                WHERE expediente_id = ?;
            """, (expediente_id,))
            row_sem = cur.fetchone()
            if row_sem:
                sem_dict = dict(row_sem)
                # Bandera derivada y explícita para el consumidor de la API.
                sem_dict["modo_degradado"] = (
                    str(sem_dict.get("estado_analisis") or "").upper() != "COMPLETADO"
                )
                raw_dto = sem_dict.pop("raw_dto_json", None)
                if raw_dto:
                    try:
                        dto_dict = json.loads(raw_dto)
                        for clave in ("subrogacion", "revision_precios", "criterios", "garantia_definitiva", "penalidades", "clausulas_sociales"):
                            if isinstance(dto_dict.get(clave), dict):
                                sem_dict[clave] = dto_dict[clave]
                    except (TypeError, json.JSONDecodeError):
                        sem_dict["modo_degradado"] = True
                exp_dict["analisis_semantico"] = sem_dict
            else:
                exp_dict["analisis_semantico"] = None

            return exp_dict

        if conn is not None:
            return _ejecutar_obtener(conn)
        else:
            with self.conectar() as c:
                return _ejecutar_obtener(c)

    def listar_alertas_boletin_paginadas(
        self,
        page: int = 1,
        limit: int = 10,
        search: Optional[str] = None,
        fuente: Optional[str] = None,
        min_score: Optional[int] = None,
        categoria: Optional[str] = None,
        estado: Optional[str] = None,
        conn: Optional[sqlite3.Connection] = None,
        incluir_descartadas: bool = False
    ) -> Tuple[List[Dict[str, Any]], int]:
        """
        Devuelve una lista paginada de alertas tempranas de boletines oficiales (DOGC/BOPB) y el recuento total.

        Esta es la consulta que alimenta el canal proactivo del Cockpit. Las alertas
        descartadas por reglas quedan fuera salvo que se filtren por su estado explícito o se
        pida `incluir_descartadas=True`: se guardan para auditoría, no para ocupar la pantalla.
        """
        def _ejecutar_listar(c: sqlite3.Connection):
            c.row_factory = sqlite3.Row
            cur = c.cursor()

            where_clauses = ["1=1"]
            params: List[Any] = []

            if search:
                term = f"%{search.strip().lower()}%"
                where_clauses.append("(LOWER(id_alerta) LIKE ? OR LOWER(titulo_anuncio) LIKE ? OR LOWER(organo_emisor) LIKE ? OR LOWER(COALESCE(municipio, '')) LIKE ?)")
                params.extend([term, term, term, term])

            if fuente:
                where_clauses.append("UPPER(fuente) = ?")
                params.append(fuente.strip().upper())

            if min_score is not None:
                where_clauses.append("score_temprano >= ?")
                params.append(min_score)

            if categoria:
                where_clauses.append("UPPER(categoria_fase_temprana) = ?")
                params.append(categoria.strip().upper())

            if estado:
                where_clauses.append("UPPER(estado_operativo) = ?")
                params.append(estado.strip().upper())
            elif not incluir_descartadas:
                where_clauses.append("UPPER(estado_operativo) != 'DESCARTADA_POR_REGLAS'")

            where_str = " AND ".join(where_clauses)

            count_sql = f"SELECT COUNT(*) FROM boletines_alertas WHERE {where_str};"
            cur.execute(count_sql, params)
            total_count = cur.fetchone()[0] or 0

            if total_count == 0:
                return [], 0

            offset = (page - 1) * limit
            data_sql = f"""
                SELECT * FROM boletines_alertas
                WHERE {where_str}
                ORDER BY fecha_publicacion DESC, id_alerta DESC
                LIMIT ? OFFSET ?;
            """
            cur.execute(data_sql, params + [limit, offset])
            rows = cur.fetchall()

            alertas = []
            for r in rows:
                d = dict(r)
                if isinstance(d.get("dictamen_ia_json"), str) and d["dictamen_ia_json"]:
                    try:
                        d["dictamen_ia_json"] = json.loads(d["dictamen_ia_json"])
                    except Exception:
                        pass
                alertas.append(d)

            return alertas, total_count

        if conn is not None:
            return _ejecutar_listar(conn)
        else:
            with self.conectar() as c:
                return _ejecutar_listar(c)

    def obtener_alerta_boletin_completa(
        self,
        id_alerta: str,
        conn: Optional[sqlite3.Connection] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Recupera una alerta temprana completa por su id_alerta (hash SHA256).
        """
        def _ejecutar_obtener(c: sqlite3.Connection):
            c.row_factory = sqlite3.Row
            cur = c.cursor()
            cur.execute("SELECT * FROM boletines_alertas WHERE id_alerta = ?;", (id_alerta,))
            row = cur.fetchone()
            if not row:
                return None

            d = dict(row)
            if isinstance(d.get("dictamen_ia_json"), str) and d["dictamen_ia_json"]:
                try:
                    d["dictamen_ia_json"] = json.loads(d["dictamen_ia_json"])
                except Exception:
                    pass
            return d

        if conn is not None:
            return _ejecutar_obtener(conn)
        else:
            with self.conectar() as c:
                return _ejecutar_obtener(c)

    def mutar_estado_lote_transaccional(
        self,
        expediente_id: str,
        lote_numero: int = 1,
        nuevo_estado: str = "Estudiando",
        notas: Optional[str] = None,
        conn: Optional[sqlite3.Connection] = None
    ) -> Tuple[bool, Optional[str], Optional[Dict[str, Any]]]:
        """
        Mutación transaccional del estado operativo y notas de un lote.
        Retorna tupla: (exito, estado_anterior, expediente_completo_dict).
        """
        def _ejecutar_mutacion(c: sqlite3.Connection):
            c.row_factory = sqlite3.Row
            cur = c.cursor()

            # Se alcanza también lo archivado (H-32). Archivar gobierna **qué se ve en el
            # canal principal, no qué se puede tocar**: filtrar aquí por `deleted_at`
            # convertía el archivado en sólo-lectura y dejaba congelado el registro de un
            # contrato ganado —su importe, sus garantías, sus costes— justo cuando toca
            # anotarlos, porque una adjudicación se resuelve mucho después de la fecha
            # límite que provocó el archivado.
            #
            # Esto NO desarchiva: el lote sigue con su `deleted_at` y fuera del Funnel. El
            # rescate `ARCHIVADO -> VIVO` es una acción explícita del contrato y vive en el
            # Paso 8. Si esta mutación lo desarchivara, la corrida siguiente volvería a
            # archivarlo —la fecha límite sigue vencida— y el lote entraría y saldría de la
            # pantalla solo: exactamente la oscilación que prohíbe la transición nº 7.
            cur.execute("""
                SELECT estado_operativo FROM lotes
                WHERE expediente_id = ? AND lote_numero = ?;
            """, (expediente_id, lote_numero))
            row = cur.fetchone()
            if not row:
                return False, None, None

            estado_anterior = row["estado_operativo"]
            now_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

            if notas is not None:
                sql = """
                    UPDATE lotes
                    SET estado_operativo = ?,
                        notas_usuario = ?,
                        updated_at = ?,
                        updated_by = 'user'
                    WHERE expediente_id = ? AND lote_numero = ?;
                """
                params = (nuevo_estado, notas, now_str, expediente_id, lote_numero)
            else:
                sql = """
                    UPDATE lotes
                    SET estado_operativo = ?,
                        updated_at = ?,
                        updated_by = 'user'
                    WHERE expediente_id = ? AND lote_numero = ?;
                """
                params = (nuevo_estado, now_str, expediente_id, lote_numero)

            cur.execute(sql, params)

            # Rastro del cambio de estado (H-31). Esta es la vía por la que el Cockpit
            # mueve una licitación por el embudo: sin esta línea, que alguien la llevara a
            # `Presentada` no dejaría constancia en ninguna parte, y el Paso 6 no podría
            # distinguirla de una oportunidad que nadie miró.
            if normalizar_estado_operativo(estado_anterior) != normalizar_estado_operativo(nuevo_estado):
                anexar_log_cambios(
                    cur, expediente_id,
                    entrada_log_cambio_estado(lote_numero, estado_anterior, nuevo_estado, autor="user")
                )

            exp_dict = self.obtener_expediente_completo(expediente_id, conn=c)
            c.commit()
            return True, estado_anterior, exp_dict

        with self.db_lock():
            if conn is not None:
                return _ejecutar_mutacion(conn)
            else:
                with self.conectar() as c:
                    return _ejecutar_mutacion(c)

    def mutar_estado_alerta_boletin_transaccional(
        self,
        id_alerta: str,
        nuevo_estado: str = "EN_ESTUDIO_PROACTIVO",
        notas: Optional[str] = None,
        conn: Optional[sqlite3.Connection] = None
    ) -> Tuple[bool, Optional[str], Optional[Dict[str, Any]]]:
        """
        Mutación transaccional del estado operativo y notas de una alerta temprana de boletín.
        Protegido con exclusión mutua db_lock y re-lectura previa al commit para aislamiento estricto.
        Retorna tupla: (exito, estado_anterior, alerta_completa_dict).
        """
        def _ejecutar_mutacion(c: sqlite3.Connection):
            c.row_factory = sqlite3.Row
            cur = c.cursor()

            cur.execute("""
                SELECT estado_operativo FROM boletines_alertas
                WHERE id_alerta = ?;
            """, (id_alerta,))
            row = cur.fetchone()
            if not row:
                return False, None, None

            estado_anterior = row["estado_operativo"]
            now_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

            if notas is not None:
                sql = """
                    UPDATE boletines_alertas 
                    SET estado_operativo = ?,
                        notas_usuario = ?,
                        updated_at = ?
                    WHERE id_alerta = ?;
                """
                params = (nuevo_estado, notas, now_str, id_alerta)
            else:
                sql = """
                    UPDATE boletines_alertas 
                    SET estado_operativo = ?,
                        updated_at = ?
                    WHERE id_alerta = ?;
                """
                params = (nuevo_estado, now_str, id_alerta)

            cur.execute(sql, params)
            alerta_dict = self.obtener_alerta_boletin_completa(id_alerta, conn=c)
            c.commit()
            return True, estado_anterior, alerta_dict

        with self.db_lock():
            if conn is not None:
                return _ejecutar_mutacion(conn)
            else:
                with self.conectar() as c:
                    return _ejecutar_mutacion(c)










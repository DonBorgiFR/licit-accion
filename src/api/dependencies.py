"""
src/api/dependencies.py — Inyección de Dependencias y Gestión de Conexiones SQLite v5
Ecosistema Automático de Licitaciones (bfr_incoop)

Módulo responsable de inyectar sesiones/conexiones transaccionales de base de datos SQLite
en modo WAL (Write-Ahead Logging) a los endpoints de la API FastAPI (Capa 7), garantizando
el aislamiento, la liberación segura de recursos y el autodiagnóstico determinista.
"""

import os
import sqlite3
import json
from datetime import datetime, timezone
from typing import Generator, Dict, Any, Optional

from src import ruta_datos
from src.memoria import Memoria, PROJECT_ROOT


# ==============================================================================
# Excepciones Tipadas de Dependencias API (Capa 7 - Paso 1)
# ==============================================================================

class APIDependencyError(Exception):
    """Excepción base para fallos en el subsistema de dependencias de la API."""
    pass


class DatabaseConnectionError(APIDependencyError):
    """Error emitido cuando falla la apertura o la verificación de la conexión a SQLite."""
    pass


class WALModeNotSupportedError(APIDependencyError):
    """Error emitido cuando la base de datos SQLite no puede operar en modo WAL."""
    pass


# ==============================================================================
# Trazabilidad JSONL de la API (Regla 3)
# ==============================================================================

def rotar_log_si_excede_tamano(log_path: str, max_bytes: int = 10 * 1024 * 1024, max_archivos: int = 5) -> None:
    """
    Rota el archivo pipeline.jsonl si supera max_bytes (defecto 10MB) y purga logs antiguos manteniendo max_archivos.
    """
    if not os.path.exists(log_path):
        return
    try:
        if os.path.getsize(log_path) >= max_bytes:
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            log_dir = os.path.dirname(os.path.abspath(log_path))
            base_name = os.path.basename(log_path).replace(".jsonl", "")
            archived_path = os.path.join(log_dir, f"{base_name}_{timestamp}.jsonl")
            
            os.rename(log_path, archived_path)
            
            archivos = sorted([
                os.path.join(log_dir, f) for f in os.listdir(log_dir)
                if f.startswith(f"{base_name}_") and f.endswith(".jsonl")
            ], key=os.path.getmtime)
            
            while len(archivos) > max_archivos:
                viejo = archivos.pop(0)
                try:
                    os.remove(viejo)
                except Exception:
                    pass
    except Exception as e:
        print(f"[!] Error en rotación defensiva de logs JSONL: {e}")


class GestorTrazabilidadAPI:
    """
    Gestor determinista de trazabilidad y auditoría de eventos de la API con rotación automática.
    Registra eventos estructurados en data/pipeline.jsonl.
    """
    def __init__(self, log_path: str = "data/pipeline.jsonl"):
        # El destino por defecto sale de ruta_datos(), no de PROJECT_ROOT: así la suite de
        # pruebas puede reubicar el directorio de datos y dejar de escribir en el del
        # proyecto. Ver tests/conftest.py y la Convención C5.
        if log_path == "data/pipeline.jsonl":
            log_path = ruta_datos("pipeline.jsonl")
        elif not os.path.isabs(log_path):
            log_path = str((PROJECT_ROOT / log_path).resolve())
        self.log_path = log_path
        os.makedirs(os.path.dirname(os.path.abspath(self.log_path)), exist_ok=True)

    def registrar_evento(self, tipo_evento: str, payload: Dict[str, Any], estado: str = "INFO") -> None:
        """
        Registra de forma síncrona un evento estructurado en data/pipeline.jsonl con rotación defensiva.
        """
        rotar_log_si_excede_tamano(self.log_path)
        evento = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "modulo": "api",
            "tipo_evento": tipo_evento,
            "estado": estado,
            "payload": payload
        }
        try:
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(evento, ensure_ascii=False) + "\n")
        except Exception as e:
            print(f"[!] Error en GestorTrazabilidadAPI al escribir JSONL: {e}")


# Instancia global por defecto del logger de trazabilidad API
trazabilidad_api = GestorTrazabilidadAPI()


# ==============================================================================
# Inyector de Dependencias de Base de Datos (FastAPI Dependency)
# ==============================================================================

def get_db(db_path: Optional[str] = None) -> Generator[sqlite3.Connection, None, None]:
    """
    Inyector de dependencias de conexión SQLite para FastAPI.
    
    Abre la conexión usando `Memoria.conectar()` e inyecta la sesión.
    Garantiza la liberación segura en el bloque `finally` sin atrapar ni alterar
    las excepciones generadas por la lógica de los endpoints.
    """
    target_path = db_path or os.getenv("DB_PATH_INCOOP") or ruta_datos("licitaciones.db")
    memoria = Memoria(db_path=target_path)
    
    try:
        conn_cm = memoria.conectar()
        conn = conn_cm.__enter__()
    except sqlite3.Error as e:
        trazabilidad_api.registrar_evento("API_DB_CONNECTION_FAILED", {"path": target_path, "error": str(e)}, estado="ERROR")
        raise DatabaseConnectionError(f"Error abriendo conexión a SQLite ({target_path}): {e}") from e
    except Exception as e:
        trazabilidad_api.registrar_evento("API_DB_UNEXPECTED_ERROR", {"path": target_path, "error": str(e)}, estado="ERROR")
        raise DatabaseConnectionError(f"Fallo inesperado en inyector get_db ({target_path}): {e}") from e

    try:
        yield conn
    finally:
        conn_cm.__exit__(None, None, None)


# ==============================================================================
# Autodiagnóstico y Salud del Subsistema de Dependencias (Regla 6)
# ==============================================================================

def healthcheck_api_dependencies(db_path: Optional[str] = None) -> Dict[str, Any]:
    """
    Ejecuta un autodiagnóstico completo sobre el motor de base de datos SQLite v5 y el inyector de dependencias.
    
    Verifica:
    1. Existencia y permisos de lectura/escritura en la carpeta del archivo `.db`.
    2. Conectividad SQLite mediante `Memoria.conectar()`.
    3. Estado activo del diario WAL (`PRAGMA journal_mode` == 'wal').
    4. Versión del esquema en la tabla `metadata` (esperada: 5).
    5. Ejecución limpia de consulta de prueba (`SELECT 1`).
    """
    target_path = db_path or os.getenv("DB_PATH_INCOOP") or ruta_datos("licitaciones.db")
    db_dir = os.path.dirname(os.path.abspath(target_path))
    
    # 1. Permisos de disco
    permiso_escritura = os.access(db_dir, os.W_OK) if os.path.exists(db_dir) else os.access(os.path.dirname(db_dir), os.W_OK)
    
    diagnostico = {
        "status": "OK",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "db_path": target_path,
        "directorio_accesible": permiso_escritura,
        "wal_mode_active": False,
        "busy_timeout_ms": 0,
        "schema_version": None,
        "query_test_ok": False,
        "error": None
    }
    
    memoria = Memoria(db_path=target_path)
    
    try:
        with memoria.conectar() as conn:
            # Check 2: Modo WAL
            cursor = conn.cursor()
            cursor.execute("PRAGMA journal_mode;")
            row_wal = cursor.fetchone()
            wal_mode = row_wal[0].lower() if row_wal else ""
            diagnostico["wal_mode_active"] = (wal_mode == "wal")
            
            if not diagnostico["wal_mode_active"]:
                diagnostico["status"] = "ERROR"
                diagnostico["error"] = f"SQLite journal_mode es '{wal_mode}', se requiere 'wal'."
                trazabilidad_api.registrar_evento("API_DEPENDENCIES_HEALTHCHECK_FAILED", diagnostico, estado="ERROR")
                return diagnostico

            # Check 3: Busy Timeout (mínimo 30000 ms)
            cursor.execute("PRAGMA busy_timeout;")
            row_timeout = cursor.fetchone()
            busy_timeout = row_timeout[0] if row_timeout else 0
            diagnostico["busy_timeout_ms"] = busy_timeout
            if busy_timeout < 30000:
                diagnostico["status"] = "ERROR"
                diagnostico["error"] = f"SQLite busy_timeout es {busy_timeout}ms, se requieren al menos 30000ms."
                trazabilidad_api.registrar_evento("API_DEPENDENCIES_HEALTHCHECK_FAILED", diagnostico, estado="ERROR")
                return diagnostico

            # Check 4: Versión de esquema
            cursor.execute("SELECT version FROM metadata LIMIT 1;")
            row_ver = cursor.fetchone()
            if row_ver:
                diagnostico["schema_version"] = row_ver[0]

            # Check 5: Consulta de prueba
            cursor.execute("SELECT 1;")
            row_test = cursor.fetchone()
            diagnostico["query_test_ok"] = (row_test and row_test[0] == 1)

            trazabilidad_api.registrar_evento("API_DEPENDENCIES_HEALTHCHECK_PASSED", diagnostico, estado="INFO")
            return diagnostico

    except Exception as e:
        diagnostico["status"] = "ERROR"
        diagnostico["error"] = str(e)
        trazabilidad_api.registrar_evento("API_DEPENDENCIES_HEALTHCHECK_FAILED", diagnostico, estado="ERROR")
        return diagnostico

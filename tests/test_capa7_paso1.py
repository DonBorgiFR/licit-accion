"""
tests/test_capa7_paso1.py — Pruebas Unitarias e Integración de Capa 7 (Paso 1)
Ecosistema Automático de Licitaciones (bfr_incoop)

Audita el paquete src/api/dependencies.py:
- Inyecciones get_db()
- Autodiagnóstico healthcheck_api_dependencies()
- Excepciones tipadas y trazabilidad JSONL
"""

import os
import sqlite3
import tempfile
import pytest
from unittest.mock import patch

from src.memoria import Memoria
from src.api.dependencies import (
    get_db,
    healthcheck_api_dependencies,
    DatabaseConnectionError,
    APIDependencyError,
    GestorTrazabilidadAPI
)


@pytest.fixture
def temp_db(tmp_path):
    """Fixture que crea y configura una base de datos SQLite v5 temporal para pruebas."""
    db_file = str(tmp_path / "test_licitaciones.db")
    memoria = Memoria(db_path=db_file)
    with memoria.conectar() as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS metadata (version INTEGER NOT NULL);")
        conn.execute("INSERT INTO metadata (version) VALUES (5);")
        conn.commit()
    return db_file


def test_get_db_yields_valid_connection(temp_db):
    """Verifica que get_db() genera una conexión válida, activa en WAL y que se cierra al terminar."""
    db_gen = get_db(db_path=temp_db)
    conn = next(db_gen)
    
    assert isinstance(conn, sqlite3.Connection)
    
    # Comprobar consulta simple
    cursor = conn.cursor()
    cursor.execute("SELECT version FROM metadata;")
    row = cursor.fetchone()
    assert row is not None
    assert row[0] == 5
    
    # Finalizar generador para cerrar conexión
    with pytest.raises(StopIteration):
        next(db_gen)
        
    # Verificar que la conexión está cerrada al intentar ejecutar consulta
    with pytest.raises(sqlite3.ProgrammingError):
        conn.execute("SELECT 1;")


def test_get_db_wal_mode(temp_db):
    """Verifica que get_db() configura explícitamente journal_mode=WAL y foreign_keys=ON."""
    db_gen = get_db(db_path=temp_db)
    conn = next(db_gen)
    
    cursor = conn.cursor()
    cursor.execute("PRAGMA journal_mode;")
    mode = cursor.fetchone()[0]
    assert mode.lower() == "wal"
    
    cursor.execute("PRAGMA foreign_keys;")
    fk = cursor.fetchone()[0]
    assert fk == 1
    
    try:
        next(db_gen)
    except StopIteration:
        pass


def test_get_db_error_handling():
    """Verifica que se lanza DatabaseConnectionError si la ruta es inválida."""
    with patch("src.memoria.Memoria.conectar", side_effect=sqlite3.Error("Fallo simulado")):
        db_gen = get_db(db_path="invalid_path/db.db")
        with pytest.raises(DatabaseConnectionError) as exc_info:
            next(db_gen)
        assert "Error abriendo conexión a SQLite" in str(exc_info.value)


def test_healthcheck_api_dependencies_success(temp_db):
    """Verifica el autodiagnóstico satisfactorio de las dependencias de la API."""
    res = healthcheck_api_dependencies(db_path=temp_db)
    
    assert res["status"] == "OK"
    assert res["db_path"] == temp_db
    assert res["directorio_accesible"] is True
    assert res["wal_mode_active"] is True
    assert res["schema_version"] == 5
    assert res["query_test_ok"] is True
    assert res["error"] is None


def test_healthcheck_api_dependencies_failure(tmp_path):
    """Verifica que healthcheck_api_dependencies detecta fallos de lectura/conexión."""
    invalid_file = str(tmp_path / "non_existent_dir" / "test.db")
    with patch("src.memoria.Memoria.conectar", side_effect=RuntimeError("Fallo de acceso")):
        res = healthcheck_api_dependencies(db_path=invalid_file)
        assert res["status"] == "ERROR"
        assert "Fallo de acceso" in res["error"]


def test_gestor_trazabilidad_api(tmp_path):
    """Verifica que GestorTrazabilidadAPI escribe correctamente eventos JSONL."""
    log_file = str(tmp_path / "pipeline_test.jsonl")
    logger = GestorTrazabilidadAPI(log_path=log_file)
    
    logger.registrar_evento("API_TEST_EVENT", {"param": 123}, estado="INFO")
    
    assert os.path.exists(log_file)
    with open(log_file, "r", encoding="utf-8") as f:
        lines = f.readlines()
        assert len(lines) == 1
        data = json_loads_safe = pytest.importorskip("json").loads(lines[0])
        assert data["modulo"] == "api"
        assert data["tipo_evento"] == "API_TEST_EVENT"
        assert data["payload"]["param"] == 123

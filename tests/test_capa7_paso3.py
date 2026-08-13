"""
tests/test_capa7_paso3.py — Pruebas de Integración de la API y Endpoint /health (Capa 7 - Paso 3)
Ecosistema Automático de Licitaciones (bfr_incoop)

Audita los componentes:
- src/api/main.py
- src/api/routers/health.py
- TestClient HTTP de FastAPI
"""

import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient

from src.memoria import Memoria
from src.api.main import app


@pytest.fixture
def temp_db(tmp_path):
    """Fixture de base de datos SQLite v5 temporal para pruebas de la API."""
    db_file = str(tmp_path / "api_health_test.db")
    memoria = Memoria(db_path=db_file)
    with memoria.conectar() as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS metadata (version INTEGER NOT NULL);")
        conn.execute("INSERT INTO metadata (version) VALUES (5);")
        conn.commit()
    return db_file


@pytest.fixture
def client():
    """Fixture del cliente HTTP de pruebas para FastAPI."""
    return TestClient(app)


def test_read_root(client):
    """Verifica el endpoint de bienvenida de la API.

    **Vivía en `/` hasta el 2026-08-13.** La Capa 10 Paso 4 le da esa raíz al Cockpit —servir
    el bundle desde FastAPI elimina Node.js y un segundo servidor de cada PC de la
    cooperativa— y traslada el JSON, íntegro, a `/api/v1/`. El cambio se declaró por
    adelantado en el contrato de la Capa 10; esta prueba es donde se ve.
    """
    response = client.get("/api/v1/")
    assert response.status_code == 200
    data = response.json()
    assert data["app"] == "Incoop Licitaciones API"
    assert data["version"] == "1.0.0"
    assert data["docs_url"] == "/docs"


def test_get_health_success(client, temp_db, monkeypatch):
    """Verifica el endpoint GET /api/v1/health cuando SQLite WAL opera correctamente (200 OK)."""
    monkeypatch.setenv("DB_PATH_INCOOP", temp_db)
    
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    
    assert data["status"] == "OK"
    assert data["db_path"] == temp_db
    assert data["directorio_accesible"] is True
    assert data["wal_mode_active"] is True
    assert data["schema_version"] == 5
    assert data["query_test_ok"] is True
    assert data["error"] is None


def test_get_health_failure(client, monkeypatch):
    """Verifica el endpoint GET /api/v1/health cuando falla la base de datos (503 Service Unavailable)."""
    mock_diag = {
        "status": "ERROR",
        "timestamp": "2026-07-26T18:00:00Z",
        "db_path": "invalid.db",
        "directorio_accesible": False,
        "wal_mode_active": False,
        "schema_version": None,
        "query_test_ok": False,
        "error": "Simulated WAL Failure"
    }
    
    with patch("src.api.routers.health.healthcheck_api_dependencies", return_value=mock_diag):
        response = client.get("/api/v1/health")
        assert response.status_code == 503
        data = response.json()
        assert data["status"] == "ERROR"
        assert data["error"] == "Simulated WAL Failure"


def test_swagger_and_openapi_docs(client):
    """Verifica que la documentación automática de OpenAPI /docs y /openapi.json son accesibles."""
    res_docs = client.get("/docs")
    assert res_docs.status_code == 200
    assert "text/html" in res_docs.headers["content-type"]
    
    res_openapi = client.get("/openapi.json")
    assert res_openapi.status_code == 200
    openapi_data = res_openapi.json()
    assert openapi_data["info"]["title"] == "Incoop Licitaciones API"
    assert "/api/v1/health" in openapi_data["paths"]

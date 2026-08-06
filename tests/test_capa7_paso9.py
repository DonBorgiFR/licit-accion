"""
tests/test_capa7_paso9.py — Pruebas de Integración de Middlewares de Seguridad y Trazabilidad (Capa 7 - Paso 9)
Ecosistema Automático de Licitaciones (bfr_incoop)

Audita los componentes:
- src/api/middleware.py (TrazabilidadMiddleware)
- CORSMiddleware en src/api/main.py
- Generación y preservación de la cabecera X-Request-ID
"""

import pytest
import uuid
from fastapi.testclient import TestClient

from src.memoria import Memoria
from src.api.main import app


@pytest.fixture
def temp_db(tmp_path):
    """Fixture de base de datos SQLite v5 temporal para pruebas de middleware."""
    db_file = str(tmp_path / "middleware_test.db")
    memoria = Memoria(db_path=db_file)
    memoria.setup_db()
    return db_file


@pytest.fixture
def client():
    """Fixture del cliente HTTP de pruebas para FastAPI."""
    return TestClient(app)


def test_trazabilidad_middleware_x_request_id_generated(client, temp_db, monkeypatch):
    """Verifica que el middleware inyecta una cabecera X-Request-ID UUIDv4 en las respuestas API."""
    monkeypatch.setenv("DB_PATH_INCOOP", temp_db)
    
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert "x-request-id" in response.headers
    
    request_id = response.headers["x-request-id"]
    # Comprobar formato UUID válido
    parsed_uuid = uuid.UUID(request_id)
    assert str(parsed_uuid) == request_id


def test_trazabilidad_middleware_custom_request_id_preserved(client, temp_db, monkeypatch):
    """Verifica que si el cliente envía su propio X-Request-ID, la API lo preserva en la respuesta."""
    monkeypatch.setenv("DB_PATH_INCOOP", temp_db)
    custom_id = "REQ-CUSTOM-HEADER-9999"
    
    response = client.get("/api/v1/health", headers={"X-Request-ID": custom_id})
    assert response.status_code == 200
    assert response.headers.get("x-request-id") == custom_id


def test_cors_middleware_preflight_headers(client):
    """Verifica que el middleware CORS procesa correctamente las solicitudes preflight OPTIONS."""
    headers = {
        "Origin": "http://localhost:5173",
        "Access-Control-Request-Method": "GET",
        "Access-Control-Request-Headers": "Content-Type"
    }
    
    response = client.options("/api/v1/licitaciones", headers=headers)
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "http://localhost:5173"
    assert "GET" in response.headers.get("access-control-allow-methods", "")

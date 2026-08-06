"""
tests/test_capa7_paso8.py — Pruebas de Integración de Mutación de Alertas del Centinela (Capa 7 - Paso 8)
Ecosistema Automático de Licitaciones (bfr_incoop)

Audita los componentes:
- src/memoria.py (mutar_estado_alerta_boletin_transaccional)
- src/api/routers/centinela.py (PUT /api/v1/alertas-tempranas/{id}/estado)
- TestClient HTTP de FastAPI
"""

import pytest
from fastapi.testclient import TestClient

from src.memoria import Memoria
from src.api.main import app


@pytest.fixture
def temp_db(tmp_path):
    """Fixture de base de datos SQLite v5 temporal para pruebas de mutación de boletines."""
    db_file = str(tmp_path / "centinela_mutate_test.db")
    memoria = Memoria(db_path=db_file)
    memoria.setup_db()
    return db_file


@pytest.fixture
def client():
    """Fixture del cliente HTTP de pruebas para FastAPI."""
    return TestClient(app)


def test_put_alerta_estado_success(client, temp_db, monkeypatch):
    """Verifica la mutación transaccional exitosa del estado operativo y notas de una alerta temprana."""
    monkeypatch.setenv("DB_PATH_INCOOP", temp_db)
    memoria = Memoria(db_path=temp_db)
    
    with memoria.conectar() as conn:
        conn.execute("""
            INSERT INTO boletines_alertas (id_alerta, fuente, num_boletin, fecha_publicacion, organo_emisor, municipio, titulo_anuncio, score_temprano, categoria_fase_temprana, estado_operativo, fecha_ingesta, updated_at)
            VALUES ('ALT-MUT-001', 'DOGC', '9200', '2026-07-26T00:00:00Z', 'Consell Comarcal del Gironès', 'Girona', 'Aprobació Pressupost 2026', 80, 'PRESUPUESTO', 'NUEVA_FASE_TEMPRANA', '2026-07-26T00:00:00Z', '2026-07-26T00:00:00Z');
        """)
        conn.commit()

    payload = {
        "nuevo_estado": "EN_ESTUDIO_PROACTIVO",
        "notas": "Reunión agendada con el área de acción social"
    }
    
    response = client.put("/api/v1/alertas-tempranas/ALT-MUT-001/estado", json=payload)
    assert response.status_code == 200
    data = response.json()
    
    assert data["id_alerta"] == "ALT-MUT-001"
    assert data["estado_operativo"] == "EN_ESTUDIO_PROACTIVO"
    assert data["notas_usuario"] == "Reunión agendada con el área de acción social"


def test_put_alerta_estado_invalid_enum(client, temp_db, monkeypatch):
    """Verifica el rechazo (422 Unprocessable Entity) al enviar un estado fuera de la enumeración."""
    monkeypatch.setenv("DB_PATH_INCOOP", temp_db)
    
    payload = {
        "nuevo_estado": "ESTADO_NO_VALIDO_CENTINELA",
        "notas": "Prueba de error"
    }
    
    response = client.put("/api/v1/alertas-tempranas/ALT-MUT-001/estado", json=payload)
    assert response.status_code == 422
    data = response.json()
    assert "detail" in data


def test_put_alerta_estado_not_found(client, temp_db, monkeypatch):
    """Verifica la respuesta 404 Not Found al intentar mutar una alerta inexistente."""
    monkeypatch.setenv("DB_PATH_INCOOP", temp_db)
    
    payload = {
        "nuevo_estado": "DESCARTADA_TEMPRANA",
        "notas": "No aplica"
    }
    
    response = client.put("/api/v1/alertas-tempranas/HASH-INEXISTENTE-999/estado", json=payload)
    assert response.status_code == 404
    data = response.json()
    assert "no encontrada" in data["detail"]

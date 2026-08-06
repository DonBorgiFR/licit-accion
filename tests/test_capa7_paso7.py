"""
tests/test_capa7_paso7.py — Pruebas de Integración de Mutación de Licitaciones (Capa 7 - Paso 7)
Ecosistema Automático de Licitaciones (bfr_incoop)

Audita los componentes:
- src/memoria.py (mutar_estado_lote_transaccional)
- src/api/routers/licitaciones.py (PUT /api/v1/licitaciones/{id}/estado)
- TestClient HTTP de FastAPI
"""

import pytest
from fastapi.testclient import TestClient

from src.memoria import Memoria
from src.api.main import app


@pytest.fixture
def temp_db(tmp_path):
    """Fixture de base de datos SQLite v5 temporal para pruebas de mutación."""
    db_file = str(tmp_path / "licitaciones_mutate_test.db")
    memoria = Memoria(db_path=db_file)
    memoria.setup_db()
    return db_file


@pytest.fixture
def client():
    """Fixture del cliente HTTP de pruebas para FastAPI."""
    return TestClient(app)


def test_put_licitacion_estado_success(client, temp_db, monkeypatch):
    """Verifica la mutación transaccional exitosa del estado operativo y notas de una licitación."""
    monkeypatch.setenv("DB_PATH_INCOOP", temp_db)
    memoria = Memoria(db_path=temp_db)
    
    with memoria.conectar() as conn:
        conn.execute("""
            INSERT INTO expedientes (id, titulo, organo, localidad, fuente, fecha_publicacion, fecha_ingesta, last_seen_feed, feed_hash)
            VALUES ('EXP-MUT-001', 'Licitación Servicios Sociales', 'Ajuntament de Girona', 'Girona', 'PSCP', '2026-07-26T00:00:00Z', '2026-07-26T00:00:00Z', '2026-07-26T00:00:00Z', 'hmut1');
        """)
        conn.execute("""
            INSERT INTO lotes (expediente_id, lote_numero, titulo_lote, pbl, vec, score_total, estado_operativo, updated_at)
            VALUES ('EXP-MUT-001', 1, 'Lote 1', 90000.0, 180000.0, 75, 'Nueva', '2026-07-26T00:00:00Z');
        """)
        conn.commit()

    payload = {
        "nuevo_estado": "Estudiando",
        "notas": "Asignado a Borja para revisión de solvencia"
    }
    
    response = client.put("/api/v1/licitaciones/EXP-MUT-001/estado?lote_numero=1", json=payload)
    assert response.status_code == 200
    data = response.json()
    
    assert data["id"] == "EXP-MUT-001"
    assert len(data["lotes"]) == 1
    assert data["lotes"][0]["estado_operativo"] == "Estudiando"
    assert data["lotes"][0]["notas_usuario"] == "Asignado a Borja para revisión de solvencia"
    assert data["lotes"][0]["updated_by"] == "user"


def test_put_licitacion_estado_invalid_enum(client, temp_db, monkeypatch):
    """Verifica el rechazo (422 Unprocessable Entity) al enviar un estado fuera de la Máquina de Estados."""
    monkeypatch.setenv("DB_PATH_INCOOP", temp_db)
    
    payload = {
        "nuevo_estado": "ESTADO_NO_PERMITIDO",
        "notas": "Intento inválido"
    }
    
    response = client.put("/api/v1/licitaciones/EXP-MUT-001/estado", json=payload)
    assert response.status_code == 422
    data = response.json()
    assert "detail" in data


def test_put_licitacion_estado_not_found(client, temp_db, monkeypatch):
    """Verifica la respuesta 404 Not Found al intentar mutar una licitación inexistente."""
    monkeypatch.setenv("DB_PATH_INCOOP", temp_db)
    
    payload = {
        "nuevo_estado": "Descartada",
        "notas": "Descarte por falta de presupuesto"
    }
    
    response = client.put("/api/v1/licitaciones/EXP-INEXISTENTE-999/estado", json=payload)
    assert response.status_code == 404
    data = response.json()
    assert "no encontrada" in data["detail"]

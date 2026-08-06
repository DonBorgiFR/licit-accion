"""
tests/test_capa7_paso4.py — Pruebas de Integración del Router de KPIs /api/v1/kpis (Capa 7 - Paso 4)
Ecosistema Automático de Licitaciones (bfr_incoop)

Audita los componentes:
- src/memoria.py (obtener_resumen_kpis)
- src/api/routers/kpis.py (GET /api/v1/kpis)
- TestClient HTTP de FastAPI
"""

import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient

from src.memoria import Memoria
from src.api.main import app


@pytest.fixture
def temp_db(tmp_path):
    """Fixture de base de datos SQLite v5 temporal para pruebas de KPIs."""
    db_file = str(tmp_path / "kpis_test.db")
    memoria = Memoria(db_path=db_file)
    memoria.setup_db()
    return db_file


@pytest.fixture
def client():
    """Fixture del cliente HTTP de pruebas para FastAPI."""
    return TestClient(app)


def test_get_kpis_empty_db(client, temp_db, monkeypatch):
    """Verifica que GET /api/v1/kpis en una base de datos recién inicializada devuelve ceros."""
    monkeypatch.setenv("DB_PATH_INCOOP", temp_db)
    
    response = client.get("/api/v1/kpis")
    assert response.status_code == 200
    data = response.json()
    
    assert data["total_expedientes"] == 0
    assert data["total_lotes"] == 0
    assert data["licitaciones_estudio"] == 0
    assert data["licitaciones_presentadas"] == 0
    assert data["licitaciones_ganadas"] == 0
    assert data["licitaciones_perdidas"] == 0
    assert data["win_rate_porcentaje"] == 0.0
    assert data["volumen_total_pbl"] == 0.0
    assert data["capital_garantias_retenidas"] == 0.0
    assert data["alertas_tempranas_activas"] == 0


def test_get_kpis_with_data(client, temp_db, monkeypatch):
    """Verifica el cálculo de KPIs cuando hay datos reales en la base de datos."""
    monkeypatch.setenv("DB_PATH_INCOOP", temp_db)
    memoria = Memoria(db_path=temp_db)
    
    # Inserción manual de datos de prueba
    with memoria.conectar() as conn:
        # Expediente 1
        conn.execute("""
            INSERT INTO expedientes (id, titulo, organo, fuente, fecha_publicacion, fecha_ingesta, last_seen_feed, feed_hash)
            VALUES ('EXP-001', 'Licitación Servicios 1', 'Ajuntament de Barcelona', 'PSCP', '2026-07-26T00:00:00Z', '2026-07-26T00:00:00Z', '2026-07-26T00:00:00Z', 'h1');
        """)
        # Lote 1 (Adjudicada)
        conn.execute("""
            INSERT INTO lotes (expediente_id, lote_numero, titulo_lote, pbl, vec, score_total, estado_operativo, importe_garantia_retenida, fecha_devolucion_garantia, updated_at)
            VALUES ('EXP-001', 1, 'Lote 1', 100000.0, 200000.0, 80, 'Adjudicada', 5000.0, '2027-07-26', '2026-07-26T00:00:00Z');
        """)
        # Lote 2 (Estudiando)
        conn.execute("""
            INSERT INTO lotes (expediente_id, lote_numero, titulo_lote, pbl, vec, score_total, estado_operativo, updated_at)
            VALUES ('EXP-001', 2, 'Lote 2', 50000.0, 50000.0, 60, 'Estudiando', '2026-07-26T00:00:00Z');
        """)
        
        # Alerta temprana Centinela
        conn.execute("""
            INSERT INTO boletines_alertas (id_alerta, fuente, num_boletin, fecha_publicacion, organo_emisor, titulo_anuncio, score_temprano, estado_operativo, fecha_ingesta, updated_at)
            VALUES ('ALERT-001', 'DOGC', '9000', '2026-07-26T00:00:00Z', 'Generalitat', 'Presupuestos 2027', 75, 'NUEVA_FASE_TEMPRANA', '2026-07-26T00:00:00Z', '2026-07-26T00:00:00Z');
        """)
        conn.commit()
        
    response = client.get("/api/v1/kpis")
    assert response.status_code == 200
    data = response.json()
    
    assert data["total_expedientes"] == 1
    assert data["total_lotes"] == 2
    assert data["licitaciones_estudio"] == 1
    assert data["licitaciones_ganadas"] == 1
    assert data["volumen_total_pbl"] == 150000.0
    assert data["capital_garantias_retenidas"] == 5000.0
    assert data["alertas_tempranas_activas"] == 1


def test_get_kpis_database_error(client, monkeypatch):
    """Verifica respuesta 503 cuando ocurre una excepción en la agregación de KPIs."""
    with patch("src.memoria.Memoria.obtener_resumen_kpis", side_effect=RuntimeError("Fallo simulado en consulta SQL")):
        response = client.get("/api/v1/kpis")
        assert response.status_code == 503
        data = response.json()
        assert "detail" in data or "message" in data, f"Data keys: {data}"
        detail_msg = data.get("detail") or data.get("message") or str(data)
        assert "Fallo calculando resumen de KPIs" in detail_msg or "Fallo simulado" in detail_msg

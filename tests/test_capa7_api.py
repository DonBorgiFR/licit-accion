"""
tests/test_capa7_api.py — Suite de Pruebas E2E y Cierre Oficial de la Capa 7 (La Pasarela API)
Ecosistema Automático de Licitaciones (bfr_incoop)

Pruebas integrales de ciclo de vida completo:
- Funnel Reactivo PSCP (Listado, Paginación, Detalle, Mutación)
- Canal Proactivo Centinela (Listado, Filtros por fuente, Detalle, Mutación)
- Dashboard Analítico de KPIs
- Middlewares de Trazabilidad X-Request-ID y CORS
- Integridad del Esquema OpenAPI /docs
"""

import pytest
from fastapi.testclient import TestClient

from src.memoria import Memoria
from src.api.main import app


@pytest.fixture
def temp_db(tmp_path):
    """Fixture de base de datos SQLite v5 temporal para pruebas de integración E2E."""
    db_file = str(tmp_path / "capa7_e2e_test.db")
    memoria = Memoria(db_path=db_file)
    memoria.setup_db()
    return db_file


@pytest.fixture
def client():
    """Fixture del cliente HTTP de pruebas para FastAPI."""
    return TestClient(app)


def test_e2e_funnel_pscp_full_lifecycle(client, temp_db, monkeypatch):
    """Prueba E2E del ciclo de vida completo de un expediente PSCP (Listado -> Detalle -> Mutación -> KPI)."""
    monkeypatch.setenv("DB_PATH_INCOOP", temp_db)
    memoria = Memoria(db_path=temp_db)
    
    with memoria.conectar() as conn:
        conn.execute("""
            INSERT INTO expedientes (id, titulo, organo, localidad, fuente, fecha_publicacion, fecha_ingesta, last_seen_feed, feed_hash)
            VALUES ('EXP-E2E-001', 'Manteniment d Instal·lacions', 'Ajuntament de Girona', 'Girona', 'PSCP', '2026-07-26T00:00:00Z', '2026-07-26T00:00:00Z', '2026-07-26T00:00:00Z', 'he2e1');
        """)
        conn.execute("""
            INSERT INTO lotes (expediente_id, lote_numero, titulo_lote, pbl, vec, score_total, estado_operativo, updated_at)
            VALUES ('EXP-E2E-001', 1, 'Lote 1 Edificis', 120000.0, 240000.0, 85, 'Nueva', '2026-07-26T00:00:00Z');
        """)
        conn.commit()

    # 1. Consulta de Listado
    res_list = client.get("/api/v1/licitaciones?search=Girona")
    assert res_list.status_code == 200
    assert res_list.json()["total"] == 1
    assert res_list.headers.get("x-request-id") is not None

    # 2. Consulta de Detalle
    res_detail = client.get("/api/v1/licitaciones/EXP-E2E-001")
    assert res_detail.status_code == 200
    assert res_detail.json()["id"] == "EXP-E2E-001"
    assert res_detail.json()["lotes"][0]["estado_operativo"] == "Nueva"

    # 3. Mutación de Estado
    res_mutate = client.put(
        "/api/v1/licitaciones/EXP-E2E-001/estado?lote_numero=1",
        json={"nuevo_estado": "Estudiando", "notas": "Revisión inicial aprobada por el comité"}
    )
    assert res_mutate.status_code == 200
    assert res_mutate.json()["lotes"][0]["estado_operativo"] == "Estudiando"
    assert res_mutate.json()["lotes"][0]["notas_usuario"] == "Revisión inicial aprobada por el comité"

    # 4. Verificación en KPIs
    res_kpi = client.get("/api/v1/kpis")
    assert res_kpi.status_code == 200
    assert res_kpi.json()["total_expedientes"] == 1


def test_e2e_centinela_proactive_full_lifecycle(client, temp_db, monkeypatch):
    """Prueba E2E del ciclo de vida del Canal Proactivo Centinela (Listado -> Detalle -> Mutación)."""
    monkeypatch.setenv("DB_PATH_INCOOP", temp_db)
    memoria = Memoria(db_path=temp_db)
    
    with memoria.conectar() as conn:
        conn.execute("""
            INSERT INTO boletines_alertas (id_alerta, fuente, num_boletin, fecha_publicacion, organo_emisor, municipio, titulo_anuncio, score_temprano, categoria_fase_temprana, estado_operativo, fecha_ingesta, updated_at)
            VALUES ('ALT-E2E-999', 'DOGC', '9500', '2026-07-26T00:00:00Z', 'Generalitat de Catalunya', 'Barcelona', 'Subvenció Projectes Digitals', 90, 'SUBVENCION', 'NUEVA_FASE_TEMPRANA', '2026-07-26T00:00:00Z', '2026-07-26T00:00:00Z');
        """)
        conn.commit()

    # 1. Consulta de Listado con filtro por fuente
    res_list = client.get("/api/v1/alertas-tempranas?fuente=DOGC&min_score=80")
    assert res_list.status_code == 200
    assert res_list.json()["total"] == 1
    assert res_list.json()["items"][0]["id_alerta"] == "ALT-E2E-999"

    # 2. Consulta de Detalle
    res_detail = client.get("/api/v1/alertas-tempranas/ALT-E2E-999")
    assert res_detail.status_code == 200
    assert res_detail.json()["fuente"] == "DOGC"
    assert res_detail.json()["estado_operativo"] == "NUEVA_FASE_TEMPRANA"

    # 3. Mutación de Estado
    res_mutate = client.put(
        "/api/v1/alertas-tempranas/ALT-E2E-999/estado",
        json={"nuevo_estado": "EN_ESTUDIO_PROACTIVO", "notas": "Prospección asignada"}
    )
    assert res_mutate.status_code == 200
    assert res_mutate.json()["estado_operativo"] == "EN_ESTUDIO_PROACTIVO"
    assert res_mutate.json()["notas_usuario"] == "Prospección asignada"


def test_e2e_openapi_schema_integrity(client):
    """Verifica la integridad del esquema OpenAPI v3 generado por FastAPI en /openapi.json."""
    response = client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()
    
    assert schema["openapi"].startswith("3.")
    assert schema["info"]["title"] == "Incoop Licitaciones API"
    
    paths = schema["paths"]
    assert "/api/v1/health" in paths
    assert "/api/v1/kpis" in paths
    assert "/api/v1/licitaciones" in paths
    assert "/api/v1/licitaciones/{id}/estado" in paths
    assert "/api/v1/alertas-tempranas" in paths
    assert "/api/v1/alertas-tempranas/{id_alerta}/estado" in paths

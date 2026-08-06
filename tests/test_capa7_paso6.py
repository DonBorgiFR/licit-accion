"""
tests/test_capa7_paso6.py — Pruebas de Integración del Router Centinela /api/v1/alertas-tempranas (Capa 7 - Paso 6)
Ecosistema Automático de Licitaciones (bfr_incoop)

Audita los componentes:
- src/memoria.py (listar_alertas_boletin_paginadas, obtener_alerta_boletin_completa)
- src/api/routers/centinela.py (GET /api/v1/alertas-tempranas, GET /api/v1/alertas-tempranas/{id_alerta})
- TestClient HTTP de FastAPI
"""

import pytest
from fastapi.testclient import TestClient

from src.memoria import Memoria
from src.api.main import app


@pytest.fixture
def temp_db(tmp_path):
    """Fixture de base de datos SQLite v5 temporal con alertas proactivas."""
    db_file = str(tmp_path / "centinela_router_test.db")
    memoria = Memoria(db_path=db_file)
    memoria.setup_db()
    return db_file


@pytest.fixture
def client():
    """Fixture del cliente HTTP de pruebas para FastAPI."""
    return TestClient(app)


def test_list_alertas_tempranas_empty_db(client, temp_db, monkeypatch):
    """Verifica GET /api/v1/alertas-tempranas en una base de datos vacía."""
    monkeypatch.setenv("DB_PATH_INCOOP", temp_db)
    
    response = client.get("/api/v1/alertas-tempranas")
    assert response.status_code == 200
    data = response.json()
    
    assert data["total"] == 0
    assert data["page"] == 1
    assert data["limit"] == 10
    assert data["total_pages"] == 0
    assert data["items"] == []


def test_list_alertas_tempranas_with_data_and_pagination(client, temp_db, monkeypatch):
    """Verifica GET /api/v1/alertas-tempranas con datos y paginación."""
    monkeypatch.setenv("DB_PATH_INCOOP", temp_db)
    memoria = Memoria(db_path=temp_db)
    
    with memoria.conectar() as conn:
        for i in range(1, 12):
            alerta_id = f"HASH-ALERT-{i:03d}"
            fuente = "DOGC" if i % 2 == 0 else "BOPB"
            conn.execute("""
                INSERT INTO boletines_alertas (id_alerta, fuente, num_boletin, fecha_publicacion, organo_emisor, municipio, titulo_anuncio, score_temprano, categoria_fase_temprana, estado_operativo, fecha_ingesta, updated_at)
                VALUES (?, ?, ?, '2026-07-26T00:00:00Z', 'Consell Comarcal', 'Barcelona', ?, ?, 'PRESUPUESTO', 'NUEVA_FASE_TEMPRANA', '2026-07-26T00:00:00Z', '2026-07-26T00:00:00Z');
            """, (alerta_id, fuente, f"NUM-{i}", f"Anuncio proactivo {i}", 60 + i * 3))
        conn.commit()

    # Página 1 limit 5
    res1 = client.get("/api/v1/alertas-tempranas?page=1&limit=5")
    assert res1.status_code == 200
    data1 = res1.json()
    assert data1["total"] == 11
    assert data1["total_pages"] == 3
    assert len(data1["items"]) == 5

    # Página 3 limit 5 (debe traer 1 elemento)
    res3 = client.get("/api/v1/alertas-tempranas?page=3&limit=5")
    assert res3.status_code == 200
    data3 = res3.json()
    assert len(data3["items"]) == 1


def test_list_alertas_tempranas_filters(client, temp_db, monkeypatch):
    """Verifica filtros por fuente, categoría, min_score y búsqueda."""
    monkeypatch.setenv("DB_PATH_INCOOP", temp_db)
    memoria = Memoria(db_path=temp_db)
    
    with memoria.conectar() as conn:
        # Alerta 1 (DOGC, SUBVENCION, Score 85, Girona)
        conn.execute("""
            INSERT INTO boletines_alertas (id_alerta, fuente, num_boletin, fecha_publicacion, organo_emisor, municipio, titulo_anuncio, score_temprano, categoria_fase_temprana, estado_operativo, fecha_ingesta, updated_at)
            VALUES ('ALT-DOGC-1', 'DOGC', '9100', '2026-07-26T00:00:00Z', 'Generalitat de Catalunya', 'Girona', 'Subvenció Projectes Socials', 85, 'SUBVENCION', 'NUEVA_FASE_TEMPRANA', '2026-07-26T00:00:00Z', '2026-07-26T00:00:00Z');
        """)
        # Alerta 2 (BOPB, PRESUPUESTO, Score 50, Mataró)
        conn.execute("""
            INSERT INTO boletines_alertas (id_alerta, fuente, num_boletin, fecha_publicacion, organo_emisor, municipio, titulo_anuncio, score_temprano, categoria_fase_temprana, estado_operativo, fecha_ingesta, updated_at)
            VALUES ('ALT-BOPB-2', 'BOPB', '5200', '2026-07-26T00:00:00Z', 'Ajuntament de Mataró', 'Mataró', 'Aprobació Inicial Pressupost', 50, 'PRESUPUESTO', 'NUEVA_FASE_TEMPRANA', '2026-07-26T00:00:00Z', '2026-07-26T00:00:00Z');
        """)
        conn.commit()

    # Filtro fuente == DOGC
    res_dogc = client.get("/api/v1/alertas-tempranas?fuente=DOGC")
    assert res_dogc.json()["total"] == 1
    assert res_dogc.json()["items"][0]["id_alerta"] == "ALT-DOGC-1"

    # Filtro categoría == SUBVENCION
    res_cat = client.get("/api/v1/alertas-tempranas?categoria=SUBVENCION")
    assert res_cat.json()["total"] == 1
    assert res_cat.json()["items"][0]["id_alerta"] == "ALT-DOGC-1"

    # Filtro score >= 80
    res_score = client.get("/api/v1/alertas-tempranas?min_score=80")
    assert res_score.json()["total"] == 1
    assert res_score.json()["items"][0]["id_alerta"] == "ALT-DOGC-1"

    # Filtro búsqueda Girona
    res_search = client.get("/api/v1/alertas-tempranas?search=Girona")
    assert res_search.json()["total"] == 1
    assert res_search.json()["items"][0]["id_alerta"] == "ALT-DOGC-1"


def test_get_alerta_by_id_success(client, temp_db, monkeypatch):
    """Verifica GET /api/v1/alertas-tempranas/{id_alerta} cuando existe."""
    monkeypatch.setenv("DB_PATH_INCOOP", temp_db)
    memoria = Memoria(db_path=temp_db)
    
    with memoria.conectar() as conn:
        conn.execute("""
            INSERT INTO boletines_alertas (id_alerta, fuente, num_boletin, fecha_publicacion, organo_emisor, municipio, titulo_anuncio, score_temprano, categoria_fase_temprana, dictamen_ia_json, estado_operativo, fecha_ingesta, updated_at)
            VALUES ('ALT-TARGET-999', 'DOGC', '8888', '2026-07-26T00:00:00Z', 'Departament de Drets Socials', 'Barcelona', 'Convocatòria d ajuts', 95, 'SUBVENCION', '{"nivel_interes": "ALTO", "resumen_ejecutivo": "Oportunidad core"}', 'EN_ESTUDIO_PROACTIVO', '2026-07-26T00:00:00Z', '2026-07-26T00:00:00Z');
        """)
        conn.commit()

    response = client.get("/api/v1/alertas-tempranas/ALT-TARGET-999")
    assert response.status_code == 200
    data = response.json()
    
    assert data["id_alerta"] == "ALT-TARGET-999"
    assert data["fuente"] == "DOGC"
    assert data["score_temprano"] == 95
    assert data["estado_operativo"] == "EN_ESTUDIO_PROACTIVO"
    assert data["dictamen_ia_json"]["nivel_interes"] == "ALTO"


def test_get_alerta_by_id_not_found(client, temp_db, monkeypatch):
    """Verifica GET /api/v1/alertas-tempranas/{id_alerta} cuando la alerta no existe (404 Not Found)."""
    monkeypatch.setenv("DB_PATH_INCOOP", temp_db)
    
    response = client.get("/api/v1/alertas-tempranas/HASH-INEXISTENTE-999")
    assert response.status_code == 404
    data = response.json()
    assert "no encontrada" in data["detail"]

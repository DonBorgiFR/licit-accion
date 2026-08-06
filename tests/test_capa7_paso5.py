"""
tests/test_capa7_paso5.py — Pruebas de Integración del Router de Licitaciones /api/v1/licitaciones (Capa 7 - Paso 5)
Ecosistema Automático de Licitaciones (bfr_incoop)

Audita los componentes:
- src/memoria.py (listar_expedientes_paginados, obtener_expediente_completo)
- src/api/routers/licitaciones.py (GET /api/v1/licitaciones, GET /api/v1/licitaciones/{id})
- TestClient HTTP de FastAPI
"""

import pytest
from fastapi.testclient import TestClient

from src.memoria import Memoria
from src.api.main import app


@pytest.fixture
def temp_db(tmp_path):
    """Fixture de base de datos SQLite v5 temporal con datos de prueba."""
    db_file = str(tmp_path / "licitaciones_router_test.db")
    memoria = Memoria(db_path=db_file)
    memoria.setup_db()
    return db_file


@pytest.fixture
def client():
    """Fixture del cliente HTTP de pruebas para FastAPI."""
    return TestClient(app)


def test_list_licitaciones_empty_db(client, temp_db, monkeypatch):
    """Verifica GET /api/v1/licitaciones en una base de datos vacía."""
    monkeypatch.setenv("DB_PATH_INCOOP", temp_db)
    
    response = client.get("/api/v1/licitaciones")
    assert response.status_code == 200
    data = response.json()
    
    assert data["total"] == 0
    assert data["page"] == 1
    assert data["limit"] == 10
    assert data["total_pages"] == 0
    assert data["items"] == []


def test_list_licitaciones_with_data_and_pagination(client, temp_db, monkeypatch):
    """Verifica GET /api/v1/licitaciones con datos y paginación."""
    monkeypatch.setenv("DB_PATH_INCOOP", temp_db)
    memoria = Memoria(db_path=temp_db)
    
    with memoria.conectar() as conn:
        for i in range(1, 15):
            exp_id = f"EXP-{i:03d}"
            conn.execute("""
                INSERT INTO expedientes (id, titulo, organo, localidad, fuente, fecha_publicacion, fecha_ingesta, last_seen_feed, feed_hash)
                VALUES (?, ?, ?, ?, 'PSCP', '2026-07-26T00:00:00Z', '2026-07-26T00:00:00Z', '2026-07-26T00:00:00Z', ?);
            """, (exp_id, f"Licitación {i}", "Ajuntament de Barcelona" if i % 2 == 0 else "Ajuntament de Badalona", "Barcelona" if i % 2 == 0 else "Badalona", f"hash_{i}"))
            
            conn.execute("""
                INSERT INTO lotes (expediente_id, lote_numero, titulo_lote, pbl, vec, score_total, pmp_dias, subrogacion, estado_operativo, updated_at)
                VALUES (?, 1, 'Lote Único', 100000.0, 200000.0, ?, ?, ?, 'Nueva', '2026-07-26T00:00:00Z');
            """, (exp_id, 50 + i * 2, 25 if i % 2 == 0 else 45, 1 if i % 3 == 0 else 0))
        conn.commit()

    # Página 1 con limit 5
    res1 = client.get("/api/v1/licitaciones?page=1&limit=5")
    assert res1.status_code == 200
    data1 = res1.json()
    assert data1["total"] == 14
    assert data1["page"] == 1
    assert data1["limit"] == 5
    assert data1["total_pages"] == 3
    assert len(data1["items"]) == 5

    # Página 3 con limit 5 (debe traer los últimos 4)
    res3 = client.get("/api/v1/licitaciones?page=3&limit=5")
    assert res3.status_code == 200
    data3 = res3.json()
    assert len(data3["items"]) == 4


def test_list_licitaciones_filters(client, temp_db, monkeypatch):
    """Verifica los filtros combinados por búsqueda, min_score, pmp_max y subrogacion_critica."""
    monkeypatch.setenv("DB_PATH_INCOOP", temp_db)
    memoria = Memoria(db_path=temp_db)
    
    with memoria.conectar() as conn:
        # EXP-A (Badalona, Score 85, PMP 20, Subrogación 1)
        conn.execute("""
            INSERT INTO expedientes (id, titulo, organo, localidad, fuente, fecha_publicacion, fecha_ingesta, last_seen_feed, feed_hash)
            VALUES ('EXP-A', 'Casal d Estiu Badalona', 'Ajuntament de Badalona', 'Badalona', 'PSCP', '2026-07-26T00:00:00Z', '2026-07-26T00:00:00Z', '2026-07-26T00:00:00Z', 'ha');
        """)
        conn.execute("""
            INSERT INTO lotes (expediente_id, lote_numero, titulo_lote, pbl, vec, score_total, pmp_dias, subrogacion, estado_operativo, updated_at)
            VALUES ('EXP-A', 1, 'Lote A', 100000.0, 200000.0, 85, 20, 1, 'Estudiando', '2026-07-26T00:00:00Z');
        """)
        
        # EXP-B (Girona, Score 60, PMP 70, Subrogación 0)
        conn.execute("""
            INSERT INTO expedientes (id, titulo, organo, localidad, fuente, fecha_publicacion, fecha_ingesta, last_seen_feed, feed_hash)
            VALUES ('EXP-B', 'Manteniment Girona', 'Ajuntament de Girona', 'Girona', 'PSCP', '2026-07-26T00:00:00Z', '2026-07-26T00:00:00Z', '2026-07-26T00:00:00Z', 'hb');
        """)
        conn.execute("""
            INSERT INTO lotes (expediente_id, lote_numero, titulo_lote, pbl, vec, score_total, pmp_dias, subrogacion, estado_operativo, updated_at)
            VALUES ('EXP-B', 1, 'Lote B', 80000.0, 80000.0, 60, 70, 0, 'Nueva', '2026-07-26T00:00:00Z');
        """)
        conn.commit()

    # Filtro búsqueda Badalona
    res_search = client.get("/api/v1/licitaciones?search=Badalona")
    assert res_search.json()["total"] == 1
    assert res_search.json()["items"][0]["id"] == "EXP-A"

    # Filtro score >= 80
    res_score = client.get("/api/v1/licitaciones?min_score=80")
    assert res_score.json()["total"] == 1
    assert res_score.json()["items"][0]["id"] == "EXP-A"

    # Filtro PMP <= 30
    res_pmp = client.get("/api/v1/licitaciones?pmp_max=30")
    assert res_pmp.json()["total"] == 1
    assert res_pmp.json()["items"][0]["id"] == "EXP-A"

    # Filtro subrogación == true
    res_sub = client.get("/api/v1/licitaciones?subrogacion_critica=true")
    assert res_sub.json()["total"] == 1
    assert res_sub.json()["items"][0]["id"] == "EXP-A"

    # Filtro estado == 'Estudiando'
    res_est = client.get("/api/v1/licitaciones?estado=Estudiando")
    assert res_est.json()["total"] == 1
    assert res_est.json()["items"][0]["id"] == "EXP-A"


def test_get_licitacion_by_id_success(client, temp_db, monkeypatch):
    """Verifica GET /api/v1/licitaciones/{id} cuando la licitación existe."""
    monkeypatch.setenv("DB_PATH_INCOOP", temp_db)
    memoria = Memoria(db_path=temp_db)
    
    with memoria.conectar() as conn:
        conn.execute("""
            INSERT INTO expedientes (id, titulo, organo, localidad, fuente, fecha_publicacion, fecha_ingesta, last_seen_feed, feed_hash)
            VALUES ('EXP-100', 'Gestión Escola Bressol', 'Ajuntament de Sabadell', 'Sabadell', 'PSCP', '2026-07-26T00:00:00Z', '2026-07-26T00:00:00Z', '2026-07-26T00:00:00Z', 'h100');
        """)
        conn.execute("""
            INSERT INTO lotes (expediente_id, lote_numero, titulo_lote, pbl, vec, score_total, estado_operativo, updated_at)
            VALUES ('EXP-100', 1, 'Lote 1', 150000.0, 300000.0, 90, 'Estudiando', '2026-07-26T00:00:00Z');
        """)
        conn.execute("""
            INSERT INTO analisis_semantico (expediente_id, subrogacion_detectada, subrogacion_riesgo, revision_precios_permitida, dictamen_recomendacion, raw_dto_json, created_at, updated_at)
            VALUES ('EXP-100', 0, 'BAJO', 1, 'RECOMENDADA', '{}', '2026-07-26T00:00:00Z', '2026-07-26T00:00:00Z');
        """)
        conn.commit()

    response = client.get("/api/v1/licitaciones/EXP-100")
    assert response.status_code == 200
    data = response.json()
    
    assert data["id"] == "EXP-100"
    assert data["titulo"] == "Gestión Escola Bressol"
    assert len(data["lotes"]) == 1
    assert data["lotes"][0]["score_total"] == 90
    assert data["analisis_semantico"]["dictamen_recomendacion"] == "RECOMENDADA"


def test_get_licitacion_by_id_not_found(client, temp_db, monkeypatch):
    """Verifica GET /api/v1/licitaciones/{id} cuando la licitación no existe (404 Not Found)."""
    monkeypatch.setenv("DB_PATH_INCOOP", temp_db)
    
    response = client.get("/api/v1/licitaciones/EXP-INEXISTENTE-999")
    assert response.status_code == 404
    data = response.json()
    assert "no encontrada" in data["detail"]

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


def test_los_descartes_por_reglas_solo_se_ven_si_se_piden(client, temp_db, monkeypatch):
    """
    Contrato del canal proactivo tras la decisión del 2026-08-06: los descartes automáticos
    se persisten para poder auditarlos y reevaluarlos, pero no ocupan el canal principal.
    El único acceso desde el Cockpit es filtrar por DESCARTADA_POR_REGLAS.

    Verifica también que el esquema de la API acepta ese estado: es un valor que el
    evaluador ya emitía pero que no figuraba en ningún contrato, así que la frontera lo
    habría rechazado.
    """
    monkeypatch.setenv("DB_PATH_INCOOP", temp_db)
    memoria = Memoria(db_path=temp_db)

    from src.centinela import AlertaBoletinDTO

    def alerta(num, municipio, score, estado):
        return AlertaBoletinDTO(
            fuente="DOGC",
            num_boletin=num,
            fecha_publicacion="2026-08-01T08:00:00Z",
            organo_emisor=f"Ajuntament de {municipio}",
            municipio=municipio,
            titulo_anuncio=f"Aprovació inicial del pressupost de {municipio}",
            seccion_boletin="Anuncis",
            url_anuncio=f"https://dogc.cat/{num}",
            texto_sumario="Presupuestos municipales",
            score_temprano=score,
            motivos_score=["REGLA: Presupuestos (+40 pts)"],
            estado_operativo=estado,
        )

    memoria.guardar_alerta_boletin(alerta("777", "Barcelona", 70, "NUEVA_FASE_TEMPRANA"))
    memoria.guardar_alerta_boletin(alerta("888", "Badalona", 15, "DESCARTADA_POR_REGLAS"))

    # El canal principal no la muestra.
    sin_filtro = client.get("/api/v1/alertas-tempranas").json()
    assert sin_filtro["total"] == 1
    assert [i["municipio"] for i in sin_filtro["items"]] == ["Barcelona"]

    # Pero es consultable pidiéndola expresamente.
    filtrado = client.get("/api/v1/alertas-tempranas?estado=DESCARTADA_POR_REGLAS")
    assert filtrado.status_code == 200, "El esquema de la API debe aceptar DESCARTADA_POR_REGLAS"
    datos = filtrado.json()
    assert datos["total"] == 1
    assert datos["items"][0]["municipio"] == "Badalona"
    assert datos["items"][0]["estado_operativo"] == "DESCARTADA_POR_REGLAS"

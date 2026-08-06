"""
tests/test_api_tolerancia_nulos.py — Robustez de la API ante datos incompletos (Paso C3)
Ecosistema Automático de Licitaciones (bfr_incoop)

Regresión de un defecto detectado en la auditoría del 2026-07-27:

El DDL de SQLite declara con `DEFAULT` pero SIN `NOT NULL` columnas que los esquemas
Pydantic modelan como obligatorias (`organo`, `fuente`, `titulo_lote`, `pbl`...).
Un `DEFAULT` de SQLite sólo actúa si la columna se omite en el INSERT; no impide
almacenar un NULL explícito. Pydantic, a su vez, rechaza `None` en un campo tipado
aunque tenga valor por defecto.

Efecto observado: un único expediente con `organo` a NULL devolvía HTTP 503 en su
ficha y, al validarse dentro de una comprensión de lista, dejaba al equipo sin ver
NINGUNA licitación del funnel.
"""

import pytest
from fastapi.testclient import TestClient

from src.memoria import Memoria
from src.api.main import app
from src.api.dependencies import get_db


@pytest.fixture
def cliente_con_datos_sucios(tmp_path):
    """BD temporal con un expediente sano y otro con NULLs explícitos en columnas clave."""
    db_file = str(tmp_path / "nulos.db")
    memoria = Memoria(db_path=db_file)
    memoria.setup_db()

    with memoria.conectar() as conn:
        with conn:
            # Expediente sano
            conn.execute("""
                INSERT INTO expedientes (id, titulo, organo, fuente, urgente, alerta_modificacion, fecha_ingesta)
                VALUES ('EXP-SANO', 'Servei educatiu correcte', 'Ajuntament de Barcelona', 'PSCP', 0, 0,
                        '2026-07-01T00:00:00Z');
            """)
            conn.execute("""
                INSERT INTO lotes (expediente_id, lote_numero, titulo_lote, pbl, vec, estado_operativo, score_total)
                VALUES ('EXP-SANO', 1, 'Lote unico', 100000.0, 200000.0, 'Nueva', 70);
            """)
            # Expediente con NULL explícito en columnas que el esquema exige
            conn.execute("""
                INSERT INTO expedientes (id, titulo, organo, fuente, urgente, alerta_modificacion, fecha_ingesta)
                VALUES ('EXP-NULO', 'Servei amb dades incompletes', NULL, NULL, NULL, NULL,
                        '2026-07-02T00:00:00Z');
            """)
            conn.execute("""
                INSERT INTO lotes (expediente_id, lote_numero, titulo_lote, pbl, vec, estado_operativo, score_total,
                                   subrogacion, revision_precios)
                VALUES ('EXP-NULO', 1, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
            """)

    def _override_db():
        cm = memoria.conectar()
        conn = cm.__enter__()
        try:
            yield conn
        finally:
            cm.__exit__(None, None, None)

    app.dependency_overrides[get_db] = _override_db
    with TestClient(app) as cliente:
        yield cliente
    app.dependency_overrides.clear()


def test_ficha_de_expediente_con_nulos_no_devuelve_503(cliente_con_datos_sucios):
    """La ficha de un expediente con NULLs debe abrirse, degradando a valores por defecto."""
    r = cliente_con_datos_sucios.get("/api/v1/licitaciones/EXP-NULO")
    assert r.status_code == 200, f"Esperado 200, recibido {r.status_code}: {r.text}"

    cuerpo = r.json()
    assert cuerpo["id"] == "EXP-NULO"
    assert cuerpo["organo"] == "No informado"
    assert cuerpo["fuente"] == "PSCP"
    assert cuerpo["urgente"] is False
    assert cuerpo["alerta_modificacion"] is False

    lote = cuerpo["lotes"][0]
    assert lote["titulo_lote"] == "(sin título)"
    assert lote["pbl"] == 0.0
    assert lote["estado_operativo"] == "Nueva"
    assert lote["subrogacion"] is False


def test_una_fila_incompleta_no_tumba_la_pagina_entera(cliente_con_datos_sucios):
    """
    El listado del funnel debe seguir sirviendo el resto de licitaciones.
    Éste era el impacto grave: pantalla en blanco para todo el equipo por un solo registro.
    """
    r = cliente_con_datos_sucios.get("/api/v1/licitaciones?page=1&limit=10")
    assert r.status_code == 200, f"Esperado 200, recibido {r.status_code}: {r.text}"

    ids = [item["id"] for item in r.json()["items"]]
    assert "EXP-SANO" in ids, "El expediente sano debe seguir visible"
    assert "EXP-NULO" in ids, "El expediente incompleto debe mostrarse degradado, no desaparecer"


def test_expediente_sano_no_queda_alterado(cliente_con_datos_sucios):
    """La tolerancia a NULL no debe modificar datos correctos."""
    cuerpo = cliente_con_datos_sucios.get("/api/v1/licitaciones/EXP-SANO").json()
    assert cuerpo["organo"] == "Ajuntament de Barcelona"
    assert cuerpo["fuente"] == "PSCP"
    assert cuerpo["lotes"][0]["pbl"] == 100000.0
    assert cuerpo["lotes"][0]["score_total"] == 70

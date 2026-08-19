"""Bloque 3, Paso 6 · El análisis semántico, visible y en tres estados.

El motor funciona e integra el pipeline desde la Capa 5 —40 análisis completados en la base de
hoy— y su trabajo quedaba enterrado en la ficha de detalle. Tanto, que dirección llegó a creer
que había que ejecutarlo a mano con un `.py`.

**Medido sobre la base real el 2026-08-19**: de los 24 expedientes vivos, **11 tienen el pliego
leído y 13 no tienen análisis**; filtrado a Catalunya, **7 de 9 lo tienen**. Ni uno degradado, así
que ese tercer estado sólo existe aquí y en una copia sembrada a mano — nunca en la base real.

Lo que estas regresiones fijan:

* **Son tres estados y no dos.** «No se intentó» y «se intentó y salió mal» exigen decisiones
  distintas de quien mira, y hasta hoy pintaban la misma etiqueta.
* **El estado positivo existe.** Cuando el pliego SÍ se ha leído la pantalla lo dice, en vez de
  manifestarlo por la ausencia de una advertencia.
* **Un estado desconocido no asciende a «leído»** — C6 aplicada a la pantalla: lo que no se pudo
  comprobar no se afirma.
* **La clasificación vive en el servidor**, que es donde hay suite. En el Cockpit estaba escrita
  dos veces, en la tabla y en la ficha.
* **H-50**: el CLI del Analista arranca como módulo. `python src/analista.py` no funciona, y era
  lo que documentaban el README y el propio Cockpit.
"""

import subprocess
import sys

import pytest
from fastapi.testclient import TestClient

from src import (
    LECTURA_DEGRADADO,
    LECTURA_LEIDO,
    LECTURA_SIN_ANALIZAR,
    PROJECT_ROOT,
    VERSION_LECTURA,
    estado_lectura_pliego,
)
from src.api.main import app
from src.api.schemas import LicitacionSchema
from src.memoria import Memoria

# Los tres casos, tal como llegan de `listar_expedientes_paginados()`.
SEMILLA = [
    ("EXP-LEIDO", "COMPLETADO", None),
    ("EXP-DEGRADADO", "DEGRADADO", "Fallo en proveedores LLM (timeout de red)"),
    ("EXP-SIN-ANALISIS", None, None),  # sin fila en `analisis_semantico`
]


@pytest.fixture
def db(tmp_path):
    memoria = Memoria(db_path=str(tmp_path / "analisis.db"))
    memoria.setup_db()
    with memoria.conectar() as conn:
        with conn:
            for exp_id, estado, error in SEMILLA:
                conn.execute(
                    "INSERT INTO expedientes (id, titulo, organo, nuts, fuente, fecha_publicacion, "
                    "fecha_ingesta, last_seen_feed, feed_hash) VALUES (?, ?, 'Órgano de prueba', "
                    "'ES511', 'PSCP', '2026-08-01T00:00:00Z', '2026-08-01T00:00:00Z', "
                    "'2026-08-01T00:00:00Z', ?);",
                    (exp_id, f"Licitació {exp_id}", f"h-{exp_id}"),
                )
                conn.execute(
                    "INSERT INTO lotes (expediente_id, lote_numero, titulo_lote, pbl, score_total, "
                    "estado_operativo, updated_at) VALUES (?, 1, ?, 100000.0, 60, 'Nueva', "
                    "'2026-08-01T00:00:00Z');",
                    (exp_id, f"Lote 1 de {exp_id}"),
                )
                if estado is not None:
                    conn.execute(
                        "INSERT INTO analisis_semantico (expediente_id, estado_analisis, "
                        "error_detalle, dictamen_recomendacion, modelo_llm, raw_dto_json, "
                        "created_at, updated_at) "
                        "VALUES (?, ?, ?, 'REVISAR_RIESGO', 'modelo-de-prueba', '{}', "
                        "'2026-08-01T00:00:00Z', '2026-08-01T00:00:00Z');",
                        (exp_id, estado, error),
                    )
    return memoria


@pytest.fixture
def client():
    return TestClient(app)


# ======================================================================================
# El criterio: tres estados, en un solo sitio y versionado
# ======================================================================================

def test_el_criterio_esta_versionado():
    """Regla 4. No se persiste —se deriva al servir—, así que la versión se declara en código."""
    assert VERSION_LECTURA == "1.0.0"


def test_sin_analisis_es_sin_analizar():
    """Ni `None` ni un diccionario vacío pueden afirmar que se haya leído nada."""
    assert estado_lectura_pliego(None) == LECTURA_SIN_ANALIZAR
    assert estado_lectura_pliego({}) == LECTURA_SIN_ANALIZAR


def test_completado_es_leido():
    assert estado_lectura_pliego({"estado_analisis": "COMPLETADO"}) == LECTURA_LEIDO
    assert estado_lectura_pliego({"estado_analisis": "completado"}) == LECTURA_LEIDO


def test_degradado_no_es_lo_mismo_que_sin_analizar():
    """**El defecto que este paso repara, y es de fondo, no de estética.**

    Las dos situaciones pintaban la misma etiqueta —«Pliego sin analizar»— y exigen decisiones
    distintas: en una no hay nada que mirar; en la otra hubo un intento, hay una causa escrita
    en `error_detalle` y conviene abrir el pliego a mano antes de decidir.
    """
    degradado = estado_lectura_pliego({"estado_analisis": "DEGRADADO"})

    assert degradado == LECTURA_DEGRADADO
    assert degradado != LECTURA_SIN_ANALIZAR


def test_pendiente_es_sin_analizar_y_no_degradado():
    """`PENDIENTE` es una cola, no un dictamen fallido.

    Es el valor con el que `obtener_expedientes_pendientes_analisis()` selecciona trabajo. Que
    exista la fila no significa que se haya intentado nada, así que llamarlo «lectura degradada»
    sería inventar un intento que no ocurrió.
    """
    assert estado_lectura_pliego({"estado_analisis": "PENDIENTE"}) == LECTURA_SIN_ANALIZAR


def test_un_estado_desconocido_no_asciende_a_leido():
    """C6 aplicada a la pantalla: lo que no se pudo comprobar, no se afirma.

    Si mañana aparece un estado nuevo que nadie mapeó, el error barato es tratarlo como bueno y
    enseñar sus riesgos como si salieran del documento. La cautela cuesta un distintivo de más;
    la alternativa cuesta decidir sobre un pliego que nadie leyó.
    """
    assert estado_lectura_pliego({"estado_analisis": "MARCIANO"}) == LECTURA_DEGRADADO


def test_sin_estado_se_cree_al_propio_registro_pero_no_se_le_asciende():
    """`modo_degradado` es un derivado del mismo dato, no una segunda opinión.

    Sólo se consulta cuando `estado_analisis` no llegó. Y su ausencia tampoco basta para
    declarar leído: un registro que no dice de dónde sale no es una lectura verificada.
    """
    assert estado_lectura_pliego({"modo_degradado": True}) == LECTURA_DEGRADADO
    assert estado_lectura_pliego({"modo_degradado": False}) == LECTURA_SIN_ANALIZAR


# ======================================================================================
# El esquema y la API
# ======================================================================================

def test_el_esquema_expone_el_estado_como_campo_computado():
    """Se calcula al servir, como `titulo_corto`. No hay columna nueva ni migración."""
    schema = LicitacionSchema.model_validate({
        "id": "EXP-1",
        "titulo": "Servei de prova",
        "organo": "Ajuntament de prova",
        "analisis_semantico": {"estado_analisis": "COMPLETADO"},
    })

    assert schema.estado_lectura == LECTURA_LEIDO
    assert "estado_lectura" in schema.model_dump()


def test_el_esquema_sin_analisis_no_afirma_lectura():
    schema = LicitacionSchema.model_validate({
        "id": "EXP-2",
        "titulo": "Servei de prova",
        "organo": "Ajuntament de prova",
    })

    assert schema.estado_lectura == LECTURA_SIN_ANALIZAR


def test_la_api_sirve_los_tres_estados(client, db, monkeypatch, tmp_path):
    """Los tres, en la misma página del Funnel, cada uno con el suyo."""
    monkeypatch.setenv("DB_PATH_INCOOP", str(tmp_path / "analisis.db"))

    items = client.get("/api/v1/licitaciones?limit=100").json()["items"]
    por_id = {i["id"]: i["estado_lectura"] for i in items}

    assert por_id == {
        "EXP-LEIDO": LECTURA_LEIDO,
        "EXP-DEGRADADO": LECTURA_DEGRADADO,
        "EXP-SIN-ANALISIS": LECTURA_SIN_ANALIZAR,
    }


def test_la_ficha_de_detalle_declara_el_mismo_estado_que_el_listado(client, db, monkeypatch, tmp_path):
    """**La tabla y la ficha no pueden discrepar sobre el mismo expediente.**

    Antes la clasificación estaba escrita dos veces en el Cockpit, con la misma cadena de
    condiciones copiada. Dos copias de una regla son dos reglas en cuanto alguien toca una.
    """
    monkeypatch.setenv("DB_PATH_INCOOP", str(tmp_path / "analisis.db"))

    items = client.get("/api/v1/licitaciones?limit=100").json()["items"]
    for item in items:
        detalle = client.get(f"/api/v1/licitaciones/{item['id']}").json()
        assert detalle["estado_lectura"] == item["estado_lectura"], item["id"]


def test_el_degradado_llega_con_su_causa(client, db, monkeypatch, tmp_path):
    """Un aviso que no dice por qué obliga a ir a buscar el registro a mano."""
    monkeypatch.setenv("DB_PATH_INCOOP", str(tmp_path / "analisis.db"))

    detalle = client.get("/api/v1/licitaciones/EXP-DEGRADADO").json()

    assert detalle["estado_lectura"] == LECTURA_DEGRADADO
    assert "timeout de red" in (detalle["analisis_semantico"]["error_detalle"] or "")


# ======================================================================================
# H-50 · El CLI del Analista, que el Cockpit recomendaba mal
# ======================================================================================

def test_el_cli_del_analista_arranca_como_modulo():
    """H-50. La ficha de detalle recomendaba `python src/analista.py`, que **no funciona**.

    Rompe con `ModuleNotFoundError: No module named 'src'` — la misma trampa que la Convención
    C1 documenta para el pipeline. Y no era un detalle: ese texto es el origen de que dirección
    creyera que el análisis había que lanzarlo a mano, cuando el motor corre solo en cada
    corrida y eso es sólo la herramienta de inspección.

    Se ejercita el arranque **real**, en subproceso, que es lo que pide la Convención C4: una
    ruta de arranque que ninguna prueba recorre es una ruta que puede estar rota desde el primer
    día. `--help` sale por `argparse` antes de construir nada, así que no toca ni red ni base.
    """
    proceso = subprocess.run(
        [sys.executable, "-m", "src.analista", "--help"],
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
    )

    assert proceso.returncode == 0, proceso.stderr
    assert "--inspeccionar" in proceso.stdout


def test_la_documentacion_no_vuelve_a_recomendar_la_forma_rota():
    """Guarda de documentación, y es barata comparada con lo que costó el defecto.

    El README la recomendaba seis veces desde la Capa 5 y nadie la ejecutó nunca tal cual.
    """
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")

    # Se mira la forma **invocable** —una línea que empieza por el comando—, no la mención.
    # El propio aviso que explica el defecto tiene que poder nombrar la forma rota; lo que no
    # puede volver a aparecer es alguien pudiendo copiarla y pegarla de un bloque de comandos.
    invocaciones = [
        linea for linea in readme.splitlines()
        if linea.strip().startswith("python src/analista.py")
    ]

    assert invocaciones == [], invocaciones
    assert "python -m src.analista --healthcheck" in readme

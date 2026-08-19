"""Bloque 3, Paso 5 · El ámbito territorial (H-47).

El Funnel ofrecía lo que no es su negocio: licitaciones de toda España mezcladas con las
catalanas, sin distintivo. La decisión de dirección del 2026-08-18 fue **filtrar en pantalla**,
con Catalunya por defecto y un interruptor para ver el resto: no se toca la ingesta ni el
scoring, así no se pierde ni un dato y la decisión es reversible.

**Medido sobre la base real el 2026-08-19**: `nuts` está poblado en 74 de 74 expedientes, sin un
solo nulo, frente a `localidad`, que trae `N/A` en la mitad. Con el filtro puesto, el Funnel pasa
de 24 expedientes vivos a 9, y el volumen licitado de 7.294.613,49 € a 2.770.211,81 €.

Lo que estas regresiones fijan:

* El criterio vive en **un solo sitio** y está versionado; nadie vuelve a escribir `ES51%` a mano.
* Un ámbito no reconocido es **error tipado**, jamás «devuelve todo». Es la trampa peligrosa del
  paso: una errata en el nombre enseñaría la población entera bajo el rótulo de Catalunya.
* **Sin ámbito, las cifras salen idénticas** a las de antes de este paso. El filtro añade una
  opción, no cambia el sistema.
* **KPIs y Funnel obedecen al mismo criterio.** Si una mitad de la pantalla filtrara y la otra no,
  sería el defecto de poblaciones mezcladas de H-08 y H-21, otra vez.
* Las **alertas tempranas no obedecen**, y es decisión escrita: el Centinela lee DOGC y BOPB.
"""

import pytest
from fastapi.testclient import TestClient

from src import AMBITOS, VERSION_AMBITO, AmbitoDesconocido, clausula_ambito
from src.api.main import app
from src.memoria import Memoria

# Expedientes sembrados: cuatro catalanes por sus cuatro provincias, tres de fuera y uno
# extra-regio. Los NUTS son los reales que trae la base: `ES51` aparece de verdad, sin el
# quinto dígito, así que el criterio tiene que alcanzarlo igual que a `ES511`.
SEMILLA = [
    ("CAT-BCN", "ES511", 100_000.0, "Nueva"),
    ("CAT-GIR", "ES512", 200_000.0, "Estudiando"),
    ("CAT-LLE", "ES513", 300_000.0, "Nueva"),
    ("CAT-GEN", "ES51", 400_000.0, "Nueva"),
    ("FUERA-MAD", "ES300", 1_000_000.0, "Nueva"),
    ("FUERA-AND", "ES618", 2_000_000.0, "Estudiando"),
    ("FUERA-VAL", "ES523", 3_000_000.0, "Nueva"),
    ("FUERA-ZZZ", "ESZZZ", 4_000_000.0, "Nueva"),
]

PBL_CATALUNYA = 1_000_000.0   # 100 + 200 + 300 + 400 mil
PBL_TOTAL = 11_000_000.0


@pytest.fixture
def db(tmp_path):
    memoria = Memoria(db_path=str(tmp_path / "ambito.db"))
    memoria.setup_db()
    with memoria.conectar() as conn:
        with conn:
            for exp_id, nuts, pbl, estado in SEMILLA:
                conn.execute(
                    "INSERT INTO expedientes (id, titulo, organo, nuts, fuente, fecha_publicacion, "
                    "fecha_ingesta, last_seen_feed, feed_hash) VALUES (?, ?, ?, ?, 'PSCP', "
                    "'2026-08-01T00:00:00Z', '2026-08-01T00:00:00Z', '2026-08-01T00:00:00Z', ?);",
                    (exp_id, f"Licitació {exp_id}", "Órgano de prueba", nuts, f"h-{exp_id}"),
                )
                conn.execute(
                    "INSERT INTO lotes (expediente_id, lote_numero, titulo_lote, pbl, score_total, "
                    "estado_operativo, updated_at) VALUES (?, 1, ?, ?, 60, ?, '2026-08-01T00:00:00Z');",
                    (exp_id, f"Lote 1 de {exp_id}", pbl, estado),
                )
    return memoria


@pytest.fixture
def client():
    return TestClient(app)


# ======================================================================================
# El criterio: un solo sitio, versionado, y cerrado
# ======================================================================================

def test_el_criterio_vive_en_un_solo_sitio_y_esta_versionado():
    """Regla 4: un criterio operativo sin versión no se implementa.

    El ámbito **no se persiste** —no hay columna «es de Catalunya»— así que la versión no se
    estampa por fila: se declara en el código, igual que `VERSION_TITULO`. Cambiar el patrón
    NUTS obliga a mover esta constante.
    """
    assert VERSION_AMBITO == "1.0.0"
    assert AMBITOS == {"catalunya": "ES51%"}


def test_sin_ambito_no_hay_clausula():
    """La ausencia de ámbito es la ausencia de filtro, no un ámbito implícito."""
    assert clausula_ambito(None) == ("", [])


def test_el_ambito_admite_la_grafia_descuidada():
    """`Catalunya`, `CATALUNYA` y ` catalunya ` son el mismo ámbito.

    Es la lección de H-27, aplicada antes de que muerda: el mismo valor escrito de dos maneras
    hacía que el sistema fuera coherente por accidente. Toda comparación va normalizada.
    """
    for grafia in ("catalunya", "Catalunya", "CATALUNYA", "  catalunya  "):
        sql, params = clausula_ambito(grafia)
        assert params == ["ES51%"], grafia
        assert "LIKE ?" in sql


def test_un_ambito_desconocido_se_rechaza_y_no_devuelve_todo():
    """**La trampa de este paso, y la única que puede llegar a producción sin ruido.**

    Si `ambito=cataluña` —con eñe, que es como se escribe en castellano— se ignorase en
    silencio, la pantalla enseñaría los 24 expedientes de toda España bajo el rótulo de
    Catalunya y nadie tendría forma de notarlo. Degradar a un valor por defecto que el
    consumidor no puede distinguir de un resultado real está prohibido por la Convención C2.
    """
    for invalido in ("cataluña", "catalonia", "ES51", "españa", ""):
        with pytest.raises(AmbitoDesconocido):
            clausula_ambito(invalido)


def test_el_error_dice_cuales_son_los_validos():
    """Un error tipado que no dice qué se esperaba obliga a leer el código fuente."""
    with pytest.raises(AmbitoDesconocido, match="catalunya"):
        clausula_ambito("cataluña")


# ======================================================================================
# El Funnel
# ======================================================================================

def test_el_funnel_sin_ambito_devuelve_todo(db):
    """Por defecto la capa de datos no esconde nada. Quien filtra es la pantalla."""
    _, total = db.listar_expedientes_paginados(limit=100)
    assert total == len(SEMILLA)


def test_el_funnel_con_ambito_solo_devuelve_catalunya(db):
    items, total = db.listar_expedientes_paginados(limit=100, ambito="catalunya")

    assert total == 4
    assert {i["id"] for i in items} == {"CAT-BCN", "CAT-GIR", "CAT-LLE", "CAT-GEN"}


def test_el_criterio_alcanza_el_nuts_de_cuatro_digitos(db):
    """`ES51` a secas existe en la base real, y es Catalunya tanto como `ES511`.

    Un criterio escrito como igualdad exacta contra las cuatro provincias habría dejado fuera
    los cuatro expedientes que traen el código de la comunidad sin provincia. Es la misma
    familia de defecto que H-49: dos grafías del mismo dato que no coinciden.
    """
    items, _ = db.listar_expedientes_paginados(limit=100, ambito="catalunya")
    assert "CAT-GEN" in {i["id"] for i in items}


def test_el_ambito_no_arrastra_los_demas_filtros(db):
    """El ámbito se compone con los filtros que ya había, no los sustituye."""
    _, total = db.listar_expedientes_paginados(
        limit=100, ambito="catalunya", estado="estudiando"
    )
    assert total == 1, "Sólo CAT-GIR está Estudiando dentro de Catalunya"


def test_el_funnel_rechaza_un_ambito_desconocido(db):
    with pytest.raises(AmbitoDesconocido):
        db.listar_expedientes_paginados(limit=100, ambito="cataluña")


# ======================================================================================
# Los KPIs: la misma población que el Funnel
# ======================================================================================

def test_los_kpis_sin_ambito_no_cambian(db):
    """El paso añade una opción; sin pedirla, el sistema cuenta exactamente lo que contaba."""
    kpis = db.obtener_resumen_kpis()

    assert kpis["total_expedientes"] == len(SEMILLA)
    assert kpis["total_lotes"] == len(SEMILLA)
    assert kpis["volumen_total_pbl"] == PBL_TOTAL
    assert kpis["ambito"] is None


def test_los_kpis_obedecen_al_ambito(db):
    kpis = db.obtener_resumen_kpis(ambito="catalunya")

    assert kpis["total_expedientes"] == 4
    assert kpis["total_lotes"] == 4
    assert kpis["volumen_total_pbl"] == PBL_CATALUNYA
    assert kpis["licitaciones_estudio"] == 4, "Nueva y Estudiando son las dos del canal vivo"


def test_los_kpis_y_el_funnel_cuentan_lo_mismo(db):
    """**La comprobación que impide repetir H-08 y H-21.**

    El interruptor gobierna las dos pantallas a la vez, y son pantallas distintas con consultas
    distintas. Si una filtrara y la otra no, la cabecera hablaría de una población y su desglose
    de otra: es el defecto más caro y más repetido de este proyecto, y aquí queda amarrado.
    """
    for ambito in (None, "catalunya"):
        kpis = db.obtener_resumen_kpis(ambito=ambito)
        _, total_funnel = db.listar_expedientes_paginados(limit=100, ambito=ambito)
        assert kpis["total_expedientes"] == total_funnel, f"ámbito={ambito}"


def test_la_respuesta_declara_su_propia_poblacion(db):
    """Sin este campo, una API que ignorase el parámetro sería indetectable desde la pantalla."""
    kpis = db.obtener_resumen_kpis(ambito="Catalunya")

    assert kpis["ambito"] == "catalunya", "Normalizado, no el literal que llegó"
    assert kpis["version_ambito"] == VERSION_AMBITO


def test_la_memoria_comercial_obedece_al_ambito(db):
    """Ganadas, perdidas y win rate se filtran también, y no es una decisión obvia.

    `vista_win_rate` ignora `deleted_at` a propósito (H-30): lo archivado sigue contando, porque
    el archivado gobierna qué se ve y no qué ocurrió. Con el ámbito la respuesta es la contraria:
    una adjudicación de Aragón no pertenece al mismo relato que un Funnel filtrado a Catalunya, y
    dejarla dentro haría que el win rate hablara de una población distinta a la del volumen
    licitado que tiene al lado.
    """
    with db.conectar() as conn:
        with conn:
            conn.execute(
                "UPDATE lotes SET estado_operativo = 'Adjudicada' WHERE expediente_id = 'CAT-BCN';"
            )
            conn.execute(
                "UPDATE lotes SET estado_operativo = 'Perdida' WHERE expediente_id = 'FUERA-MAD';"
            )

    todo = db.obtener_resumen_kpis()
    catalunya = db.obtener_resumen_kpis(ambito="catalunya")

    assert (todo["licitaciones_ganadas"], todo["licitaciones_perdidas"]) == (1, 1)
    assert todo["win_rate_porcentaje"] == 50.0

    assert (catalunya["licitaciones_ganadas"], catalunya["licitaciones_perdidas"]) == (1, 0)
    assert catalunya["win_rate_porcentaje"] == 100.0, "La perdida de Madrid queda fuera"


def test_el_win_rate_filtrado_usa_las_mismas_columnas_que_la_vista(db):
    """No puede haber dos definiciones de «ganada».

    La consulta filtrada por ámbito y `vista_win_rate` salen de la misma constante compartida.
    Si alguien añadiera un estado a una sola de las dos, el Cockpit daría un win rate distinto
    según si el interruptor está puesto — y las dos cifras parecerían igual de auditadas.
    """
    with db.conectar() as conn:
        with conn:
            conn.execute(
                "UPDATE lotes SET estado_operativo = 'Adjudicada' WHERE expediente_id = 'CAT-BCN';"
            )
            conn.execute(
                "UPDATE lotes SET estado_operativo = 'Presentada' WHERE expediente_id = 'FUERA-MAD';"
            )
        fila = conn.execute(
            "SELECT ganadas, perdidas, pendientes_resolucion, tasa_exito_porcentaje "
            "FROM vista_win_rate;"
        ).fetchone()

    kpis = db.obtener_resumen_kpis()

    assert kpis["licitaciones_ganadas"] == fila[0]
    assert kpis["licitaciones_perdidas"] == fila[1]
    assert kpis["licitaciones_presentadas"] == fila[2]
    assert kpis["win_rate_porcentaje"] == pytest.approx(fila[3] or 0.0)


def test_las_alertas_tempranas_no_obedecen_al_ambito(db):
    """Decisión escrita del contrato: el Centinela lee DOGC y BOPB, catalanes de origen.

    Y filtrarlas por NUTS no es que sea redundante: es que no hay por dónde. La alerta temprana
    **precede al expediente** —ése es justamente su oficio, avisar antes de que exista—, así que
    no tiene `nuts`. Sólo queda `expediente_licitacion_vinculado`, que se rellena después y sólo
    si la licitación llega a publicarse: filtrar por ahí dejaría fuera exactamente las alertas
    que todavía sirven para algo.
    """
    with db.conectar() as conn:
        with conn:
            conn.execute(
                "INSERT INTO boletines_alertas (id_alerta, fuente, num_boletin, fecha_publicacion, "
                "organo_emisor, titulo_anuncio, estado_operativo, fecha_ingesta, updated_at) "
                "VALUES ('AL-1', 'DOGC', '9000', '2026-08-01', 'Ajuntament de prova', "
                "'Anunci de licitació futura', 'NUEVA_FASE_TEMPRANA', "
                "'2026-08-01T00:00:00Z', '2026-08-01T00:00:00Z');"
            )

    assert db.obtener_resumen_kpis()["alertas_tempranas_activas"] == 1
    assert db.obtener_resumen_kpis(ambito="catalunya")["alertas_tempranas_activas"] == 1


# ======================================================================================
# La API
# ======================================================================================

def test_la_api_sin_ambito_devuelve_todo(client, db, monkeypatch, tmp_path):
    """Lo contrario que `incluir_archivadas`, y a propósito.

    Lo archivado es un concepto de negocio —qué está en el canal principal—; el ámbito es una
    preferencia de quien mira. Una API que esconde por gusto propio produce la clase de sorpresa
    que este proyecto lleva cuatro capas persiguiendo.
    """
    monkeypatch.setenv("DB_PATH_INCOOP", str(tmp_path / "ambito.db"))

    assert client.get("/api/v1/licitaciones?limit=100").json()["total"] == len(SEMILLA)
    assert client.get("/api/v1/kpis").json()["ambito"] is None


def test_la_api_filtra_las_dos_pantallas(client, db, monkeypatch, tmp_path):
    monkeypatch.setenv("DB_PATH_INCOOP", str(tmp_path / "ambito.db"))

    listado = client.get("/api/v1/licitaciones?limit=100&ambito=catalunya").json()
    kpis = client.get("/api/v1/kpis?ambito=catalunya").json()

    assert listado["total"] == 4
    assert kpis["total_expedientes"] == 4
    assert kpis["ambito"] == "catalunya"
    assert kpis["version_ambito"] == VERSION_AMBITO


def test_la_api_devuelve_400_ante_un_ambito_desconocido(client, db, monkeypatch, tmp_path):
    """400 y no 503: es un error de quien pide, no una avería del servidor.

    Y sobre todo no un 200 con la población entera dentro, que es lo que ocurriría si el ámbito
    inválido se ignorase.
    """
    monkeypatch.setenv("DB_PATH_INCOOP", str(tmp_path / "ambito.db"))

    assert client.get("/api/v1/licitaciones?ambito=cataluña").status_code == 400
    assert client.get("/api/v1/kpis?ambito=cataluña").status_code == 400

"""H-59 · Una alerta diferida deja de estar diferida para siempre.

`ANALISIS_DIFERIDO_BOLETIN` significa *diferido*, no *descartado*. Pero el flujo del Centinela
es *ingesta → filtro → análisis → score → persistencia* y **sólo analiza lo que acaba de
ingerir**: ninguna consulta sacaba de `boletines_alertas` las alertas que degradaron para
volver a intentarlo.

**Se descubrió al verificar la reparación de H-56.** El motor ya emitía dictámenes completos
—comprobado contra el modelo real— y las **cinco** alertas del canal seguían sin ninguno, y lo
habrían seguido estando para siempre. *Reparar el motor no rescata a quien se quedó en la
cuneta mientras estaba averiado.*

Es la **cuarta** vez que este proyecto pisa la misma forma: H-33, H-53 cara B con
`OCR_DIFERIDO`, H-58 con `DESCARGANDO` y ésta. La invariante que lo impide dejó de estar sólo
escrita y vive ahora en `tests/test_vocabularios_de_estado.py`.

⚠️ **El tope de reintentos entra desde el primer día, y es la lección de H-58 aplicada antes
de repetirla**: sin él, una alerta que degradara siempre se reintentaría en cada corrida para
siempre, gastando cuota real. Sería cambiar un agujero por un bucle.
"""

import json

import pytest

from src.centinela import AlertaBoletinDTO, DictamenCentinelaDTO
from src.memoria import ESQUEMA_VERSION_ACTUAL, Memoria


# =====================================================================
# ANDAMIAJE
# =====================================================================

@pytest.fixture
def base(tmp_path):
    db = Memoria(db_path=str(tmp_path / "licitaciones.db"))
    db.setup_db()
    return db


def alerta(id_alerta="a1", estado="ANALISIS_DIFERIDO_BOLETIN"):
    a = AlertaBoletinDTO(
        fuente="BOPB",
        num_boletin="2026-08-27",
        fecha_publicacion="2026-08-27T07:00:00Z",
        organo_emisor="Ajuntament de Prova",
        municipio="Prova",
        titulo_anuncio="Pressupost per al servei d'escoles bressol",
        texto_sumario="Dotació per a escoles bressol.",
        id_alerta=id_alerta,
        estado_operativo=estado,
    )
    return a


def intentos_de(base, id_alerta):
    with base.conectar() as conn:
        fila = conn.execute(
            "SELECT intentos_analisis FROM boletines_alertas WHERE id_alerta = ?;", (id_alerta,)
        ).fetchone()
    return fila[0]


# =====================================================================
# 1 · EL ESQUEMA v9
# =====================================================================

def test_el_esquema_esta_en_v9(base):
    with base.conectar() as conn:
        version = conn.execute("SELECT version FROM metadata;").fetchone()[0]
    assert version == ESQUEMA_VERSION_ACTUAL == 9


def test_las_alertas_nacen_con_cero_intentos(base):
    base.guardar_alerta_boletin(alerta())

    assert intentos_de(base, "a1") == 0


def test_una_base_v8_migra_sin_perder_alertas(tmp_path):
    """La migración es aditiva: las alertas que ya existen conservan su fila.

    Y nacen con `intentos_analisis = 0`, que es lo correcto: son alertas analizadas cuando el
    motor estaba roto por H-56, así que **merecen sus tres intentos con el motor reparado**.
    Ponerlas a 3 las daría por perdidas por un fallo que no era suyo.
    """
    ruta = str(tmp_path / "licitaciones.db")
    vieja = Memoria(db_path=ruta)
    vieja.setup_db()
    vieja.guardar_alerta_boletin(alerta("preexistente"))

    # Se retrocede el marcador de versión para forzar la migración al reabrir.
    with vieja.conectar() as conn:
        with conn:
            conn.execute("UPDATE metadata SET version = 8;")

    migrada = Memoria(db_path=ruta)
    migrada.setup_db()

    with migrada.conectar() as conn:
        version = conn.execute("SELECT version FROM metadata;").fetchone()[0]
    assert version == 9
    assert intentos_de(migrada, "preexistente") == 0


# =====================================================================
# 2 · LA RECOGIDA
# =====================================================================

def test_una_alerta_diferida_vuelve_a_la_cola(base):
    """**La regresión central.** Es lo que no existía y dejaba las 5 alertas sin dictamen."""
    base.guardar_alerta_boletin(alerta())

    recogidas = base.obtener_alertas_diferidas()

    assert [a.id_alerta for a in recogidas] == ["a1"]


def test_las_alertas_ya_resueltas_no_se_reanalizan(base):
    """Reanalizar lo que ya tiene dictamen gastaría cuota para no cambiar nada."""
    base.guardar_alerta_boletin(alerta("resuelta", estado="NUEVA_FASE_TEMPRANA"))
    base.guardar_alerta_boletin(alerta("descartada", estado="DESCARTADA_POR_REGLAS"))

    assert base.obtener_alertas_diferidas() == []


def test_una_alerta_que_agoto_sus_intentos_no_se_recoge(base):
    """El agujero no se cambia por un bucle. Es la lección de H-58."""
    base.guardar_alerta_boletin(alerta())
    for _ in range(3):
        base.anotar_intento_de_analisis("a1")

    assert base.obtener_alertas_diferidas() == []
    assert intentos_de(base, "a1") == 3


def test_con_un_intento_gastado_todavia_se_recoge(base):
    """El tope es 3, no 1: un fallo puntual de red no puede condenar una alerta."""
    base.guardar_alerta_boletin(alerta())
    base.anotar_intento_de_analisis("a1")

    assert [a.id_alerta for a in base.obtener_alertas_diferidas()] == ["a1"]


def test_el_tope_es_configurable_por_el_llamador(base):
    base.guardar_alerta_boletin(alerta())
    base.anotar_intento_de_analisis("a1")

    assert base.obtener_alertas_diferidas(max_intentos=1) == []
    assert len(base.obtener_alertas_diferidas(max_intentos=2)) == 1


def test_una_alerta_anterior_a_v9_con_intentos_nulos_se_recoge(base):
    """`COALESCE` en la consulta: un NULL heredado de la migración no puede excluirla.

    Sin él, `NULL < 3` es `NULL` —no es cierto— y las alertas migradas quedarían fuera de la
    cola en silencio. Sería el mismo defecto que se está reparando, reintroducido por la
    propia reparación.
    """
    base.guardar_alerta_boletin(alerta())
    with base.conectar() as conn:
        with conn:
            conn.execute("UPDATE boletines_alertas SET intentos_analisis = NULL WHERE id_alerta = 'a1';")

    assert [a.id_alerta for a in base.obtener_alertas_diferidas()] == ["a1"]


# =====================================================================
# 3 · LA RECONSTRUCCIÓN DESDE LA BASE
# =====================================================================

def test_la_alerta_recogida_conserva_lo_que_hacia_falta_para_reanalizarla(base):
    """Sin título ni sumario no hay nada que analizar: la recogida sería inútil."""
    base.guardar_alerta_boletin(alerta())

    (recogida,) = base.obtener_alertas_diferidas()

    assert recogida.titulo_anuncio == "Pressupost per al servei d'escoles bressol"
    assert recogida.texto_sumario == "Dotació per a escoles bressol."
    assert recogida.fuente == "BOPB"


def test_el_contador_sube_de_uno_en_uno(base):
    base.guardar_alerta_boletin(alerta())

    base.anotar_intento_de_analisis("a1")
    base.anotar_intento_de_analisis("a1")

    assert intentos_de(base, "a1") == 2


def test_anotar_el_intento_de_una_alerta_no_toca_a_las_demas(base):
    base.guardar_alerta_boletin(alerta("a1"))
    base.guardar_alerta_boletin(alerta("a2"))

    base.anotar_intento_de_analisis("a1")

    assert intentos_de(base, "a1") == 1
    assert intentos_de(base, "a2") == 0

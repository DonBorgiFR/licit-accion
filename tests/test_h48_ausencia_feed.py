"""H-48 · La ausencia del feed no prueba que una licitación haya terminado.

`soft_delete_obsoletos()` daba por expirada toda licitación `Nueva` ausente del feed **sin
consultar su fecha límite**. Las tres fuentes del proyecto son ventanas de publicaciones
recientes —la catalana pide literalmente las 100 últimas por fecha de publicación, y los feeds
ATOM se descargan sin seguir la paginación—, así que salir de la ventana ocurre por antigüedad
y no por haber terminado.

**Medido sobre la base real el 2026-08-19**: 45 lotes archivados como expirados con el plazo
todavía abierto, **19.986.870,63 €** de PBL, y las dos oportunidades mejor puntuadas de todo el
histórico (82 puntos) invisibles en el Funnel mientras el máximo visible era 71.

Lo que estas regresiones fijan:

* Una `Nueva` ausente **con el plazo abierto** conserva su estado. Es el defecto.
* Una `Nueva` ausente **con el plazo vencido** sigue archivándose. La reparación no desactiva
  el barrido, sólo le exige mirar el calendario.
* Sin fecha legible **no se archiva**: el daño es asimétrico y está medido.
* La rama de *posible anulación* **no se toca** — la medición la exculpó: los 48 archivados
  salieron de la rama `Nueva` y ésta no se ha disparado nunca.
"""

import json
from datetime import datetime, timedelta, timezone

import pytest

from src.memoria import (
    PLAZO_ABIERTO,
    PLAZO_ILEGIBLE,
    PLAZO_VENCIDO,
    Memoria,
    clasificar_plazo,
)

AHORA = datetime.now(timezone.utc)


def en_dias(dias: int) -> str:
    return (AHORA + timedelta(days=dias)).strftime("%Y-%m-%dT%H:%M:%SZ")


@pytest.fixture
def memoria(tmp_path):
    db = Memoria(db_path=str(tmp_path / "licitaciones.db"))
    db.setup_db()
    return db


def sembrar_ausente(memoria, exp_id, estado, fecha_limite):
    """Un expediente que el feed ya no trae: `last_seen_feed` anterior a la corrida."""
    with memoria.conectar() as conn:
        with conn:
            conn.execute(
                "INSERT INTO expedientes (id, titulo, fecha_ingesta, fecha_limite, last_seen_feed) "
                "VALUES (?, ?, ?, ?, ?);",
                (exp_id, f"Expediente {exp_id}", en_dias(-30), fecha_limite, en_dias(-30)),
            )
            conn.execute(
                "INSERT INTO lotes (expediente_id, lote_numero, titulo_lote, estado_operativo) "
                "VALUES (?, 1, ?, ?);",
                (exp_id, f"Lote 1 de {exp_id}", estado),
            )


def leer_lote(memoria, exp_id):
    with memoria.conectar() as conn:
        conn.row_factory = None
        fila = conn.execute(
            "SELECT estado_operativo, deleted_at, deleted_reason FROM lotes WHERE expediente_id = ?;",
            (exp_id,),
        ).fetchone()
    return {"estado": fila[0], "deleted_at": fila[1], "deleted_reason": fila[2]}


def barrer(memoria, run_id=None):
    """Ejecuta el barrido como lo hace el pipeline: la corrida empieza ahora."""
    return memoria.soft_delete_obsoletos(
        datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), run_id=run_id
    )


# ======================================================================================
# El defecto: archivar una oportunidad viva
# ======================================================================================

def test_una_nueva_ausente_con_el_plazo_abierto_no_se_archiva(memoria):
    """El caso que costó 19.986.870,63 € de PBL escondidos.

    Es exactamente la situación de las dos licitaciones de 82 puntos: publicadas hace semanas,
    fuera ya de la ventana de 100 del feed catalán, y con el plazo de presentación abierto
    hasta septiembre.
    """
    sembrar_ausente(memoria, "EXP-VIVA", "Nueva", en_dias(26))

    barrer(memoria)

    lote = leer_lote(memoria, "EXP-VIVA")
    assert lote["estado"] == "Nueva", "Una licitación con el plazo abierto sigue viva"
    assert lote["deleted_at"] is None, "No puede salir del canal principal"
    assert lote["deleted_reason"] is None


def test_una_nueva_ausente_con_el_plazo_vencido_si_se_archiva(memoria):
    """La reparación no desactiva el barrido: le exige mirar el calendario.

    Sin esta prueba, "arreglar" H-48 dejando de archivar nunca pasaría igual de verde.
    """
    sembrar_ausente(memoria, "EXP-MUERTA", "Nueva", en_dias(-5))

    barrer(memoria)

    lote = leer_lote(memoria, "EXP-MUERTA")
    assert lote["estado"] == "Inactiva"
    assert lote["deleted_at"] is not None
    assert "Expirado" in lote["deleted_reason"]


@pytest.mark.parametrize("fecha", [None, "", "N/A", "sin fecha", "2026"])
def test_sin_fecha_limite_legible_no_se_archiva(memoria, fecha):
    """Ante la duda no se archiva, porque el daño es asimétrico y está medido.

    Mostrar de más una licitación muerta cuesta una línea en pantalla. Esconder las vivas costó
    casi 20 M€ y las dos mejores puntuaciones de la base. `"2026"` entra aquí a propósito: una
    fecha truncada comparada como cadena daba `"2026" < "2026-08-19"`, es decir, **vencida**.
    """
    sembrar_ausente(memoria, "EXP-SIN-FECHA", "Nueva", fecha)

    barrer(memoria)

    assert leer_lote(memoria, "EXP-SIN-FECHA")["estado"] == "Nueva"
    assert leer_lote(memoria, "EXP-SIN-FECHA")["deleted_at"] is None


# ======================================================================================
# Lo que NO cambia: la rama de posible anulación
# ======================================================================================

def test_la_rama_de_anulacion_sigue_intacta(memoria):
    """Un lote que alguien ya tocó y desaparece antes de su plazo: sigue siendo alerta.

    La medición exculpó a esta rama —de los 48 lotes archivados por ausencia, los 48 salieron
    de la rama `Nueva`, y ésta no se ha disparado nunca—, así que la reparación no la toca. El
    contrato de la Capa 9 cita literalmente este escenario.
    """
    sembrar_ausente(memoria, "EXP-OFERTADA", "Presentada", en_dias(30))

    resumen = barrer(memoria)

    lote = leer_lote(memoria, "EXP-OFERTADA")
    assert lote["estado"] == "Anulada_Administracion"
    assert "Posible anulación" in lote["deleted_reason"]
    assert resumen["anulaciones"] == 1


def test_un_lote_ya_archivado_no_se_vuelve_a_tocar(memoria):
    """El barrido es idempotente: pasar dos veces no reescribe fechas ni motivos."""
    sembrar_ausente(memoria, "EXP-YA", "Nueva", en_dias(-5))

    barrer(memoria)
    primero = leer_lote(memoria, "EXP-YA")
    barrer(memoria)
    segundo = leer_lote(memoria, "EXP-YA")

    assert primero == segundo


# ======================================================================================
# El resumen y su rastro (Reglas 3 y 7)
# ======================================================================================

def test_el_barrido_cuenta_lo_que_conserva_y_no_solo_lo_que_archiva(memoria):
    """H-48 vivió meses porque este barrido no contaba nada.

    Lo que de verdad importa vigilar no es cuántas archiva, sino **cuántas vivas conserva**:
    si ese número se desploma un día, algo ha vuelto a romperse.
    """
    sembrar_ausente(memoria, "EXP-A", "Nueva", en_dias(20))
    sembrar_ausente(memoria, "EXP-B", "Nueva", en_dias(10))
    sembrar_ausente(memoria, "EXP-C", "Nueva", en_dias(-3))
    sembrar_ausente(memoria, "EXP-D", "Nueva", "N/A")

    resumen = barrer(memoria)

    assert resumen["revisados"] == 4
    assert resumen["ignorados_plazo_abierto"] == 2
    assert resumen["expirados"] == 1
    assert resumen["ignorados_sin_fecha"] == 1
    assert resumen["anulaciones"] == 0


def test_conservar_una_licitacion_viva_deja_rastro_en_el_jsonl(memoria):
    """Sin evento, la decisión de no archivar sería invisible — igual que lo fue el defecto."""
    sembrar_ausente(memoria, "EXP-RASTRO", "Nueva", en_dias(15))

    barrer(memoria, run_id=77)

    # Se lee por el lector canónico y no abriendo el fichero a mano: desde el Paso 9 de la
    # Capa 10 el rastro tiene una sola gramática y una sola puerta de lectura (H-39).
    import os

    from src.rastro import leer_rastro

    ruta = os.path.join(os.path.dirname(memoria.db_path), "pipeline.jsonl")
    eventos = leer_rastro(ruta=ruta).eventos

    nombres = [e.evento for e in eventos]
    assert "RADAR_AUSENCIA_IGNORADA_PLAZO_ABIERTO" in nombres
    assert "RADAR_OBSOLESCENCIA_RESUMEN" in nombres

    conservada = next(e for e in eventos if e.evento == "RADAR_AUSENCIA_IGNORADA_PLAZO_ABIERTO")
    assert conservada.datos["expediente_id"] == "EXP-RASTRO"
    assert conservada.run_id == 77


def test_sin_run_id_no_se_escribe_jsonl_pero_se_decide_igual(memoria):
    """El barrido tiene que poder invocarse fuera de una corrida sin ensuciar la auditoría.

    Es la misma doctrina del healthcheck del Paso 2 de la Capa 10: comprobar no modifica nada,
    y quien decide dejar rastro es el llamador.
    """
    sembrar_ausente(memoria, "EXP-SIN-RUN", "Nueva", en_dias(12))

    resumen = barrer(memoria, run_id=None)

    assert resumen["ignorados_plazo_abierto"] == 1
    assert leer_lote(memoria, "EXP-SIN-RUN")["estado"] == "Nueva"


# ======================================================================================
# El clasificador, por separado
# ======================================================================================

@pytest.mark.parametrize(
    "fecha,esperado",
    [
        ("2099-01-01T00:00:00Z", PLAZO_ABIERTO),
        ("2000-01-01T00:00:00Z", PLAZO_VENCIDO),
        ("2026-09-14", PLAZO_ABIERTO),
        (None, PLAZO_ILEGIBLE),
        ("", PLAZO_ILEGIBLE),
        ("   ", PLAZO_ILEGIBLE),
        ("N/A", PLAZO_ILEGIBLE),
        ("n/a", PLAZO_ILEGIBLE),
        ("2026", PLAZO_ILEGIBLE),
        ("xyz", PLAZO_ILEGIBLE),
        ("14/09/2026", PLAZO_ILEGIBLE),
    ],
)
def test_clasificar_plazo(fecha, esperado):
    """Tres valores y no un booleano: "no se pudo leer" no es "venció".

    `"xyz"` y `"14/09/2026"` son los casos que delatan por qué: comparados como cadena contra
    una fecha ISO dan `> `, es decir **futuro**, y una comparación booleana los daría por
    abiertos por accidente en vez de por criterio.
    """
    assert clasificar_plazo(fecha, "2026-08-19T12:00:00Z") == esperado

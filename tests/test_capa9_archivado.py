"""Motor de archivado y rastro del ciclo de vida — Capa 9, Paso 4.

Archivar es la operación reversible del Depurador: escribe `deleted_at` y saca el lote del
canal principal sin borrar nada. Las regresiones que importan de verdad son tres, y ninguna
comprueba que "archive bien":

* **La memoria comercial sigue contando después de archivarse** (H-30). `vista_win_rate`
  excluía lo archivado, de modo que archivar un lote `Adjudicada` —cosa que ahora hace el
  motor por política— habría vaciado el win-rate sin borrar un solo dato.
* **El estado operativo no se toca jamás.** Es la primera transición prohibida del contrato.
* **Los cambios de estado dejan rastro** (H-31). Sin él, el Paso 6 no podrá distinguir un
  lote que llegó a `Presentada` de una oportunidad que nadie miró, y la invariante que
  protege la memoria comercial sería incomprobable.
"""

import json
import textwrap
from datetime import datetime, timedelta, timezone

import pytest

from src.depurador import (
    MOTIVO_FECHA_LIMITE,
    MOTIVO_SIN_FECHA_LIMITE,
    Depurador,
)
from src.memoria import MARCA_LOG_ESTADO, Memoria
from src.retencion import (
    NOMBRE_FICHERO,
    PoliticaArchivado,
    PoliticaRetencion,
    PoliticaRetencionInvalida,
    cargar_politica,
)

AHORA = datetime(2026, 8, 7, 12, 0, 0, tzinfo=timezone.utc)


def hace_dias(dias: int) -> str:
    return (AHORA - timedelta(days=dias)).strftime("%Y-%m-%dT%H:%M:%SZ")


def politica_de_prueba(dias=60, estados=("nueva", "descartada", "estudiando", "adjudicada", "perdida"), cascada=True):
    return PoliticaRetencion(
        version="1.1.0-test",
        documentos_dias=180,
        backups_dias=7,
        archivado=PoliticaArchivado(
            dias_tras_fecha_limite=dias,
            estados_archivables=tuple(estados),
            archivar_expediente_con_todos_sus_lotes=cascada,
        ),
    )


@pytest.fixture
def memoria(tmp_path):
    db = Memoria(db_path=str(tmp_path / "licitaciones.db"))
    db.setup_db()
    return db


def sembrar(memoria, exp_id, lotes, fecha_limite=None, fecha_ingesta=None):
    """Inserta un expediente con sus lotes. `lotes` es una lista de (numero, estado)."""
    with memoria.conectar() as conn:
        with conn:
            conn.execute(
                "INSERT INTO expedientes (id, titulo, fecha_ingesta, fecha_limite) VALUES (?, ?, ?, ?);",
                (exp_id, f"Expediente {exp_id}", fecha_ingesta or hace_dias(400), fecha_limite),
            )
            for numero, estado in lotes:
                conn.execute(
                    "INSERT INTO lotes (expediente_id, lote_numero, titulo_lote, estado_operativo) "
                    "VALUES (?, ?, ?, ?);",
                    (exp_id, numero, f"Lote {numero} de {exp_id}", estado),
                )


def leer_lote(memoria, exp_id, numero):
    with memoria.conectar() as conn:
        conn.row_factory = None
        fila = conn.execute(
            "SELECT estado_operativo, deleted_at, deleted_reason FROM lotes "
            "WHERE expediente_id = ? AND lote_numero = ?;",
            (exp_id, numero),
        ).fetchone()
    return {"estado": fila[0], "deleted_at": fila[1], "deleted_reason": fila[2]}


# ======================================================================================
# El bloque `archivado` de la política
# ======================================================================================

def test_la_politica_del_proyecto_declara_los_criterios_acordados():
    """60 días y cinco estados, por decisión de dirección del 2026-08-07."""
    politica = cargar_politica()
    assert politica.archivado is not None
    assert politica.archivado.dias_tras_fecha_limite == 60
    assert set(politica.archivado.estados_archivables) == {
        "nueva", "descartada", "estudiando", "adjudicada", "perdida"
    }
    assert politica.archivado.archivar_expediente_con_todos_sus_lotes is True


def test_presentada_nunca_es_archivable():
    """Una oferta entregada y sin resolver es lo más vivo del embudo."""
    politica = cargar_politica()
    assert "presentada" not in politica.archivado.estados_archivables


def escribir_politica(tmp_path, contenido):
    ruta = tmp_path / NOMBRE_FICHERO
    ruta.write_text(textwrap.dedent(contenido), encoding="utf-8")
    return str(ruta)


BASE_SIN_ARCHIVADO = """
    retencion:
      version: "1.0.0"
      documentos_dias: 180
      backups_dias: 7
    """


def test_sin_bloque_archivado_la_politica_sigue_siendo_valida(tmp_path):
    """Ausencia de criterio no es un error: es "no archives nada".

    La purga documental debe seguir funcionando aunque nadie haya declarado archivado.
    """
    politica = cargar_politica(escribir_politica(tmp_path, BASE_SIN_ARCHIVADO))
    assert politica.archivado is None
    assert politica.documentos_dias == 180


def test_un_bloque_archivado_mal_formado_se_rechaza_entero(tmp_path):
    """Presente pero incoherente sí es un error: no se adivina lo que quiso decir."""
    ruta = escribir_politica(tmp_path, """
        retencion:
          version: "1.0.0"
          documentos_dias: 180
          backups_dias: 7
          archivado: "60 dias"
        """)
    with pytest.raises(PoliticaRetencionInvalida, match="mapa de claves"):
        cargar_politica(ruta)


def test_declarar_presentada_como_archivable_se_rechaza(tmp_path):
    ruta = escribir_politica(tmp_path, """
        retencion:
          version: "1.0.0"
          documentos_dias: 180
          backups_dias: 7
          archivado:
            dias_tras_fecha_limite: 60
            estados_archivables: ["Nueva", "Presentada"]
            archivar_expediente_con_todos_sus_lotes: true
        """)
    with pytest.raises(PoliticaRetencionInvalida, match="trabajo en curso"):
        cargar_politica(ruta)


def test_un_estado_inexistente_se_rechaza(tmp_path):
    """Un estado mal escrito no archivaría nada, y el fallo pasaría inadvertido."""
    ruta = escribir_politica(tmp_path, """
        retencion:
          version: "1.0.0"
          documentos_dias: 180
          backups_dias: 7
          archivado:
            dias_tras_fecha_limite: 60
            estados_archivables: ["Nuevaa"]
            archivar_expediente_con_todos_sus_lotes: true
        """)
    with pytest.raises(PoliticaRetencionInvalida, match="no es un estado operativo reconocido"):
        cargar_politica(ruta)


def test_una_lista_vacia_de_estados_se_rechaza(tmp_path):
    """Vacío no significa "archívalo todo": significa que no hay criterio."""
    ruta = escribir_politica(tmp_path, """
        retencion:
          version: "1.0.0"
          documentos_dias: 180
          backups_dias: 7
          archivado:
            dias_tras_fecha_limite: 60
            estados_archivables: []
            archivar_expediente_con_todos_sus_lotes: true
        """)
    with pytest.raises(PoliticaRetencionInvalida, match="lista no vacía"):
        cargar_politica(ruta)


@pytest.mark.parametrize("valor", ["0", "-5", "'60'"])
def test_un_plazo_de_archivado_invalido_se_rechaza(tmp_path, valor):
    ruta = escribir_politica(tmp_path, f"""
        retencion:
          version: "1.0.0"
          documentos_dias: 180
          backups_dias: 7
          archivado:
            dias_tras_fecha_limite: {valor}
            estados_archivables: ["Nueva"]
            archivar_expediente_con_todos_sus_lotes: true
        """)
    with pytest.raises(PoliticaRetencionInvalida):
        cargar_politica(ruta)


def test_la_cascada_debe_declararse_de_forma_explicita(tmp_path):
    ruta = escribir_politica(tmp_path, """
        retencion:
          version: "1.0.0"
          documentos_dias: 180
          backups_dias: 7
          archivado:
            dias_tras_fecha_limite: 60
            estados_archivables: ["Nueva"]
            archivar_expediente_con_todos_sus_lotes: "si"
        """)
    with pytest.raises(PoliticaRetencionInvalida, match="true o false"):
        cargar_politica(ruta)


# ======================================================================================
# El motor: qué archiva y qué no
# ======================================================================================

def test_archiva_lo_vencido_hace_mas_del_plazo(memoria):
    sembrar(memoria, "EXP-VIEJO", [(1, "Nueva")], fecha_limite=hace_dias(90))

    resultado = Depurador(memoria, politica_de_prueba()).archivar(ahora=AHORA)

    assert resultado.ejecutado is True
    assert resultado.lotes_archivados == 1
    assert resultado.por_motivo[MOTIVO_FECHA_LIMITE] == 1
    assert leer_lote(memoria, "EXP-VIEJO", 1)["deleted_at"] is not None


def test_no_archiva_lo_vencido_hace_menos_del_plazo(memoria):
    """El margen es el margen: 30 días después de la fecha límite todavía se ve."""
    sembrar(memoria, "EXP-RECIENTE", [(1, "Nueva")], fecha_limite=hace_dias(30))

    resultado = Depurador(memoria, politica_de_prueba()).archivar(ahora=AHORA)

    assert resultado.lotes_archivados == 0
    assert leer_lote(memoria, "EXP-RECIENTE", 1)["deleted_at"] is None


def test_no_archiva_una_oferta_presentada_por_muy_vencida_que_este(memoria):
    """Está esperando adjudicación: archivarla escondería el trabajo en curso."""
    sembrar(memoria, "EXP-PRESENTADA", [(1, "Presentada")], fecha_limite=hace_dias(400))

    resultado = Depurador(memoria, politica_de_prueba()).archivar(ahora=AHORA)

    assert resultado.lotes_archivados == 0
    assert leer_lote(memoria, "EXP-PRESENTADA", 1)["deleted_at"] is None


def test_el_archivado_no_toca_jamas_el_estado_operativo(memoria):
    """Primera transición prohibida del contrato: `estado_operativo` no es su columna."""
    sembrar(memoria, "EXP-ADJ", [(1, "Adjudicada")], fecha_limite=hace_dias(200))

    Depurador(memoria, politica_de_prueba()).archivar(ahora=AHORA)

    lote = leer_lote(memoria, "EXP-ADJ", 1)
    assert lote["estado"] == "Adjudicada"
    assert lote["deleted_at"] is not None


def test_la_grafia_del_estado_no_decide_si_se_archiva(memoria):
    """H-27: la misma columna contiene 'Nueva' y 'nueva'. Comparar contra el literal
    devolvería cero filas sin que nada fallase."""
    sembrar(memoria, "EXP-GRAFIA", [(1, "Nueva"), (2, "nueva"), (3, "  NUEVA  ")],
            fecha_limite=hace_dias(120))

    resultado = Depurador(memoria, politica_de_prueba()).archivar(ahora=AHORA)

    assert resultado.lotes_archivados == 3


def test_sin_fecha_limite_conocida_se_recurre_a_la_de_ingesta(memoria):
    """Y se guarda con un motivo distinto: no es una caducidad normal, es un aviso
    sobre la calidad del feed de origen."""
    sembrar(memoria, "EXP-NA", [(1, "Nueva")], fecha_limite="N/A", fecha_ingesta=hace_dias(300))

    resultado = Depurador(memoria, politica_de_prueba()).archivar(ahora=AHORA)

    assert resultado.por_motivo[MOTIVO_SIN_FECHA_LIMITE] == 1
    assert resultado.por_motivo[MOTIVO_FECHA_LIMITE] == 0
    assert "sin fecha límite conocida" in leer_lote(memoria, "EXP-NA", 1)["deleted_reason"]


def test_sin_fecha_limite_y_recien_ingestado_no_se_archiva(memoria):
    sembrar(memoria, "EXP-NA-NUEVO", [(1, "Nueva")], fecha_limite=None, fecha_ingesta=hace_dias(5))

    resultado = Depurador(memoria, politica_de_prueba()).archivar(ahora=AHORA)

    assert resultado.lotes_archivados == 0


# ======================================================================================
# Idempotencia (Regla 10)
# ======================================================================================

def test_archivar_dos_veces_no_cuenta_dos_veces_ni_reescribe_la_fecha(memoria):
    sembrar(memoria, "EXP-IDEM", [(1, "Nueva")], fecha_limite=hace_dias(120))
    depurador = Depurador(memoria, politica_de_prueba())

    primera = depurador.archivar(ahora=AHORA)
    marca_original = leer_lote(memoria, "EXP-IDEM", 1)["deleted_at"]
    segunda = depurador.archivar(ahora=AHORA + timedelta(days=3))

    assert primera.lotes_archivados == 1
    assert segunda.lotes_archivados == 0
    assert leer_lote(memoria, "EXP-IDEM", 1)["deleted_at"] == marca_original


# ======================================================================================
# Cascada al expediente
# ======================================================================================

def test_el_expediente_se_archiva_solo_cuando_ningun_lote_sigue_vivo(memoria):
    """El expediente es el contenedor: mientras un lote siga en juego, sigue en juego."""
    sembrar(memoria, "EXP-MIXTO", [(1, "Nueva"), (2, "Presentada")], fecha_limite=hace_dias(120))

    resultado = Depurador(memoria, politica_de_prueba()).archivar(ahora=AHORA)

    assert resultado.lotes_archivados == 1
    assert resultado.expedientes_archivados == 0
    with memoria.conectar() as conn:
        assert conn.execute(
            "SELECT deleted_at FROM expedientes WHERE id = 'EXP-MIXTO';"
        ).fetchone()[0] is None


def test_el_expediente_se_archiva_cuando_todos_sus_lotes_lo_estan(memoria):
    sembrar(memoria, "EXP-COMPLETO", [(1, "Nueva"), (2, "Descartada")], fecha_limite=hace_dias(120))

    resultado = Depurador(memoria, politica_de_prueba()).archivar(ahora=AHORA)

    assert resultado.lotes_archivados == 2
    assert resultado.expedientes_archivados == 1


def test_un_expediente_sin_lotes_no_se_archiva_por_estar_vacio(memoria):
    """Sin el EXISTS, un expediente sin hijos cumpliría el NOT EXISTS de forma trivial."""
    with memoria.conectar() as conn:
        with conn:
            conn.execute(
                "INSERT INTO expedientes (id, titulo, fecha_ingesta, fecha_limite) "
                "VALUES ('EXP-VACIO', 'Sin lotes', ?, ?);",
                (hace_dias(400), hace_dias(400)),
            )

    Depurador(memoria, politica_de_prueba()).archivar(ahora=AHORA)

    with memoria.conectar() as conn:
        assert conn.execute(
            "SELECT deleted_at FROM expedientes WHERE id = 'EXP-VACIO';"
        ).fetchone()[0] is None


# ======================================================================================
# H-30 · La memoria comercial sobrevive al archivado
# ======================================================================================

def test_el_win_rate_no_cambia_al_archivar_lo_adjudicado_y_lo_perdido(memoria):
    """El defecto que habría convertido el archivado en destrucción de indicadores.

    `vista_win_rate` filtraba `deleted_at IS NULL`. Con `Adjudicada` y `Perdida` entre los
    estados archivables, la primera corrida del motor habría dejado ganadas y perdidas a
    cero y la tasa de éxito en blanco, sin borrar un solo dato.
    """
    sembrar(memoria, "EXP-GANADA", [(1, "adjudicada")], fecha_limite=hace_dias(300))
    sembrar(memoria, "EXP-PERDIDA", [(1, "perdida")], fecha_limite=hace_dias(300))

    def win_rate():
        with memoria.conectar() as conn:
            return conn.execute("SELECT ganadas, perdidas, tasa_exito_porcentaje FROM vista_win_rate;").fetchone()

    antes = win_rate()
    resultado = Depurador(memoria, politica_de_prueba()).archivar(ahora=AHORA)

    assert resultado.lotes_archivados == 2, "los dos lotes debían archivarse"
    assert win_rate() == antes
    assert antes[0] == 1 and antes[1] == 1


def test_lo_archivado_desaparece_del_canal_principal(memoria):
    """La otra cara: el Funnel sí deja de mostrarlo. Es el objeto del archivado."""
    sembrar(memoria, "EXP-FUERA", [(1, "Nueva")], fecha_limite=hace_dias(300))

    def vivos():
        with memoria.conectar() as conn:
            return conn.execute("SELECT COUNT(*) FROM lotes WHERE deleted_at IS NULL;").fetchone()[0]

    assert vivos() == 1
    Depurador(memoria, politica_de_prueba()).archivar(ahora=AHORA)
    assert vivos() == 0


# ======================================================================================
# Modo degradado (Regla 5): en caso de duda, no hacer nada
# ======================================================================================

def test_sin_politica_no_se_archiva_nada_y_se_dice_por_que(memoria):
    sembrar(memoria, "EXP-SIN-POL", [(1, "Nueva")], fecha_limite=hace_dias(300))

    resultado = Depurador(memoria, politica=None).archivar(ahora=AHORA)

    assert resultado.ejecutado is False
    assert "politica_retencion_ausente" in resultado.motivo_degradacion
    assert leer_lote(memoria, "EXP-SIN-POL", 1)["deleted_at"] is None


def test_sin_bloque_archivado_no_se_archiva_nada(memoria):
    """No se inventa un plazo por defecto: es la lección de H-18."""
    sembrar(memoria, "EXP-SIN-BLOQUE", [(1, "Nueva")], fecha_limite=hace_dias(300))
    politica = PoliticaRetencion(version="1.0.0", documentos_dias=180, backups_dias=7)

    resultado = Depurador(memoria, politica).archivar(ahora=AHORA)

    assert resultado.ejecutado is False
    assert "politica_sin_bloque_archivado" in resultado.motivo_degradacion
    assert leer_lote(memoria, "EXP-SIN-BLOQUE", 1)["deleted_at"] is None


def test_un_archivado_vacio_es_distinguible_de_uno_degradado(memoria):
    """Convención C2: no encontrar nada que archivar no puede parecerse a no poder hacerlo."""
    sembrar(memoria, "EXP-AL-DIA", [(1, "Nueva")], fecha_limite=hace_dias(1))

    vacio = Depurador(memoria, politica_de_prueba()).archivar(ahora=AHORA)
    degradado = Depurador(memoria, politica=None).archivar(ahora=AHORA)

    assert vacio.ejecutado is True and vacio.lotes_archivados == 0
    assert vacio.motivo_degradacion is None
    assert degradado.ejecutado is False and degradado.motivo_degradacion


# ======================================================================================
# Auditoría (Regla 3)
# ======================================================================================

def test_cada_archivado_deja_su_fila_en_purgas(memoria):
    sembrar(memoria, "EXP-AUDIT", [(1, "Nueva")], fecha_limite=hace_dias(120))

    Depurador(memoria, politica_de_prueba()).archivar(ahora=AHORA, solicitado_por="pipeline")

    with memoria.conectar() as conn:
        fila = conn.execute(
            "SELECT tipo, solicitada_por, version_politica, resultado, "
            "expedientes_archivados, detalle FROM purgas;"
        ).fetchone()

    assert fila[0] == "ARCHIVADO"
    assert fila[1] == "pipeline"
    assert fila[2] == "1.1.0-test"
    assert fila[3] == "COMPLETADA"
    detalle = json.loads(fila[5])
    assert detalle["lotes_archivados"] == 1
    assert detalle["dias_tras_fecha_limite"] == 60


def test_un_archivado_sin_cambios_no_ensucia_la_auditoria(memoria):
    """Una purga que no purgó nada no es una purga."""
    sembrar(memoria, "EXP-NADA", [(1, "Nueva")], fecha_limite=hace_dias(1))

    Depurador(memoria, politica_de_prueba()).archivar(ahora=AHORA)

    with memoria.conectar() as conn:
        assert conn.execute("SELECT COUNT(*) FROM purgas;").fetchone()[0] == 0


# ======================================================================================
# H-31 · Rastro de los cambios de estado
# ======================================================================================

def leer_log(memoria, exp_id):
    with memoria.conectar() as conn:
        return conn.execute(
            "SELECT COALESCE(log_cambios, '') FROM expedientes WHERE id = ?;", (exp_id,)
        ).fetchone()[0]


def test_un_cambio_de_estado_desde_el_cockpit_deja_rastro(memoria):
    """La vía del Cockpit. Sin esta línea, llegar a `Presentada` no consta en ninguna parte."""
    sembrar(memoria, "EXP-TRAZA", [(1, "Nueva")], fecha_limite=hace_dias(10))

    memoria.mutar_estado_lote_transaccional("EXP-TRAZA", 1, "Presentada")

    log = leer_log(memoria, "EXP-TRAZA")
    assert MARCA_LOG_ESTADO in log
    assert "'nueva' -> 'presentada'" in log


def test_un_cambio_de_estado_por_el_dao_deja_rastro(memoria):
    sembrar(memoria, "EXP-TRAZA-DAO", [(1, "Nueva")], fecha_limite=hace_dias(10))

    memoria.actualizar_estado_lote("EXP-TRAZA-DAO", 1, "Estudiando")

    assert "'nueva' -> 'estudiando'" in leer_log(memoria, "EXP-TRAZA-DAO")


def test_reafirmar_el_mismo_estado_no_ensucia_el_historico(memoria):
    sembrar(memoria, "EXP-IGUAL", [(1, "Estudiando")], fecha_limite=hace_dias(10))

    memoria.actualizar_estado_lote("EXP-IGUAL", 1, "estudiando")

    assert MARCA_LOG_ESTADO not in leer_log(memoria, "EXP-IGUAL")


def test_el_radar_deja_constancia_del_estado_que_pisa(memoria):
    """El escenario que el contrato de la Capa 9 cita literalmente.

    Un lote `Presentada` que desaparece del feed antes de su fecha límite acaba en
    `Anulada_Administracion`. Hasta ahora el estado anterior se perdía, y con él la única
    prueba de que hubo negocio invertido: el Paso 6 lo habría considerado eliminable.
    """
    futuro = (AHORA + timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
    sembrar(memoria, "EXP-PISADO", [(1, "Presentada")], fecha_limite=futuro)

    # El Radar da por ausente todo lo que no vio en esta corrida.
    memoria.soft_delete_obsoletos(datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))

    log = leer_log(memoria, "EXP-PISADO")
    assert "'presentada' -> 'anulada_administracion'" in log
    assert leer_lote(memoria, "EXP-PISADO", 1)["estado"] == "Anulada_Administracion"


# ======================================================================================
# H-32 · Archivar gobierna la visibilidad, no la editabilidad
# ======================================================================================

def test_un_lote_archivado_se_puede_seguir_editando(memoria):
    """El bloqueo que hacía impracticable archivar estados que la gente edita.

    Una adjudicación se resuelve mucho después de la fecha límite que provocó el archivado.
    Si archivar dejara el lote en sólo lectura, el importe adjudicado, las garantías y los
    costes —lo que alimenta el win-rate y el CAC— no podrían anotarse nunca.
    """
    sembrar(memoria, "EXP-EDITABLE", [(1, "Adjudicada")], fecha_limite=hace_dias(300))
    Depurador(memoria, politica_de_prueba()).archivar(ahora=AHORA)
    assert leer_lote(memoria, "EXP-EDITABLE", 1)["deleted_at"] is not None

    exito, anterior, _ = memoria.mutar_estado_lote_transaccional("EXP-EDITABLE", 1, "Perdida")

    assert exito is True
    assert anterior == "Adjudicada"
    assert leer_lote(memoria, "EXP-EDITABLE", 1)["estado"] == "Perdida"


def test_editar_un_lote_archivado_no_lo_desarchiva(memoria):
    """La garantía contra la oscilación.

    Si la edición desarchivara, la corrida siguiente volvería a archivarlo —la fecha límite
    sigue vencida— y el lote entraría y saldría del Funnel solo. El rescate es una acción
    explícita del contrato, no un efecto colateral de tocar un campo.
    """
    sembrar(memoria, "EXP-NO-RESCATE", [(1, "Estudiando")], fecha_limite=hace_dias(300))
    Depurador(memoria, politica_de_prueba()).archivar(ahora=AHORA)
    marca = leer_lote(memoria, "EXP-NO-RESCATE", 1)["deleted_at"]

    memoria.mutar_estado_lote_transaccional("EXP-NO-RESCATE", 1, "Descartada")

    assert leer_lote(memoria, "EXP-NO-RESCATE", 1)["deleted_at"] == marca


def test_la_ficha_de_un_expediente_archivado_no_llega_vacia(memoria):
    """Antes filtraba los lotes archivados: la ficha se abría sin nada dentro."""
    sembrar(memoria, "EXP-FICHA", [(1, "Nueva")], fecha_limite=hace_dias(300))
    Depurador(memoria, politica_de_prueba()).archivar(ahora=AHORA)

    ficha = memoria.obtener_expediente_completo("EXP-FICHA")

    assert len(ficha["lotes"]) == 1
    assert ficha["lotes"][0]["deleted_at"] is not None
    assert ficha["lotes"][0]["deleted_reason"]


def test_el_funnel_sigue_sin_arrastrar_lo_archivado_por_defecto(memoria):
    """H-22 no se reabre: la tabla con la que se decide sigue limpia."""
    sembrar(memoria, "EXP-VIVO", [(1, "Nueva")], fecha_limite=hace_dias(10))
    sembrar(memoria, "EXP-ARCH", [(1, "Nueva")], fecha_limite=hace_dias(300))
    Depurador(memoria, politica_de_prueba()).archivar(ahora=AHORA)

    items, total = memoria.listar_expedientes_paginados()

    assert total == 1
    assert [i["id"] for i in items] == ["EXP-VIVO"]


def test_lo_archivado_se_alcanza_pidiendolo_y_llega_marcado(memoria):
    """La vía de auditoría y rescate, con el mismo patrón que el filtro del Centinela."""
    sembrar(memoria, "EXP-VIVO-2", [(1, "Nueva")], fecha_limite=hace_dias(10))
    sembrar(memoria, "EXP-ARCH-2", [(1, "Nueva")], fecha_limite=hace_dias(300))
    Depurador(memoria, politica_de_prueba()).archivar(ahora=AHORA)

    items, total = memoria.listar_expedientes_paginados(incluir_archivadas=True)
    por_id = {i["id"]: i for i in items}

    assert total == 2
    assert por_id["EXP-ARCH-2"]["archivada"] == 1
    assert por_id["EXP-VIVO-2"]["archivada"] == 0
    # Y llega con sus lotes: un expediente listado sin lotes se pintaría como fila fantasma
    # de "0 € y 0 pts", que es exactamente H-22.
    assert len(por_id["EXP-ARCH-2"]["lotes"]) == 1


# ======================================================================================
# Métricas de la corrida
# ======================================================================================

def test_las_metricas_de_la_ejecucion_se_persisten(memoria):
    ejecucion_id = memoria.iniciar_ejecucion()

    memoria.registrar_metricas_ejecucion(
        ejecucion_id,
        expedientes_nuevos=12,
        lotes_evaluados=30,
        version_politica_retencion="1.1.0",
    )

    with memoria.conectar() as conn:
        fila = conn.execute(
            "SELECT expedientes_nuevos, lotes_evaluados, version_politica_retencion "
            "FROM ejecuciones WHERE id = ?;", (ejecucion_id,)
        ).fetchone()
    assert fila == (12, 30, "1.1.0")


def test_una_metrica_desconocida_se_rechaza_en_vez_de_perderse(memoria):
    ejecucion_id = memoria.iniciar_ejecucion()

    with pytest.raises(ValueError, match="desconocidas"):
        memoria.registrar_metricas_ejecucion(ejecucion_id, expedientes_nuevoss=3)


def test_los_valores_nulos_no_pisan_lo_ya_escrito(memoria):
    """El pipeline escribe métricas en el `finally`, también cuando falló a mitad."""
    ejecucion_id = memoria.iniciar_ejecucion()
    memoria.registrar_metricas_ejecucion(ejecucion_id, expedientes_nuevos=7)

    memoria.registrar_metricas_ejecucion(ejecucion_id, expedientes_nuevos=None, lotes_evaluados=4)

    with memoria.conectar() as conn:
        fila = conn.execute(
            "SELECT expedientes_nuevos, lotes_evaluados FROM ejecuciones WHERE id = ?;",
            (ejecucion_id,)
        ).fetchone()
    assert fila == (7, 4)

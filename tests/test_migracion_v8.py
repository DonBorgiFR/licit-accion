"""Migración a esquema v8 y cerrojo de ejecución — Capa 10, Paso 6 (repara H-40).

v8 añade dos columnas a `ejecuciones`: `pid` y `pid_creado_en`. Suenan a detalle de
implementación y no lo son — son lo que permite distinguir **una corrida viva del cadáver de
una corrida muerta a mitad**.

Hasta v8, `iniciar_ejecucion()` sólo sabía preguntar *"¿empezó hace menos de seis horas?"*.
Una corrida interrumpida —un apagón, un cierre de sesión, el apagado de nivel 3 del
Lanzador— dejaba una fila `RUNNING` fantasma que **bloqueaba la prospección durante seis
horas**. Con una persona lanzando el pipeline desde una terminal, el mensaje se leía y se
resolvía; con el despertador de la Capa 10 lanzándolo de madrugada, es una mañana entera sin
prospectar y sin que nadie sepa por qué.

**Lo que estas pruebas vigilan, y por qué cada una**:

1. Que la migración añada de verdad las columnas sobre una base **realmente** en v7, con el
   DDL legado escrito a mano — si se reutilizaran las constantes del módulo, la "base v7"
   nacería ya con las columnas de v8 y la prueba no probaría nada (método de
   `test_migracion_v6.py`).
2. Que un dueño muerto se reclame **al instante**, que es la reparación.
3. Que un dueño vivo **siga bloqueando**. Reparar sólo la primera mitad convertiría una
   protección en un adorno — misma lección que H-37.
4. Que ante la duda —fila sin PID, instante irresoluble— se conserve **intacta** la regla de
   las seis horas. Es la asimetría deliberada: no arrancar cuesta una mañana; arrancar sobre
   una corrida viva son dos procesos borrando pliegos a la vez.
"""

import os
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from src.memoria import (
    ESQUEMA_VERSION_ACTUAL,
    SQL_CREATE_ANALISIS_SEMANTICO,
    SQL_CREATE_BOLETINES_ALERTAS,
    SQL_CREATE_DOCUMENTOS,
    SQL_CREATE_EXPEDIENTES,
    SQL_CREATE_LOTES,
    SQL_CREATE_PURGAS,
    Memoria,
    motivo_ejecucion_huerfana,
)

PID_MUERTO = 999999


# DDL congelado de v7: `ejecuciones` con sus métricas pero **sin** las columnas de
# identidad del proceso. Escrito a mano a propósito (ver la cabecera).
DDL_V7_EJECUCIONES = """
CREATE TABLE ejecuciones (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    start_time TEXT NOT NULL,
    end_time TEXT,
    estado TEXT NOT NULL,
    expedientes_nuevos INTEGER DEFAULT 0,
    expedientes_actualizados INTEGER DEFAULT 0,
    lotes_evaluados INTEGER DEFAULT 0,
    documentos_descargados INTEGER DEFAULT 0,
    analisis_realizados INTEGER DEFAULT 0,
    alertas_generadas INTEGER DEFAULT 0,
    errores INTEGER DEFAULT 0,
    version_scoring TEXT,
    version_politica_retencion TEXT
);
"""


def ahora():
    return datetime.now(timezone.utc)


def marca(desplazamiento_horas: float = 0.0) -> str:
    return (ahora() + timedelta(hours=desplazamiento_horas)).strftime("%Y-%m-%dT%H:%M:%SZ")


def columnas(conn, tabla):
    return {fila[1] for fila in conn.execute(f"PRAGMA table_info({tabla});")}


@pytest.fixture
def base_v7(tmp_path):
    """Una base realmente en v7, con una corrida `RUNNING` de la que no se sabe quién la lanzó."""
    ruta = str(tmp_path / "licitaciones.db")
    conn = sqlite3.connect(ruta)
    with conn:
        conn.execute("CREATE TABLE metadata (version INTEGER NOT NULL);")
        conn.execute("INSERT INTO metadata (version) VALUES (7);")
        conn.execute(DDL_V7_EJECUCIONES)
        # El resto no cambia en v8, así que se reutilizan sus constantes: una v7 real las
        # tiene, y sin ellas la recreación de vistas posterior a la migración falla.
        conn.execute(SQL_CREATE_EXPEDIENTES)
        conn.execute(SQL_CREATE_LOTES)
        conn.execute(SQL_CREATE_DOCUMENTOS)
        conn.execute(SQL_CREATE_ANALISIS_SEMANTICO)
        conn.execute(SQL_CREATE_BOLETINES_ALERTAS)
        conn.execute(SQL_CREATE_PURGAS)
        conn.execute(
            "INSERT INTO ejecuciones (start_time, estado) VALUES (?, 'RUNNING');",
            (marca(-1.0),),
        )
    conn.close()
    return ruta


# --------------------------------------------------------------------------------------
# 1. La migración
# --------------------------------------------------------------------------------------

def test_una_base_v7_real_no_tiene_las_columnas_de_identidad(base_v7):
    """Guarda del método: si esto fallara, la prueba de migración no probaría nada."""
    conn = sqlite3.connect(base_v7)
    assert "pid" not in columnas(conn, "ejecuciones")
    assert "pid_creado_en" not in columnas(conn, "ejecuciones")
    conn.close()


def test_la_migracion_v7_a_v8_anade_la_identidad_del_proceso(base_v7):
    Memoria(db_path=base_v7).setup_db()

    conn = sqlite3.connect(base_v7)
    try:
        assert {"pid", "pid_creado_en"} <= columnas(conn, "ejecuciones")
        version = conn.execute("SELECT MAX(version) FROM metadata;").fetchone()[0]
        # Lo que esta prueba afirma es que **migrar desde v7 añade la identidad del proceso**
        # y deja la base al día, no que el esquema se haya quedado en 8 para siempre. Fijar
        # el 8 literal la hacía caer al llegar la v9 (H-59) por un motivo que no era el suyo.
        assert version == ESQUEMA_VERSION_ACTUAL
    finally:
        conn.close()


def test_la_migracion_no_inventa_dueno_para_las_corridas_antiguas(base_v7):
    """Una fila heredada queda con `pid` a NULL, y eso es lo correcto.

    NULL dice "no lo sé" y un cero diría "murió". Rellenarlas con un valor inventado
    convertiría corridas de las que no sabemos nada en corridas reclamables al instante.
    """
    Memoria(db_path=base_v7).setup_db()

    conn = sqlite3.connect(base_v7)
    try:
        pid, instante = conn.execute(
            "SELECT pid, pid_creado_en FROM ejecuciones ORDER BY id LIMIT 1;"
        ).fetchone()
    finally:
        conn.close()
    assert pid is None
    assert instante is None


def test_una_base_nueva_nace_en_v8(tmp_path):
    memoria = Memoria(db_path=str(tmp_path / "nueva.db"))
    memoria.setup_db()

    conn = sqlite3.connect(memoria.db_path)
    try:
        assert {"pid", "pid_creado_en"} <= columnas(conn, "ejecuciones")
    finally:
        conn.close()


# --------------------------------------------------------------------------------------
# 2. El criterio: quién puede reclamarse y quién no
# --------------------------------------------------------------------------------------

def test_un_dueno_muerto_se_reclama_al_instante():
    """La reparación de H-40. Recién empezada, pero su proceso ya no existe."""
    motivo = motivo_ejecucion_huerfana(marca(), PID_MUERTO, "123456789", ahora())
    assert motivo is not None
    assert str(PID_MUERTO) in motivo


def test_un_dueno_vivo_sigue_bloqueando():
    """La otra mitad, sin la cual la protección sería un adorno."""
    from src.proceso import instante_creacion_proceso

    pid = os.getpid()
    motivo = motivo_ejecucion_huerfana(
        marca(), pid, str(instante_creacion_proceso(pid)), ahora()
    )
    assert motivo is None


def test_un_numero_de_proceso_reciclado_no_cuenta_como_dueno_vivo():
    """La sección E del contrato: la identidad de un proceso no es su número.

    El PID está vivo —es el nuestro— pero el instante anotado es otro, así que quien lanzó
    aquella corrida ya no está. Sin esta comprobación, un número reciclado por Windows
    mantendría un cerrojo muerto en pie.
    """
    motivo = motivo_ejecucion_huerfana(marca(), os.getpid(), "0", ahora())
    assert motivo is not None
    assert "otro proceso" in motivo


def test_sin_pid_anotado_se_conserva_intacta_la_regla_de_las_seis_horas():
    """Ante la duda se respeta el cerrojo: es el comportamiento anterior a v8, sin tocar."""
    assert motivo_ejecucion_huerfana(marca(-1.0), None, None, ahora()) is None
    assert motivo_ejecucion_huerfana(marca(-5.9), None, None, ahora()) is None

    vencida = motivo_ejecucion_huerfana(marca(-6.1), None, None, ahora())
    assert vencida is not None and "plazo" in vencida


def test_un_pid_vivo_cuyo_instante_no_se_resuelve_no_se_da_por_muerto():
    """`instante_creacion_proceso()` devuelve `None` fuera de Windows y cuando faltan
    permisos. Ese `None` significa *"no lo sé"*, nunca *"no vive"*: tratarlo como muerte
    reclamaría el cerrojo de una corrida en marcha."""
    assert motivo_ejecucion_huerfana(marca(), os.getpid(), None, ahora()) is None


# --------------------------------------------------------------------------------------
# 3. El cerrojo de ejecución de extremo a extremo
# --------------------------------------------------------------------------------------

def test_iniciar_ejecucion_anota_el_proceso_que_la_corre(tmp_path):
    memoria = Memoria(db_path=str(tmp_path / "licitaciones.db"))
    memoria.setup_db()
    ejecucion_id = memoria.iniciar_ejecucion()

    conn = sqlite3.connect(memoria.db_path)
    try:
        pid, _ = conn.execute(
            "SELECT pid, pid_creado_en FROM ejecuciones WHERE id = ?;", (ejecucion_id,)
        ).fetchone()
    finally:
        conn.close()
    assert pid == os.getpid()


def test_una_corrida_muerta_a_mitad_no_bloquea_la_siguiente(tmp_path):
    """**La prueba que demuestra que H-40 quedó reparado.**

    Antes de v8 esto habría lanzado `RuntimeError` durante seis horas: la fila empezó hace
    un minuto y nadie podía saber que su dueño ya no existe.
    """
    memoria = Memoria(db_path=str(tmp_path / "licitaciones.db"))
    memoria.setup_db()

    with memoria.conectar() as conn:
        with conn:
            conn.execute(
                "INSERT INTO ejecuciones (start_time, estado, pid, pid_creado_en) "
                "VALUES (?, 'RUNNING', ?, '123456789');",
                (marca(), PID_MUERTO),
            )

    nueva = memoria.iniciar_ejecucion()
    assert nueva > 0

    with memoria.conectar() as conn:
        estados = [f[0] for f in conn.execute("SELECT estado FROM ejecuciones ORDER BY id;")]
    # La huérfana queda cerrada como fallida, no borrada: consta que existió y que se reclamó.
    assert estados == ["FAILED", "RUNNING"]


def test_una_corrida_viva_sigue_abortando_la_paralela(tmp_path):
    """El daño que este cerrojo impide no es un desperdicio: desde la Capa 9 el pipeline
    borra ficheros del disco, así que dos corridas a la vez son dos procesos destruyendo
    peso documental simultáneamente."""
    memoria = Memoria(db_path=str(tmp_path / "licitaciones.db"))
    memoria.setup_db()
    memoria.iniciar_ejecucion()  # la corrida viva es este mismo proceso de prueba

    with pytest.raises(RuntimeError, match="Ejecución paralela"):
        memoria.iniciar_ejecucion()


def test_reclamar_una_corrida_ajena_deja_rastro(tmp_path):
    """Cerrar la corrida de otro es una decisión, no una limpieza: tiene que constar."""
    memoria = Memoria(db_path=str(tmp_path / "licitaciones.db"))
    memoria.setup_db()
    with memoria.conectar() as conn:
        with conn:
            conn.execute(
                "INSERT INTO ejecuciones (start_time, estado, pid, pid_creado_en) "
                "VALUES (?, 'RUNNING', ?, '123456789');",
                (marca(), PID_MUERTO),
            )

    memoria.iniciar_ejecucion()

    registro = os.path.join(os.path.dirname(memoria.db_path), "pipeline.jsonl")
    assert "EJECUCION_HUERFANA_RECLAMADA" in open(registro, encoding="utf-8").read()

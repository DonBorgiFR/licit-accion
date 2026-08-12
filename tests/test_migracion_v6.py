"""Migración a esquema v6 — Capa 9, Paso 3.

v6 añade el ciclo de vida del dato: borrado lógico a nivel de expediente, la generación de
scoring con la que se puntuó cada lote, métricas por ejecución y la tabla de auditoría
`purgas`. Y cierra H-27 normalizando las dos grafías del estado archivado.

**El DDL de v5 se escribe aquí a mano, a propósito.** Reutilizar las constantes
`SQL_CREATE_*` del módulo produciría una supuesta "base v5" que ya nace con las columnas de
v6, y la prueba de migración no probaría nada: sólo comprobaría que `setup_db()` no se
rompe. Con el DDL legado explícito, las columnas realmente no existen antes de migrar.
"""

import sqlite3

import pytest

from src.memoria import (
    ESQUEMA_VERSION_ACTUAL,
    ESTADO_ANULADA_ADMINISTRACION,
    ESTADO_INACTIVA,
    SQL_CREATE_ANALISIS_SEMANTICO,
    SQL_CREATE_BOLETINES_ALERTAS,
    SQL_CREATE_DOCUMENTOS,
    SQL_INSERT_INITIAL_VERSION,
    Memoria,
)


# DDL congelado de v5: sin deleted_at/deleted_reason en expedientes, sin version_scoring en
# lotes y con `ejecuciones` reducida a cuándo empezó y acabó la corrida.
DDL_V5_EXPEDIENTES = """
CREATE TABLE expedientes (
    id TEXT PRIMARY KEY, titulo TEXT NOT NULL, organo TEXT, localidad TEXT, nuts TEXT,
    procedimiento TEXT, tipo_contrato TEXT, urgente INTEGER DEFAULT 0, fuente TEXT,
    link TEXT, fecha_publicacion TEXT, fecha_limite TEXT, fecha_ingesta TEXT NOT NULL,
    alerta_modificacion INTEGER DEFAULT 0, log_cambios TEXT DEFAULT '',
    last_seen_feed TEXT, feed_hash TEXT
);
"""

DDL_V5_LOTES = """
CREATE TABLE lotes (
    id INTEGER PRIMARY KEY AUTOINCREMENT, expediente_id TEXT NOT NULL,
    lote_numero INTEGER NOT NULL DEFAULT 1, titulo_lote TEXT, cpvs TEXT,
    pbl REAL DEFAULT 0.0, vec REAL DEFAULT 0.0, garantia_definitiva REAL DEFAULT 0.0,
    subrogacion INTEGER DEFAULT 0, revision_precios INTEGER DEFAULT 0, dias_restantes INTEGER,
    score_total INTEGER DEFAULT 0, motivos_scoring TEXT, sector TEXT,
    prioridad TEXT DEFAULT 'Media', pmp_dias INTEGER DEFAULT 30, ratio_prorrogas REAL DEFAULT 1.0,
    estado_operativo TEXT DEFAULT 'Nueva', notes_usuario TEXT DEFAULT '',
    notas_usuario TEXT DEFAULT '', empresa_adjudicataria TEXT, importe_adjudicacion REAL,
    dinero_en_la_mesa REAL, horas_internas_invertidas INTEGER DEFAULT 0,
    costes_externos REAL DEFAULT 0.0, importe_garantia_retenida REAL DEFAULT 0.0,
    fecha_devolucion_garantia TEXT, deleted_at TEXT, deleted_reason TEXT,
    updated_by TEXT DEFAULT 'radar', updated_at TEXT,
    FOREIGN KEY (expediente_id) REFERENCES expedientes(id) ON DELETE RESTRICT,
    UNIQUE(expediente_id, lote_numero)
);
"""

DDL_V5_EJECUCIONES = """
CREATE TABLE ejecuciones (
    id INTEGER PRIMARY KEY AUTOINCREMENT, start_time TEXT NOT NULL, end_time TEXT,
    estado TEXT NOT NULL
);
"""


@pytest.fixture
def base_v5(tmp_path):
    """Una base realmente en v5, con un lote archivado en la grafía antigua (minúsculas)."""
    ruta = str(tmp_path / "licitaciones.db")
    conn = sqlite3.connect(ruta)
    with conn:
        conn.execute("CREATE TABLE metadata (version INTEGER NOT NULL);")
        conn.execute("INSERT INTO metadata (version) VALUES (5);")
        conn.execute(DDL_V5_EXPEDIENTES)
        conn.execute(DDL_V5_LOTES)
        conn.execute(DDL_V5_EJECUCIONES)
        # Estas tres no cambian en v6, así que se reutilizan sus constantes. Una v5 real
        # las tiene, y sin ellas la recreación de vistas posterior a la migración falla.
        conn.execute(SQL_CREATE_DOCUMENTOS)
        conn.execute(SQL_CREATE_ANALISIS_SEMANTICO)
        conn.execute(SQL_CREATE_BOLETINES_ALERTAS)
        conn.execute(
            "INSERT INTO expedientes (id, titulo, fecha_ingesta) "
            "VALUES ('EXP-V5', 'Licitación heredada de v5', '2026-07-01T10:00:00Z');"
        )
        # Un lote con memoria comercial y otro archivado con la grafía antigua.
        conn.execute(
            "INSERT INTO lotes (expediente_id, lote_numero, titulo_lote, score_total, "
            "estado_operativo, importe_adjudicacion, horas_internas_invertidas) "
            "VALUES ('EXP-V5', 1, 'Lote adjudicado', 82, 'Adjudicada', 145000.0, 37);"
        )
        conn.execute(
            "INSERT INTO lotes (expediente_id, lote_numero, titulo_lote, estado_operativo) "
            "VALUES ('EXP-V5', 2, 'Lote caducado', 'inactiva');"
        )
        conn.execute(
            "INSERT INTO lotes (expediente_id, lote_numero, titulo_lote, estado_operativo) "
            "VALUES ('EXP-V5', 3, 'Lote anulado', 'anulada_administracion');"
        )
    conn.close()
    return ruta


def columnas(conn, tabla):
    return {fila[1] for fila in conn.execute(f"PRAGMA table_info({tabla});")}


# --------------------------------------------------------------------------------------
# Fuente única de la versión
# --------------------------------------------------------------------------------------

def test_la_version_del_esquema_no_esta_duplicada():
    """El INSERT inicial declaraba un literal, y podía desincronizarse de la constante.

    Una base nueva habría nacido anunciando una versión distinta de la esperada,
    disparando una migración sobre un esquema que ya estaba al día.
    """
    assert Memoria.ESQUEMA_VERSION == ESQUEMA_VERSION_ACTUAL
    assert f"VALUES ({ESQUEMA_VERSION_ACTUAL})" in SQL_INSERT_INITIAL_VERSION


# --------------------------------------------------------------------------------------
# Instalación nueva
# --------------------------------------------------------------------------------------

def test_una_base_nueva_nace_en_v6_completa(tmp_path):
    memoria = Memoria(db_path=str(tmp_path / "nueva.db"))
    memoria.setup_db()

    with memoria.conectar() as conn:
        assert conn.execute("SELECT version FROM metadata;").fetchone()[0] == ESQUEMA_VERSION_ACTUAL
        assert {"deleted_at", "deleted_reason"} <= columnas(conn, "expedientes")
        assert "version_scoring" in columnas(conn, "lotes")
        assert {"expedientes_nuevos", "errores", "version_politica_retencion"} <= columnas(conn, "ejecuciones")
        assert conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='purgas';"
        ).fetchone() is not None


# --------------------------------------------------------------------------------------
# Migración v5 → v6
# --------------------------------------------------------------------------------------

def test_la_migracion_desde_v5_anade_las_columnas_del_ciclo_de_vida(base_v5):
    with sqlite3.connect(base_v5) as previo:
        assert "deleted_at" not in columnas(previo, "expedientes"), "El DDL de v5 no debe traerla"
        assert "version_scoring" not in columnas(previo, "lotes")

    memoria = Memoria(db_path=base_v5)
    memoria.setup_db()

    with memoria.conectar() as conn:
        assert conn.execute("SELECT version FROM metadata;").fetchone()[0] == ESQUEMA_VERSION_ACTUAL
        assert {"deleted_at", "deleted_reason"} <= columnas(conn, "expedientes")
        assert "version_scoring" in columnas(conn, "lotes")
        assert {"lotes_evaluados", "version_politica_retencion"} <= columnas(conn, "ejecuciones")


def test_la_migracion_no_pierde_la_memoria_comercial(base_v5):
    """Lo que protege el contrato de la Capa 9 debe sobrevivir a la propia migración."""
    memoria = Memoria(db_path=base_v5)
    memoria.setup_db()

    with memoria.conectar() as conn:
        fila = conn.execute(
            "SELECT estado_operativo, importe_adjudicacion, horas_internas_invertidas, score_total "
            "FROM lotes WHERE expediente_id='EXP-V5' AND lote_numero=1;"
        ).fetchone()
        assert tuple(fila) == ("Adjudicada", 145000.0, 37, 82)
        assert conn.execute("SELECT COUNT(*) FROM lotes;").fetchone()[0] == 3


def test_la_migracion_es_idempotente(base_v5):
    """Reejecutar setup_db() sobre una base ya migrada no debe alterar nada."""
    memoria = Memoria(db_path=base_v5)
    memoria.setup_db()
    memoria.setup_db()

    with memoria.conectar() as conn:
        assert conn.execute("SELECT version FROM metadata;").fetchone()[0] == ESQUEMA_VERSION_ACTUAL
        assert conn.execute("SELECT COUNT(*) FROM lotes;").fetchone()[0] == 3


# --------------------------------------------------------------------------------------
# H-27 · Normalización de las dos grafías del estado archivado
# --------------------------------------------------------------------------------------

def test_la_migracion_normaliza_las_grafias_del_estado_archivado(base_v5):
    """H-27: convivían 'inactiva' y "Inactiva" en la misma columna.

    A partir de v6 la Capa 9 compara estados para decidir qué puede borrarse, y ahí un
    falso negativo significa eliminar algo que no debía eliminarse.
    """
    memoria = Memoria(db_path=base_v5)
    memoria.setup_db()

    with memoria.conectar() as conn:
        estados = dict(conn.execute(
            "SELECT lote_numero, estado_operativo FROM lotes WHERE expediente_id='EXP-V5';"
        ).fetchall())

    assert estados[2] == ESTADO_INACTIVA
    assert estados[3] == ESTADO_ANULADA_ADMINISTRACION


def test_el_radar_escribe_la_grafia_canonica(tmp_path):
    """La otra mitad de H-27: no basta con normalizar lo viejo si se sigue escribiendo mal."""
    memoria = Memoria(db_path=str(tmp_path / "radar.db"))
    memoria.setup_db()

    with memoria.conectar() as conn:
        with conn:
            conn.execute(
                "INSERT INTO expedientes (id, titulo, fecha_ingesta, last_seen_feed) "
                "VALUES ('EXP-VIEJO', 'Ausente del feed', '2026-07-01T10:00:00Z', '2026-07-01T10:00:00Z');"
            )
            conn.execute(
                "INSERT INTO lotes (expediente_id, lote_numero, titulo_lote, estado_operativo) "
                "VALUES ('EXP-VIEJO', 1, 'Lote', 'Nueva');"
            )

    memoria.soft_delete_obsoletos("2026-08-01T00:00:00Z")

    with memoria.conectar() as conn:
        estado, borrado = conn.execute(
            "SELECT estado_operativo, deleted_at FROM lotes WHERE expediente_id='EXP-VIEJO';"
        ).fetchone()

    assert estado == ESTADO_INACTIVA, "El Radar debe escribir la grafía canónica"
    assert borrado is not None, "Y marcar el borrado lógico"


def test_la_purga_documental_ya_no_mira_el_estado_operativo(base_v5):
    """Aquí vivía una regresión sobre las dos grafías del estado archivado (H-27).

    Ha dejado de tener objeto: desde el Paso 5, `obtener_documentos_para_purga()` **no lee
    `estado_operativo`**, así que no puede depender de cómo esté escrito. La lección de H-27
    sigue vigilada donde sigue aplicando, que es el filtro de estados del motor de archivado
    (`tests/test_capa9_archivado.py`).

    Lo que se fija ahora es la decisión que la sustituye *(dirección, 2026-08-12)*: **ningún
    estado permite saltarse el plazo**. Antes, un expediente con todos sus lotes inactivos
    perdía sus pliegos de inmediato; pero desaparecer del feed no es estar resuelto, y esa
    regla borraba la documentación de una oferta viva mientras se esperaba la adjudicación.
    """
    memoria = Memoria(db_path=base_v5)
    memoria.setup_db()

    with memoria.conectar() as conn:
        with conn:
            # El caso que antes purgaba de inmediato: expediente entero archivado.
            conn.execute("UPDATE lotes SET estado_operativo = ? WHERE expediente_id='EXP-V5';",
                         (ESTADO_INACTIVA,))
            conn.execute(
                "INSERT INTO documentos (expediente_id, titulo, url, tipo, hash_documento, "
                "estado, local_path, updated_at) VALUES ('EXP-V5', 'PCA.pdf', "
                "'http://example.invalid/p.pdf', 'PCA', 'h1', 'PROCESADO', '/tmp/p.pdf', "
                "'2026-07-01T10:00:00Z');"
            )

    # El expediente se ingestó el 2026-07-01 y no trae fecha límite, así que el plazo se
    # cuenta desde la ingesta. Con el corte antes de esa fecha, no toca purgar nada por
    # mucho que todos sus lotes estén archivados.
    assert memoria.obtener_documentos_para_purga("2026-01-01T00:00:00Z") == []

    # Y con el plazo vencido sí, sin que ningún estado haya cambiado entre una llamada y otra.
    candidatos = memoria.obtener_documentos_para_purga("2026-12-31T00:00:00Z")
    assert [d["titulo"] for d in candidatos] == ["PCA.pdf"]


# --------------------------------------------------------------------------------------
# version_scoring: la columna debe llenarse, no sólo existir
# --------------------------------------------------------------------------------------

def test_el_lote_registra_con_que_version_de_scoring_se_puntuo(tmp_path):
    """Lección del Paso D10: los datos de la beta hubo que tirarlos porque dos generaciones
    de puntuación convivían en la misma tabla sin nada que las distinguiera.

    Una columna que existiera pero quedara siempre vacía daría una falsa sensación de
    protección, así que se comprueba el recorrido real: Filtro → upsert → SQLite.
    """
    from src.filtro import Filtro

    filtro = Filtro()
    memoria = Memoria(db_path=str(tmp_path / "scoring.db"))
    memoria.setup_db()

    licitacion = {
        "id": "EXP-SCORING", "titulo": "Servei d'atenció domiciliària",
        "organo": "Ajuntament de Terrassa", "localidad": "Terrassa", "importe": 150000.0,
        "vec": 150000.0, "cpvs": ["85312000"], "estado": "PUB", "procedimiento_codigo": "1",
        "tipo_contrato_codigo": "2", "fecha_limite": "2099-12-31",
        "country_subentity_code": "ES511", "fuente": "prueba",
        "link": "https://example.invalid/x", "fecha_publicacion": "2026-08-07",
    }
    evaluacion = filtro.filtrar(licitacion)
    assert evaluacion["version_scoring"] == filtro.version_scoring

    memoria.upsert_oportunidad(licitacion, evaluacion)

    with memoria.conectar() as conn:
        persistida = conn.execute(
            "SELECT version_scoring FROM lotes WHERE expediente_id='EXP-SCORING';"
        ).fetchone()[0]

    assert persistida == filtro.version_scoring
    assert persistida != "desconocida", "El perfil debe declarar scoring.version"

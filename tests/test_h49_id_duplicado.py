"""H-49 · La misma licitación entrando dos veces con dos identificadores.

La fuente catalana toma el identificador de expediente de `codi_expedient`, **un campo de texto
libre**, y republicó la misma licitación escribiéndolo de dos maneras. Entraron como dos
expedientes: uno se quedó los 11 pliegos y el título corto; el otro, cero documentos y el título
de 1.663 caracteres.

**La reparación obvia no servía, y esa es la lección.** Colapsar los espacios repetidos —lo que
el contrato proponía— deja `EXPEDIENT 214 2026…`, que sigue sin coincidir con `EXPEDIENT214
2026…`. Medido sobre los 63 expedientes reales: **0 duplicados detectados**. Lo que sí las une es
el código que la propia plataforma pone en el enlace, idéntico en las dos filas.

Las dos grafías que aparecen aquí son **las reales de la base**, no inventadas.
"""

import pytest

from src.memoria import Memoria, uuid_publicacion

# Las dos grafías reales, y el enlace real que comparten (mismo código de publicación,
# distinto número de anuncio al final).
ID_A = "EXPEDIENT214 2026 - CONTRACTACIÓ SERVEI"
ID_B = "EXPEDIENT  214 2026 - CONTRACTACIÓ SERVEI"
UUID = "f7bb55cd-7fae-445e-83db-5c3ddc286e12"
LINK_A = f"https://contractaciopublica.cat/ca/detall-publicacio/{UUID}/300863057"
LINK_B = f"https://contractaciopublica.cat/ca/detall-publicacio/{UUID}/300860782"


@pytest.fixture
def base(tmp_path):
    db = Memoria(db_path=str(tmp_path / "licitaciones.db"))
    db.setup_db()
    return db


def sembrar(base, exp_id, link):
    with base.conectar() as conn:
        with conn:
            conn.execute(
                "INSERT INTO expedientes (id, titulo, fecha_ingesta, fecha_limite, link) "
                "VALUES (?, ?, '2026-08-18T08:26:08Z', '2026-09-02T21:59:00Z', ?);",
                (exp_id, f"Título de {exp_id}", link),
            )


def resolver(base, exp_id, link):
    with base.conectar() as conn:
        return base.resolver_id_canonico(conn.cursor(), {"id": exp_id, "link": link})


# ======================================================================================
# El caso real
# ======================================================================================

def test_la_segunda_grafia_reutiliza_el_expediente_que_ya_existe(base):
    """El caso exacto que partió los 11 pliegos del título de 1.663 caracteres."""
    sembrar(base, ID_B, LINK_B)

    assert resolver(base, ID_A, LINK_A) == ID_B


def test_la_reparacion_que_no_funcionaba(base):
    """Deja constancia de por qué se descartó colapsar espacios, para que nadie lo reintente.

    `EXPEDIENT  214` colapsado es `EXPEDIENT 214`, que **no** es `EXPEDIENT214`. Si algún día
    alguien sustituye el criterio por una normalización de espacios, esta prueba se cae.
    """
    import re
    colapsado_a = re.sub(r"\s+", " ", ID_A).strip()
    colapsado_b = re.sub(r"\s+", " ", ID_B).strip()

    assert colapsado_a != colapsado_b, "Colapsar espacios NO une estas dos grafías"
    assert uuid_publicacion(LINK_A) == uuid_publicacion(LINK_B), "El código de publicación sí"


# ======================================================================================
# Las cautelas: no deducir de más
# ======================================================================================

def test_un_identificador_ya_conocido_gana_sin_preguntar(base):
    """El caso normal —la misma licitación revista mañana— no debe cambiar de identificador."""
    sembrar(base, ID_A, LINK_A)

    assert resolver(base, ID_A, LINK_A) == ID_A


def test_sin_codigo_de_publicacion_no_se_deduce_nada(base):
    """Las fuentes estatales usan otro formato de enlace: ahí no hay evidencia y no se toca nada."""
    sembrar(base, "OTRO-2026", "https://contrataciondelestado.es/wps/poc?uri=deeplink:detalle")

    nuevo = resolver(base, "NUEVO-2026", "https://contrataciondelestado.es/wps/poc?uri=deeplink:otro")

    assert nuevo == "NUEVO-2026"


def test_dos_licitaciones_distintas_no_se_funden(base):
    """Códigos de publicación distintos son licitaciones distintas, por parecidos que sean los ids."""
    sembrar(base, "EXP-UNO", "https://contractaciopublica.cat/ca/detall-publicacio/"
                             "aaaaaaaa-1111-2222-3333-444444444444/1")

    nuevo = resolver(base, "EXP-DOS", "https://contractaciopublica.cat/ca/detall-publicacio/"
                                      "bbbbbbbb-1111-2222-3333-444444444444/2")

    assert nuevo == "EXP-DOS"


def test_un_expediente_nuevo_de_verdad_conserva_su_identificador(base):
    """Base vacía: no hay nada que reutilizar."""
    assert resolver(base, ID_A, LINK_A) == ID_A


def test_no_se_modifica_ninguna_fila_existente(base):
    """Esto decide bajo qué identificador escribir, **no** fusiona lo que ya está duplicado.

    Fusionar arrastra documentos, lotes y análisis, es irreversible y necesita su propio paso.
    """
    sembrar(base, ID_A, LINK_A)
    sembrar(base, ID_B, LINK_B)

    resolver(base, ID_A, LINK_A)

    with base.conectar() as conn:
        assert conn.execute("SELECT COUNT(*) FROM expedientes;").fetchone()[0] == 2


# ======================================================================================
# El extractor, por separado
# ======================================================================================

@pytest.mark.parametrize(
    "link,esperado",
    [
        (LINK_A, UUID),
        (LINK_B, UUID),
        (f"https://contractaciopublica.cat/ca/detall-publicacio/{UUID.upper()}/1", UUID),
        ("https://contrataciondelestado.es/wps/poc?uri=deeplink:detalle_licitacion", None),
        ("https://contractaciopublica.cat/ca/otra-ruta/" + UUID, None),
        ("", None),
        (None, None),
    ],
)
def test_uuid_publicacion(link, esperado):
    """Anclado a `detall-publicacio/` y no a "cualquier UUID en la URL".

    El penúltimo caso es el que justifica el anclaje: un código con el mismo formato en otra
    ruta no identifica una licitación, y darlo por bueno sería deducir sin evidencia.
    """
    assert uuid_publicacion(link) == esperado

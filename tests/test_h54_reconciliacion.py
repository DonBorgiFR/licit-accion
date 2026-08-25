"""H-54 · Que la base deje de reclamar pliegos que no tiene.

H-36 borró 63 pliegos de producción el 2026-08-12 y se cerró impidiendo que vuelva a pasar. Lo
que nadie hizo fue reconciliar la base: trece días después, 63 filas seguían diciendo
`PROCESADO` con un `local_path` que apuntaba a ficheros inexistentes.

Lo que estas pruebas fijan es que la herramienta **mide en vez de fiarse de una lista** —la
condición es "el fichero no está", comprobada contra el disco—, que **no toca nada sin
confirmación explícita**, que **sin copia de seguridad no escribe** (Regla 5), y que el hecho y
su rastro en `purgas` viajan juntos.

Los ficheros de estas pruebas son reales y se crean en `tmp_path`: comprobar la existencia de un
fichero contra un `os.path.exists` simulado sería comprobar el simulacro.
"""

import os
import sys

import pytest

from src.memoria import Memoria

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools import reconciliar_h54  # noqa: E402


# =====================================================================
# ANDAMIAJE
# =====================================================================

@pytest.fixture
def base(tmp_path):
    db = Memoria(db_path=str(tmp_path / "licitaciones.db"))
    db.setup_db()
    return db


def sembrar_documento(db, doc_id, exp_id, ruta, estado="PROCESADO", texto="texto del pliego"):
    """Inserta un expediente y su documento, con el fichero real si la ruta se da."""
    with db.conectar() as conn:
        with conn:
            conn.execute(
                "INSERT OR IGNORE INTO expedientes (id, titulo, fecha_ingesta) "
                "VALUES (?, ?, '2026-08-12T12:02:00Z');",
                (exp_id, f"Expediente {exp_id}"),
            )
            conn.execute(
                "INSERT INTO documentos (id, expediente_id, titulo, url, tipo, hash_documento, "
                "local_path, estado, mida_bytes, texto_extraido, updated_at) "
                "VALUES (?, ?, ?, ?, 'PCA', ?, ?, ?, ?, ?, '2026-08-12T12:02:00Z');",
                (doc_id, exp_id, f"Pliego {doc_id}", f"https://ejemplo/{doc_id}.pdf",
                 f"hash-{doc_id}", ruta, estado, 555_555, texto),
            )


def fila(db, doc_id):
    with db.conectar() as conn:
        c = conn.execute(
            "SELECT estado, local_path, texto_extraido, error_detalle FROM documentos WHERE id = ?;",
            (doc_id,),
        )
        return c.fetchone()


def purgas(db):
    with db.conectar() as conn:
        return conn.execute(
            "SELECT tipo, solicitada_por, documentos_purgados, bytes_liberados, resultado, detalle "
            "FROM purgas ORDER BY id;"
        ).fetchall()


@pytest.fixture
def escenario(base, tmp_path):
    """Tres documentos: dos huérfanos --el defecto-- y uno sano, que no debe tocarse."""
    presente = tmp_path / "documents" / "vivo.pdf"
    presente.parent.mkdir(parents=True, exist_ok=True)
    presente.write_bytes(b"%PDF-1.4 contenido real")

    ausente_a = str(tmp_path / "documents" / "borrado_por_h36_a.pdf")
    ausente_b = str(tmp_path / "documents" / "borrado_por_h36_b.pdf")

    sembrar_documento(base, 1, "EXP-A", ausente_a)
    sembrar_documento(base, 2, "EXP-A", ausente_b)
    sembrar_documento(base, 3, "EXP-B", str(presente))
    return base


@pytest.fixture
def herramienta(escenario, monkeypatch):
    """La herramienta apuntando a la base de la prueba, nunca a la real."""
    monkeypatch.setattr(reconciliar_h54, "Memoria", lambda *a, **k: escenario)
    return escenario


def ejecutar(argv):
    return reconciliar_h54.main(), argv


# =====================================================================
# 1. QUÉ SELECCIONA, Y QUÉ NO
# =====================================================================

def test_selecciona_solo_las_filas_cuyo_fichero_no_esta(escenario):
    """La condición es el disco, no una lista de identificadores anotada una vez."""
    desalineados = reconciliar_h54.localizar_desalineados(escenario)

    assert sorted(d["id"] for d in desalineados) == [1, 2]
    assert 3 not in [d["id"] for d in desalineados], "tocó un documento cuyo fichero sí existe"


def test_no_vuelve_a_seleccionar_lo_ya_purgado(escenario):
    """Idempotencia: ejecutarla dos veces no debe encontrar trabajo la segunda vez."""
    escenario.marcar_documentos_como_purgados([1, 2])

    assert reconciliar_h54.localizar_desalineados(escenario) == []


def test_un_documento_sin_ruta_no_es_un_desalineado(escenario):
    """`local_path` nulo es "nunca se descargó", no "se perdió". No es este defecto."""
    sembrar_documento(escenario, 4, "EXP-C", None)

    assert 4 not in [d["id"] for d in reconciliar_h54.localizar_desalineados(escenario)]


# =====================================================================
# 2. NO SE ESCRIBE SIN QUE ALGUIEN LO PIDA DOS VECES
# =====================================================================

def test_la_previsualizacion_no_toca_nada(herramienta, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["reconciliar_h54.py"])

    assert reconciliar_h54.main() == 0
    assert fila(herramienta, 1)[0] == "PROCESADO", "la previsualización escribió"
    assert purgas(herramienta) == []


def test_ejecutar_sin_confirmar_no_toca_nada(herramienta, monkeypatch):
    """Un `--ejecutar` a solas es "olvidé el resto", no "sí, adelante"."""
    monkeypatch.setattr(sys, "argv", ["reconciliar_h54.py", "--ejecutar"])

    assert reconciliar_h54.main() == 2
    assert fila(herramienta, 1)[0] == "PROCESADO"
    assert purgas(herramienta) == []


def test_si_la_copia_de_seguridad_falla_no_se_escribe(herramienta, monkeypatch):
    """Regla 5, y aquí no se relaja porque la operación parezca pequeña."""
    def reventar(*args, **kwargs):
        raise OSError("disco lleno")

    monkeypatch.setattr(herramienta, "realizar_backup", reventar)
    monkeypatch.setattr(sys, "argv", ["reconciliar_h54.py", "--ejecutar", "--confirmar"])

    assert reconciliar_h54.main() == 3
    assert fila(herramienta, 1)[0] == "PROCESADO", "escribió sin copia de seguridad"
    assert purgas(herramienta) == []


# =====================================================================
# 3. LO QUE DEJA CUANDO SÍ SE EJECUTA
# =====================================================================

def test_reconcilia_por_el_libro_y_deja_rastro(herramienta, monkeypatch):
    """Estado, ruta, texto y auditoría: las cuatro cosas o ninguna."""
    monkeypatch.setattr(sys, "argv", ["reconciliar_h54.py", "--ejecutar", "--confirmar"])

    assert reconciliar_h54.main() == 0

    for doc_id in (1, 2):
        estado, ruta, texto, error = fila(herramienta, doc_id)
        assert estado == "PURGADO"
        assert ruta is None, "la fila sigue nombrando un fichero que no existe"
        assert texto is None, "el texto no se vació: es postcondición del contrato de la Capa 9"
        assert error == "PURGADO_HISTORICO"

    intacto = fila(herramienta, 3)
    assert intacto[0] == "PROCESADO" and intacto[1] is not None, "tocó el documento sano"


def test_la_auditoria_no_se_apunta_bytes_que_no_libero(herramienta, monkeypatch):
    """Los bytes se fueron el 2026-08-12. Contarlos hoy sería una liberación inventada."""
    monkeypatch.setattr(sys, "argv", ["reconciliar_h54.py", "--ejecutar", "--confirmar"])
    reconciliar_h54.main()

    registradas = purgas(herramienta)
    assert len(registradas) == 1, "el hecho quedó sin rastro, o con más de uno"
    tipo, solicitada_por, documentos, bytes_liberados, resultado, detalle = registradas[0]

    assert documentos == 2
    assert bytes_liberados == 0, "se apuntó una liberación de disco que no ha ocurrido"
    assert resultado == "COMPLETADA"
    assert solicitada_por == "reconciliacion_h54", "no consta quién lo pidió"
    assert "H-54" in detalle and "1111110" in detalle, "el detalle no dice qué peso se perdió y cuándo"


def test_ejecutarla_dos_veces_no_duplica_el_rastro(herramienta, monkeypatch):
    """La segunda pasada no encuentra trabajo, así que no debe inventarse una purga."""
    monkeypatch.setattr(sys, "argv", ["reconciliar_h54.py", "--ejecutar", "--confirmar"])
    reconciliar_h54.main()
    reconciliar_h54.main()

    assert len(purgas(herramienta)) == 1, "la segunda pasada registró una purga vacía"

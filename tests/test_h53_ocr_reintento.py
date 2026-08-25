"""H-53 · Un pliego escaneado deja de ser un callejón sin salida.

Cuando Tesseract no está instalado, el Lector guarda el documento como `OCR_DIFERIDO` y sigue.
Eso es correcto y está previsto. Lo que no lo era: `obtener_documentos_para_ocr()` seleccionaba
**sólo** `OCR_REQUERIDO`, así que un documento que hubiera pasado por el modo degradado no volvía
a mirarse nunca. **El nombre decía *diferido* y el comportamiento era *descartado***: instalar
Tesseract al día siguiente no habría recuperado ni uno.

Es la forma exacta de H-33 —un estado que se escribe y que ninguna consulta lee— en otro punto del
mismo vocabulario documental.

Estas pruebas fijan las dos mitades de la reparación: que **el diferido vuelve a la cola**, y que
volver a la cola **no se convierte en reprocesar en vacío** cada corrida cuando Tesseract sigue sin
estar.
"""

import pytest

from src.lector import ExtraccionResult, Lector
from src.memoria import Memoria


# =====================================================================
# ANDAMIAJE
# =====================================================================

@pytest.fixture
def base(tmp_path):
    db = Memoria(db_path=str(tmp_path / "licitaciones.db"))
    db.setup_db()
    return db


@pytest.fixture
def pliego(tmp_path):
    """Un fichero real: el Lector comprueba que existe antes de decidir nada."""
    ruta = tmp_path / "escaneado.pdf"
    ruta.write_bytes(b"%PDF-1.4 da igual el contenido, aqui no se abre")
    return str(ruta)


def sembrar(base, doc_id, estado, ruta, exp_id="EXP-1"):
    with base.conectar() as conn:
        with conn:
            conn.execute(
                "INSERT OR IGNORE INTO expedientes (id, titulo, fecha_ingesta) "
                "VALUES (?, 'Expediente de prueba', '2026-08-25T09:00:00Z');",
                (exp_id,),
            )
            conn.execute(
                "INSERT INTO documentos (id, expediente_id, titulo, url, tipo, hash_documento, "
                "local_path, estado, texto_extraido, updated_at) "
                "VALUES (?, ?, ?, ?, 'PPT', ?, ?, ?, 'texto previo', '2026-08-25T09:00:00Z');",
                (doc_id, exp_id, f"Pliego {doc_id}", f"https://ejemplo/{doc_id}.pdf",
                 f"hash-{doc_id}", ruta, estado),
            )


def estado_de(base, doc_id):
    with base.conectar() as conn:
        return conn.execute("SELECT estado FROM documentos WHERE id = ?;", (doc_id,)).fetchone()[0]


def lector_sin_tesseract(base):
    lector = Lector(db_memoria=base, run_id=53)
    lector.tesseract_path_bin = None
    lector.ocr_estado = "ocr_ausente"
    return lector


def lector_con_tesseract(base):
    lector = Lector(db_memoria=base, run_id=53)
    lector.tesseract_path_bin = r"C:\ficticio\tesseract.exe"
    lector.ocr_estado = "ocr_disponible"
    lector.tesseract_idiomas = ["spa", "cat"]
    return lector


# =====================================================================
# 1. QUIÉN VUELVE A LA COLA
# =====================================================================

def test_un_documento_diferido_vuelve_a_ser_candidato(base, pliego):
    """El corazón de H-53: sin esto, instalar Tesseract no recupera nada."""
    sembrar(base, 1, "OCR_DIFERIDO", pliego)

    candidatos = base.obtener_documentos_para_ocr()

    assert [d["id"] for d in candidatos] == [1]


def test_un_documento_requerido_sigue_siendo_candidato(base, pliego):
    """La reparación amplía la cola, no la sustituye."""
    sembrar(base, 1, "OCR_REQUERIDO", pliego)

    assert [d["id"] for d in base.obtener_documentos_para_ocr()] == [1]


@pytest.mark.parametrize("estado", ["PROCESADO", "PURGADO", "DESCARGADO", "ERROR_DESCARGA"])
def test_los_demas_estados_no_entran_en_la_cola_de_ocr(base, pliego, estado):
    """Ampliar la cola no puede significar barrerlo todo dentro."""
    sembrar(base, 1, estado, pliego)

    assert base.obtener_documentos_para_ocr() == []


def test_un_diferido_sin_fichero_no_es_candidato(base):
    """Sin `local_path` no hay nada que reintentar. Es el caso de un documento purgado."""
    sembrar(base, 1, "OCR_DIFERIDO", None)

    assert base.obtener_documentos_para_ocr() == []


# =====================================================================
# 2. VOLVER A LA COLA NO ES REPROCESAR EN VACÍO
# =====================================================================

def test_sin_tesseract_y_solo_diferidos_no_se_toca_nada(base, pliego):
    """Reprocesar 63 documentos cada corrida para dejarlos igual es ruido, no trabajo."""
    sembrar(base, 1, "OCR_DIFERIDO", pliego)
    sembrar(base, 2, "OCR_DIFERIDO", pliego, exp_id="EXP-2")
    lector = lector_sin_tesseract(base)

    llamadas = []
    lector.ejecutar_ocr_pdf_diferido = lambda *a, **k: llamadas.append(a)

    lector.procesar_ocr_diferido_lote()

    assert llamadas == [], "reproceso documentos que no podia cambiar"
    assert estado_de(base, 1) == "OCR_DIFERIDO"
    assert estado_de(base, 2) == "OCR_DIFERIDO"


def test_sin_tesseract_pero_con_uno_nuevo_si_se_procesa(base, pliego):
    """Un `OCR_REQUERIDO` sí cambia de estado aunque falte Tesseract, y ese registro importa.

    Es lo que hace que mañana se le vuelva a mirar: si se saltara, el documento se quedaría en
    `OCR_REQUERIDO` sin que constara nunca que se intentó.
    """
    sembrar(base, 1, "OCR_DIFERIDO", pliego)
    sembrar(base, 2, "OCR_REQUERIDO", pliego, exp_id="EXP-2")
    lector = lector_sin_tesseract(base)

    lector.procesar_ocr_diferido_lote()

    assert estado_de(base, 2) == "OCR_DIFERIDO", "el nuevo no dejó constancia de su intento"


def test_con_tesseract_el_diferido_sale_del_estado(base, pliego):
    """El final del recorrido: lo que se difirió ayer se procesa hoy y deja de estar pendiente."""
    sembrar(base, 1, "OCR_DIFERIDO", pliego)
    lector = lector_con_tesseract(base)

    lector.ejecutar_ocr_pdf_diferido = lambda *a, **k: ExtraccionResult(
        exito=True, texto="texto reconocido por OCR", metodo="tesseract",
        num_paginas=3, paginas_ocr=3, idioma_detectado="ca",
        version_reglas=lector.VERSION_REGLAS, tiempo_procesamiento_ms=1200,
        error_detalle=None,
    )

    lector.procesar_ocr_diferido_lote()

    assert estado_de(base, 1) == "PROCESADO", "el documento sigue atrapado en OCR_DIFERIDO"


def test_el_aplazamiento_queda_registrado(base, pliego):
    """Si el lote decide no hacer nada, eso también se cuenta: nada ocurre en silencio."""
    sembrar(base, 1, "OCR_DIFERIDO", pliego)
    lector = lector_sin_tesseract(base)

    eventos = []
    lector.registrar_log_JSONL = lambda action, **k: eventos.append((action, k.get("reason", "")))

    lector.procesar_ocr_diferido_lote()

    acciones = [a for a, _ in eventos]
    assert "doc_ocr_batch_pospuesto" in acciones, "el lote se saltó el trabajo sin decirlo"
    motivo = next(r for a, r in eventos if a == "doc_ocr_batch_pospuesto")
    assert "Tesseract" in motivo, "el registro no dice por qué se pospuso"

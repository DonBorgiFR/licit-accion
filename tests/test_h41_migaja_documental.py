"""H-41 · Qué se estaba leyendo cuando el proceso murió.

El pipeline terminó con `0xC0000005` —`ACCESS_VIOLATION`— sobre datos reales. Es una violación
de acceso **nativa**, no una excepción de Python: mata el proceso en seco, sin `except`, sin
`finally` y sin desenrollar la pila. La auditoría dejó escrito qué faltaba para diagnosticarlo:
**registrar qué fichero se está procesando antes de abrirlo, no después.**

El rastro que había se escribía cuando la función volvía. Si la biblioteca nativa revienta
dentro, no vuelve — y no queda una sola línea diciendo qué pliego era. Eso es lo que estas
pruebas cierran.

**Cómo se simula aquí una muerte nativa, y por qué así.** No se puede provocar un
`ACCESS_VIOLATION` de verdad dentro de la suite. Lo que sí se puede reproducir es la propiedad
que lo hace indiagnosticable: **que la función no vuelva**. Una `BaseException` atraviesa los
`except Exception` del lector igual que un crash atraviesa todo, así que el estado que queda en
disco es el mismo. Lo que se comprueba no es el crash: es que **la marca ya estaba escrita antes**.

Los PDF son reales y se generan con el propio PyMuPDF: la suite no sale a la red (C5).
"""

import io
import json
import os

import pytest

from src import ruta_datos
from src.lector import Lector

fitz = pytest.importorskip("fitz", reason="PyMuPDF es la pieza nativa que H-41 investiga")


# =====================================================================
# ANDAMIAJE
# =====================================================================

@pytest.fixture(autouse=True)
def sin_migaja_previa():
    """Cada prueba empieza sin cadáveres de la anterior."""
    destino = ruta_datos("logs", Lector.CENTINELA_DOC)
    if os.path.exists(destino):
        os.remove(destino)
    yield
    if os.path.exists(destino):
        os.remove(destino)


@pytest.fixture
def pdf_de_tres_paginas(tmp_path):
    """Un PDF real, con texto de sobra para que no se desvíe al OCR."""
    ruta = tmp_path / "pliego.pdf"
    doc = fitz.open()
    for numero in range(3):
        pagina = doc.new_page()
        pagina.insert_text(
            (72, 72),
            f"Pliego de clausulas administrativas particulares. Pagina {numero + 1}. "
            "Objeto del contrato, presupuesto base de licitacion y criterios de adjudicacion.",
        )
    doc.save(str(ruta))
    doc.close()
    return str(ruta)


def leer_migaja():
    """Devuelve la marca que hay en disco ahora mismo, o None si no hay ninguna."""
    destino = ruta_datos("logs", Lector.CENTINELA_DOC)
    if not os.path.exists(destino):
        return None
    with io.open(destino, encoding="utf-8") as f:
        return json.loads(f.read())


class BaseFalsa:
    """Sustituto de `Memoria` que sólo recuerda en qué orden le hablaron."""

    def __init__(self, documentos):
        self.documentos = documentos
        self.eventos = []
        self.guardados = []

    def obtener_documentos_para_extraccion(self):
        return self.documentos

    def registrar_log_json(self, run_id, action, expediente_id=None, reason=None,
                           duration_ms=None, updated_by="lector"):
        self.eventos.append((action, reason))

    def guardar_resultado_extraccion_texto(self, doc_id, estado, texto_extraido, metodo,
                                           idioma, version_reglas, error_detalle=None):
        self.guardados.append((doc_id, estado))


# =====================================================================
# 1. LA MARCA ESTÁ EN DISCO **ANTES** DE TOCAR LA PÁGINA
# =====================================================================

def test_la_marca_existe_antes_de_leer_cada_pagina(pdf_de_tres_paginas, monkeypatch):
    """El corazón de H-41: cuando el código nativo recibe el control, la marca ya está escrita.

    Se interceptan las páginas y, en el instante en que se les pide el texto, se lee el fichero
    de disco. Si la marca se escribiera después —como hacía el rastro anterior— aquí se leería
    `None`, que es exactamente lo que dejó la corrida del 2026-08-17.
    """
    observado = []
    abrir_real = fitz.open

    class PaginaEspia:
        def __init__(self, pagina):
            self._pagina = pagina

        def get_text(self, *args, **kwargs):
            observado.append(leer_migaja())
            return self._pagina.get_text(*args, **kwargs)

    class DocEspia:
        def __init__(self, doc):
            self._doc = doc

        def __len__(self):
            return len(self._doc)

        def __getitem__(self, i):
            return PaginaEspia(self._doc[i])

        def close(self):
            self._doc.close()

    monkeypatch.setattr(fitz, "open", lambda ruta: DocEspia(abrir_real(ruta)))

    lector = Lector(db_memoria=None, run_id=41)
    resultado = lector.extraer_texto_pdf_nativo(pdf_de_tres_paginas, doc_id=777)

    assert resultado.exito is True
    assert len(observado) == 3, "se esperaban tres páginas observadas"
    for numero, marca in enumerate(observado, start=1):
        assert marca is not None, f"la página {numero} se leyó sin marca en disco"
        assert marca["pagina"] == numero
        assert marca["num_paginas"] == 3
        assert marca["doc_id"] == 777
        assert marca["fase"] == "pymupdf"
        assert marca["local_path"] == pdf_de_tres_paginas


def test_la_marca_identifica_la_maquina_y_el_proceso(pdf_de_tres_paginas):
    """Dos PCs sobre la misma carpeta sincronizada: una migaja sin `host` no diría de quién es.

    Es la misma carencia que H-52 describe en el cerrojo de corridas. Aquí sale barata.
    """
    lector = Lector(db_memoria=None, run_id=41)
    lector._marcar_pagina_en_curso(
        fase="pymupdf", local_path=pdf_de_tres_paginas, pagina=1, num_paginas=3, doc_id=1,
    )
    marca = leer_migaja()

    assert marca["pid"] == os.getpid()
    assert marca["host"] == (os.environ.get("COMPUTERNAME") or "desconocido")
    assert marca["run_id"] == 41
    assert marca["timestamp"].endswith("Z")


# =====================================================================
# 2. SI EL PROCESO NO VUELVE, LA MARCA SOBREVIVE Y SEÑALA LA PÁGINA
# =====================================================================

def test_una_muerte_a_media_lectura_deja_la_pagina_culpable_en_disco(pdf_de_tres_paginas,
                                                                     monkeypatch):
    """Es el escenario de H-41 completo: la función no vuelve y aun así sabemos dónde murió."""
    abrir_real = fitz.open

    class PaginaQueMuere:
        def __init__(self, pagina, numero):
            self._pagina = pagina
            self._numero = numero

        def get_text(self, *args, **kwargs):
            if self._numero == 2:
                # `BaseException` atraviesa los `except Exception` del lector igual que un
                # `ACCESS_VIOLATION` atraviesa el intérprete entero.
                raise BaseException("violacion de acceso simulada")
            return self._pagina.get_text(*args, **kwargs)

    class DocQueMuere:
        def __init__(self, doc):
            self._doc = doc

        def __len__(self):
            return len(self._doc)

        def __getitem__(self, i):
            return PaginaQueMuere(self._doc[i], i + 1)

        def close(self):
            self._doc.close()

    monkeypatch.setattr(fitz, "open", lambda ruta: DocQueMuere(abrir_real(ruta)))

    lector = Lector(db_memoria=None, run_id=41)
    with pytest.raises(BaseException, match="violacion de acceso simulada"):
        lector.extraer_texto_pdf_nativo(pdf_de_tres_paginas, doc_id=777)

    marca = leer_migaja()
    assert marca is not None, "el cadáver no dejó marca: H-41 seguiría sin diagnosticarse"
    assert marca["pagina"] == 2, "la marca señala una página que no es donde murió"
    assert marca["local_path"] == pdf_de_tres_paginas


def test_una_lectura_limpia_no_deja_cadaver(pdf_de_tres_paginas):
    """Si la marca sigue ahí al terminar el lote, es que algo murió leyendo. No debe mentir."""
    documentos = [{
        "id": 1, "expediente_id": "EXP-1",
        "local_path": pdf_de_tres_paginas, "titulo": "Pliego de prueba",
    }]
    base = BaseFalsa(documentos)
    lector = Lector(db_memoria=base, run_id=41)

    lector.procesar_extraccion_texto_lote()

    assert leer_migaja() is None, "quedó una marca de un documento que se leyó sin incidencias"


# =====================================================================
# 3. EL EVENTO POR DOCUMENTO, QUE ES LA ASIMETRÍA QUE HABÍA
# =====================================================================

def test_el_lote_anuncia_el_documento_antes_de_abrirlo(pdf_de_tres_paginas):
    """El lote de OCR ya lo hacía (`doc_ocr_started`); el de extracción nativa, no.

    Esa asimetría no era intencionada, y es la que dejó la corrida del 2026-08-17 sin poder
    decir qué pliego estaba leyendo cuando reventó.
    """
    documentos = [{
        "id": 1, "expediente_id": "EXP-1",
        "local_path": pdf_de_tres_paginas, "titulo": "Pliego de prueba",
    }]
    base = BaseFalsa(documentos)
    lector = Lector(db_memoria=base, run_id=41)

    lector.procesar_extraccion_texto_lote()

    acciones = [accion for accion, _ in base.eventos]
    assert "doc_extraccion_started" in acciones, "el documento se abrió sin anunciarse"

    posicion_inicio = acciones.index("doc_extraccion_started")
    posicion_lote = acciones.index("doc_extraction_batch_start")
    assert posicion_lote < posicion_inicio < len(acciones) - 1, (
        "el anuncio no está entre la apertura del lote y el resultado del documento"
    )

    motivo = base.eventos[posicion_inicio][1]
    assert pdf_de_tres_paginas in motivo, "el anuncio no dice qué fichero se va a abrir"


# =====================================================================
# 4. LA MIGAJA NUNCA PUEDE TUMBAR EL PIPELINE
# =====================================================================

def test_si_la_marca_no_se_puede_escribir_la_extraccion_sigue(pdf_de_tres_paginas, monkeypatch):
    """Sin marca se pierde el diagnóstico; con una excepción aquí se perdería la corrida."""
    def reventar(*args, **kwargs):
        raise OSError("disco lleno")

    monkeypatch.setattr("src.lector.ruta_datos", reventar)

    lector = Lector(db_memoria=None, run_id=41)
    resultado = lector.extraer_texto_pdf_nativo(pdf_de_tres_paginas, doc_id=777)

    assert resultado.exito is True
    assert resultado.num_paginas == 3


def test_la_marca_nunca_queda_a_medias(pdf_de_tres_paginas):
    """Se escribe con `os.replace`, que es atómico: o la marca vieja, o la nueva, nunca la nada.

    Abrir el destino en modo `"w"` lo dejaría **vacío** durante un instante, y morir justo ahí
    daría una migaja muda — que es el único caso para el que existe.
    """
    lector = Lector(db_memoria=None, run_id=41)
    for pagina in range(1, 4):
        lector._marcar_pagina_en_curso(
            fase="pymupdf", local_path=pdf_de_tres_paginas,
            pagina=pagina, num_paginas=3, doc_id=1,
        )
        marca = leer_migaja()
        assert marca["pagina"] == pagina

    temporal = ruta_datos("logs", Lector.CENTINELA_DOC) + ".tmp"
    assert not os.path.exists(temporal), "quedó un fichero temporal huérfano"

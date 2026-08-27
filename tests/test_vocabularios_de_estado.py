"""La invariante de los vocabularios de estado, comprobada en vez de escrita.

**Este proyecto ha pisado el mismo defecto cuatro veces, todas en agosto de 2026:**

| | Estado huérfano | Qué se perdía |
|---|---|---|
| **H-33** | *(el primero de la familia)* | Documentos sin procesar |
| **H-53 cara B** | `OCR_DIFERIDO` | Pliegos escaneados que no se recuperaban al instalar Tesseract |
| **H-58** | `DESCARGANDO` | 6 pliegos reales, en una corrida que constaba `COMPLETED` con 0 errores |
| **H-59** | `ANALISIS_DIFERIDO_BOLETIN` | Las 5 alertas del canal, sin dictamen para siempre |

Las cuatro tienen la misma forma exacta: **un estado que se escribe y que ninguna consulta
lee**. Y las cuatro se encontraron por casualidad, mirando otra cosa.

La invariante estaba escrita en el contrato del Paso 10 —*todo estado transitorio tiene
exactamente un consumidor que lo recoge; uno que se escribe y no se lee sólo es admisible si
es terminal declarado*— y **escribirla no impidió la cuarta**. Así que aquí deja de ser texto:

* Cada estado del vocabulario **declara su naturaleza** y, si es transitorio, **quién lo
  recoge, por su nombre**.
* La prueba resuelve ese consumidor y **lee su código fuente** para exigir que mencione el
  estado. Si alguien lo retira de la consulta, cae aquí y no en producción seis semanas
  después.
* Y un estado que aparezca en el código sin estar declarado también cae, que es como
  aparecieron los cuatro.
"""

import inspect
import re
from pathlib import Path

import pytest

import src.centinela as centinela_mod
import src.lector as lector_mod
import src.memoria as memoria_mod

TRANSITORIO = "transitorio"
TERMINAL = "terminal"

#: Un valor que existe **sólo dentro de una corrida** y nunca llega a la base: otra pieza del
#: mismo flujo lo resuelve antes de persistir. No necesita consumidor porque no hay nada que
#: recoger — pero **sí necesita una prueba que demuestre que se resuelve**, o sería un
#: transitorio huérfano disfrazado. La categoría apareció al escribir este fichero: la
#: comprobación de estados sin declarar cazó `ANALIZADA_IA` en su primera ejecución, y no
#: encajaba ni en transitorio ni en terminal.
EN_VUELO = "en_vuelo"

RAIZ = Path(__file__).resolve().parent.parent


# =====================================================================
# EL VOCABULARIO DECLARADO
# =====================================================================
#
# `consumidor` es el nombre cualificado del método que recoge ese estado. Es la parte que
# hace ejecutable a la invariante: no basta con decir "es transitorio", hay que decir quién
# vuelve a por él, y la prueba lo comprueba de verdad.

VOCABULARIO_DOCUMENTOS = {
    "DETECTADO": (TRANSITORIO, "Memoria.obtener_documentos_pendientes"),
    "DESCARGANDO": (TRANSITORIO, "Memoria.obtener_documentos_pendientes"),
    "ERROR_DESCARGA": (TRANSITORIO, "Memoria.obtener_documentos_pendientes"),
    "DESCARGADO": (TRANSITORIO, "Memoria.obtener_documentos_para_extraccion"),
    "OCR_REQUERIDO": (TRANSITORIO, "Memoria.obtener_documentos_para_ocr"),
    "OCR_DIFERIDO": (TRANSITORIO, "Memoria.obtener_documentos_para_ocr"),
    "TEXTO_EXTRAIDO": (TRANSITORIO, "Memoria.setup_db"),
    "PROCESADO": (TERMINAL, None),
    "PURGADO": (TERMINAL, None),
    "OMITIDO_FORMATO_NO_PDF": (TERMINAL, None),
}

VOCABULARIO_ALERTAS = {
    "ANALISIS_DIFERIDO_BOLETIN": (TRANSITORIO, "Memoria.obtener_alertas_diferidas"),
    "ANALIZADA_IA": (EN_VUELO, None),
    "NUEVA_FASE_TEMPRANA": (TERMINAL, None),
    "EN_ESTUDIO_PROACTIVO": (TERMINAL, None),
    "DESCARTADA_POR_REGLAS": (TERMINAL, None),
    "DESCARTADA_TEMPRANA": (TERMINAL, None),
    "CONVERTIDA_A_LICITACION": (TERMINAL, None),
}

VOCABULARIOS = {
    "documentos.estado": VOCABULARIO_DOCUMENTOS,
    "boletines_alertas.estado_operativo": VOCABULARIO_ALERTAS,
}


def _resolver(nombre_cualificado):
    """`"Memoria.obtener_documentos_pendientes"` -> la función real."""
    clase, metodo = nombre_cualificado.split(".")
    for modulo in (memoria_mod, lector_mod, centinela_mod):
        objeto = getattr(modulo, clase, None)
        if objeto is not None:
            return getattr(objeto, metodo)
    raise AssertionError(f"No se encontró {nombre_cualificado}")


# =====================================================================
# 1 · TODO TRANSITORIO TIENE UN CONSUMIDOR, Y EXISTE
# =====================================================================

CASOS_TRANSITORIOS = [
    pytest.param(tabla, estado, consumidor, id=f"{tabla}::{estado}")
    for tabla, vocabulario in VOCABULARIOS.items()
    for estado, (naturaleza, consumidor) in vocabulario.items()
    if naturaleza == TRANSITORIO
]


@pytest.mark.parametrize("tabla, estado, consumidor", CASOS_TRANSITORIOS)
def test_cada_estado_transitorio_tiene_quien_lo_recoja(tabla, estado, consumidor):
    """**La prueba que impide la quinta vez.**

    No comprueba que el consumidor exista —eso sería trivial de satisfacer— sino que
    **mencione el estado en su código**. Retirar `DESCARGANDO` de la consulta de recogida,
    que es exactamente H-58, cae aquí.
    """
    assert consumidor, f"{estado} se declara transitorio y no dice quién lo recoge"

    fuente = inspect.getsource(_resolver(consumidor))

    assert estado in fuente, (
        f"{tabla}: '{estado}' es transitorio y su consumidor declarado "
        f"({consumidor}) no lo menciona. Un estado que se escribe y no se lee "
        f"es un agujero por el que se cae trabajo en silencio."
    )


def test_ningun_estado_terminal_declara_consumidor():
    """Un terminal con consumidor es una contradicción: o no es terminal, o sobra el lector."""
    for tabla, vocabulario in VOCABULARIOS.items():
        for estado, (naturaleza, consumidor) in vocabulario.items():
            if naturaleza == TERMINAL:
                assert consumidor is None, f"{tabla}: '{estado}' es terminal y declara consumidor"


def test_un_estado_en_vuelo_se_resuelve_antes_de_persistir():
    """Lo que justifica que `EN_VUELO` no necesite consumidor, demostrado y no supuesto.

    `ANALIZADA_IA` no llega nunca a la base porque el evaluador lo convierte en
    `NUEVA_FASE_TEMPRANA` o en `DESCARTADA_POR_REGLAS`. **Si algún día dejara de resolverse,
    sería un transitorio huérfano** —la quinta vez de la familia— y esta prueba lo diría.

    Se asigna **por atributo y no en el constructor**, igual que hace `analizar_alerta()`:
    `ANALIZADA_IA` está deliberadamente fuera de `ESTADOS_BOLETIN_VALIDOS` para que una
    alerta no pueda reconstruirse desde la base con ese valor. Ver la nota en
    `src/centinela.py`.
    """
    from src.centinela import AlertaBoletinDTO, EvaluadorScoringCentinela

    alerta = AlertaBoletinDTO(
        fuente="BOPB",
        num_boletin="1",
        fecha_publicacion="2026-08-27T07:00:00Z",
        organo_emisor="Ajuntament de Prova",
        municipio="Prova",
        titulo_anuncio="Pressupost per al servei d'escoles bressol",
        texto_sumario="Dotació per a escoles bressol i atenció domiciliària.",
    )
    alerta.estado_operativo = "ANALIZADA_IA"

    resultado = EvaluadorScoringCentinela().evaluar_alerta(alerta)

    assert resultado.estado_operativo != "ANALIZADA_IA", (
        "`ANALIZADA_IA` se declara EN_VUELO, es decir que nunca se persiste. Si el evaluador "
        "deja de resolverlo, pasa a ser un estado transitorio sin nadie que lo recoja."
    )
    assert VOCABULARIO_ALERTAS[resultado.estado_operativo][0] == TERMINAL


# =====================================================================
# 2 · NINGÚN ESTADO SE ESCRIBE SIN ESTAR DECLARADO
# =====================================================================

#: Cómo se escribe un estado en este proyecto. Las tres formas que existen hoy.
PATRONES_DE_ESCRITURA = (
    re.compile(r"""actualizar_estado_documento\([^,]+,\s*["']([A-Z_]+)["']"""),
    re.compile(r"""SET\s+estado\s*=\s*'([A-Z_]+)'"""),
    re.compile(r"""estado_operativo\s*=\s*["']([A-Z_]+)["']"""),
)

#: Estados de OTRAS tablas que estos patrones capturan de rebote. No pertenecen a los dos
#: vocabularios que esta prueba gobierna, y listarlos aquí es más honesto que afinar el
#: regex hasta que deje de verlos.
DE_OTRAS_TABLAS = {"FAILED", "RUNNING", "COMPLETED"}


def test_ningun_estado_se_escribe_sin_estar_declarado():
    """Un estado nuevo sin entrada en el vocabulario es cómo nacieron los cuatro defectos.

    Si alguien añade `REVISANDO` mañana y no lo declara, esta prueba lo obliga a decidir si
    es transitorio —y entonces a nombrar quién lo recoge— o terminal.
    """
    declarados = set()
    for vocabulario in VOCABULARIOS.values():
        declarados |= set(vocabulario)

    encontrados = {}
    for fichero in ("src/memoria.py", "src/lector.py", "src/centinela.py"):
        texto = (RAIZ / fichero).read_text(encoding="utf-8")
        for patron in PATRONES_DE_ESCRITURA:
            for estado in patron.findall(texto):
                encontrados.setdefault(estado, set()).add(fichero)

    sin_declarar = {
        e: sorted(f) for e, f in encontrados.items()
        if e not in declarados and e not in DE_OTRAS_TABLAS
    }

    assert not sin_declarar, (
        f"Estados que el código escribe y el vocabulario no declara: {sin_declarar}. "
        f"Añádelos a este fichero diciendo si son transitorios —y quién los recoge— o "
        f"terminales."
    )


def test_el_vocabulario_declarado_no_inventa_estados():
    """El espejo del anterior: un vocabulario que declara lo que nadie escribe también miente.

    Es el defecto que tenía el comentario del DDL antes de H-58: nombraba `OCR_PENDIENTE` y
    `ERROR_EXTRACCION`, que no se escriben en ninguna parte, y quien lo leyera creía estar
    viendo el vocabulario del sistema.
    """
    texto = "".join(
        (RAIZ / f).read_text(encoding="utf-8")
        for f in ("src/memoria.py", "src/lector.py", "src/centinela.py")
    )

    fantasmas = [
        estado
        for vocabulario in VOCABULARIOS.values()
        for estado in vocabulario
        if estado not in texto
    ]

    assert not fantasmas, f"Estados declarados que no aparecen en el código: {fantasmas}"

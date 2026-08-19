"""
src/ — Paquete raíz del Ecosistema Automático de Licitaciones (bfr_incoop).

Todos los módulos internos se importan de forma absoluta bajo el prefijo `src.`
(p. ej. `from src.memoria import Memoria`). Esta es la única raíz de importación
válida del proyecto: no deben usarse imports planos (`from memoria import ...`),
porque crearían un segundo objeto-módulo distinto para el mismo fichero.

Punto de entrada del pipeline: `python -m src.main` desde la raíz del proyecto,
o bien `python run.py`.
"""

import os
import re
from pathlib import Path

# Raíz del proyecto, deducida de la ubicación de este fichero. Es el único ancla
# fiable: el directorio de trabajo puede ser cualquiera, y de hecho lo será cuando
# el lanzador VBS de la Capa 10 arranque el pipeline.
PROJECT_ROOT = Path(__file__).resolve().parent.parent


def ruta_proyecto(ruta) -> str:
    """
    Resuelve una ruta relativa contra la raíz del proyecto, **nunca** contra el
    directorio de trabajo. Las rutas absolutas se devuelven intactas.

    Por qué existe: `config/perfil_incoop.yaml` y `data/` se resolvían contra el CWD.
    Ejecutado desde otra carpeta, el perfil comercial de Incoop no se cargaba y el
    sistema seguía adelante en silencio con los valores por defecto. Medido: la misma
    licitación puntuaba 71 desde la raíz y 47 desde otro directorio, con el umbral de
    recomendación en 65. No fallaba: decidía distinto.
    """
    p = Path(ruta)
    if p.is_absolute():
        return str(p)
    return str((PROJECT_ROOT / p).resolve())


#: Estados operativos válidos de un lote, en su forma normalizada (minúsculas).
#: Definición canónica: `EstadoLicitacionEnum` (`src/api/schemas.py`) declara las mismas
#: ocho, y `src/memoria.py` las reexporta. Viven aquí, en la raíz del paquete, porque
#: `src/retencion.py` necesita validarlas contra la política sin arrastrar FastAPI ni la
#: capa de persistencia.
#:
#: Por qué normalizadas: H-27 documentó que el mismo estado se escribía con dos grafías
#: —`Inactiva` e `inactiva`— y que el sistema era coherente por accidente. Toda comparación
#: de estado se hace normalizada, nunca contra el literal.
ESTADOS_OPERATIVOS_VALIDOS = (
    "nueva",
    "estudiando",
    "presentada",
    "adjudicada",
    "perdida",
    "descartada",
    "anulada_administracion",
    "inactiva",
)


#: Grafía con la que un estado debe **escribirse y mostrarse**, indexada por su forma
#: normalizada. Es la contraparte de la tupla de arriba: aquélla sirve para comparar, ésta
#: para persistir y pintar.
#:
#: Por qué hace falta y no basta con `.capitalize()`: `anulada_administracion` tiene dos
#: mayúsculas y el método se comería la segunda, produciendo una tercera grafía del mismo
#: estado. Que es exactamente cómo empezó H-27.
ESTADOS_OPERATIVOS_CANONICOS = {
    "nueva": "Nueva",
    "estudiando": "Estudiando",
    "presentada": "Presentada",
    "adjudicada": "Adjudicada",
    "perdida": "Perdida",
    "descartada": "Descartada",
    "anulada_administracion": "Anulada_Administracion",
    "inactiva": "Inactiva",
}


def normalizar_estado_operativo(estado) -> str:
    """Reduce un estado operativo a su forma comparable: sin espacios y en minúsculas."""
    return str(estado or "").strip().lower()


def grafia_canonica_estado(estado) -> str:
    """Devuelve la grafía con la que se escribe un estado en la base y en pantalla.

    Un estado desconocido se devuelve tal cual: esta función normaliza la escritura, no
    valida el vocabulario. Quien deba rechazar un estado inválido lo hace antes, contra
    `ESTADOS_OPERATIVOS_VALIDOS`, y con un error explícito.
    """
    return ESTADOS_OPERATIVOS_CANONICOS.get(normalizar_estado_operativo(estado), estado)


#: Versión del criterio con el que se deriva un título legible (Regla 4). Se declara aquí y no
#: se estampa por fila **porque el título derivado no se persiste**: se calcula al leer. Ver
#: `.agents/CONTRATO_BLOQUE_3.md`, apartado B, donde consta por qué se descartó la columna.
VERSION_TITULO = "1.0.0"

#: Tope de longitud del título derivado, en caracteres. **No es un número elegido a ojo.**
#: Medido sobre los 63 expedientes reales, ya aplicados los cortes por párrafo y por frase:
#: con 120 llegan enteros 27 (43 %), con 160 llegan 37 (59 %), con 200 llegan **48 (76 %)** y
#: con 240 llegan 52 (83 %). Se elige 200 porque por debajo se empieza a recortar títulos que
#: **ya eran correctos** —los de 125-135 caracteres son títulos de licitación normales y
#: completos— y el oficio del tope es alcanzar sólo a los quince desbocados.
TOPE_TITULO = 200

#: Punto final seguido de espacio y mayúscula. El `(?<![A-Z])` evita cortar por una
#: abreviatura en versales, frecuentes en los pliegos ("S.A. de capital…", "U.T.E. formada…").
_FIN_DE_FRASE = re.compile(r"(?<![A-Z])\.\s+(?=[A-ZÁÉÍÓÚÀÈÒÏÜÇÑ¿¡])")

#: Por debajo de esto, un punto no delimita una frase sino una sigla o una numeración.
_MINIMO_FRASE = 30


def titulo_legible(titulo, tope: int = TOPE_TITULO) -> str:
    """Deriva de un título de licitación uno que se pueda leer, sin tocar el original.

    Por qué hace falta: **son dos problemas con el mismo síntoma** y confundirlos lleva a
    arreglar el que no es. Uno es de presentación —la tabla recorta a dos líneas—; el otro es
    de datos: la fuente vuelca el anuncio entero en el campo, y el título más largo de la base
    mide **1.663 caracteres** siendo su título real las primeras veinte palabras. Lo segundo no
    lo arregla ningún ancho de columna.

    Tres reglas en orden, parando en la primera que deja algo legible:

    1. **El primer párrafo**, que separa el título del cuerpo del anuncio. Sólo alcanza a 5 de
       63 —los que traen salto de línea—, pero incluye el peor caso de todos.
    2. **La primera frase**, que es la que más trabaja: casi todos los títulos largos son una
       frase seguida de la descripción del objeto.
    3. **El tope**, en frontera de palabra. Nunca parte una palabra: comprobado sobre los 63.

    El original **no se modifica jamás**: sigue íntegro en la base y en la ficha de detalle.
    """
    if not titulo:
        return ""
    texto = str(titulo).replace("\r\n", "\n")
    texto = re.sub(r"\s+", " ", texto.split("\n\n")[0].split("\n")[0]).strip()
    if len(texto) <= tope:
        return texto

    corte = _FIN_DE_FRASE.search(texto)
    if corte and _MINIMO_FRASE <= corte.start() <= tope:
        return texto[: corte.start() + 1]

    recorte = texto[:tope]
    if " " in recorte:
        recorte = recorte[: recorte.rindex(" ")]
    return recorte.rstrip(" ,;:.·-—") + "…"


#: Versión del criterio de ámbito territorial (Regla 4). Se declara aquí porque el criterio
#: **no se persiste**: no hay columna «es de Catalunya», se decide al leer, igual que el
#: título derivado. Un cambio del criterio es un cambio de código y de esta versión.
VERSION_AMBITO = "1.0.0"

#: Ámbitos territoriales que la pantalla puede pedir, con su patrón NUTS.
#:
#: **Vocabulario cerrado a propósito.** Un ámbito que no esté aquí es un error tipado
#: (`AmbitoDesconocido`), nunca «devuelve todo»: degradar a un valor por defecto que el
#: consumidor no puede distinguir de un resultado real está prohibido por la Convención C2.
#: Escrito mal el nombre, la pantalla enseñaría 24 expedientes diciendo que enseña 9.
#:
#: Por qué `nuts` y no `localidad`: medido sobre la base real, `nuts` está poblado en **74 de
#: 74** filas sin un solo nulo, mientras que `localidad` trae `N/A` en la mitad.
#:
#: ⚠️ **Hay una segunda definición de Catalunya en el proyecto, y es deliberado.**
#: `config/perfil_incoop.yaml` lista `ES51`, `ES511`…`ES514` para el **scoring** comercial.
#: `ES51%` cubre exactamente esa unión, pero son dos criterios separados porque hacen dos
#: oficios distintos: aquél puntúa una oportunidad, éste decide qué se enseña. El contrato
#: del Bloque 3 prohíbe expresamente que el filtro de pantalla toque la ingesta o el scoring.
AMBITOS = {
    "catalunya": "ES51%",
}


class AmbitoDesconocido(ValueError):
    """El ámbito solicitado no está en el vocabulario. Se rechaza, no se ignora."""


def clausula_ambito(ambito, columna: str = "e.nuts"):
    """Traduce un ámbito a su condición SQL. Devuelve `(sql, params)`.

    Sin ámbito devuelve `("", [])`, que es la ausencia de filtro. **Ese es el
    comportamiento por defecto de la API a propósito**: quien decide mostrar sólo Catalunya
    es la pantalla, con su interruptor puesto de inicio, no la capa de datos. Es lo contrario
    que `incluir_archivadas`, y por un motivo: lo archivado es un concepto de negocio —qué
    está en el canal principal—, mientras el ámbito es una preferencia de quien mira. Una API
    que esconde por gusto propio produce la clase de sorpresa que este proyecto lleva cuatro
    capas persiguiendo.
    """
    if ambito is None:
        return "", []
    clave = str(ambito).strip().lower()
    if clave not in AMBITOS:
        raise AmbitoDesconocido(
            f"Ámbito '{ambito}' no reconocido. Válidos: {', '.join(sorted(AMBITOS))}."
        )
    return f"{columna} LIKE ?", [AMBITOS[clave]]


def ruta_datos(*partes) -> str:
    """
    Resuelve una ruta **dentro del directorio de datos**: base de datos, documentos
    descargados, registros JSONL e informes. Por defecto es `<raíz>/data`, pero la variable
    de entorno `DATA_DIR_INCOOP` permite reubicarlo.

    Por qué existe: la suite de pruebas escribía en el `data/` real del proyecto. Creaba
    `licitaciones.db` y volcaba `pipeline.jsonl` en la carpeta de trabajo, de modo que
    ejecutar los tests con datos reales dentro habría tocado la base de producción. Con esta
    variable, `tests/conftest.py` redirige toda escritura a un directorio temporal.
    """
    base = os.environ.get("DATA_DIR_INCOOP") or str(PROJECT_ROOT / "data")
    return str(Path(base).joinpath(*partes))

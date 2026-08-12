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

"""
src/ — Paquete raíz del Ecosistema Automático de Licitaciones (bfr_incoop).

Todos los módulos internos se importan de forma absoluta bajo el prefijo `src.`
(p. ej. `from src.memoria import Memoria`). Esta es la única raíz de importación
válida del proyecto: no deben usarse imports planos (`from memoria import ...`),
porque crearían un segundo objeto-módulo distinto para el mismo fichero.

Punto de entrada del pipeline: `python -m src.main` desde la raíz del proyecto,
o bien `python run.py`.
"""

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

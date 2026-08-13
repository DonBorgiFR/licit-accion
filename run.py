"""
run.py — Punto de entrada único del pipeline (Ecosistema Automático de Licitaciones).

Equivalente a `python -m src.main`, pero como fichero concreto al que puede apuntar
el Lanzador Silencioso VBS de la Capa 10.

El directorio de trabajo es indiferente: desde el Paso D3 (H-18) todas las rutas se
anclan a `PROJECT_ROOT` (`src/__init__.py`), no al directorio desde el que se invoca.
Por eso el Lanzador de la Capa 10 no necesita fijarlo antes de arrancar el pipeline.

Uso:
    python run.py [--dry-run] [--skip-centinela] [--batch-size N]
"""

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from src.main import main

if __name__ == "__main__":
    main()

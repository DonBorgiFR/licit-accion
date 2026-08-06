"""
run.py — Punto de entrada único del pipeline (Ecosistema Automático de Licitaciones).

Equivalente a `python -m src.main`, pero como fichero concreto al que puede apuntar
el Lanzador Silencioso VBS de la Capa 10.

IMPORTANTE: debe ejecutarse desde la raíz del proyecto, porque los módulos aún
resuelven `config/` y `data/` como rutas relativas al directorio de trabajo.

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

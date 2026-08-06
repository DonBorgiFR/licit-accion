"""
src/ — Paquete raíz del Ecosistema Automático de Licitaciones (bfr_incoop).

Todos los módulos internos se importan de forma absoluta bajo el prefijo `src.`
(p. ej. `from src.memoria import Memoria`). Esta es la única raíz de importación
válida del proyecto: no deben usarse imports planos (`from memoria import ...`),
porque crearían un segundo objeto-módulo distinto para el mismo fichero.

Punto de entrada del pipeline: `python -m src.main` desde la raíz del proyecto,
o bien `python run.py`.
"""

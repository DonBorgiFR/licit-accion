# Punto de entrada

Este proyecto se desarrolla en sesiones sucesivas y **con agentes de IA distintos** (Antigravity,
Claude Code y otros). El estado canónico **no vive en la conversación**: vive en `.agents/`.

**Antes de tocar nada, lee en este orden:**

1. **[`.agents/AGENTS.md`](.agents/AGENTS.md)** — las 14 Reglas de Rigor Operativo, las 7
   Convenciones Técnicas (C1–C7) y el estado capa por capa. **Son de obligado cumplimiento**, no
   recomendaciones: cada convención nació de un defecto real que llegó a producción.
2. **[`.agents/AUDITORIA_2026-07-27.md`](.agents/AUDITORIA_2026-07-27.md)** — los hallazgos con su
   evidencia reproducible. **No rediagnostiques lo que ya está ahí.**
3. **[`README.md`](README.md)** — diseño funcional, marco LCSP y detalle de cada capa.

**Lo que nunca hay que olvidar:**

* Punto de entrada del pipeline: `python run.py` desde la raíz. **Nunca** `python src/main.py`.
* Verificación antes de dar nada por bueno: `python -m pytest tests/ -q`.
* No se salta de capa, no se codifica sin plan validado por el usuario, y no se cierra una capa sin
  arrancar la aplicación contra la base real (Convención C7).

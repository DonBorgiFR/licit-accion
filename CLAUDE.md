# Punto de entrada

Este proyecto se desarrolla en sesiones sucesivas y **con agentes de IA distintos** (Antigravity,
Claude Code y otros). El estado canónico **no vive en la conversación**: vive en `.agents/`.

**Antes de tocar nada, lee en este orden:**

1. **[`.agents/ESTADO.md`](.agents/ESTADO.md)** — dónde está el proyecto, cuál es la tarea activa y
   qué se cerró en cada capa. **Es el fichero que cambia**, y el único donde se anota el resultado
   de un paso.
2. **[`.agents/AGENTS.md`](.agents/AGENTS.md)** — las 14 Reglas de Rigor Operativo y las 7
   Convenciones Técnicas (C1–C7). **Son de obligado cumplimiento**, no recomendaciones: cada
   convención nació de un defecto real que llegó a producción. Casi nunca cambia.
3. **[`.agents/AUDITORIA_2026-07-27.md`](.agents/AUDITORIA_2026-07-27.md)** — los hallazgos con su
   evidencia reproducible. **No rediagnostiques lo que ya está ahí.**
4. **[`README.md`](README.md)** — diseño funcional, marco LCSP y detalle de cada capa.

> Reglas y estado vivían juntos hasta el 2026-08-13, y esa mezcla producía deriva: en una sola
> revisión aparecieron tres recuentos distintos del mismo dato. **Al cerrar un paso se actualiza
> `ESTADO.md`, no `AGENTS.md`.**

**Lo que nunca hay que olvidar:**

* Punto de entrada del pipeline: `python run.py` desde la raíz. **Nunca** `python src/main.py`.
* Verificación antes de dar nada por bueno: `python -m pytest tests/ -q`.
* No se salta de capa, no se codifica sin plan validado por el usuario, y no se cierra una capa sin
  arrancar la aplicación contra la base real (Convención C7).

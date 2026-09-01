"""
tools/verificar_rastro_real.py — El lector canónico, medido contra el rastro de verdad.

**Por qué está aquí y no en la suite.** Una prueba que dependiera de `data/pipeline.jsonl`
fallaría en un clon limpio y cambiaría de resultado cada mañana, porque el despertador escribe
en él todos los días. Es la misma doctrina de la Convención C5 que sacó de la suite las llamadas
al LLM: lo que depende de datos reales se verifica aquí, a mano y cuando se quiere.

**Qué comprueba**, que es lo que cierra el bloque 9.B del contrato del Paso 9:

1. **La conservación**: toda línea no vacía o se tradujo a un evento o se contó como ilegible.
   Ninguna se pierde por el camino. Es la invariante que H-39 incumplía.
2. **Que las cuatro gramáticas siguen ahí** y el lector las reconoce todas.
3. **Que las líneas partidas de H-55 no crecen.** Hasta el 2026-09-01 este criterio sólo
   exigía que no desaparecieran, porque el defecto seguía vivo y sólo podía ir a más. Reparado
   el bloque 10.B.3, la exigencia se invierte: **19 y ni una más**. Si sube, o la reparación no
   funciona —y entonces la carrera también es entre procesos, no sólo entre hilos, y hace falta
   un cerrojo del sistema operativo— o queda un proceso anterior a la reparación escribiendo.
4. **Que la última corrida se puede reconstruir**, incluido el `boletin_fetch_started` de la
   gramática D —la minoritaria, la que acotó H-41— atribuido por ventana temporal.

Las cifras de la línea base se midieron el **2026-09-01**, al cerrar el bloque 10.B.3. **El
fichero crece**, así que de casi todo se informa la deriva en vez de exigir igualdad: lo que sí
se exige es que nada de lo medido entonces haya desaparecido, **y que las ilegibles se queden
exactamente donde están**.

    python tools/verificar_rastro_real.py
"""

import os
import sqlite3
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# La consola de Windows suele ser cp1252 y un solo carácter fuera de esa tabla aborta la
# impresión a mitad de informe. `errors="replace"` respeta la codificación del terminal y
# garantiza que una herramienta de diagnóstico nunca muera por cómo se ve, sólo por lo que mide.
sys.stdout.reconfigure(errors="replace")

from src import ruta_datos  # noqa: E402
from src.rastro import EstadoEvento, Gramatica, a_instante, leer_rastro  # noqa: E402

# Línea base medida el 2026-09-01, al reparar H-55 (bloque 10.B.3). La anterior era del
# 2026-08-27 —4.768 líneas y 14 ilegibles— y se quedó tres semanas atrás: el fichero había
# crecido un 55 % y sus cifras ya no servían de referencia para nada.
BASE = {"lineas": 7395, "ilegibles": 19, "A": 2306, "B": 1965, "C": 378, "D": 105,
        "CANONICA": 2622, "nombres": 98}


def encabezado(texto):
    print(f"\n{texto}\n{'=' * len(texto)}")


def main() -> int:
    destino = ruta_datos("pipeline.jsonl")
    encabezado(f"RASTRO REAL — {destino}")

    resultado = leer_rastro()
    if not resultado.existe:
        print("  El rastro no existe. Nada que verificar.")
        return 1

    traducidos = sum(resultado.gramaticas.values())
    conserva = resultado.lineas_totales == traducidos + resultado.lineas_ilegibles

    print(f"  Líneas no vacías ......... {resultado.lineas_totales:>6}   (base: {BASE['lineas']})")
    print(f"  Traducidas a evento ...... {traducidos:>6}")
    print(f"  Ilegibles ................ {resultado.lineas_ilegibles:>6}   (base: {BASE['ilegibles']})")
    print(f"  Degradado ................ {resultado.degradado}")
    if resultado.numeros_ilegibles:
        print(f"  Números de línea ......... {resultado.numeros_ilegibles}")
        if resultado.numeros_ilegibles_truncados:
            print("  (lista truncada; el recuento de arriba es el bueno)")

    encabezado("GRAMÁTICAS")
    for nombre in (g.value for g in Gramatica):
        cuantas = resultado.gramaticas.get(nombre, 0)
        referencia = BASE.get(nombre)
        sufijo = f"   (base: {referencia})" if referencia else ""
        print(f"  {nombre:<12} {cuantas:>6}{sufijo}")

    nombres = Counter(e.evento for e in resultado.eventos)
    estados = Counter(e.estado.value for e in resultado.eventos)
    print(f"\n  Nombres de evento distintos: {len(nombres)}   (base: {BASE['nombres']})")
    print(f"  Estados resueltos: {dict(estados)}")

    # -- La última corrida, reconstruida ---------------------------------------------------
    encabezado("LA ÚLTIMA CORRIDA, RECONSTRUIDA")
    corrida = None
    try:
        conexion = sqlite3.connect(ruta_datos("licitaciones.db"))
        conexion.row_factory = sqlite3.Row
        corrida = conexion.execute(
            "SELECT id, start_time, end_time, estado, errores FROM ejecuciones "
            "ORDER BY id DESC LIMIT 1"
        ).fetchone()
        conexion.close()
    except sqlite3.Error as exc:
        print(f"  No se pudo consultar la base: {exc}")

    degradados = []
    if corrida is None:
        print("  No consta ninguna corrida.")
    else:
        print(f"  Corrida nº {corrida['id']} — {corrida['estado']}, errores={corrida['errores']}")
        print(f"  Ventana: {corrida['start_time']} -> {corrida['end_time']}")

        # Por ventana temporal, no por `run_id`: las gramáticas C y D no lo escriben nunca, y es
        # justamente ahí donde vive el evento que acotó H-41.
        de_la_corrida = leer_rastro(
            desde=a_instante(corrida["start_time"]), hasta=a_instante(corrida["end_time"])
        ).eventos
        print(f"  Eventos atribuidos por ventana: {len(de_la_corrida)}")

        arranques = [e for e in de_la_corrida if e.evento == "boletin_fetch_started"]
        for evento in arranques:
            print(f"    · {evento.timestamp}  {evento.evento}  "
                  f"[gramática {evento.gramatica.value}, línea {evento.linea}]  "
                  f"{evento.datos.get('fuente', '')}")

        degradados = [e for e in de_la_corrida if e.estado is EstadoEvento.DEGRADADO]
        if degradados:
            print(f"\n  [!] La corrida consta '{corrida['estado']}' con errores={corrida['errores']}, "
                  f"y contiene {len(degradados)} evento(s) DEGRADADO:")
            for evento in degradados:
                detalle = evento.datos.get("error") or evento.datos.get("reason") or ""
                print(f"    · {evento.evento}  {evento.datos.get('fuente', '')}  {detalle[:90]}")
            print("  Es exactamente el estado COMPLETADA_CON_DEGRADACION que el Paso 9 añade.")

    # -- Veredicto -------------------------------------------------------------------------
    encabezado("VEREDICTO")
    comprobaciones = [
        ("Conservación: ninguna línea se pierde", conserva),
        ("Las cuatro gramáticas siguen reconociéndose",
         all(resultado.gramaticas.get(g, 0) > 0 for g in ("A", "B", "C", "D"))),
        # El criterio de la reparación, no el del diagnóstico: **congeladas en 19**. Las ya
        # rotas no se tocan —borrarlas sería destruir rastro—, así que lo que se vigila es que
        # no aparezca ninguna nueva.
        (f"Las líneas partidas de H-55 siguen congeladas en {BASE['ilegibles']}",
         resultado.lineas_ilegibles == BASE["ilegibles"]),
        ("Se reconstruye el `boletin_fetch_started` de la gramática D",
         any(e.evento == "boletin_fetch_started" for e in resultado.eventos)),
        ("El catálogo resuelve algún DEGRADADO histórico",
         estados.get(EstadoEvento.DEGRADADO.value, 0) > 0),
    ]
    for texto, bien in comprobaciones:
        print(f"  [{'OK ' if bien else 'MAL'}] {texto}")

    todo_bien = all(bien for _, bien in comprobaciones)
    print(f"\n  {'CORRECTO' if todo_bien else 'HAY FALLOS'}")
    return 0 if todo_bien else 1


if __name__ == "__main__":
    sys.exit(main())

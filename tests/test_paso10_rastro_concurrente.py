"""Regresiones de la escritura concurrente del rastro — Capa 10, Paso 10, bloque B.3.

Contrato: `.agents/CONTRATO_PASO_10.md` v1.3.0, **Operación 5**.
Plan: `.agents/PLAN_10B3.md`, sección 6. Hallazgo: **H-55**.

**QUÉ SE AFIRMA AQUÍ, Y POR QUÉ EL RECUENTO ES LO QUE IMPORTA.** H-55 se catalogó como *«líneas
partidas en el rastro»* porque es lo único que se ve leyendo el fichero. Medido el 2026-09-01, el
defecto real es otro y es peor: **con 16 hilos se pierde entre el 4,8 % y el 5,8 % de los
eventos**, y sólo 0-2 líneas quedan partidas. Las roturas son la parte visible, y es la pequeña —
**un evento que nunca llegó a escribirse no deja hueco**.

De ahí la forma de estas pruebas: **cuentan**. Con el defecto vivo, 16 hilos × 60 eventos dejan
906 líneas de 960 **y todas parsean**, así que una prueba que sólo comprobara la parseabilidad
daría verde sobre el defecto entero. `test_n_hilos_dejan_n_lineas` y
`test_cada_evento_aparece_exactamente_una_vez` son las que sostienen el bloque; el resto acompaña.

**Por qué el control de un solo hilo no sobra.** Es lo que separa *«el escritor está mal»* de
*«la concurrencia está mal»*, y es lo que protege de reparar la carrera rompiendo el caso normal,
que es el 99 % de las escrituras del proyecto.

**Ninguna sale a la red ni toca `data/`** *(Convención C5)*: todo ocurre en `tmp_path`.
"""

import json
import os
import subprocess
import sys
import threading

import pytest

from src.rastro import registrar_evento

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

#: El guion que ejecuta cada proceso hijo de `test_varios_procesos_no_pierden_eventos`.
#: **Tiene que ser un proceso de verdad**: la carrera que mide es entre espacios de memoria
#: distintos, y ahí un cerrojo de módulo no llega por definición. Simularla con hilos daría un
#: verde que no significa nada.
GUION_ESCRITOR = """
import sys, threading
sys.path.insert(0, sys.argv[1])
from src.rastro import registrar_evento
ruta, proceso, hilos, eventos = sys.argv[2], int(sys.argv[3]), int(sys.argv[4]), int(sys.argv[5])
barrera = threading.Barrier(hilos)
def trabajo(h):
    barrera.wait()
    for n in range(eventos):
        registrar_evento("prueba", "EVENTO_MULTIPROCESO", "INFO",
                         {"hilo": h, "n": n, "proceso": proceso}, ruta=ruta)
ts = [threading.Thread(target=trabajo, args=(i,)) for i in range(hilos)]
[t.start() for t in ts]
[t.join() for t in ts]
"""

#: Suficientes hilos para que la carrera se produzca siempre. Medido: con esta configuración el
#: código sin cerrojo perdió eventos en las cinco vueltas que se le dieron el 2026-09-01, entre
#: 41 y 56 de 960. Bajarlo volvería la prueba intermitente, que es peor que no tenerla.
HILOS = 16
EVENTOS_POR_HILO = 60
ESPERADOS = HILOS * EVENTOS_POR_HILO


def escribir_en_paralelo(ruta, hilos=HILOS, eventos=EVENTOS_POR_HILO, escritor=None):
    """Lanza `hilos` escritores simultáneos y devuelve cuando todos han terminado.

    La barrera no es adorno: sin ella los hilos arrancan escalonados, el solapamiento real es
    mucho menor y la prueba se vuelve intermitente. Se quiere el peor caso, y se quiere siempre.

    Cada evento lleva su `(hilo, n)` para poder comprobar **identidad** y no sólo cantidad: un
    recuento correcto con un duplicado y una pérdida también sumaría bien.
    """
    escribir = escritor or (
        lambda datos: registrar_evento("prueba", "EVENTO_CONCURRENTE", "INFO", datos, ruta=str(ruta))
    )
    barrera = threading.Barrier(hilos)

    def trabajo(identificador):
        barrera.wait()
        for numero in range(eventos):
            escribir({"hilo": identificador, "n": numero})

    trabajadores = [threading.Thread(target=trabajo, args=(i,)) for i in range(hilos)]
    for trabajador in trabajadores:
        trabajador.start()
    for trabajador in trabajadores:
        trabajador.join()


def leer_crudo(*rutas):
    """Devuelve `(lineas_totales, ilegibles, identidades)` de uno o varios ficheros de rastro.

    Se lee a mano en vez de con `leer_rastro()` a propósito: estas pruebas afirman sobre **lo que
    hay escrito en el disco**, y hacerlo pasar por el lector metería su traducción de por medio.
    El lector ya tiene sus propias regresiones en `test_paso9_rastro.py`.
    """
    totales = ilegibles = 0
    identidades = []
    for ruta in rutas:
        if not os.path.exists(ruta):
            continue
        with open(ruta, encoding="utf-8", errors="replace") as fichero:
            for linea in fichero:
                if not linea.strip():
                    continue
                totales += 1
                try:
                    evento = json.loads(linea)
                    identidades.append((evento["datos"]["hilo"], evento["datos"]["n"]))
                except (ValueError, KeyError, TypeError):
                    ilegibles += 1
    return totales, ilegibles, identidades


# ==============================================================================
# R4 · El control: un solo hilo. Si esto falla, el defecto no es la concurrencia
# ==============================================================================


def test_un_solo_hilo_no_pierde_ni_parte_nada(tmp_path):
    ruta = tmp_path / "pipeline.jsonl"
    escribir_en_paralelo(ruta, hilos=1, eventos=ESPERADOS)

    totales, ilegibles, identidades = leer_crudo(str(ruta))

    assert totales == ESPERADOS, "el escritor, solo, no puede perder una línea"
    assert ilegibles == 0
    assert len(set(identidades)) == ESPERADOS


# ==============================================================================
# R1 y R2 · Las dos que sostienen el bloque
# ==============================================================================


def test_n_hilos_dejan_n_lineas(tmp_path):
    """La postcondición de la Operación 5, **contada**.

    Es la prueba que H-55 no tenía y por la que el defecto sobrevivió a dos diagnósticos: nadie
    contaba, porque lo que se buscaba eran líneas rotas.
    """
    ruta = tmp_path / "pipeline.jsonl"
    escribir_en_paralelo(ruta)

    totales, _, _ = leer_crudo(str(ruta))

    assert totales == ESPERADOS, (
        f"se emitieron {ESPERADOS} eventos y hay {totales} líneas: "
        f"faltan {ESPERADOS - totales}, y las que faltan no dejaron hueco"
    )


def test_cada_evento_aparece_exactamente_una_vez(tmp_path):
    """Identidad, no cantidad. Un duplicado y una pérdida también sumarían bien."""
    ruta = tmp_path / "pipeline.jsonl"
    escribir_en_paralelo(ruta)

    _, _, identidades = leer_crudo(str(ruta))

    esperadas = {(hilo, n) for hilo in range(HILOS) for n in range(EVENTOS_POR_HILO)}
    perdidas = esperadas - set(identidades)
    duplicadas = len(identidades) - len(set(identidades))

    assert not perdidas, f"{len(perdidas)} eventos no llegaron nunca al fichero"
    assert duplicadas == 0, f"{duplicadas} eventos aparecen más de una vez"


# ==============================================================================
# R3 · Lo que el contrato pedía literalmente, que sigue haciendo falta
# ==============================================================================


def test_ninguna_linea_queda_partida(tmp_path):
    ruta = tmp_path / "pipeline.jsonl"
    escribir_en_paralelo(ruta)

    _, ilegibles, _ = leer_crudo(str(ruta))

    assert ilegibles == 0, f"{ilegibles} líneas quedaron partidas por la mitad"


# ==============================================================================
# R6 · Entre procesos, que es lo que la corrida real destapó el 2026-09-01
# ==============================================================================


def test_varios_procesos_no_pierden_eventos(tmp_path):
    """El cerrojo de módulo no bastaba, y esto lo comprobó una corrida real.

    **Cómo se descubrió**, y merece contarse porque el contrato afirmaba lo contrario. La
    Operación 5 declaraba *«alcance: sólo intra-proceso»*, con la evidencia de que **16 de las 19
    líneas rotas del rastro real se produjeron sin ninguna corrida activa**. Era cierto y era
    incompleto: en la corrida 24, con el cerrojo de módulo ya puesto, aparecieron **dos líneas
    rotas nuevas**, y las dos con la misma firma —un evento del pipeline encajado entre dos del
    servidor—:

        9594   radar   doc_detected
        9595   ROTA    's\\\\Antigravity\\\\...\\\\licitaciones.db", "directorio_accesible"...'
        9596   api     API_DEPENDENCIES_HEALTHCHECK_PASSED

    **La API y el pipeline escriben a la vez todos los días.** El plan dejó escrito el criterio
    que refutaría la apuesta —*«si el contador de rotas vuelve a subir, la carrera también es
    entre procesos»*— y saltó a la primera corrida real.

    Medido antes de reparar, con el cerrojo de módulo puesto: dos procesos de cuatro hilos
    perdían entre el **1,3 % y el 5,5 %** de los eventos, **sin una sola línea rota** en tres
    vueltas. Otra vez el mismo patrón: la pérdida no deja huella, y por eso hay que contar.
    """
    ruta = tmp_path / "pipeline.jsonl"
    procesos, hilos, eventos = 2, 4, 150

    hijos = [
        subprocess.Popen(
            [sys.executable, "-c", GUION_ESCRITOR, RAIZ, str(ruta), str(p), str(hilos), str(eventos)]
        )
        for p in range(procesos)
    ]
    for hijo in hijos:
        assert hijo.wait(timeout=120) == 0, "un escritor hijo terminó mal"

    esperados = {
        (p, h, n) for p in range(procesos) for h in range(hilos) for n in range(eventos)
    }
    vistos, ilegibles = set(), 0
    with open(str(ruta), encoding="utf-8", errors="replace") as fichero:
        for linea in fichero:
            if not linea.strip():
                continue
            try:
                datos = json.loads(linea)["datos"]
                vistos.add((datos["proceso"], datos["hilo"], datos["n"]))
            except (ValueError, KeyError, TypeError):
                ilegibles += 1

    perdidos = esperados - vistos
    assert not perdidos, f"{len(perdidos)} de {len(esperados)} eventos no llegaron al fichero"
    assert ilegibles == 0, f"{ilegibles} líneas quedaron partidas entre procesos"


# ==============================================================================
# R5 · La rotación, que hoy falla en silencio
# ==============================================================================


def test_la_rotacion_bajo_carga_no_pierde_eventos(tmp_path, monkeypatch):
    """`os.rename()` sobre un fichero que otro hilo tiene abierto **lanza `PermissionError`**.

    Medido el 2026-09-01. Y ese error lo traga un `except Exception` que sólo imprime
    *(`src/api/dependencies.py`)*, así que con el Cockpit abierto la rotación **falla en
    silencio** y el fichero crece sin límite. Hoy no se nota porque `pipeline.jsonl` va por 2,1 MB
    de los 10 que la disparan.

    El umbral se baja por monkeypatch para no tener que escribir 10 MB en una prueba. **Se
    calibra para que la rotación ocurra UNA vez**, no veinte: el nombre del archivo lleva la
    marca de tiempo al segundo, así que veinte rotaciones seguidas colisionarían entre ellas y la
    prueba estaría midiendo una carrera que en producción no existe —a 10 MB, volver a llenar el
    fichero en el mismo segundo es imposible—. Se quiere el defecto real, no uno fabricado.
    """
    from src.api import dependencies

    rotacion_real = dependencies.rotar_log_si_excede_tamano
    monkeypatch.setattr(
        dependencies,
        "rotar_log_si_excede_tamano",
        # 64 KB sobre ~100 KB de escritura total: una rotación, y lo que queda no vuelve a
        # alcanzar el umbral. `max_archivos` alto a propósito: la purga de archivos viejos borra
        # eventos de forma legítima, y aquí se mide pérdida accidental — mezclarlas daría un
        # rojo falso.
        lambda ruta, max_bytes=64 * 1024, max_archivos=1000: rotacion_real(ruta, max_bytes, max_archivos),
    )

    destino = tmp_path / "pipeline.jsonl"
    gestor = dependencies.GestorTrazabilidadAPI(log_path=str(destino))
    escribir_en_paralelo(
        destino,
        eventos=40,
        escritor=lambda datos: gestor.registrar_evento("EVENTO_CONCURRENTE", datos, estado="INFO"),
    )

    archivos = sorted(tmp_path.glob("pipeline_*.jsonl"))
    totales, ilegibles, identidades = leer_crudo(str(destino), *[str(a) for a in archivos])
    esperados = HILOS * 40

    assert archivos, "con el umbral en 64 KB la rotación tenía que haber ocurrido"
    assert ilegibles == 0
    assert len(set(identidades)) == esperados, (
        f"entre el fichero vivo y sus {len(archivos)} archivos hay "
        f"{len(set(identidades))} eventos de {esperados}"
    )

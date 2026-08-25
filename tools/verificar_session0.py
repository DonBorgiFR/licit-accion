"""
tools/verificar_session0.py — La prueba que de verdad cierra el Paso 8.

**Qué se está probando, y por qué no basta con que la tarea se registre.** Marcar *"ejecutar
tanto si el usuario ha iniciado sesión como si no"* es lo correcto para una tarea nocturna, y es
a la vez lo que lleva el proceso a la **Session 0**: un entorno sin escritorio. Cualquier llamada
gráfica que se escape allí —un diálogo de error, un navegador— **no falla**: se queda esperando a
un usuario que no existe, para siempre. El síntoma no es un error en ningún registro; es una
tarea que no termina nunca y un cerrojo que nadie suelta.

Por eso el contrato de la Capa 10 dice, literalmente, que la prueba que cierra la capa no es que
la tarea se registre, **sino que una corrida sin escritorio termine sola y no deje proceso vivo**.
Eso no se puede comprobar con la suite: hace falta una sesión cerrada de verdad.

**Cómo se usa** *(tres pasos, y el de en medio lo hace una persona)*:

    python tools/verificar_session0.py --preparar        # tarea de una sola vez, dentro de 3 min
    ... CERRAR SESIÓN de Windows (no apagar), esperar, volver a entrar ...
    python tools/verificar_session0.py --revisar         # el veredicto
    python tools/verificar_session0.py --retirar         # limpiar

**Por qué una tarea aparte y no la de verdad.** Para no dejar el despertador dado de alta como
efecto colateral de una prueba: darlo de alta es una decisión, y se toma aparte. Pero el XML lo
construye `registrar_despertador._construir_xml()`, **el mismo que la tarea real**, de modo que
usuario, `LogonType`, directorio de trabajo y orden son idénticos. Si la prueba se construyera por
su cuenta, se parecería a la de verdad hoy y dejaría de parecérsele el día que alguien cambiara
una de las dos — y estaríamos verificando otra cosa.

**Cerrar sesión, no apagar ni bloquear.** Bloquear la pantalla **no** vale: la sesión sigue
abierta y el proceso no iría a la Session 0, así que la prueba pasaría sin haber probado nada.
Es el falso verde que esta herramienta existe para evitar.
"""

import argparse
import io
import json
import os
import platform
import subprocess
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import ruta_datos  # noqa: E402
from src.lanzador import cargar_configuracion  # noqa: E402
from src.memoria import Memoria  # noqa: E402
from tools import registrar_despertador as despertador  # noqa: E402


NOMBRE_PRUEBA = "Incoop - Prueba Session 0"
FICHERO_TESTIGO = "prueba_session0.json"


def _ruta_testigo() -> str:
    return ruta_datos("logs", FICHERO_TESTIGO)


def _ultima_ejecucion():
    """El id de la última corrida registrada, para saber cuál nace de la prueba."""
    db = Memoria()
    with db.conectar() as conn:
        fila = conn.execute("SELECT MAX(id) FROM ejecuciones;").fetchone()
    return fila[0] if fila and fila[0] is not None else 0


def _procesos_del_lanzador():
    """PIDs de procesos que estén ejecutando nuestro módulo ahora mismo.

    Se pregunta por la línea de órdenes y no por el nombre del ejecutable: `python.exe` hay
    muchos —éste mismo lo es— y lo que se busca es **el nuestro**.

    ⚠️ **Y se excluye el proceso que pregunta.** Descubierto probando el propio detector: un
    `python -c` que mencionaba `src.lanzador` en su código **se encontraba a sí mismo**, porque
    ese texto vive en su línea de órdenes. Aquí no ocurriría —esta herramienta se invoca por su
    ruta— pero es justo la clase de detalle que convertiría el veredicto en un ❌ eterno sin
    que nada estuviera mal. **Una prueba mal montada mide su propio andamiaje**, que es la
    lección que `src/proceso.py` ya dejó escrita para el caso hermano.
    """
    yo = os.getpid()
    try:
        completado = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "Get-CimInstance Win32_Process -Filter \"Name='python.exe' or Name='pythonw.exe'\" "
             "| Where-Object { $_.CommandLine -like '*src.lanzador*' } "
             "| Select-Object -ExpandProperty ProcessId"],
            capture_output=True, text=True, encoding="cp850", errors="replace",
        )
        encontrados = [int(p) for p in (completado.stdout or "").split() if p.strip().isdigit()]
        return [p for p in encontrados if p != yo]
    except Exception:
        return []


def preparar(minutos: int) -> int:
    config = cargar_configuracion()
    cuando = datetime.now() + timedelta(minutes=minutos)

    xml = despertador._construir_xml(
        hora=config.despertador.hora,
        ejecutar_si_se_perdio=config.despertador.ejecutar_si_se_perdio,
        tope_minutos=config.despertador.duracion_maxima_minutos,
        una_sola_vez=cuando,
        nota="[PRUEBA DE SESSION 0 - se puede borrar]",
    )

    codigo, salida = despertador.registrar_xml(NOMBRE_PRUEBA, xml)
    if codigo != 0:
        print()
        print("  [!] El Programador rechazó la tarea de prueba.")
        print(f"      {salida.strip()}")
        print()
        print("  Si el motivo es 'S4U', este equipo no permite ejecutar sin sesión iniciada")
        print("  sin guardar una contraseña. Esta herramienta no las maneja: habría que")
        print("  ajustarlo desde el Programador de tareas de Windows.")
        return 1

    testigo = {
        "preparada_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "equipo": platform.node(),
        "disparo_previsto": cuando.strftime("%Y-%m-%d %H:%M:%S"),
        "ultima_ejecucion_antes": _ultima_ejecucion(),
        "procesos_antes": _procesos_del_lanzador(),
    }
    os.makedirs(os.path.dirname(_ruta_testigo()), exist_ok=True)
    with io.open(_ruta_testigo(), "w", encoding="utf-8") as f:
        f.write(json.dumps(testigo, ensure_ascii=False, indent=1))

    print()
    print("=" * 74)
    print("PRUEBA DE SESSION 0 · preparada")
    print("=" * 74)
    print(f"  Tarea            : {NOMBRE_PRUEBA}")
    print(f"  Se disparará a las: {cuando.strftime('%H:%M:%S')}  (dentro de {minutos} min)")
    print(f"  Última corrida antes de la prueba: id {testigo['ultima_ejecucion_antes']}")
    print()
    print("  AHORA, Y ESTO NO LO PUEDE HACER LA HERRAMIENTA:")
    print()
    print("   1. CIERRA SESIÓN de Windows.  Menú Inicio → tu usuario → 'Cerrar sesión'.")
    print("      NO vale bloquear la pantalla (Win+L): la sesión seguiría abierta y el")
    print("      proceso NO iría a la Session 0. La prueba pasaría sin probar nada.")
    print("      NO apagues el equipo: la tarea no llegaría a dispararse.")
    print()
    print(f"   2. Espera al menos {minutos + 3} minutos con la sesión cerrada.")
    print("      La prospección real tarda unos minutos; dale margen.")
    print()
    print("   3. Vuelve a iniciar sesión y ejecuta:")
    print("         python tools/verificar_session0.py --revisar")
    return 0


def _consultar_tarea():
    codigo, salida = despertador._schtasks(
        ["/Query", "/TN", NOMBRE_PRUEBA, "/FO", "LIST", "/V"]
    )
    datos = {}
    for linea in salida.splitlines():
        if ":" in linea:
            clave, _, valor = linea.partition(":")
            datos[clave.strip()] = valor.strip()
    return codigo, datos, salida


def _valor(datos, *claves):
    for clave in claves:
        if clave in datos:
            return datos[clave]
    return None


def revisar() -> int:
    if not os.path.exists(_ruta_testigo()):
        print("  [!] No hay ninguna prueba preparada. Ejecuta primero --preparar.")
        return 2

    with io.open(_ruta_testigo(), encoding="utf-8") as f:
        testigo = json.load(f)

    print()
    print("=" * 74)
    print("PRUEBA DE SESSION 0 · veredicto")
    print("=" * 74)
    print(f"  Preparada el      : {testigo['preparada_at']} en {testigo['equipo']}")
    print(f"  Disparo previsto  : {testigo['disparo_previsto']}")
    print()

    _, datos, _ = _consultar_tarea()
    estado_tarea = _valor(datos, "Estado", "Status")
    ultima = _valor(datos, "Hora última ejecución", "Last Run Time")
    resultado = _valor(datos, "Último resultado", "Last Result")

    # --- 1. ¿Se disparó? ---
    corrida_nueva = _ultima_ejecucion() > testigo["ultima_ejecucion_antes"]
    print(f"  1. ¿Se disparó la tarea?           {ultima or '(sin dato)'}")
    print(f"     ¿Nació una corrida nueva?       {'SÍ' if corrida_nueva else 'NO'}")

    if not corrida_nueva:
        print()
        print("  [!] VEREDICTO: la prueba NO llegó a ejecutarse.")
        print("     No demuestra nada, ni bueno ni malo. Comprueba si esperaste lo bastante,")
        print("     si cerraste sesión de verdad y si el equipo siguió encendido.")
        return 3

    # --- 2. ¿Terminó, o sigue ahí? ---
    print(f"  2. Estado de la tarea ahora        {estado_tarea or '(sin dato)'}")
    print(f"     Código que registró Windows     {resultado or '(sin dato)'}")
    sigue_corriendo = (estado_tarea or "").lower() in ("running", "en ejecución", "en ejecucion")

    # --- 3. Lo decisivo: ¿queda algún proceso vivo? ---
    vivos = _procesos_del_lanzador()
    nuevos = [p for p in vivos if p not in testigo.get("procesos_antes", [])]
    print(f"  3. Procesos del lanzador vivos     {nuevos if nuevos else 'ninguno'}")

    # --- 4. ¿La corrida quedó cerrada en la base? ---
    db = Memoria()
    with db.conectar() as conn:
        fila = conn.execute(
            "SELECT id, estado, start_time, end_time FROM ejecuciones ORDER BY id DESC LIMIT 1;"
        ).fetchone()
    print(f"  4. Última corrida                  id {fila[0]} · {fila[1]}")
    corrida_cerrada = fila[1] != "RUNNING"

    # --- 5. ¿El lanzador supo que no había escritorio? ---
    eventos = _eventos_del_lanzador()
    print(f"  5. Eventos del lanzador            {', '.join(eventos) if eventos else '(ninguno)'}")

    print()
    if sigue_corriendo or nuevos:
        print("  [X] VEREDICTO: FALLA. Quedó algo vivo después de la prueba.")
        print("     Es exactamente el fallo que el Paso 8 existe para impedir: una llamada")
        print("     gráfica se escapó a la Session 0 y está esperando a un usuario que no")
        print("     existe. Hay que buscarla, y el sitio es `es_sesion_interactiva()`.")
        if nuevos:
            print(f"     Procesos a matar a mano: {nuevos}")
        return 1

    if not corrida_cerrada:
        print("  [!] VEREDICTO: PARCIAL. No quedó proceso vivo, pero la corrida sigue RUNNING.")
        print("     Se murió sin ejecutar su `finally`. No es el fallo de la Session 0, pero")
        print("     conviene mirar por qué: es la firma de H-41.")
        return 1

    print("  [OK] VEREDICTO: PASA.")
    print("     Una corrida sin escritorio terminó sola, no dejó ningún proceso vivo y su")
    print("     fila quedó cerrada. Es lo que cierra el Paso 8.")
    print()
    print("     Para limpiar:  python tools/verificar_session0.py --retirar")
    return 0


def _eventos_del_lanzador(ultimos: int = 400):
    """Los `LANZADOR_*` recientes del rastro, tolerando líneas rotas (H-55)."""
    ruta = ruta_datos("pipeline.jsonl")
    if not os.path.exists(ruta):
        return []
    vistos = []
    with io.open(ruta, encoding="utf-8", errors="replace") as f:
        for linea in f.readlines()[-ultimos:]:
            try:
                dato = json.loads(linea)
            except Exception:
                continue
            accion = dato.get("action") or dato.get("tipo_evento") or ""
            if accion.startswith("LANZADOR_") and accion not in vistos:
                vistos.append(accion)
    return vistos


def retirar() -> int:
    codigo, salida = despertador.retirar_tarea(NOMBRE_PRUEBA)
    if codigo != 0:
        print(f"  [!] No se pudo retirar la tarea de prueba: {salida.strip()}")
        return 1
    try:
        os.remove(_ruta_testigo())
    except OSError:
        pass
    print()
    print(f"  [+] Tarea de prueba retirada. El despertador de verdad no se ha tocado.")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Verifica que una corrida sin escritorio termina sola (Capa 10, Paso 8)."
    )
    grupo = parser.add_mutually_exclusive_group(required=True)
    grupo.add_argument("--preparar", action="store_true", help="Registra la tarea de prueba.")
    grupo.add_argument("--revisar", action="store_true", help="Da el veredicto tras volver.")
    grupo.add_argument("--retirar", action="store_true", help="Retira la tarea de prueba.")
    parser.add_argument("--minutos", type=int, default=3,
                        help="Dentro de cuántos minutos se dispara (por defecto 3).")
    args = parser.parse_args(argv)

    if os.name != "nt":
        print("[!] La Session 0 es un concepto de Windows.")
        return 1

    if args.preparar:
        if args.minutos < 2:
            print("[!] Menos de 2 minutos no da tiempo a cerrar sesión. Sube --minutos.")
            return 2
        return preparar(args.minutos)
    if args.revisar:
        return revisar()
    return retirar()


if __name__ == "__main__":
    raise SystemExit(main())

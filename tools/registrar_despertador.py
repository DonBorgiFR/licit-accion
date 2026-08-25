"""
tools/registrar_despertador.py — Dar de alta y de baja el despertador nocturno.

**Por qué una herramienta y no la interfaz del Programador de tareas** *(decisión de dirección,
2026-08-12)*: lo que se hace a mano no se documenta ni se reproduce. Dentro de un año nadie
recordará qué casillas se marcaron, y en un PC nuevo habría que adivinarlas.

Uso:

    python tools/registrar_despertador.py            # estado; no toca nada
    python tools/registrar_despertador.py --alta
    python tools/registrar_despertador.py --baja

---

### Las cuatro decisiones de esta herramienta, y por qué

**1. Se registra por XML y no con los modificadores de `schtasks`.** No es preferencia: la
configuración declara `ejecutar_si_se_perdio`, que en el Programador es `StartWhenAvailable`, y
**la línea de órdenes de `schtasks` no sabe ponerlo**. Registrar con `/SC DAILY /ST 06:30` habría
dado una tarea que ignora en silencio la mitad de lo que el fichero declara — un fin de semana con
el equipo apagado y un lunes sin las oportunidades del viernes.

**2. La tarea invoca `python.exe`, no `pythonw.exe` — y nunca `Incoop.vbs`.** Lo del `.vbs` viene
del Paso 7 y es la invariante central: su diálogo de arranque colgaría **para siempre** en la
Session 0. Lo de `python.exe` es más fino y va al revés que en el doble clic: la lanzadera usa
`pythonw` porque ahí hay una persona que vería la consola negra, y aquí no hay nadie. A cambio,
un proceso con consola **puede recibir `CTRL_BREAK_EVENT`**, que es el nivel 2 de la escalera con
la que el Paso 8 detiene un pipeline colgado — y la diferencia entre ese nivel y el siguiente es
la diferencia entre una corrida cerrada limpiamente y una fila `RUNNING` fantasma.

**3. `LogonType = S4U`, que es *"ejecutar tanto si el usuario ha iniciado sesión como si no"* sin
guardar ninguna contraseña.** La casilla es la decisión crítica del paso: es lo correcto para una
tarea nocturna y es lo que lleva el proceso a la Session 0. La alternativa —`Password`— obligaría a
teclear la contraseña de Windows aquí dentro, y **esta herramienta no maneja contraseñas**. Si S4U
no funcionara en este equipo, el remedio no es que la herramienta pida la contraseña: es que la
persona cambie ese ajuste desde el Programador, con sus credenciales y sin intermediarios.

**4. `WorkingDirectory` en la raíz del proyecto, y la orden es `-m src.lanzador`.** `python
src/lanzador.py` **no arranca** —`ModuleNotFoundError: No module named 'src'`—, que es la trampa de
la Convención C1 y exactamente el defecto que fue H-50. Una tarea nocturna que fallara así no lo
diría en ningún sitio salvo en un código de salida que nadie mira.
"""

import argparse
import os
import platform
import subprocess
import sys
import tempfile
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import PROJECT_ROOT  # noqa: E402
from src.lanzador import cargar_configuracion  # noqa: E402


#: El nombre con el que la tarea aparece en el Programador. Estable a propósito: cambiarlo
#: convertiría una actualización en dos tareas nocturnas sobre la misma base.
NOMBRE_TAREA = "Incoop - Despertador"


def _interprete() -> str:
    """`python.exe`, aunque nos hayan invocado con `pythonw.exe`. Ver la decisión 2 de arriba."""
    ejecutable = sys.executable
    if os.path.basename(ejecutable).lower() == "pythonw.exe":
        candidato = os.path.join(os.path.dirname(ejecutable), "python.exe")
        if os.path.exists(candidato):
            return candidato
    return ejecutable


def _construir_xml(hora: str, ejecutar_si_se_perdio: bool, tope_minutos: int) -> str:
    """El XML de la tarea, construido desde `config/lanzador.yaml` y de ningún otro sitio."""
    usuario = f"{os.environ.get('USERDOMAIN', '')}\\{os.environ.get('USERNAME', '')}".strip("\\")
    equipo = platform.node()
    hoy = datetime.now().strftime("%Y-%m-%d")
    recuperar = "true" if ejecutar_si_se_perdio else "false"

    # El tope del lanzador y el del Programador no son el mismo mecanismo, y conviene que no
    # coincidan: el nuestro detiene el pipeline y **deja constancia** con el código 32; el del
    # Programador mata la tarea entera sin contar nada. Se le da margen (el doble) para que el
    # que actúe primero sea siempre el que sabe explicarse.
    limite_programador = f"PT{max(tope_minutos * 2, 120)}M"

    descripcion = (
        f"Prospeccion nocturna del Ecosistema de Licitaciones de Incoop. "
        f"Dada de alta por tools/registrar_despertador.py en el equipo {equipo} el {hoy}. "
        f"Ejecuta el modo 'solo pipeline': sin servidor, sin pantalla y sin una sola llamada "
        f"grafica, porque corre en la Session 0. No invocar Incoop.vbs desde aqui."
    )

    return f"""<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>{descripcion}</Description>
    <URI>\\{NOMBRE_TAREA}</URI>
  </RegistrationInfo>
  <Triggers>
    <CalendarTrigger>
      <StartBoundary>2026-01-01T{hora}:00</StartBoundary>
      <Enabled>true</Enabled>
      <ScheduleByDay><DaysInterval>1</DaysInterval></ScheduleByDay>
    </CalendarTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <UserId>{usuario}</UserId>
      <LogonType>S4U</LogonType>
      <RunLevel>LeastPrivilege</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <AllowHardTerminate>true</AllowHardTerminate>
    <StartWhenAvailable>{recuperar}</StartWhenAvailable>
    <RunOnlyIfNetworkAvailable>false</RunOnlyIfNetworkAvailable>
    <Enabled>true</Enabled>
    <Hidden>false</Hidden>
    <WakeToRun>false</WakeToRun>
    <ExecutionTimeLimit>{limite_programador}</ExecutionTimeLimit>
    <Priority>7</Priority>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>{_interprete()}</Command>
      <Arguments>-m src.lanzador --modo pipeline</Arguments>
      <WorkingDirectory>{PROJECT_ROOT}</WorkingDirectory>
    </Exec>
  </Actions>
</Task>
"""


def _schtasks(argumentos):
    """Invoca `schtasks` y devuelve (codigo, salida). Nunca lanza."""
    try:
        completado = subprocess.run(
            ["schtasks"] + argumentos,
            capture_output=True, text=True, encoding="cp850", errors="replace",
        )
        return completado.returncode, (completado.stdout or "") + (completado.stderr or "")
    except Exception as e:
        return -1, f"no se pudo invocar schtasks: {e}"


def existe_tarea() -> bool:
    codigo, _ = _schtasks(["/Query", "/TN", NOMBRE_TAREA])
    return codigo == 0


def informar_estado(config) -> int:
    print()
    print("=" * 74)
    print(f"Despertador · tarea '{NOMBRE_TAREA}'")
    print("=" * 74)
    print(f"  Equipo actual        : {platform.node()}")
    print(f"  Hora declarada       : {config.despertador.hora}  (config/lanzador.yaml)")
    print(f"  Si se perdió         : {'se recupera al arrancar' if config.despertador.ejecutar_si_se_perdio else 'se salta'}")
    print(f"  Tope del pipeline    : {config.despertador.duracion_maxima_minutos} min")
    print()

    if not existe_tarea():
        print("  Estado: NO DADA DE ALTA en este equipo.")
        print()
        print("  Para darla de alta:  python tools/registrar_despertador.py --alta")
        return 0

    codigo, salida = _schtasks(["/Query", "/TN", NOMBRE_TAREA, "/FO", "LIST", "/V"])
    print("  Estado: DADA DE ALTA.")
    interesan = (
        "Hora próxima ejecución", "Next Run Time", "Estado", "Status",
        "Hora última ejecución", "Last Run Time", "Último resultado", "Last Result",
        "Ejecutar como usuario", "Run As User", "Tarea que se ejecutará", "Task To Run",
        "Comentario", "Comment",
    )
    for linea in salida.splitlines():
        if any(linea.strip().startswith(c) for c in interesan):
            print(f"    {linea.strip()}")
    return 0 if codigo == 0 else 1


def dar_de_alta(config) -> int:
    ya_estaba = existe_tarea()

    xml = _construir_xml(
        hora=config.despertador.hora,
        ejecutar_si_se_perdio=config.despertador.ejecutar_si_se_perdio,
        tope_minutos=config.despertador.duracion_maxima_minutos,
    )

    # El Programador exige el XML en UTF-16; en UTF-8 lo rechaza con un error que no explica
    # nada. Se escribe a un temporal y se retira siempre.
    manejador, ruta_xml = tempfile.mkstemp(suffix=".xml", prefix="incoop_despertador_")
    os.close(manejador)
    try:
        with open(ruta_xml, "w", encoding="utf-16") as f:
            f.write(xml)

        # `/F` es lo que hace esto idempotente: sustituye la tarea si ya existía, en vez de
        # fallar o —peor— crear una segunda que prospectaría sobre la misma base.
        codigo, salida = _schtasks(["/Create", "/TN", NOMBRE_TAREA, "/XML", ruta_xml, "/F"])
    finally:
        try:
            os.remove(ruta_xml)
        except OSError:
            pass

    if codigo != 0:
        print()
        print("  [!] El Programador de tareas rechazó el alta.")
        print(f"      {salida.strip()}")
        print()
        print("  Lo más probable es que este equipo no permita 'S4U' —ejecutar sin sesión")
        print("  iniciada y sin contraseña guardada—. Esta herramienta NO pide contraseñas:")
        print("  si hace falta una, la tarea hay que ajustarla desde el Programador de tareas")
        print("  de Windows, marcando 'Ejecutar tanto si el usuario inició sesión como si no'.")
        return 1

    print()
    print(f"  [+] Tarea {'actualizada' if ya_estaba else 'creada'}: '{NOMBRE_TAREA}'")
    print(f"      Equipo    : {platform.node()}")
    print(f"      Hora      : {config.despertador.hora} cada día")
    print(f"      Ejecuta   : {_interprete()} -m src.lanzador --modo pipeline")
    print(f"      Desde     : {PROJECT_ROOT}")
    print()
    print("  ⚠️  Que la tarea se registre NO cierra el Paso 8. Lo que lo cierra es comprobar")
    print("      que una corrida SIN SESIÓN INICIADA termina sola y no deja proceso vivo:")
    print("      el síntoma de un diálogo esperando a nadie es un proceso que no acaba nunca.")
    return 0


def dar_de_baja() -> int:
    if not existe_tarea():
        # Dar de baja lo que no existe no es un error: es el estado que se pedía.
        print()
        print(f"  [~] La tarea '{NOMBRE_TAREA}' no estaba dada de alta. Nada que hacer.")
        return 0

    codigo, salida = _schtasks(["/Delete", "/TN", NOMBRE_TAREA, "/F"])
    if codigo != 0:
        print(f"  [!] No se pudo dar de baja: {salida.strip()}")
        return 1
    print()
    print(f"  [+] Tarea '{NOMBRE_TAREA}' dada de baja. El pipeline ya no se ejecutará solo.")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Da de alta o de baja el despertador nocturno (Capa 10, Paso 8)."
    )
    grupo = parser.add_mutually_exclusive_group()
    grupo.add_argument("--alta", action="store_true", help="Registra la tarea. Idempotente.")
    grupo.add_argument("--baja", action="store_true", help="Retira la tarea. Idempotente.")
    args = parser.parse_args(argv)

    if os.name != "nt":
        print("[!] El Programador de tareas de Windows sólo existe en Windows.")
        return 1

    config = cargar_configuracion()

    if args.alta:
        return dar_de_alta(config)
    if args.baja:
        return dar_de_baja()
    return informar_estado(config)


if __name__ == "__main__":
    raise SystemExit(main())

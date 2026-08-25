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

**2. Nunca `Incoop.vbs`.** Viene del Paso 7 y es la invariante central: su diálogo de arranque
colgaría **para siempre** si la tarea corriera sin escritorio.

**3. `LogonType = InteractiveToken` por defecto, y no `S4U`** *(decisión de dirección,
2026-08-25, tomada con la medición delante)*.

El paso se diseñó sobre `S4U` —*"ejecutar tanto si el usuario ha iniciado sesión como si no"* sin
guardar contraseña—, porque es lo canónico para una tarea nocturna. **Al ir a registrarla, el
Programador la rechazó: `Acceso denegado`.** La cuenta de este equipo (`AROMAN\\USUARIO`) es un
usuario estándar, sin permisos de administrador, y *"ejecutar sin sesión iniciada"* exige el
privilegio *Iniciar sesión como trabajo por lotes*, que sólo un administrador concede. Medido
contra el sistema real, no deducido: con `S4U` el alta da `Acceso denegado`; con
`InteractiveToken` se crea sin una queja.

**Y lo que parecía un recorte resultó ser una simplificación.** Toda la dificultad de este paso
—la Session 0, el diálogo que espera a un usuario que no existe, la verificación con la sesión
cerrada— **venía exclusivamente de `S4U`**. Con `InteractiveToken` el pipeline corre en la sesión
de la persona, igual que tras un doble clic, y esa clase entera de fallo desaparece.

**Lo que se pierde, dicho sin adornos**: no prospecta con el equipo encendido y la sesión cerrada.
Lo amortigua `StartWhenAvailable` —que ya estaba decidido—: una ejecución perdida se lanza **en
cuanto la persona entra**, así que un día sin prospectar se convierte en una prospección al
encender por la mañana.

**`Password` no se contempla**: obligaría a teclear la contraseña de Windows dentro de una
herramienta del proyecto, y **esta herramienta no maneja contraseñas**. Si algún día hiciera falta
`S4U`, lo concede un administrador desde fuera, sin intermediarios.

**4. El intérprete depende de eso mismo**, y por eso `_interprete()` recibe el modo. Con sesión
abierta, `pythonw.exe`: `python.exe` plantaría una consola negra delante de quien esté trabajando,
y el Programador no sabe ocultar la ventana de una acción. Ver el detalle en esa función.

**5. `WorkingDirectory` en la raíz del proyecto, y la orden es `-m src.lanzador`.** `python
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


def _interprete(sin_sesion: bool = False) -> str:
    """Qué intérprete pone la tarea, y depende de si habrá alguien delante.

    * **Con la sesión abierta (`sin_sesion=False`, el caso normal): `pythonw.exe`.** La tarea
      corre en el escritorio de la persona, y `python.exe` le plantaría **una consola negra
      delante mientras trabaja**, a las 06:30 o al encender el equipo. El Programador de tareas
      no sabe ocultar la ventana de una acción, así que la única forma de no molestar es un
      intérprete que no cree ninguna.
    * **Sin sesión iniciada (`sin_sesion=True`): `python.exe`.** Ahí no hay nadie a quien
      molestar, y a cambio un proceso **con** consola puede recibir `CTRL_BREAK_EVENT` —el
      nivel 2 de la escalera que detiene un pipeline colgado—, que es la diferencia entre una
      corrida cerrada limpiamente y una fila `RUNNING` fantasma.

    ⚠️ **El coste de `pythonw` está medido y asumido**: bajo él, `CTRL_BREAK_EVENT` falla con
    «WinError 6» *(Paso 5, 2026-08-18)*, de modo que un pipeline que agote su tope se detendrá
    por las bravas y dejará su fila `RUNNING` sin cerrar. **No es un cabo suelto**: es lo que
    H-40 reparó en el Paso 6 —la corrida siguiente ve que el PID ya no existe y la reclama—.
    Se prefiere eso a una ventana negra en la cara de quien está trabajando.
    """
    ejecutable = sys.executable
    carpeta = os.path.dirname(ejecutable)
    deseado = "python.exe" if sin_sesion else "pythonw.exe"

    if os.path.basename(ejecutable).lower() != deseado:
        candidato = os.path.join(carpeta, deseado)
        if os.path.exists(candidato):
            return candidato
    return ejecutable


def _construir_xml(
    hora: str,
    ejecutar_si_se_perdio: bool,
    tope_minutos: int,
    una_sola_vez=None,
    nota: str = "",
    sin_sesion: bool = False,
) -> str:
    """El XML de la tarea, construido desde `config/lanzador.yaml` y de ningún otro sitio.

    `una_sola_vez` —un `datetime`— cambia el disparador diario por uno de una sola vez a esa
    hora. Lo usa `tools/verificar_session0.py`, y **por eso vive aquí y no allí**: la
    verificación de la Session 0 sólo demuestra algo si la tarea que se prueba tiene el mismo
    usuario, el mismo `LogonType`, el mismo directorio y la misma orden que la de verdad. Una
    tarea de prueba construida aparte se le parecería hoy y dejaría de parecérsele el día que
    alguien cambiara una de las dos.
    """
    usuario = f"{os.environ.get('USERDOMAIN', '')}\\{os.environ.get('USERNAME', '')}".strip("\\")
    equipo = platform.node()
    hoy = datetime.now().strftime("%Y-%m-%d")
    recuperar = "true" if ejecutar_si_se_perdio else "false"

    # El tope del lanzador y el del Programador no son el mismo mecanismo, y conviene que no
    # coincidan: el nuestro detiene el pipeline y **deja constancia** con el código 32; el del
    # Programador mata la tarea entera sin contar nada. Se le da margen (el doble) para que el
    # que actúe primero sea siempre el que sabe explicarse.
    limite_programador = f"PT{max(tope_minutos * 2, 120)}M"

    cuando_corre = (
        "Corre sin sesion iniciada, en la Session 0: ni una sola llamada grafica."
        if sin_sesion else
        "Corre dentro de la sesion del usuario, asi que no necesita permisos de administrador."
    )
    descripcion = (
        f"Prospeccion del Ecosistema de Licitaciones de Incoop. "
        f"Dada de alta por tools/registrar_despertador.py en el equipo {equipo} el {hoy}. "
        f"Ejecuta el modo 'solo pipeline': sin servidor y sin pantalla. {cuando_corre} "
        f"No invocar Incoop.vbs desde aqui."
    )
    if nota:
        descripcion = f"{nota} {descripcion}"

    if una_sola_vez is not None:
        disparador = f"""    <TimeTrigger>
      <StartBoundary>{una_sola_vez.strftime('%Y-%m-%dT%H:%M:%S')}</StartBoundary>
      <Enabled>true</Enabled>
    </TimeTrigger>"""
    else:
        disparador = f"""    <CalendarTrigger>
      <StartBoundary>2026-01-01T{hora}:00</StartBoundary>
      <Enabled>true</Enabled>
      <ScheduleByDay><DaysInterval>1</DaysInterval></ScheduleByDay>
    </CalendarTrigger>"""

    return f"""<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>{descripcion}</Description>
  </RegistrationInfo>
  <Triggers>
{disparador}
  </Triggers>
  <Principals>
    <Principal id="Author">
      <UserId>{usuario}</UserId>
      <LogonType>{'S4U' if sin_sesion else 'InteractiveToken'}</LogonType>
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
      <Command>{_interprete(sin_sesion)}</Command>
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


def existe_tarea(nombre: str = NOMBRE_TAREA) -> bool:
    codigo, _ = _schtasks(["/Query", "/TN", nombre])
    return codigo == 0


def registrar_xml(nombre: str, xml: str):
    """Entrega el XML al Programador. Devuelve `(codigo, salida)`.

    El Programador exige el fichero en **UTF-16**; en UTF-8 lo rechaza con un error que no
    explica nada. Se escribe a un temporal y se retira siempre, pase lo que pase.

    `/F` es lo que hace idempotente el alta: sustituye la tarea si ya existía, en vez de
    fallar o —peor— dejar una segunda que prospectaría sobre la misma base.
    """
    manejador, ruta_xml = tempfile.mkstemp(suffix=".xml", prefix="incoop_despertador_")
    os.close(manejador)
    try:
        with open(ruta_xml, "w", encoding="utf-16") as f:
            f.write(xml)
        return _schtasks(["/Create", "/TN", nombre, "/XML", ruta_xml, "/F"])
    finally:
        try:
            os.remove(ruta_xml)
        except OSError:
            pass


def retirar_tarea(nombre: str):
    """Retira una tarea. Devuelve `(codigo, salida)`; si no existía, `(0, ...)`."""
    if not existe_tarea(nombre):
        return 0, "no estaba dada de alta"
    return _schtasks(["/Delete", "/TN", nombre, "/F"])


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

    codigo, salida = registrar_xml(NOMBRE_TAREA, xml)

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
    print("  [i] Corre DENTRO de tu sesion, no en la Session 0. Eso significa:")
    print("      - Si el equipo esta encendido y has entrado, prospecta a esa hora.")
    print("      - Si estaba apagado o fuera, lo hace en cuanto entras. No se pierde el dia.")
    print("      - No prospecta con el equipo encendido y la sesion cerrada: eso exigiria")
    print("        permisos de administrador que esta cuenta no tiene.")
    print()
    print("  [i] Para verla funcionar ahora sin esperar a manana:")
    print(f'      schtasks /Run /TN "{NOMBRE_TAREA}"')
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

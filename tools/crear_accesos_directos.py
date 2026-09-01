"""Alta y baja de los accesos directos del Ecosistema (Capa 10, Paso 7).

**Por qué una herramienta y no unas instrucciones.** Lo que se hace a mano por la interfaz
gráfica de Windows no se documenta, no se reproduce y no se puede deshacer igual en otro
equipo. Es el mismo criterio con el que el Paso 8 registrará la tarea programada: la
instalación en un equipo nuevo forma parte de la capa (Consideración 12), y el momento en
que menos experto hay delante es justo el arranque en frío.

Crea dos accesos, que son los dos modos que una persona invoca:

* **Incoop** — modo completo: arranca el servidor, abre el Cockpit y prospecta.
* **Incoop (solo Cockpit)** — abre la pantalla sin lanzar el pipeline.

*(El tercer modo, «sólo pipeline», no tiene acceso directo a propósito: lo invoca la tarea
programada de madrugada, y un icono que dispara un proceso que archiva y purga ficheros sin
abrir nada en pantalla es una escopeta cargada encima de la mesa.)*

Tres detalles que parecen menores y no lo son:

1. **Las carpetas las resuelve Windows, no nosotros.** Con OneDrive activo —el caso de esta
   instalación— el Escritorio real **no** está en `%USERPROFILE%\\Desktop`. Preguntar por
   `SpecialFolders` es la única forma de acertar en un equipo cualquiera.

2. **El acceso apunta a `wscript.exe` y no al `.vbs`.** Depender de la asociación de
   ficheros `.vbs` es depender de que nadie la haya cambiado —y en equipos gestionados suele
   estar redirigida a un editor de texto, con lo que el doble clic abriría el código fuente
   en vez de arrancar el sistema.

3. **El icono se genera desde el logo con fondo transparente.** El PNG de origen viene con
   fondo blanco opaco, que en el escritorio se vería como un azulejo blanco.

Uso:
    python tools/crear_accesos_directos.py alta
    python tools/crear_accesos_directos.py baja
    python tools/crear_accesos_directos.py estado
"""

import argparse
import os
import subprocess
import sys
import tempfile

# Misma linea que el resto de `tools/`: estas herramientas se invocan como script desde la
# raiz, y entonces sys.path[0] es `tools/`, no el proyecto. No contradice la Convencion C1
# —que prohibe manipular sys.path en modulos y en pruebas, para que no convivan dos raices
# de importacion—: aqui se anade la unica raiz que hay, y la importacion sigue siendo `src.`.
sys.path.insert(0, os.getcwd())

from src import PROJECT_ROOT, ruta_proyecto  # noqa: E402

NOMBRE_LANZADERA = "Incoop.vbs"
NOMBRE_ICONO = "Incoop.ico"
LOGO_ORIGEN = "logo sin letras.png"

#: Nombre del acceso, modo que invoca y descripción que Windows muestra al pasar el ratón.
#: **Son los del uso diario**, y por eso van al escritorio y al menú de inicio.
ACCESOS = (
    ("Incoop", "completo",
     "Abre el Cockpit de licitaciones y prospecta las novedades del dia"),
    ("Incoop (solo Cockpit)", "cockpit",
     "Abre el Cockpit de licitaciones sin lanzar la prospeccion"),
)

#: Accesos que **sólo van al menú de inicio** *(bloque 10.C, decisión 5.4)*. Nombre, envoltorio
#: al que apuntan y descripción.
#:
#: **El escritorio es para lo que se usa cada día**, y llenarlo de iconos de una-sola-vez le
#: quita valor al que sí se usa. Activar la prospección nocturna se hace una vez y se olvida.
#:
#: *«Preparar equipo» no está aquí y no es un olvido*: se ejecuta **antes** de que existan los
#: accesos directos —de hecho es quien los crea—, así que en un PC recién copiado no habría
#: ningún icono al que ir. Vive en la carpeta del proyecto, junto a `Incoop.vbs`.
ACCESOS_SOLO_MENU = (
    ("Despertador (prospeccion nocturna)", "Despertador.vbs",
     "Activa o desactiva la prospeccion automatica de cada noche"),
)

#: Tamaños que Windows usa según el contexto: la lista de detalles, el escritorio, la barra
#: de tareas y la vista de iconos grandes. Un .ico con un solo tamaño se reescala solo, y mal.
TAMANOS_ICONO = [(n, n) for n in (16, 24, 32, 48, 64, 128, 256)]


def _ejecutar_vbs(codigo: str) -> str:
    """Ejecuta un VBScript y devuelve lo que imprimió. Sin dependencias externas.

    Se usa `cscript //nologo` —la variante de consola— porque `wscript` no tiene salida
    estándar que leer, y el resultado de esta herramienta debe poder comprobarse.
    """
    with tempfile.NamedTemporaryFile("w", suffix=".vbs", delete=False, encoding="ascii") as f:
        f.write(codigo)
        ruta = f.name
    try:
        completado = subprocess.run(
            ["cscript", "//nologo", ruta],
            capture_output=True, text=True, timeout=60,
        )
        if completado.returncode != 0:
            raise RuntimeError(completado.stderr.strip() or "cscript falló sin decir por qué")
        return completado.stdout
    finally:
        try:
            os.remove(ruta)
        except OSError:
            pass


def carpetas_del_sistema():
    """Escritorio y Menú de Inicio **según Windows**, que es quien sabe dónde están."""
    salida = _ejecutar_vbs(
        'Set sh = CreateObject("WScript.Shell")\n'
        'WScript.Echo sh.SpecialFolders("Desktop")\n'
        'WScript.Echo sh.SpecialFolders("Programs")\n'
    )
    lineas = [l.strip() for l in salida.splitlines() if l.strip()]
    if len(lineas) < 2:
        raise RuntimeError("Windows no devolvió las carpetas de Escritorio y Menú de Inicio")
    return lineas[0], os.path.join(lineas[1], "Incoop")


def generar_icono(destino=None, origen=None) -> str:
    """Convierte el logo en un `.ico` multitamaño con el fondo vaciado.

    El vaciado se hace por **relleno desde los bordes y desde el hueco central**, no
    borrando todo lo blanco: así, si algún día el logo tuviera blanco dentro de una figura,
    el método no se lo comería.
    """
    from PIL import Image, ImageDraw

    destino = destino or ruta_proyecto(NOMBRE_ICONO)
    origen = origen or ruta_proyecto(LOGO_ORIGEN)
    if not os.path.isfile(origen):
        raise FileNotFoundError(
            f"No se encuentra el logo «{origen}». El icono se genera a partir de él."
        )

    imagen = Image.open(origen).convert("RGBA")
    ancho, alto = imagen.size
    semillas = [(0, 0), (ancho - 1, 0), (0, alto - 1), (ancho - 1, alto - 1),
                (ancho // 2, alto // 2)]
    for semilla in semillas:
        try:
            ImageDraw.floodfill(imagen, semilla, (255, 255, 255, 0), thresh=40)
        except ValueError:
            continue  # semilla fuera de la imagen: el resto sigue valiendo

    imagen.save(destino, format="ICO", sizes=TAMANOS_ICONO)
    return destino


def _codigo_alta(rutas_lnk, ruta_icono):
    """VBScript que crea los accesos. Se genera aquí para que sea auditable en una prueba.

    Cada fila trae **su propio envoltorio**: desde el bloque 10.C no todos apuntan a
    `Incoop.vbs` — el del despertador abre `Despertador.vbs`.
    """
    wscript = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "wscript.exe")
    lineas = ['Set sh = CreateObject("WScript.Shell")',
              'Set fso = CreateObject("Scripting.FileSystemObject")']
    for destino, lanzadera, modo, descripcion in rutas_lnk:
        carpeta = os.path.dirname(destino)
        argumentos = f'"""{lanzadera}"" {modo}"'.rstrip() if modo else f'"""{lanzadera}"""'
        lineas += [
            f'If Not fso.FolderExists("{carpeta}") Then fso.CreateFolder("{carpeta}")',
            f'Set acceso = sh.CreateShortcut("{destino}")',
            f'acceso.TargetPath = "{wscript}"',
            f'acceso.Arguments = {argumentos}',
            f'acceso.WorkingDirectory = "{PROJECT_ROOT}"',
            f'acceso.IconLocation = "{ruta_icono}"',
            f'acceso.Description = "{descripcion}"',
            'acceso.Save',
            f'WScript.Echo "creado: {destino}"',
        ]
    return "\n".join(lineas) + "\n"


def _rutas(carpetas):
    """Dónde va cada acceso. Mismos nombres siempre: dar de alta dos veces no duplica nada.

    **La última carpeta es el menú de inicio**, que es como la devuelve `carpetas_del_sistema()`,
    y es la única que recibe además los accesos de `ACCESOS_SOLO_MENU`.
    """
    destinos = []
    lanzadera_diaria = ruta_proyecto(NOMBRE_LANZADERA)
    for carpeta in carpetas:
        for nombre, modo, descripcion in ACCESOS:
            destinos.append(
                (os.path.join(carpeta, f"{nombre}.lnk"), lanzadera_diaria, modo, descripcion)
            )
    if carpetas:
        menu = carpetas[-1]
        for nombre, envoltorio, descripcion in ACCESOS_SOLO_MENU:
            destinos.append(
                (os.path.join(menu, f"{nombre}.lnk"), ruta_proyecto(envoltorio), "", descripcion)
            )
    return destinos


def alta(carpetas=None):
    carpetas = carpetas or list(carpetas_del_sistema())
    lanzadera = ruta_proyecto(NOMBRE_LANZADERA)
    if not os.path.isfile(lanzadera):
        raise FileNotFoundError(
            f"No se encuentra «{lanzadera}»: un acceso directo que apunta a nada es peor "
            "que no tener acceso directo, porque el fallo aparece al hacer doble clic."
        )
    icono = ruta_proyecto(NOMBRE_ICONO)
    if not os.path.isfile(icono):
        icono = generar_icono()

    destinos = _rutas(carpetas)
    salida = _ejecutar_vbs(_codigo_alta(destinos, icono))
    return [d[0] for d in destinos], salida


def baja(carpetas=None):
    carpetas = carpetas or list(carpetas_del_sistema())
    retirados = []
    for destino, *_ in _rutas(carpetas):
        if os.path.isfile(destino):
            os.remove(destino)
            retirados.append(destino)
    # La carpeta del Menú de Inicio se retira si queda vacía: dejarla sería dejar rastro.
    for carpeta in carpetas:
        if os.path.isdir(carpeta) and not os.listdir(carpeta) and os.path.basename(carpeta) == "Incoop":
            os.rmdir(carpeta)
    return retirados


def estado(carpetas=None):
    carpetas = carpetas or list(carpetas_del_sistema())
    return [(destino, os.path.isfile(destino)) for destino, *_ in _rutas(carpetas)]


def main(argv=None) -> int:
    analizador = argparse.ArgumentParser(
        prog="python tools/crear_accesos_directos.py",
        description="Accesos directos del Ecosistema de Licitaciones (Capa 10, Paso 7).",
    )
    analizador.add_argument("accion", choices=("alta", "baja", "estado"))
    analizador.add_argument(
        "--destino", action="append", default=None,
        help="Carpeta donde crear los accesos. Repetible. Sin ella se usan el Escritorio y "
             "el Menú de Inicio que declare Windows.",
    )
    argumentos = analizador.parse_args(argv)
    carpetas = argumentos.destino

    if argumentos.accion == "alta":
        creados, _ = alta(carpetas)
        for ruta in creados:
            print(f"[+] {ruta}")
        print(f"\nIcono: {ruta_proyecto(NOMBRE_ICONO)}")
        return 0

    if argumentos.accion == "baja":
        retirados = baja(carpetas)
        for ruta in retirados:
            print(f"[-] {ruta}")
        if not retirados:
            print("No había ningún acceso directo que retirar.")
        return 0

    for ruta, existe in estado(carpetas):
        print(f"[{'x' if existe else ' '}] {ruta}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

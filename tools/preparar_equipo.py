"""
tools/preparar_equipo.py — Dejar listo un equipo nuevo, sin escribir un comando.

**Por qué existe** *(bloque 10.C, decisión A.1 de dirección)*. El `MANUAL.md` no menciona una
línea de comandos, y hoy hay cosas que sólo se pueden hacer escribiendo: instalar las
dependencias, migrar la base, crear los accesos directos. Sin este envoltorio, esa decisión sería
**un recorte del alcance disfrazado**: un manual que no menciona la terminal, sobre un sistema que
la necesita. Y lo dice la Consideración 12 del README — *«la instalación en un equipo nuevo forma
parte de la capa»*.

Uso:

    Doble clic en `Preparar equipo.vbs`          # lo normal, con ventana
    python tools/preparar_equipo.py              # sin ventana, informe por consola
    python tools/preparar_equipo.py --despertador # y además da de alta el despertador

---

### Las cuatro decisiones de este módulo

**1. Aquí no hay ventana.** Este fichero calcula y decide; `tools/preparar_equipo_ventana.py` la
dibuja. No es estilo: una ventana de tkinter **no se puede probar con la suite**, así que todo lo
que pueda romperse tiene que vivir donde sí se puede — la misma doctrina con la que el Paso 7 dejó
`Incoop.vbs` en tres líneas.

**2. Un paso que falla no detiene a los siguientes.** Un instalador que se para en el primer
tropiezo obliga a ejecutarlo cinco veces para enterarse de cinco cosas. Se ejecutan todos, cada uno
reporta lo suyo, y **el veredicto sale al final**. Ningún fallo se traga: cada uno consta con su
motivo y con su remedio *(Convención C2)*.

**3. Todos los pasos son idempotentes, y eso se prueba.** Esta herramienta se va a ejecutar sobre
equipos ya preparados —por costumbre, por duda o por error—, y no puede estropear ninguno.

**4. El veredicto no lo da esta herramienta: lo da el healthcheck.** Terminar diciendo *«listo»*
porque ningún paso ha fallado es exactamente la clase de afirmación que este proyecto lleva un mes
desmontando. `ejecutar_healthcheck()` del Paso 3 comprueba de verdad el entorno, y **cada
comprobación suya trae su `remedio`**: ese campo nació para este momento, *«el único en que no hay
nadie experto delante»*.
"""

import argparse
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from typing import Callable, List, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# La consola de Windows suele ser cp1252 y un solo carácter fuera de esa tabla aborta la
# impresión a mitad de informe (trampa ya pisada en `tools/verificar_rastro_real.py`).
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(errors="replace")

from src import ruta_proyecto  # noqa: E402

#: Cuánto se le concede a `pip`. Una instalación completa sobre una conexión lenta puede pasar de
#: los cinco minutos; quedarse corto dejaría el equipo a medias **y diciendo que falló**, que es
#: peor que tardar.
TOPE_INSTALACION_S = 900

#: Dónde busca Tesseract, en el mismo orden que `Lector._autodetectar_tesseract()`. Se repite en
#: vez de instanciar un Lector entero: aquí sólo se quiere saber si el binario está.
RUTAS_TESSERACT = (
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\Tesseract-OCR\tesseract.exe"),
)

PYTHON_MINIMO = (3, 10)


@dataclass(frozen=True)
class Resultado:
    """Lo que dejó un paso. Misma forma que la `Comprobacion` del healthcheck, y a propósito:
    el informe final los mezcla en una sola lista y quien lo lee no tiene que distinguirlos."""

    nombre: str
    ok: bool
    detalle: str
    remedio: Optional[str] = None
    #: Un aviso no impide usar el sistema. Tesseract ausente es el caso: el OCR degrada y el
    #: resto funciona. Presentarlo como fallo mandaría a alguien a resolver lo que no urge.
    critico: bool = True


@dataclass
class Informe:
    """Lo que hizo la preparación y en qué estado quedó el equipo."""

    pasos: List[Resultado] = field(default_factory=list)
    comprobaciones: List[Resultado] = field(default_factory=list)

    @property
    def fallos(self) -> List[Resultado]:
        return [r for r in self.pasos + self.comprobaciones if not r.ok and r.critico]

    @property
    def avisos(self) -> List[Resultado]:
        return [r for r in self.pasos + self.comprobaciones if not r.ok and not r.critico]

    @property
    def listo(self) -> bool:
        """**No es «no ha fallado nada»**: es que el healthcheck, ejecutado después de tocar el
        equipo, no encuentra ningún fallo crítico."""
        return not self.fallos

    def texto(self) -> str:
        lineas = ["PREPARACIÓN DEL EQUIPO", "=" * 22, ""]
        for titulo, grupo in (("Lo que se ha hecho", self.pasos),
                              ("Cómo ha quedado el equipo", self.comprobaciones)):
            lineas.append(titulo)
            lineas.append("-" * len(titulo))
            for r in grupo:
                marca = "OK " if r.ok else ("!! " if r.critico else " * ")
                lineas.append(f"  [{marca}] {r.nombre}: {r.detalle}")
                if r.remedio and not r.ok:
                    lineas.append(f"         -> {r.remedio}")
            lineas.append("")
        if self.listo and not self.avisos:
            lineas.append("EL EQUIPO ESTÁ LISTO.")
        elif self.listo:
            lineas.append(f"EL EQUIPO ESTÁ LISTO, con {len(self.avisos)} aviso(s) sin urgencia.")
        else:
            lineas.append(f"QUEDAN {len(self.fallos)} COSA(S) POR RESOLVER. Ver las marcadas «!!».")
        return "\n".join(lineas)


# ==============================================================================
# Los pasos. Ninguno lanza: un fallo se convierte en su `Resultado` y el siguiente sigue
# ==============================================================================


def paso_python() -> Resultado:
    actual = sys.version_info[:2]
    if actual >= PYTHON_MINIMO:
        return Resultado("Python", True, f"versión {actual[0]}.{actual[1]}")
    return Resultado(
        "Python", False, f"versión {actual[0]}.{actual[1]}, y hacen falta "
        f"{PYTHON_MINIMO[0]}.{PYTHON_MINIMO[1]} o superior",
        remedio="Instalar Python 3.12 desde python.org marcando «Add python.exe to PATH».",
    )


def instalar_con_pip(requirements: str) -> subprocess.CompletedProcess:
    """El instalador de verdad. **Se inyecta** para que la suite no salga a la red *(C5)*."""
    return subprocess.run(
        [sys.executable, "-m", "pip", "install", "-r", requirements,
         "--disable-pip-version-check"],
        capture_output=True, text=True, timeout=TOPE_INSTALACION_S,
    )


def paso_dependencias(instalador: Callable[[str], subprocess.CompletedProcess] = instalar_con_pip,
                      raiz: Optional[str] = None) -> Resultado:
    requirements = (os.path.join(raiz, "requirements.txt") if raiz
                    else ruta_proyecto("requirements.txt"))
    if not os.path.isfile(requirements):
        return Resultado(
            "Dependencias", False, f"no se encuentra {requirements}",
            remedio="La copia del proyecto está incompleta: vuelve a copiar la carpeta entera.",
        )
    try:
        completado = instalador(requirements)
    except subprocess.TimeoutExpired:
        return Resultado(
            "Dependencias", False, f"la instalación pasó de {TOPE_INSTALACION_S // 60} minutos",
            remedio="Comprobar la conexión a internet y volver a ejecutar la preparación.",
        )
    except OSError as exc:
        return Resultado("Dependencias", False, f"no se pudo ejecutar pip: {exc}",
                         remedio="Reinstalar Python marcando «Add python.exe to PATH».")

    if completado.returncode == 0:
        return Resultado("Dependencias", True, "instaladas o ya presentes")
    # La última línea de pip es la que dice algo; el resto es ruido de descarga.
    motivo = (completado.stderr or completado.stdout or "").strip().splitlines()
    return Resultado(
        "Dependencias", False,
        f"pip terminó con código {completado.returncode}: {motivo[-1] if motivo else 'sin detalle'}",
        remedio="Lo más frecuente es no tener conexión a internet. Comprobarla y repetir.",
    )


def paso_base_de_datos() -> Resultado:
    """Crea la base si no existe y **migra el esquema si se quedó atrás**. Ya era idempotente."""
    try:
        from src.memoria import Memoria
        memoria = Memoria()
        memoria.setup_db()
        return Resultado("Base de datos", True,
                         f"esquema al día en {os.path.basename(memoria.db_path)}")
    except Exception as exc:  # noqa: BLE001 - se reporta con su tipo, no se silencia (C2)
        return Resultado("Base de datos", False, f"{type(exc).__name__}: {exc}",
                         remedio="Cerrar el Cockpit si está abierto y repetir la preparación.")


def paso_bundle(raiz: Optional[str] = None) -> Resultado:
    indice = (os.path.join(raiz, "frontend", "dist", "index.html") if raiz
              else ruta_proyecto(os.path.join("frontend", "dist", "index.html")))
    if os.path.isfile(indice):
        return Resultado("Pantalla del Cockpit", True, "compilada y lista")
    return Resultado(
        "Pantalla del Cockpit", False, "falta frontend/dist/index.html",
        remedio="La copia del proyecto está incompleta: vuelve a copiar la carpeta entera.",
    )


def paso_accesos_directos(alta: Optional[Callable[[], object]] = None) -> Resultado:
    try:
        if alta is None:
            from tools.crear_accesos_directos import alta as alta_real
            alta = alta_real
        alta()
        return Resultado("Accesos directos", True, "creados en el escritorio y el menú de inicio")
    except Exception as exc:  # noqa: BLE001
        return Resultado("Accesos directos", False, f"{type(exc).__name__}: {exc}",
                         remedio="Se puede seguir usando el sistema desde Incoop.vbs.",
                         critico=False)


def paso_despertador(registrar: Optional[Callable[[], int]] = None) -> Resultado:
    try:
        if registrar is None:
            from tools.registrar_despertador import main as main_despertador

            def registrar():
                return main_despertador(["--alta"])
        codigo = registrar()
    except Exception as exc:  # noqa: BLE001
        return Resultado("Despertador", False, f"{type(exc).__name__}: {exc}",
                         remedio="Se puede activar después desde el icono «Despertador».",
                         critico=False)
    if codigo == 0:
        return Resultado("Despertador", True, "dado de alta")
    return Resultado("Despertador", False, f"el alta terminó con código {codigo}",
                     remedio="Volver a intentarlo desde el icono «Despertador».",
                     critico=False)


def paso_ocr() -> Resultado:
    """**Se detecta y se explica; no se instala.**

    Traer e instalar un programa de terceros que nadie ha pedido no es cosa de esta herramienta.
    Y callarlo tampoco: **es la lección de H-53**, donde el OCR llevaba meses sin funcionar y no
    se sabía porque nadie lo comprobaba. Es aviso y no fallo porque el sistema arranca igual y el
    OCR degrada de forma declarada.
    """
    binario = shutil.which("tesseract") or next(
        (r for r in RUTAS_TESSERACT if os.path.isfile(r)), None
    )
    if binario:
        return Resultado("Lectura de PDF escaneados (OCR)", True, binario)
    return Resultado(
        "Lectura de PDF escaneados (OCR)", False, "Tesseract no está instalado",
        remedio="Opcional. Sin él, los pliegos escaneados quedan pendientes en vez de leerse. "
                "Se instala desde github.com/UB-Mannheim/tesseract, añadiendo los idiomas "
                "«spa» y «cat».",
        critico=False,
    )


# ==============================================================================
# El veredicto: lo da el healthcheck, no el hecho de que no haya fallado nada
# ==============================================================================


def comprobar_como_quedo() -> List[Resultado]:
    try:
        from src.lanzador import cargar_configuracion, ejecutar_healthcheck
    except Exception as exc:  # noqa: BLE001
        return [Resultado("Comprobación final", False, f"no se pudo cargar el lanzador: {exc}",
                          remedio="Revisar que las dependencias se instalaran bien.")]

    try:
        config = cargar_configuracion()
        diagnostico = ejecutar_healthcheck(
            host=config.servidor.host,
            puerto=config.servidor.puerto,
            ruta_bundle=config.ruta_bundle_absoluta(),
            espacio_minimo_mb=config.servidor.espacio_minimo_mb,
            exige_servidor=False,
        )
    except Exception as exc:  # noqa: BLE001
        return [Resultado("Comprobación final", False, f"{type(exc).__name__}: {exc}",
                          remedio="Revisar config/lanzador.yaml.")]

    # `exige_servidor=False`: preparar un equipo no levanta ningún servidor, así que un puerto
    # ocupado ahora mismo no dice nada sobre si mañana arrancará. Se informa, no se exige.
    return [
        Resultado(c.nombre, c.ok, c.detalle, c.remedio, critico=c.critica)
        for c in diagnostico.comprobaciones
    ]


def preparar(
    con_despertador: bool = False,
    instalador: Callable[[str], subprocess.CompletedProcess] = instalar_con_pip,
    alta_accesos: Optional[Callable[[], object]] = None,
    alta_despertador: Optional[Callable[[], int]] = None,
    avisar: Optional[Callable[[Resultado], None]] = None,
) -> Informe:
    """Ejecuta la preparación entera y devuelve el informe.

    `avisar` se llama con cada resultado **según se produce**, y es lo que permite que la ventana
    enseñe el progreso sin conocer los pasos: los pinta conforme llegan.
    """
    informe = Informe()

    def anotar(resultado: Resultado) -> None:
        informe.pasos.append(resultado)
        if avisar:
            avisar(resultado)

    anotar(paso_python())
    anotar(paso_dependencias(instalador))
    anotar(paso_base_de_datos())
    anotar(paso_bundle())
    anotar(paso_accesos_directos(alta_accesos))
    anotar(paso_ocr())
    if con_despertador:
        anotar(paso_despertador(alta_despertador))

    informe.comprobaciones = comprobar_como_quedo()
    if avisar:
        for comprobacion in informe.comprobaciones:
            avisar(comprobacion)
    return informe


def main(argv=None) -> int:
    analizador = argparse.ArgumentParser(
        description="Deja listo un equipo nuevo. Lo normal es hacer doble clic en "
                    "«Preparar equipo.vbs»; esta vía existe para diagnosticar.",
    )
    analizador.add_argument("--despertador", action="store_true",
                            help="Da de alta además la prospección nocturna.")
    argumentos = analizador.parse_args(argv)

    informe = preparar(con_despertador=argumentos.despertador)
    print(informe.texto())
    return 0 if informe.listo else 1


if __name__ == "__main__":
    sys.exit(main())

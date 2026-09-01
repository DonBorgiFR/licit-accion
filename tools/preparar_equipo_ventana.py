"""
tools/preparar_equipo_ventana.py — La ventana de «Preparar equipo».

**Esta ventana no decide nada.** Pide los pasos a `tools/preparar_equipo.py` y los pinta conforme
llegan. Es deliberado y es la doctrina del bloque: una ventana de tkinter **no se puede probar con
la suite**, así que todo lo que puede romperse vive donde sí se puede — igual que `Incoop.vbs` no
tiene lógica desde el Paso 7.

**Por qué hay ventana y no un cartel al final** *(decisión 5.1 del plan)*: instalar las
dependencias tarda minutos. Sin nada en pantalla durante ese rato, la preparación **parece
colgada**, y lo que parece colgado se mata.

**Por qué no empieza sola** *(decisión 5.2)*: descarga de internet y modifica el equipo. La ventana
abre enseñando lo que va a hacer y espera un clic.

**El trabajo va en un hilo aparte y se comunica por cola.** tkinter no es seguro entre hilos: pintar
desde el hilo trabajador cuelga la ventana de formas que no se reproducen. El trabajador sólo
encola resultados; quien pinta es el bucle de la ventana, con `after()`.
"""

import os
import queue
import subprocess
import sys
import threading
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.preparar_equipo import Informe, Resultado, preparar  # noqa: E402

TITULO = "Preparar este equipo · Incoop"

PRESENTACION = """Esto deja el equipo listo para usar el Ecosistema de Licitaciones.

Va a hacer lo siguiente:

  1.  Comprobar la versión de Python.
  2.  Instalar los componentes que el sistema necesita (se descargan de internet).
  3.  Crear o poner al día la base de datos.
  4.  Comprobar la pantalla del Cockpit.
  5.  Crear los accesos directos en el escritorio y el menú de inicio.
  6.  Comprobar si se pueden leer los PDF escaneados.

Se puede ejecutar tantas veces como haga falta: no estropea un equipo que ya funcionaba.

Puede tardar varios minutos la primera vez.
"""

#: Códigos de salida. El 2 es el único que no habla del equipo sino de esta ventana.
EXITO, PENDIENTES, SIN_VENTANA = 0, 1, 2


def hay_tkinter() -> bool:
    try:
        import tkinter  # noqa: F401
        import tkinter.scrolledtext  # noqa: F401
    except Exception:  # noqa: BLE001 - cualquier fallo al importar cuenta igual
        return False
    return True


def escribir_aviso_sin_ventana(destino: str) -> str:
    """Deja por escrito por qué no hay ventana y cómo se resuelve.

    **No prepara nada a espaldas de nadie.** La alternativa era instalar en silencio, y eso es
    justo lo que la decisión 5.2 prohíbe: esto descarga de internet y modifica el equipo, así que
    sin poder preguntar no se hace. *(Ajuste sobre el plan, decidido al escribir el código: la
    redacción original decía «se escribe el informe», que habría significado preparar sin
    permiso.)*
    """
    texto = (
        "PREPARAR ESTE EQUIPO - no se ha podido abrir la ventana\n"
        "=======================================================\n\n"
        "Esta instalación de Python no incluye el componente que dibuja ventanas (tcl/tk),\n"
        "así que la preparación no puede pedirte permiso antes de descargar e instalar nada.\n"
        "Por eso NO se ha hecho ningún cambio en el equipo.\n\n"
        "Cómo resolverlo:\n\n"
        "  Reinstalar Python 3.12 desde python.org dejando marcadas las dos casillas que\n"
        "  vienen puestas por defecto: «tcl/tk and IDLE» y «Add python.exe to PATH».\n\n"
        "Después, volver a hacer doble clic en «Preparar equipo».\n"
    )
    with open(destino, "w", encoding="utf-8") as fichero:
        fichero.write(texto)
    return destino


def abrir_con_el_bloc_de_notas(ruta: str) -> None:
    try:
        os.startfile(ruta)  # noqa: S606 - es un .txt propio, en el equipo de quien ejecuta
    except Exception:  # noqa: BLE001
        subprocess.Popen(["notepad.exe", ruta])


class Ventana:
    """La ventana. Pinta lo que le llega por la cola y no interpreta nada de lo que pinta."""

    def __init__(self, raiz):
        import tkinter as tk
        from tkinter import scrolledtext

        self.tk = tk
        self.raiz = raiz
        self.cola: "queue.Queue" = queue.Queue()
        self.informe: Optional[Informe] = None

        raiz.title(TITULO)
        raiz.geometry("720x560")
        raiz.minsize(600, 420)

        self.texto = scrolledtext.ScrolledText(
            raiz, wrap=tk.WORD, font=("Consolas", 10), padx=12, pady=12,
            background="#1e1e1e", foreground="#e6e6e6", insertbackground="#e6e6e6",
        )
        self.texto.pack(fill=tk.BOTH, expand=True, padx=10, pady=(10, 4))
        self.texto.tag_config("ok", foreground="#6bd968")
        self.texto.tag_config("fallo", foreground="#ff6b6b")
        self.texto.tag_config("aviso", foreground="#ffc861")
        self.texto.tag_config("titulo", foreground="#8ab4ff")
        self._escribir(PRESENTACION)

        pie = tk.Frame(raiz)
        pie.pack(fill=tk.X, padx=10, pady=(0, 10))

        self.con_despertador = tk.BooleanVar(value=True)
        tk.Checkbutton(
            pie, variable=self.con_despertador,
            text="Prospectar cada noche automáticamente (recomendado)",
        ).pack(side=tk.LEFT)

        self.boton = tk.Button(pie, text="Preparar el equipo", width=20, command=self._arrancar)
        self.boton.pack(side=tk.RIGHT)

    # -- pintar -----------------------------------------------------------------------
    def _escribir(self, texto: str, etiqueta: str = "") -> None:
        self.texto.insert(self.tk.END, texto, etiqueta)
        self.texto.see(self.tk.END)

    def _pintar_resultado(self, resultado: Resultado) -> None:
        if resultado.ok:
            marca, etiqueta = "  OK  ", "ok"
        elif resultado.critico:
            marca, etiqueta = "  !!  ", "fallo"
        else:
            marca, etiqueta = "  ··  ", "aviso"
        self._escribir(marca, etiqueta)
        self._escribir(f"{resultado.nombre}: {resultado.detalle}\n")
        if resultado.remedio and not resultado.ok:
            self._escribir(f"        {resultado.remedio}\n", etiqueta)

    # -- trabajar ---------------------------------------------------------------------
    def _arrancar(self) -> None:
        self.boton.config(state=self.tk.DISABLED, text="Preparando…")
        self._escribir("\n" + "─" * 66 + "\n", "titulo")
        self._escribir("Preparando. Esto puede tardar varios minutos.\n\n", "titulo")

        hilo = threading.Thread(target=self._trabajar, daemon=True)
        hilo.start()
        self.raiz.after(100, self._vaciar_cola)

    def _trabajar(self) -> None:
        try:
            informe = preparar(
                con_despertador=self.con_despertador.get(),
                avisar=self.cola.put,
            )
        except Exception as exc:  # noqa: BLE001 - la ventana es el único canal que hay
            self.cola.put(Resultado("Preparación", False, f"{type(exc).__name__}: {exc}",
                                    remedio="Vuelve a intentarlo; si se repite, avisa."))
            informe = Informe()
        self.cola.put(informe)

    def _vaciar_cola(self) -> None:
        try:
            while True:
                elemento = self.cola.get_nowait()
                if isinstance(elemento, Informe):
                    self._terminar(elemento)
                    return
                self._pintar_resultado(elemento)
        except queue.Empty:
            pass
        self.raiz.after(100, self._vaciar_cola)

    def _terminar(self, informe: Informe) -> None:
        self.informe = informe
        self._escribir("\n" + "─" * 66 + "\n", "titulo")
        if informe.listo and not informe.avisos:
            self._escribir("EL EQUIPO ESTÁ LISTO.\n", "ok")
            self._escribir("\nYa puedes cerrar esta ventana y usar el icono «Incoop».\n")
        elif informe.listo:
            self._escribir(f"EL EQUIPO ESTÁ LISTO, con {len(informe.avisos)} aviso(s) "
                           "que no impiden trabajar.\n", "aviso")
            self._escribir("\nYa puedes cerrar esta ventana y usar el icono «Incoop».\n")
        else:
            self._escribir(f"QUEDAN {len(informe.fallos)} COSA(S) POR RESOLVER.\n", "fallo")
            self._escribir("\nMira las líneas marcadas «!!»: cada una dice qué hacer.\n")
        self.boton.config(state=self.tk.NORMAL, text="Volver a preparar")


def main(argv=None) -> int:
    if not hay_tkinter():
        destino = os.path.join(os.path.expanduser("~"), "Incoop - preparar equipo.txt")
        abrir_con_el_bloc_de_notas(escribir_aviso_sin_ventana(destino))
        return SIN_VENTANA

    import tkinter as tk

    raiz = tk.Tk()
    ventana = Ventana(raiz)
    raiz.mainloop()

    if ventana.informe is None:
        return EXITO  # se cerró sin preparar: no es un fallo, es no haber querido
    return EXITO if ventana.informe.listo else PENDIENTES


if __name__ == "__main__":
    sys.exit(main())

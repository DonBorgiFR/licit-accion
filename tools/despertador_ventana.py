"""
tools/despertador_ventana.py — Activar o desactivar la prospección nocturna con doble clic.

**Por qué un solo icono y no dos** *(decisión 5.3 del bloque 10.C)*. Dos accesos —«Activar» y
«Desactivar»— invitan a equivocarse y **no contestan la pregunta que la persona tiene de verdad**,
que es *«¿está activo?»*. Esta ventana empieza contestándola y ofrece el botón contrario al estado.

**Aquí no hay lógica de despertador**: la tiene `tools/registrar_despertador.py` desde el Paso 8,
con sus cinco decisiones y su registro por XML. Esto la envuelve; no la reimplementa *(Regla 14)*.

**Y no se afirma el resultado: se comprueba.** Tras actuar, el estado se **vuelve a leer** del
Programador de tareas en vez de dar por bueno que la orden funcionó. Es la misma doctrina con la
que el lanzador dejó de fiarse de los códigos de salida y pasó a mirar la fila de la corrida:
*medir el efecto en vez de dar por bueno que se ejecutó*.
"""

import os
import subprocess
import sys
from dataclasses import dataclass
from typing import Callable, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(errors="replace")

TITULO = "Prospección nocturna · Incoop"

EXITO, FALLO, SIN_VENTANA = 0, 1, 2


@dataclass(frozen=True)
class Estado:
    """Lo que hay ahora mismo en el Programador de tareas, no lo que debería haber."""

    activo: bool
    hora: str
    equipo: str

    def frase(self) -> str:
        if self.activo:
            return (f"La prospección nocturna está ACTIVADA.\n\n"
                    f"Cada día a las {self.hora} este equipo ({self.equipo}) busca las\n"
                    f"licitaciones nuevas por su cuenta.\n\n"
                    f"Si el equipo estaba apagado a esa hora, lo hace en cuanto entras:\n"
                    f"no se pierde el día.")
        return (f"La prospección nocturna está DESACTIVADA.\n\n"
                f"Las licitaciones nuevas sólo se buscan cuando abres Incoop a mano.\n\n"
                f"Si la activas, este equipo ({self.equipo}) lo hará solo cada día\n"
                f"a las {self.hora}.")


def leer_estado(existe: Optional[Callable[[], bool]] = None,
                cargar: Optional[Callable[[], object]] = None) -> Estado:
    """Lee el estado real. Las dependencias se inyectan para poder probarlo sin Programador."""
    import platform

    if existe is None or cargar is None:
        from tools.registrar_despertador import cargar_configuracion, existe_tarea
        existe = existe or existe_tarea
        cargar = cargar or cargar_configuracion

    config = cargar()
    return Estado(activo=existe(), hora=config.despertador.hora, equipo=platform.node())


def cambiar(activar: bool,
            alta: Optional[Callable[[], int]] = None,
            baja: Optional[Callable[[], int]] = None,
            leer: Optional[Callable[[], Estado]] = None):
    """Activa o desactiva, y **devuelve el estado releído**, no el que se pretendía dejar.

    Returns:
        `(consiguio, mensaje, estado_real)`. `consiguio` compara lo pedido con lo que hay
        **después** de mirar: una orden que devuelve 0 y no cambia nada sería un éxito mentiroso.
    """
    if alta is None or baja is None:
        from tools.registrar_despertador import cargar_configuracion, dar_de_alta, dar_de_baja
        alta = alta or (lambda: dar_de_alta(cargar_configuracion()))
        baja = baja or dar_de_baja
    leer = leer or leer_estado

    try:
        codigo = alta() if activar else baja()
    except Exception as exc:  # noqa: BLE001 - la ventana es el único canal que hay
        return False, f"{type(exc).__name__}: {exc}", leer()

    estado = leer()
    if estado.activo == activar:
        return True, "", estado
    if codigo != 0:
        return False, (
            "El Programador de tareas de Windows rechazó el cambio. Suele ocurrir cuando la\n"
            "cuenta no tiene permisos para crear tareas programadas: lo puede hacer un\n"
            "administrador del equipo."
        ), estado
    return False, (
        "La orden se ejecutó sin error pero el estado no ha cambiado. Vuelve a intentarlo;\n"
        "si se repite, hay que mirarlo desde el Programador de tareas de Windows."
    ), estado


# ==============================================================================
# La ventana, que no decide nada
# ==============================================================================


def hay_tkinter() -> bool:
    try:
        import tkinter  # noqa: F401
    except Exception:  # noqa: BLE001
        return False
    return True


class Ventana:
    def __init__(self, raiz, estado: Estado):
        import tkinter as tk

        self.tk = tk
        self.raiz = raiz
        self.estado = estado

        raiz.title(TITULO)
        raiz.geometry("560x330")
        raiz.resizable(False, False)

        self.etiqueta = tk.Label(raiz, justify=tk.LEFT, anchor="nw", font=("Segoe UI", 10),
                                 padx=18, pady=18, wraplength=520)
        self.etiqueta.pack(fill=tk.BOTH, expand=True)

        pie = tk.Frame(raiz)
        pie.pack(fill=tk.X, padx=18, pady=(0, 18))
        self.boton = tk.Button(pie, width=22, command=self._pulsar)
        self.boton.pack(side=tk.RIGHT)
        tk.Button(pie, text="Cerrar", width=10, command=raiz.destroy).pack(side=tk.RIGHT, padx=8)

        self._pintar()

    def _pintar(self, mensaje: str = "") -> None:
        texto = self.estado.frase()
        if mensaje:
            texto += "\n\n" + mensaje
        self.etiqueta.config(text=texto)
        self.boton.config(
            text="Desactivarla" if self.estado.activo else "Activarla",
            state=self.tk.NORMAL,
        )

    def _pulsar(self) -> None:
        self.boton.config(state=self.tk.DISABLED, text="Un momento…")
        self.raiz.update_idletasks()
        consiguio, mensaje, self.estado = cambiar(not self.estado.activo)
        self._pintar("" if consiguio else mensaje)


def main(argv=None) -> int:
    if os.name != "nt":
        print("El Programador de tareas de Windows sólo existe en Windows.")
        return FALLO

    try:
        estado = leer_estado()
    except Exception as exc:  # noqa: BLE001
        estado = None
        motivo = f"{type(exc).__name__}: {exc}"

    if not hay_tkinter():
        # Sin ventana no se toca nada: activar la prospección nocturna es un cambio en el
        # equipo, y hacerlo sin poder preguntar es justo lo que el bloque 10.C evita.
        print("No se puede abrir la ventana: esta instalación de Python no trae tcl/tk.")
        print("Reinstalar Python 3.12 dejando marcada la casilla «tcl/tk and IDLE».")
        return SIN_VENTANA

    import tkinter as tk
    from tkinter import messagebox

    if estado is None:
        raiz = tk.Tk()
        raiz.withdraw()
        messagebox.showerror(TITULO, f"No se pudo leer el estado del despertador.\n\n{motivo}")
        return FALLO

    raiz = tk.Tk()
    Ventana(raiz, estado)
    raiz.mainloop()
    return EXITO


if __name__ == "__main__":
    sys.exit(main())

"""La identidad de un proceso, en un solo sitio.

**Por qué existe este módulo, que es lo único no obvio de él.** Las dos mitades de la
pregunta *"¿sigue vivo el proceso que anotamos?"* vivían en capas distintas:
`es_pid_activo()` en `src/memoria.py` (Capa 3) e `instante_creacion_proceso()` en
`src/lanzador.py` (Capa 10). Mientras cada una respondía a su dueño no molestaba.

Dejó de no molestar al reparar **H-40** (Capa 10, Paso 6): el cerrojo de ejecución de la
Capa 3 necesita saber si el dueño de una fila `RUNNING` sigue vivo, y esa respuesta exige
las dos mitades. La Capa 3 **no puede importar de la Capa 10** —invertiría la dependencia
sobre la que está construido todo el proyecto, que se desarrolla estrictamente de abajo
arriba—, así que la respuesta se muda a un módulo neutro del que importan las dos.

**Es un traslado, no un cambio de comportamiento.** `db_lock()` sigue decidiendo
exactamente igual que antes, y la nota de alcance del contrato de la Capa 10 sobre
endurecer su `created_at` sigue vigente y sin tocar.

---

**La idea que gobierna el fichero**: un número de proceso **no es una identidad**. Windows
recicla los identificadores, de modo que un proceso que muere deja su número libre y el
sistema puede dárselo a cualquier otro. Con el número a secas:

* *"apago sólo lo mío"* puede acabar matando algo inocente que heredó el número, y
* *"el dueño del cerrojo sigue vivo"* puede afirmarse sobre un dueño que murió hace horas,
  respetando un cerrojo muerto y dejando plantada a la corrida siguiente (H-15, H-40).

El instante de creación no se recicla, así que **el par (pid, instante) sí identifica**.

---

**Cómo NO medir si un proceso sigue vivo** *(aprendido el 2026-08-17, verificando el Paso 6,
y anotado aquí porque volverá a morder a quien escriba la próxima comprobación)*:

*Mientras alguien conserve un handle abierto sobre un proceso, Windows mantiene su
objeto-proceso aunque haya terminado*, y `OpenProcess` sigue funcionando sobre él. Medido:

| Quién pregunta | Proceso matado hace 1 s | Respuesta |
|---|---|---|
| Otro proceso cualquiera | sí | `False` — correcta |
| **El propio proceso que lo engendró, conservando su objeto `Popen`** | sí | **`True` — falsa** |
| El propio proceso que lo engendró, **habiendo soltado el objeto** | sí | `False` — correcta |

Las dos formas en que el proyecto pregunta caen en el lado bueno: el supervisor del Paso 5
suelta el `Popen` al salir de `arrancar_servidor()` —comprobado— y el cerrojo de ejecución
lo pregunta siempre desde una invocación posterior, que es otro proceso. Pero **una prueba
que engendre un proceso y luego lo dé por muerto en el mismo sitio medirá su propio
andamiaje**, no el sistema. Es la lección del Paso 2 de la Capa 10 otra vez: *medir el
efecto no basta si no se comprueba también por qué salió ese número.*
"""

import os
from typing import Optional

#: `PROCESS_QUERY_LIMITED_INFORMATION`. Basta para preguntar cuándo nació un proceso y no
#: pide privilegios: se consulta la identidad de procesos ajenos, no se toca ninguno.
_ACCESO_CONSULTA = 0x1000


def es_pid_activo(pid: int) -> bool:
    """¿Existe hoy un proceso con este número? Windows y POSIX, sin librerías externas.

    **Es sólo la primera mitad de la identidad**: contesta por el número, que se recicla.
    Para saber si sigue vivo *el mismo* proceso que anotamos, ver `es_el_mismo_proceso()`.
    """
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError as e:
        # WinError 5 / EACCES significan "existe, pero no me dejas tocarlo": el proceso
        # está vivo y pertenece a otro usuario o tiene más privilegios. Tratarlo como
        # muerto sería reclamar un cerrojo cuyo dueño sigue trabajando.
        if getattr(e, 'winerror', None) == 5 or getattr(e, 'errno', None) == 13:
            return True
        return False
    except Exception:
        return False


def instante_creacion_proceso(pid: int) -> Optional[int]:
    """Instante de creación del proceso, o `None` si no existe o no se puede resolver.

    **Es la mitad que le falta al PID para ser una identidad.** Sólo Windows: en el resto
    de plataformas devuelve `None`, y quien lo consuma debe tratar ese `None` como *"no lo
    sé"*, nunca como *"no vive"*.
    """
    try:
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        manejador = kernel32.OpenProcess(_ACCESO_CONSULTA, False, pid)
        if not manejador:
            return None
        try:
            creacion, salida = wintypes.FILETIME(), wintypes.FILETIME()
            nucleo, usuario = wintypes.FILETIME(), wintypes.FILETIME()
            ok = kernel32.GetProcessTimes(
                manejador, ctypes.byref(creacion), ctypes.byref(salida),
                ctypes.byref(nucleo), ctypes.byref(usuario),
            )
            if not ok:
                return None
            return (creacion.dwHighDateTime << 32) | creacion.dwLowDateTime
        finally:
            kernel32.CloseHandle(manejador)
    except Exception:
        return None


def es_el_mismo_proceso(pid: int, instante_creacion: Optional[int]) -> bool:
    """¿Sigue vivo **el mismo** proceso que anotamos, y no otro que heredó su número?

    Sin `instante_creacion` anotado se responde `False`. La asimetría es deliberada y hay
    que leerla en el sitio donde se usa, porque `False` significa cosas distintas:

    * En el **apagado** (Capa 10, Paso 5): "no es el mío" → no se toca nada. Ante la duda
      no se mata; dejar un proceso de más es visible y molesto, matar el que no era puede
      tumbar el trabajo de alguien.
    * En el **cerrojo de ejecución** (Capa 3, esquema v8): "el dueño ya no vive" → la fila
      es reclamable. Aquí la duda **no puede resolverse con esta función**, porque sería
      reclamar un cerrojo ajeno: por eso quien la consume comprueba antes que haya un
      instante anotado y, si no lo hay, cae a la regla temporal en vez de decidir aquí.
    """
    if instante_creacion is None:
        return False
    return instante_creacion_proceso(pid) == instante_creacion

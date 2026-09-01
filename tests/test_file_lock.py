"""
tests/test_file_lock.py — Pruebas de Cerrojo de Fichero con PID y TTL (Capa 8.5 - Iteración 2)
Ecosistema Automático de Licitaciones (bfr_incoop)
"""

import os
import json
import subprocess
import sys
import tempfile
import time

import pytest

from src.memoria import Memoria, es_pid_activo


def test_es_pid_activo():
    """
    Verifica que es_pid_activo detecte correctamente el PID propio y PIDs inexistentes.

    ⚠️ **Esto pasaba en verde mientras la función estaba rota, y ése es el hallazgo H-62.**
    Preguntar por el PID propio y por dos inexistentes deja fuera **el único caso que le
    importa a quien la usa**: un proceso vivo que no es el que pregunta. En Windows,
    `os.kill(pid, 0)` acierta sobre uno mismo y falla sobre cualquier otro, así que estas
    tres afirmaciones eran ciegas justo donde había que mirar. Ver
    `test_un_proceso_vivo_y_ajeno_se_ve_vivo`.
    """
    my_pid = os.getpid()
    assert es_pid_activo(my_pid) is True
    assert es_pid_activo(-1) is False
    assert es_pid_activo(9999999) is False


class _Kernel32Falso:
    """Un `kernel32` de mentira que devuelve lo que se le diga y anota lo que se le pide."""

    def __init__(self, manejador, error=0):
        self._manejador = manejador
        self._error = error
        self.aperturas = []
        self.cerrados = []

    def OpenProcess(self, acceso, heredar, pid):  # noqa: N802 - nombre del API de Windows
        self.aperturas.append((acceso, pid))
        return self._manejador

    def GetLastError(self):  # noqa: N802
        return self._error

    def CloseHandle(self, manejador):  # noqa: N802
        self.cerrados.append(manejador)


def _con_kernel32(monkeypatch, falso):
    import ctypes
    monkeypatch.setattr(ctypes, "windll", type("W", (), {"kernel32": falso})(), raising=False)


@pytest.mark.parametrize("manejador, error, esperado, por_que", [
    (1234, 0, True, "OpenProcess abrió: el proceso existe"),
    (0, 87, False, "ERROR_INVALID_PARAMETER es el único código que afirma que no vive"),
    (0, 5, True, "ERROR_ACCESS_DENIED: existe y no se deja consultar"),
    (0, 299, True, "cualquier otro error no es una respuesta: ante la duda, vive"),
])
def test_la_existencia_se_decide_por_el_codigo_de_error(monkeypatch, manejador, error,
                                                        esperado, por_que):
    """**El cuadro de decisión de H-62**, que es la sustancia de la reparación.

    Se prueba con un `kernel32` de mentira y no con procesos reales, y es deliberado: una
    prueba que engendre procesos para preguntarles si viven **mide su propio andamiaje** —lo
    avisa la cabecera de `src/proceso.py` con una tabla— y encima depende de que ganen una
    carrera. *Escrita así primero, pasaba por casualidad: el proceso que engendraba moría
    antes de un segundo y la prueba lo alcanzaba viva por los pelos.*

    Lo que aquí se afirma es lo que estaba mal: **la implementación anterior devolvía `False`
    ante cualquier error que no fuera el 5**, y en Windows el error habitual sobre un proceso
    ajeno es el **87**... que ahora es el único que permite afirmar la muerte. Los otros dos
    casos son los que impiden que la reparación se pase de frenada y dé todo por vivo.
    """
    from src.proceso import _existe_en_windows

    falso = _Kernel32Falso(manejador, error)
    _con_kernel32(monkeypatch, falso)

    assert _existe_en_windows(4321) is esperado, por_que


def test_abrir_un_proceso_para_mirarlo_no_deja_el_manejador_suelto(monkeypatch):
    """Un handle sin cerrar mantiene vivo el objeto-proceso en Windows, y entonces **un
    proceso muerto seguiría pareciendo vivo** — la trampa que la cabecera de `src/proceso.py`
    documenta. Esta comprobación se hace en cada corrida y en cada consulta del Cockpit."""
    from src.proceso import _ACCESO_CONSULTA, _existe_en_windows

    falso = _Kernel32Falso(manejador=777)
    _con_kernel32(monkeypatch, falso)

    _existe_en_windows(4321)

    assert falso.cerrados == [777], "el manejador se cierra siempre"
    assert falso.aperturas == [(_ACCESO_CONSULTA, 4321)], (
        "se pide sólo consulta, no acceso total: preguntar por la identidad de un proceso "
        "ajeno no debe exigir privilegios sobre él"
    )


def test_el_cerrojo_respeta_una_corrida_cuyo_dueno_sigue_vivo():
    """H-62 en el sitio donde hacía daño, y con los procesos de verdad de este equipo.

    Medido el 2026-09-01 verificando en vivo el bloque 10.E: la API del Cockpit, el lanzador
    y `explorer.exe` —los tres vivos y respondiendo— daban `False`. `motivo_ejecucion_huerfana()`
    pregunta por ahí **antes que por nada**, así que el cerrojo se reclamaba sobre corridas
    cuyo dueño seguía trabajando: dos pipelines archivando y purgando a la vez, que es
    exactamente el daño que H-40 vino a impedir. Y en pantalla, una corrida en curso se
    anunciaba como *«quedó sin terminar: su proceso ya no existe»*.

    Se usa **el propio proceso de las pruebas** como dueño vivo: no hace falta engendrar nada
    para comprobar la invariante — *si consta que existe, el cerrojo se respeta*.
    """
    from datetime import datetime, timezone

    from src.memoria import motivo_ejecucion_huerfana
    from src.proceso import instante_creacion_proceso

    yo = os.getpid()
    ahora = datetime.now(timezone.utc)

    motivo = motivo_ejecucion_huerfana(
        ahora.strftime("%Y-%m-%dT%H:%M:%SZ"), yo, str(instante_creacion_proceso(yo)), ahora,
    )

    assert motivo is None, f"el cerrojo se reclamó sobre un dueño vivo: {motivo}"


def test_la_coherencia_entre_las_dos_mitades_de_la_identidad():
    """Las dos mitades del módulo tienen que contestar lo mismo sobre la existencia.

    **Es la invariante que H-62 rompía**: `instante_creacion_proceso()` encontraba procesos
    que `es_pid_activo()` daba por muertos, en el mismo fichero y en el mismo instante. Un
    módulo que se contradice a sí mismo no puede sostener un cerrojo.
    """
    from src.proceso import instante_creacion_proceso

    for pid in (os.getpid(), os.getppid(), 9999999, 1):
        existe = instante_creacion_proceso(pid) is not None
        if existe:
            assert es_pid_activo(pid) is True, (
                f"pid {pid}: se puede consultar su instante de creación y se le da por muerto"
            )


def test_lock_creacion_y_payload_json():
    """
    Verifica que db_lock cree el fichero .lock con el payload JSON conteniendo pid y created_at.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = os.path.join(tmp_dir, "test_lock.db")
        lock_path = db_path + ".lock"
        memoria = Memoria(db_path=db_path)

        with memoria.db_lock(timeout=2.0):
            assert os.path.exists(lock_path)
            with open(lock_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                assert data["pid"] == os.getpid()
                assert isinstance(data["created_at"], (int, float))

        # Al salir del bloque con context manager, debe borrarse
        assert not os.path.exists(lock_path)


def test_lock_recuperacion_pid_huerfano():
    """
    Simula un lock abandonado por un proceso muerto (PID 9999999) y verifica que
    db_lock lo limpie y adquiera el cerrojo sin lanzar RuntimeError.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = os.path.join(tmp_dir, "test_lock_huerfano.db")
        lock_path = db_path + ".lock"
        memoria = Memoria(db_path=db_path)

        # Crear lock huérfano simulado con PID inexistente
        with open(lock_path, "w", encoding="utf-8") as f:
            json.dump({"pid": 9999999, "created_at": time.time()}, f)

        # db_lock debe detectar que PID 9999999 no existe, eliminar el lock huérfano y adquirirlo
        with memoria.db_lock(timeout=2.0):
            assert os.path.exists(lock_path)
            with open(lock_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                assert data["pid"] == os.getpid()


def test_lock_ilegible_reciente_no_se_reclama():
    """
    Un cerrojo vacío o corrupto pero RECIENTE puede ser un proceso sano que acaba de
    crearlo y todavía no ha escrito el payload. No debe reclamarse: pisarlo abriría la
    puerta a dos escritores simultáneos sobre la base de datos.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = os.path.join(tmp_dir, "test_lock_ilegible_nuevo.db")
        lock_path = db_path + ".lock"
        memoria = Memoria(db_path=db_path)

        # Cerrojo de 0 bytes: sin PID y sin created_at legibles.
        open(lock_path, "w").close()

        try:
            with memoria.db_lock(timeout=1.0, ttl=600.0):
                assert False, "No debía adquirirse un cerrojo ilegible pero reciente"
        except RuntimeError:
            pass  # Comportamiento esperado: se respeta el cerrojo.

        assert os.path.exists(lock_path)


def test_lock_ilegible_antiguo_se_reclama():
    """
    Regresión del bloqueo permanente: si el proceso muere entre crear el fichero .lock
    y escribir su payload, queda un cerrojo de 0 bytes sin PID ni fecha. Debe caducar
    por la fecha de modificación del fichero, o el sistema queda bloqueado para siempre.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = os.path.join(tmp_dir, "test_lock_ilegible_viejo.db")
        lock_path = db_path + ".lock"
        memoria = Memoria(db_path=db_path)

        open(lock_path, "w").close()
        # Envejecer el fichero 1000 s por su mtime, que es el único dato disponible.
        hace_1000s = time.time() - 1000
        os.utime(lock_path, (hace_1000s, hace_1000s))

        with memoria.db_lock(timeout=2.0, ttl=600.0):
            with open(lock_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                assert data["pid"] == os.getpid()


def test_lock_recuperacion_ttl_caducado():
    """
    Simula un lock cuyo timestamp supera el TTL y verifica que db_lock lo limpie y adquiera el cerrojo.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = os.path.join(tmp_dir, "test_lock_ttl.db")
        lock_path = db_path + ".lock"
        memoria = Memoria(db_path=db_path)

        # Crear lock con timestamp antiguo (hace 1000 segundos)
        hace_1000s = time.time() - 1000
        with open(lock_path, "w", encoding="utf-8") as f:
            json.dump({"pid": os.getpid(), "created_at": hace_1000s}, f)

        # db_lock con ttl=600 debe caducar el lock viejo y adquirir el nuevo
        with memoria.db_lock(timeout=2.0, ttl=600.0):
            assert os.path.exists(lock_path)
            with open(lock_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                assert data["created_at"] > hace_1000s

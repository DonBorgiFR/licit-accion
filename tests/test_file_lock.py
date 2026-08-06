"""
tests/test_file_lock.py — Pruebas de Cerrojo de Fichero con PID y TTL (Capa 8.5 - Iteración 2)
Ecosistema Automático de Licitaciones (bfr_incoop)
"""

import os
import json
import tempfile
import time

from src.memoria import Memoria, es_pid_activo


def test_es_pid_activo():
    """
    Verifica que es_pid_activo detecte correctamente el PID propio y PIDs inexistentes.
    """
    my_pid = os.getpid()
    assert es_pid_activo(my_pid) is True
    assert es_pid_activo(-1) is False
    assert es_pid_activo(9999999) is False


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

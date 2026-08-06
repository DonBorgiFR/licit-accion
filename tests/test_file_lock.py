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

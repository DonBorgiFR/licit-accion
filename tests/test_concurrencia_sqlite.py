"""
tests/test_concurrencia_sqlite.py — Pruebas de Concurrencia y Resiliencia SQLite (Capa 8.5 - Iteración 1)
Ecosistema Automático de Licitaciones (bfr_incoop)
"""

import os
import sqlite3
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
import pytest

from src.memoria import Memoria
from src.api.dependencies import healthcheck_api_dependencies, get_db


def test_busy_timeout_pragma_configurado():
    """
    Verifica que Memoria.conectar() configure PRAGMA busy_timeout = 30000ms.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = os.path.join(tmp_dir, "test_busy_timeout.db")
        memoria = Memoria(db_path=db_path)
        memoria.setup_db()

        with memoria.conectar() as conn:
            cursor = conn.cursor()
            cursor.execute("PRAGMA busy_timeout;")
            timeout_val = cursor.fetchone()[0]
            assert timeout_val >= 30000, f"El busy_timeout debe ser >= 30000 ms, se obtuvo: {timeout_val}"


def test_healthcheck_dependencies_con_busy_timeout():
    """
    Verifica que healthcheck_api_dependencies valide busy_timeout >= 30000ms correctamente.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = os.path.join(tmp_dir, "test_health.db")
        memoria = Memoria(db_path=db_path)
        memoria.setup_db()

        res = healthcheck_api_dependencies(db_path=db_path)
        assert res["status"] == "OK"
        assert res["wal_mode_active"] is True
        assert res["busy_timeout_ms"] >= 30000
        assert res["query_test_ok"] is True


def test_concurrencia_multihilo_escritura_lectura():
    """
    Simula escrituras y lecturas concurrentes intensivas con 10 hilos simultáneos
    para asegurar que 0 peticiones devuelvan "database is locked".
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = os.path.join(tmp_dir, "test_concurrent_stress.db")
        memoria = Memoria(db_path=db_path)
        memoria.setup_db()

        def operacion_hilo(hilo_id: int):
            # Alternar entre lecturas y escrituras
            for i in range(10):
                with memoria.conectar() as conn:
                    cursor = conn.cursor()
                    if hilo_id % 2 == 0:
                        cursor.execute("SELECT COUNT(*) FROM expedientes;")
                        _ = cursor.fetchone()
                    else:
                        cursor.execute(
                            "INSERT OR IGNORE INTO metadata (version) VALUES (?);",
                            (5,)
                        )
                        conn.commit()
                time.sleep(0.005)
            return True

        num_hilos = 10
        with ThreadPoolExecutor(max_workers=num_hilos) as executor:
            futures = [executor.submit(operacion_hilo, i) for i in range(num_hilos)]
            resultados = [f.result() for f in as_completed(futures)]

        assert len(resultados) == num_hilos
        assert all(resultados)

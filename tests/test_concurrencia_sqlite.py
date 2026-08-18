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


# ==============================================================================
# H-42 — La conexión que cruzaba de hilo (Capa 10, Paso 7)
# ==============================================================================
#
# Descubierto el 2026-08-18 arrancando la aplicación, no leyendo el código: con el Cockpit
# abierto, **16 de 40 peticiones concurrentes devolvían 500** y las pantallas se pintaban a
# cero. La causa no está en la concurrencia de SQLite sino en la de FastAPI: `get_db()` es un
# generador síncrono, de modo que el framework lo ejecuta en un hilo del threadpool, mientras
# que el endpoint que consume la conexión corre en OTRO hilo del mismo pool. Con poca carga
# suele tocar el mismo hilo, y por eso llevaba latente desde la Capa 7.
#
# Las dos pruebas que siguen cubren las dos mitades: la conexión cruda y el inyector real.

def test_una_conexion_abierta_en_un_hilo_se_puede_usar_en_otro():
    """La forma exacta en que FastAPI usa `get_db`: abrir aquí, consultar allá."""
    import queue
    import threading

    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = os.path.join(tmp_dir, "cruce_de_hilos.db")
        Memoria(db_path=db_path).setup_db()

        # **Ojo a cómo se monta esto**: `conectar()` es un contextmanager, de modo que
        # llamarlo dentro del hilo sólo crea el generador — la conexión no nace hasta el
        # `__enter__()`. La primera versión de esta prueba lo hacía en el hilo principal y
        # pasaba con y sin reparación: medía su propio andamiaje, que es justo la trampa
        # anotada en `src/proceso.py`. El `__enter__()` tiene que ocurrir en el otro hilo.
        buzon = queue.Queue()

        def abrir_de_verdad():
            gestor_local = Memoria(db_path=db_path).conectar()
            buzon.put((gestor_local, gestor_local.__enter__()))

        hilo = threading.Thread(target=abrir_de_verdad)
        hilo.start()
        hilo.join()

        gestor, conn = buzon.get()
        try:
            # Antes de la reparación, esta línea lanzaba ProgrammingError desde otro hilo.
            assert conn.execute("SELECT COUNT(*) FROM expedientes;").fetchone()[0] == 0
        finally:
            gestor.__exit__(None, None, None)


def test_el_inyector_de_la_api_soporta_el_reparto_de_hilos_del_threadpool():
    """El mismo cruce, pero por la ruta real del framework (Convención C4).

    Lo que se ejercita no es una conexión cualquiera: es `get_db()`, que es quien de verdad
    entrega la conexión a cada endpoint, y que fallaba en producción devolviendo 500.
    """
    import threading

    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = os.path.join(tmp_dir, "inyector.db")
        Memoria(db_path=db_path).setup_db()

        generador = get_db(db_path=db_path)
        conn = next(generador)

        resultado = {}

        def consultar_desde_otro_hilo():
            try:
                resultado["filas"] = conn.execute("SELECT COUNT(*) FROM lotes;").fetchone()[0]
            except Exception as e:  # noqa: BLE001 — se guarda para afirmar sobre ella
                resultado["error"] = f"{type(e).__name__}: {e}"

        hilo = threading.Thread(target=consultar_desde_otro_hilo)
        hilo.start()
        hilo.join()

        assert "error" not in resultado, resultado.get("error")
        assert resultado["filas"] == 0

        for _ in generador:  # agota el generador para que se cierre la conexión
            pass

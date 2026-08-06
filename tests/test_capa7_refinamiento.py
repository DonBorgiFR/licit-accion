"""
tests/test_capa7_refinamiento.py — Pruebas de Integración de Refinamientos y Optimizaciones (Capa 7 & Memoria)
Ecosistema Automático de Licitaciones (bfr_incoop)

Audita:
1. Paginación Batch en Bloque (eliminación de N+1 consultas).
2. Bloqueo Mutex db_lock() en mutaciones API.
3. Aislamiento atómico en mutaciones (re-lectura previa a commit).
4. Rotación defensiva y retención de logs JSONL (pipeline.jsonl).
"""

import os
import pytest
from src.memoria import Memoria
from src.api.dependencies import rotar_log_si_excede_tamano, GestorTrazabilidadAPI


@pytest.fixture
def temp_db(tmp_path):
    """Fixture de base de datos SQLite v5 temporal para pruebas de refinamiento."""
    db_file = str(tmp_path / "refinamiento_test.db")
    memoria = Memoria(db_path=db_file)
    memoria.setup_db()
    return db_file


def test_batch_query_pagination_performance(temp_db):
    """Verifica que la paginación batch reconstruye correctamente expedientes, lotes y análisis semántico."""
    memoria = Memoria(db_path=temp_db)
    
    with memoria.conectar() as conn:
        for i in range(1, 11):
            exp_id = f"EXP-BATCH-{i:03d}"
            conn.execute("""
                INSERT INTO expedientes (id, titulo, organo, localidad, fuente, fecha_publicacion, fecha_ingesta, last_seen_feed, feed_hash)
                VALUES (?, ?, 'Ajuntament de Girona', 'Girona', 'PSCP', '2026-07-26T00:00:00Z', '2026-07-26T00:00:00Z', '2026-07-26T00:00:00Z', ?);
            """, (exp_id, f"Expediente {i}", f"hash_{i}"))
            
            # 2 lotes por expediente
            conn.execute("""
                INSERT INTO lotes (expediente_id, lote_numero, titulo_lote, pbl, vec, score_total, estado_operativo, updated_at)
                VALUES (?, 1, 'Lote 1', 50000.0, 100000.0, 80, 'Nueva', '2026-07-26T00:00:00Z');
            """, (exp_id,))
            conn.execute("""
                INSERT INTO lotes (expediente_id, lote_numero, titulo_lote, pbl, vec, score_total, estado_operativo, updated_at)
                VALUES (?, 2, 'Lote 2', 60000.0, 120000.0, 70, 'Nueva', '2026-07-26T00:00:00Z');
            """, (exp_id,))
            
            # Análisis semántico para impares
            if i % 2 != 0:
                conn.execute("""
                    INSERT INTO analisis_semantico (expediente_id, dictamen_recomendacion, subrogacion_detectada, subrogacion_riesgo, revision_precios_permitida, raw_dto_json, created_at, updated_at)
                    VALUES (?, 'LICITAR_PRIORITARIO', 0, 'BAJO', 1, '{}', '2026-07-26T00:00:00Z', '2026-07-26T00:00:00Z');
                """, (exp_id,))
        conn.commit()

    # Ejecutar consulta paginada
    expedientes, total_count = memoria.listar_expedientes_paginados(page=1, limit=5)
    
    assert total_count == 10
    assert len(expedientes) == 5
    
    for exp in expedientes:
        assert len(exp["lotes"]) == 2
        exp_num = int(exp["id"].split("-")[-1])
        if exp_num % 2 != 0:
            assert exp["analisis_semantico"] is not None
            assert exp["analisis_semantico"]["dictamen_recomendacion"] == "LICITAR_PRIORITARIO"
        else:
            assert exp["analisis_semantico"] is None


def test_mutation_db_lock_and_atomic_read(temp_db):
    """Verifica que las mutaciones con db_lock leen el objeto atómicamente antes del commit."""
    memoria = Memoria(db_path=temp_db)
    
    with memoria.conectar() as conn:
        conn.execute("""
            INSERT INTO expedientes (id, titulo, organo, localidad, fuente, fecha_publicacion, fecha_ingesta, last_seen_feed, feed_hash)
            VALUES ('EXP-LOCK-001', 'Licitación Mutex', 'Ajuntament de Barcelona', 'Barcelona', 'PSCP', '2026-07-26T00:00:00Z', '2026-07-26T00:00:00Z', '2026-07-26T00:00:00Z', 'hlock1');
        """)
        conn.execute("""
            INSERT INTO lotes (expediente_id, lote_numero, titulo_lote, pbl, vec, score_total, estado_operativo, updated_at)
            VALUES ('EXP-LOCK-001', 1, 'Lote 1', 100000.0, 200000.0, 85, 'Nueva', '2026-07-26T00:00:00Z');
        """)
        conn.commit()

    exito, estado_ant, exp_dict = memoria.mutar_estado_lote_transaccional(
        expediente_id="EXP-LOCK-001",
        lote_numero=1,
        nuevo_estado="Estudiando",
        notas="Verificación atómica"
    )
    
    assert exito is True
    assert estado_ant == "Nueva"
    assert exp_dict["lotes"][0]["estado_operativo"] == "Estudiando"
    assert exp_dict["lotes"][0]["notas_usuario"] == "Verificación atómica"


def test_jsonl_log_rotation(tmp_path):
    """Verifica la rotación defensiva de archivos de log JSONL cuando superan el umbral de tamaño."""
    log_file = str(tmp_path / "test_pipeline.jsonl")
    logger = GestorTrazabilidadAPI(log_path=log_file)
    
    # Crear un archivo de log ficticio grande (> 100 bytes en prueba con threshold bajo)
    with open(log_file, "w", encoding="utf-8") as f:
        f.write("A" * 500 + "\n")
        
    rotar_log_si_excede_tamano(log_file, max_bytes=100, max_archivos=3)
    
    # Verificar que el archivo original se rotó y se creó uno nuevo al registrar evento
    logger.registrar_evento("TEST_EVENT", {"status": "ok"})
    
    archivos = os.listdir(tmp_path)
    jsonl_files = [f for f in archivos if f.endswith(".jsonl")]
    
    assert len(jsonl_files) == 2
    assert "test_pipeline.jsonl" in jsonl_files

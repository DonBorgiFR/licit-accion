import os
import sys
import unittest
import tempfile
import sqlite3
import shutil
from datetime import datetime, timezone

# Añadir src al path de Python

from src.memoria import Memoria, SQL_CREATE_METADATA, SQL_CREATE_EXPEDIENTES, SQL_CREATE_LOTES, SQL_CREATE_EJECUCIONES, SQL_CREATE_DOCUMENTOS, SQL_CREATE_INDICES
from src.analista import AnalisisSemanticoDTO, SubrogacionDTO, RevisionPreciosDTO, CriteriosAdjudicacionDTO, DictamenIA

class TestMemoriaEsquemaV4(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "test_licitaciones.db")
        self.memoria = Memoria(db_path=self.db_path)

    def tearDown(self):
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_inicializacion_limpia_v4(self):
        """Valida que setup_db() en una BD inexistente crea el esquema v4+ directamente."""
        self.memoria.setup_db()
        self.assertGreaterEqual(self.memoria.ESQUEMA_VERSION, 4)

        hc = self.memoria.healthcheck_memoria()
        self.assertEqual(hc["status"], "OK")
        self.assertGreaterEqual(hc["version_actual"], 4)
        self.assertIn("analisis_semantico", hc["tablas_detectadas"])

    def test_migracion_desde_v3_a_v4(self):
        """Crea sintéticamente una BD en esquema v3 y verifica que setup_db() la migra a v4+ sin perder datos."""
        # 1. Crear BD v3 en disco
        conn = sqlite3.connect(self.db_path)
        with conn:
            conn.execute(SQL_CREATE_METADATA)
            conn.execute("INSERT INTO metadata (version) VALUES (3);")
            conn.execute(SQL_CREATE_EXPEDIENTES)
            conn.execute(SQL_CREATE_LOTES)
            conn.execute(SQL_CREATE_EJECUCIONES)
            conn.execute(SQL_CREATE_DOCUMENTOS)
            for query in SQL_CREATE_INDICES:
                # Esta BD sintética es un v3: sólo puede indexar las tablas que existían
                # entonces. `purgas` llegó con v6 y `expedientes.deleted_at` también.
                if not any(
                    posterior in query
                    for posterior in ("analisis_semantico", "boletines_alertas", "purgas", "deleted_at")
                ):
                    conn.execute(query)


            # Insertar un expediente y un documento procesado
            conn.execute(
                "INSERT INTO expedientes (id, titulo, fecha_ingesta) VALUES ('EXP-TEST-001', 'Licitación de Prueba V3', '2026-07-24T12:00:00Z');"
            )
            conn.execute(
                "INSERT INTO documentos (expediente_id, titulo, url, tipo, hash_documento, estado, updated_at) "
                "VALUES ('EXP-TEST-001', 'PCA.pdf', 'http://example.com/pca.pdf', 'PCA', 'hash123', 'PROCESADO', '2026-07-24T12:00:00Z');"
            )
        conn.close()

        # 2. Ejecutar setup_db() para gatillar la migración v3 -> v4
        self.memoria.setup_db()

        # 3. Comprobar resultados
        hc = self.memoria.healthcheck_memoria()
        self.assertEqual(hc["status"], "OK")
        self.assertGreaterEqual(hc["version_actual"], 4)


        pendientes = self.memoria.listar_expedientes_pendientes_analisis()
        self.assertEqual(len(pendientes), 1)
        self.assertEqual(pendientes[0]["id"], "EXP-TEST-001")

    def test_guardar_y_recuperar_analisis_semantico(self):
        """Prueba el ciclo de vida completo: inserción y reconstrucción de AnalisisSemanticoDTO."""
        self.memoria.setup_db()

        # Crear expediente previo
        with self.memoria.conectar() as conn:
            with conn:
                conn.execute(
                    "INSERT INTO expedientes (id, titulo, fecha_ingesta) VALUES ('EXP-SEM-100', 'Limpieza Hospitalaria', '2026-07-24T12:00:00Z');"
                )

        dto_original = AnalisisSemanticoDTO(
            subrogacion=SubrogacionDTO(
                detectada=True,
                num_trabajadores=15,
                convenio_colectivo="Convenio Colectivo de Limpieza de Edificios y Locales",
                desglose_salarial_completo=True,
                coste_estimado_anual=350000.0,
                riesgo_evaluado="ALTO"
            ),
            revision_precios=RevisionPreciosDTO(
                permitida=True,
                formula_detectada="Fórmula BOE Art. 103 LCSP Limpieza",
                art_103_aplica=True,
                observaciones="Revisión sujeta a variación del IPC de mano de obra"
            ),
            criterios=CriteriosAdjudicacionDTO(
                peso_precio_formulas=60,
                peso_juicio_valor=40,
                requiere_memoria_tecnica=True,
                criterios_desglose=[{"nombre": "Oferta económica", "peso": 60}, {"nombre": "Plan de calidad", "peso": 40}]
            ),
            dictamen=DictamenIA(
                recomendacion="REVISAR_RIESGO",
                motivos=["Riesgo laboral por subrogación de 15 trabajadores", "Revisión de precios incluida"],
                ajuste_score=-10,
                resumen_ejecutivo="Licitación atractiva con margen aceptable pero riesgo laboral alto por subrogación."
            ),
            version_esquema=1
        )

        metadatos = {
            "modelo_llm": "ollama/llama3:8b",
            "prompt_tokens": 1250,
            "completion_tokens": 480,
            "tiempo_procesamiento_seg": 3.45,
            "estado_analisis": "COMPLETADO"
        }

        # Guardar en BD
        exito = self.memoria.guardar_analisis_semantico("EXP-SEM-100", dto_original, metadatos=metadatos)
        self.assertTrue(exito)

        # Recuperar DTO
        dto_recuperado = self.memoria.obtener_analisis_semantico("EXP-SEM-100")
        self.assertIsNotNone(dto_recuperado)
        self.assertTrue(dto_recuperado.subrogacion.detectada)
        self.assertEqual(dto_recuperado.subrogacion.num_trabajadores, 15)
        self.assertEqual(dto_recuperado.subrogacion.riesgo_evaluado, "ALTO")
        self.assertTrue(dto_recuperado.revision_precios.permitida)
        self.assertEqual(dto_recuperado.criterios.peso_precio_formulas, 60)
        self.assertEqual(dto_recuperado.dictamen.recomendacion, "REVISAR_RIESGO")
        self.assertEqual(dto_recuperado.dictamen.ajuste_score, -10)

        # Recuperar Raw
        raw = self.memoria.obtener_analisis_semantico_raw("EXP-SEM-100")
        self.assertIsNotNone(raw)
        self.assertEqual(raw["modelo_llm"], "ollama/llama3:8b")
        self.assertEqual(raw["prompt_tokens"], 1250)
        self.assertEqual(raw["estado_analisis"], "COMPLETADO")

    def test_jsonl_log_escritura(self):
        """Verifica que guardar_analisis_semantico registra evento en pipeline.jsonl."""
        self.memoria.setup_db()
        with self.memoria.conectar() as conn:
            with conn:
                conn.execute("INSERT INTO expedientes (id, titulo, fecha_ingesta) VALUES ('EXP-LOG-01', 'Test Log', '2026-07-24T12:00:00Z');")

        dto = AnalisisSemanticoDTO(
            subrogacion=SubrogacionDTO(),
            revision_precios=RevisionPreciosDTO(),
            criterios=CriteriosAdjudicacionDTO(),
            dictamen=DictamenIA()
        )
        self.memoria.guardar_analisis_semantico("EXP-LOG-01", dto)

        log_path = os.path.join(self.temp_dir, "pipeline.jsonl")
        self.assertTrue(os.path.exists(log_path))
        with open(log_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
            self.assertGreaterEqual(len(lines), 1)
            self.assertIn("guardar_analisis_semantico", lines[-1])
            self.assertIn("EXP-LOG-01", lines[-1])

if __name__ == "__main__":
    unittest.main()

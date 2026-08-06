import os
import sys
import unittest
import json
import tempfile
import shutil
import csv
from unittest.mock import patch, MagicMock


from src.memoria import Memoria
from src.analista import AnalistaIA

class TestAnalistaMainIntegration(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "licitaciones_test.db")
        self.config_path = os.path.join(self.temp_dir, "analista_config.yaml")
        self.prompts_path = os.path.join(self.temp_dir, "prompts_lcsp.yaml")
        self.reports_dir = os.path.join(self.temp_dir, "reports")
        self.csv_path = os.path.join(self.reports_dir, "analisis_semantico_summary.csv")

        with open(self.config_path, "w", encoding="utf-8") as f:
            f.write(f"""
proveedor_preferente: "ollama"
permitir_fallback: true
timeout_segundos: 5
prompts_path: "{self.prompts_path.replace('\\', '/')}"

ollama:
  host: "http://localhost:11434"
  modelo: "llama3.1:8b"
""")

        with open(self.prompts_path, "w", encoding="utf-8") as f:
            f.write("""
version: "1.0.0"
sistema_base: "Sistema de prueba integracion"
""")

        # Inicializar Memoria
        self.memoria = Memoria(db_path=self.db_path)
        self.memoria.setup_db()

        # Inicializar AnalistaIA
        self.analista = AnalistaIA(config_path=self.config_path)

        self.sample_json = json.dumps({
            "subrogacion": {"detectada": True, "num_trabajadores": 5, "convenio_colectivo": "Hostelería", "desglose_salarial_completo": True, "coste_estimado_anual": 120000.0, "riesgo_evaluado": "BAJO"},
            "revision_precios": {"permitida": True, "formula_detectada": "IPC", "art_103_aplica": True, "observaciones": "Aplica formula"},
            "criterios": {"peso_precio_formulas": 60, "peso_juicio_valor": 40, "requiere_memoria_tecnica": True, "criterios_desglose": []},
            "dictamen": {"recomendacion": "RECOMENDADA", "motivos": ["Buen equilibrio"], "ajuste_score": 10, "resumen_ejecutivo": "Oportunidad viable"},
            "version_esquema": 1
        })

    def tearDown(self):
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _crear_expediente_sintetico(self, exp_id="EXP-MAIN-001"):
        lic = {
            "id": exp_id,
            "titulo": "Servicio de Menjador Escolar Test",
            "organo": "Ajuntament de Barcelona",
            "importe": 150000.0,
            "vec": 300000.0,
            "fecha_limite": "2026-12-31"
        }
        eval_data = {
            "apta": True,
            "score": 70,
            "motivos": ["Sector core"],
            "sector_detectado": "Educación",
            "prioridad": "Alta",
            "garantia_estimada": 7500.0,
            "pmp_detectado": 30,
            "ratio_prorrogas": 2.0,
            "subrogacion_detectada": True,
            "revision_precios_detectada": True,
            "dias_restantes": 30
        }
        self.memoria.upsert_oportunidades_batch([(lic, eval_data)], run_id=1)
        doc = {
            "titulo": "Pliego de Cláusulas Administrativas",
            "url": "http://ejemplo.com/pca.pdf",
            "tipo": "PCA",
            "hash": "abc123456789"
        }
        self.memoria.registrar_documento_detectado(exp_id, doc)
        
        # Marcar documento como PROCESADO con texto extraído
        with self.memoria.conectar() as conn:
            with conn:
                conn.execute("""
                UPDATE documentos
                SET estado = 'PROCESADO', texto_extraido = 'Texto del pliego con clausula de subrogacion articulo 130 LCSP y revision de precios articulo 103 LCSP.'
                WHERE expediente_id = ?;
                """, (exp_id,))

    @patch('urllib.request.urlopen')
    def test_procesar_lote_pendientes_e2e(self, mock_urlopen):
        """Valida que procesar_lote_pendientes analiza la licitación y genera el informe CSV."""
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = json.dumps({"message": {"content": self.sample_json}}).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        self._crear_expediente_sintetico("EXP-MAIN-001")

        # Ejecutar lote
        res = self.analista.procesar_lote_pendientes(memoria=self.memoria, limite=10)
        self.assertEqual(res["total_pendientes"], 1)
        self.assertEqual(res["procesados_exito"], 1)

        # Verificar BD SQLite v4
        an_db = self.memoria.obtener_analisis_semantico_raw("EXP-MAIN-001")
        self.assertIsNotNone(an_db)
        self.assertEqual(an_db["dictamen_recomendacion"], "RECOMENDADA")
        self.assertEqual(an_db["subrogacion_num_trabajadores"], 5)

        # Generar y verificar reporte CSV
        csv_generado = self.analista.generar_reporte_csv(memoria=self.memoria, csv_path=self.csv_path)
        self.assertTrue(os.path.exists(csv_generado))

        with open(csv_generado, "r", encoding="utf-8-sig") as f:
            reader = csv.reader(f, delimiter=";")
            rows = list(reader)
            self.assertGreaterEqual(len(rows), 2)
            headers = rows[0]
            self.assertIn("expediente_id", headers)
            self.assertIn("score_recalibrado", headers)
            self.assertIn("dictamen_final", headers)
            
            data_row = rows[1]
            self.assertEqual(data_row[0], "EXP-MAIN-001")
            self.assertEqual(data_row[6], "RECOMENDADA")

if __name__ == "__main__":
    unittest.main()

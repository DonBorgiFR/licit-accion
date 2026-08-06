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

class TestCapa5E2E(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "licitaciones_e2e.db")
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

recalibracion:
  umbral_recomendada: 65.0
  umbral_descartada: 40.0
""")

        with open(self.prompts_path, "w", encoding="utf-8") as f:
            f.write("""
version: "1.0.0"
sistema_base: "Sistema de prueba E2E"
""")

        self.memoria = Memoria(db_path=self.db_path)
        self.memoria.setup_db()
        self.analista = AnalistaIA(config_path=self.config_path)

    def tearDown(self):
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _crear_expediente_y_documento(self, exp_id, titulo, score_cuantitativo, texto_pliego):
        lic = {"id": exp_id, "titulo": titulo, "organo": "Organo Publico Test", "importe": 200000.0, "vec": 400000.0, "fecha_limite": "2026-12-31"}
        eval_data = {"apta": True, "score": score_cuantitativo, "motivos": ["Core"], "sector_detectado": "Servicios", "prioridad": "Alta", "garantia_estimada": 10000.0, "pmp_detectado": 30, "ratio_prorrogas": 2.0, "subrogacion_detectada": False, "revision_precios_detectada": True, "dias_restantes": 30}
        self.memoria.upsert_oportunidades_batch([(lic, eval_data)], run_id=1)

        doc = {"titulo": "PCA Pliego Test", "url": "http://ejemplo.com/pca.pdf", "tipo": "PCA", "hash": f"hash_{exp_id}"}
        self.memoria.registrar_documento_detectado(exp_id, doc)

        with self.memoria.conectar() as conn:
            with conn:
                conn.execute("""
                UPDATE documentos
                SET estado = 'PROCESADO', texto_extraido = ?
                WHERE expediente_id = ?;
                """, (texto_pliego, exp_id))

    @patch('urllib.request.urlopen')
    def test_e2e_subrogacion_critica_veto(self, mock_urlopen):
        """Escenario A: Licitación con subrogación crítica activa veto comercial y dictamen DESCARTADA_POR_RIESGO."""
        self._crear_expediente_y_documento("EXP-E2E-001", "Servicio de Limpieza con Subrogacion", 75.0, "Texto pliego...")

        sample_critico = json.dumps({
            "subrogacion": {"detectada": True, "num_trabajadores": 25, "convenio_colectivo": "Limpieza", "desglose_salarial_completo": False, "coste_estimado_anual": 450000.0, "riesgo_evaluado": "CRITICO"},
            "revision_precios": {"permitida": False, "formula_detectada": None, "art_103_aplica": False, "observaciones": "No permitida"},
            "criterios": {"peso_precio_formulas": 40, "peso_juicio_valor": 60, "requiere_memoria_tecnica": True, "criterios_desglose": []},
            "dictamen": {"recomendacion": "DESCARTADA_POR_RIESGO", "motivos": ["Subrogacion critica"], "ajuste_score": -35, "resumen_ejecutivo": "Alto riesgo laboral"},
            "version_esquema": 1
        })
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = json.dumps({"message": {"content": sample_critico}}).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        res = self.analista.procesar_lote_pendientes(memoria=self.memoria, limite=5)
        self.assertEqual(res["procesados_exito"], 1)

        raw = self.memoria.obtener_analisis_semantico_raw("EXP-E2E-001")
        self.assertEqual(raw["dictamen_recomendacion"], "DESCARTADA_POR_RIESGO")
        self.assertEqual(raw["subrogacion_riesgo"], "CRITICO")

    @patch('urllib.request.urlopen')
    def test_e2e_oportunidad_recomendada(self, mock_urlopen):
        """Escenario B: Licitación favorable con revisión de precios activa dictamen RECOMENDADA."""
        self._crear_expediente_y_documento("EXP-E2E-002", "Servicio Educativo Favorables", 60.0, "Texto pliego...")

        sample_bueno = json.dumps({
            "subrogacion": {"detectada": False, "num_trabajadores": None, "convenio_colectivo": None, "desglose_salarial_completo": True, "coste_estimado_anual": None, "riesgo_evaluado": "BAJO"},
            "revision_precios": {"permitida": True, "formula_detectada": "IPC", "art_103_aplica": True, "observaciones": "Formula activa"},
            "criterios": {"peso_precio_formulas": 70, "peso_juicio_valor": 30, "requiere_memoria_tecnica": False, "criterios_desglose": []},
            "dictamen": {"recomendacion": "RECOMENDADA", "motivos": ["Favorable"], "ajuste_score": 15, "resumen_ejecutivo": "Excelente oportunidad"},
            "version_esquema": 1
        })
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = json.dumps({"message": {"content": sample_bueno}}).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        res = self.analista.procesar_lote_pendientes(memoria=self.memoria, limite=5)
        self.assertEqual(res["procesados_exito"], 1)

        raw = self.memoria.obtener_analisis_semantico_raw("EXP-E2E-002")
        self.assertEqual(raw["dictamen_recomendacion"], "RECOMENDADA")

    @patch('urllib.request.urlopen')
    def test_e2e_modo_degradado_sin_llm(self, mock_urlopen):
        """Escenario C: Caída total de LLMs asigna estado ANALISIS_DIFERIDO preservando el score inicial."""
        self._crear_expediente_y_documento("EXP-E2E-003", "Servicio sin LLM activo", 65.0, "Texto pliego...")
        mock_urlopen.side_effect = Exception("Sin conexion a red/Ollama")

        res = self.analista.procesar_lote_pendientes(memoria=self.memoria, limite=5)
        self.assertEqual(res["procesados_degradados"], 1)

        raw = self.memoria.obtener_analisis_semantico_raw("EXP-E2E-003")
        self.assertEqual(raw["estado_analisis"], "DEGRADADO")
        # La degradación debe quedar persistida como dato estructurado en el DTO,
        # no inferible del texto libre del resumen.
        dto_recuperado = self.memoria.obtener_analisis_semantico("EXP-E2E-003")
        self.assertTrue(dto_recuperado.modo_degradado)

    @patch('urllib.request.urlopen')
    def test_e2e_generacion_reporte_csv(self, mock_urlopen):
        """Escenario D: Ingesta de múltiples expedientes genera un reporte CSV consolidado estructurado."""
        self._crear_expediente_y_documento("EXP-E2E-CSV1", "Licitacion CSV 1", 70.0, "Texto 1")
        self._crear_expediente_y_documento("EXP-E2E-CSV2", "Licitacion CSV 2", 50.0, "Texto 2")

        sample = json.dumps({
            "subrogacion": {"detectada": False, "num_trabajadores": None, "convenio_colectivo": None, "desglose_salarial_completo": True, "coste_estimado_anual": None, "riesgo_evaluado": "BAJO"},
            "revision_precios": {"permitida": True, "formula_detectada": "IPC", "art_103_aplica": True, "observaciones": "OK"},
            "criterios": {"peso_precio_formulas": 60, "peso_juicio_valor": 40, "requiere_memoria_tecnica": True, "criterios_desglose": []},
            "dictamen": {"recomendacion": "RECOMENDADA", "motivos": ["OK"], "ajuste_score": 5, "resumen_ejecutivo": "OK"},
            "version_esquema": 1
        })
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = json.dumps({"message": {"content": sample}}).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        self.analista.procesar_lote_pendientes(memoria=self.memoria, limite=5)
        csv_file = self.analista.generar_reporte_csv(memoria=self.memoria, csv_path=self.csv_path)

        self.assertTrue(os.path.exists(csv_file))
        with open(csv_file, "r", encoding="utf-8-sig") as f:
            reader = csv.reader(f, delimiter=";")
            rows = list(reader)
            self.assertEqual(len(rows), 3) # Header + 2 rows

if __name__ == "__main__":
    unittest.main()

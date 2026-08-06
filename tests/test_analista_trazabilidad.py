import os
import sys
import unittest
import json
import tempfile
import shutil
from unittest.mock import patch, MagicMock


from src.analista import AnalistaIA

class TestAnalistaTrazabilidad(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.config_path = os.path.join(self.temp_dir, "analista_config.yaml")
        self.prompts_path = os.path.join(self.temp_dir, "prompts_lcsp.yaml")
        self.data_dir = os.path.join(self.temp_dir, "data")
        os.makedirs(self.data_dir, exist_ok=True)

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
sistema_base: "Sistema de prueba"
""")

        self.analista = AnalistaIA(config_path=self.config_path)

        self.sample_json = json.dumps({
            "subrogacion": {"detectada": False, "num_trabajadores": None, "convenio_colectivo": None, "desglose_salarial_completo": True, "coste_estimado_anual": None, "riesgo_evaluado": "BAJO"},
            "revision_precios": {"permitida": True, "formula_detectada": "IPC", "art_103_aplica": True, "observaciones": "Formula activa"},
            "criterios": {"peso_precio_formulas": 60, "peso_juicio_valor": 40, "requiere_memoria_tecnica": True, "criterios_desglose": []},
            "dictamen": {"recomendacion": "RECOMENDADA", "motivos": ["OK"], "ajuste_score": 0, "resumen_ejecutivo": "Excelente"},
            "version_esquema": 1
        })

    def tearDown(self):
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    @patch('urllib.request.urlopen')
    def test_procesar_expediente_exito_trazabilidad(self, mock_urlopen):
        """Valida que un procesamiento exitoso registra todos los eventos JSONL requeridos."""
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = json.dumps({"message": {"content": self.sample_json}}).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        with patch.object(self.analista, 'registrar_log_jsonl') as mock_log:
            res = self.analista.procesar_expediente(
                expediente_id="EXP-TRAZ-01",
                texto_pliego="Pliego con clausula de subrogacion articulo 130 LCSP...",
                score_cuantitativo=70.0,
                duracion_meses=12,
                idioma="es"
            )

            self.assertEqual(res["estado_operativo"], "COMPLETADO")
            self.assertEqual(res["recalibracion"]["dictamen_final"], "RECOMENDADA")

            # Verificar llamadas a registrar_log_jsonl
            events_logged = [call.args[0] for call in mock_log.call_args_list]
            self.assertIn("doc_analysis_started", events_logged)
            self.assertIn("SMART_CHUNKING_COMPLETED", events_logged)
            self.assertIn("PROMPT_GENERATED", events_logged)
            self.assertIn("LLM_REQUEST_START", events_logged)
            self.assertIn("LLM_REQUEST_SUCCESS", events_logged)
            self.assertIn("SCORE_RECALIBRATED", events_logged)
            self.assertIn("doc_analysis_completed", events_logged)

    @patch('urllib.request.urlopen')
    def test_procesar_expediente_modo_degradado_diferido(self, mock_urlopen):
        """Fallo en proveedores LLM asigna estado ANALISIS_DIFERIDO y evento doc_analysis_degraded."""
        mock_urlopen.side_effect = Exception("Inaccesible")

        with patch.object(self.analista, 'registrar_log_jsonl') as mock_log:
            res = self.analista.procesar_expediente(
                expediente_id="EXP-DEG-01",
                texto_pliego="Texto del pliego...",
                score_cuantitativo=65.0
            )

            self.assertEqual(res["estado_operativo"], "ANALISIS_DIFERIDO")
            self.assertEqual(res["metadatos"]["estado_analisis"], "DEGRADADO")
            self.assertEqual(res["recalibracion"]["score_recalibrado"], 65.0)

            events_logged = [call.args[0] for call in mock_log.call_args_list]
            self.assertIn("LLM_REQUEST_DEGRADED", events_logged)
            self.assertIn("doc_analysis_degraded", events_logged)

    def test_healthcheck_logger_status(self):
        """Verifica la audibilidad del escritor de logs en healthcheck_analista()."""
        hc = self.analista.healthcheck_analista()
        self.assertIn("logger_writer_status", hc)
        self.assertEqual(hc["logger_writer_status"], "OK")

if __name__ == "__main__":
    unittest.main()

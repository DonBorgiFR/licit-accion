import os
import sys
import unittest
import json
import io
import tempfile
import shutil
from unittest.mock import patch, MagicMock


from src.analista import (
    AnalistaIA, OllamaProvider, GeminiProvider, ProviderError,
    AnalisisSemanticoDTO, SubrogacionDTO, RevisionPreciosDTO, CriteriosAdjudicacionDTO, DictamenIA
)

class TestAnalistaLLM(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.config_path = os.path.join(self.temp_dir, "analista_config.yaml")
        with open(self.config_path, "w", encoding="utf-8") as f:
            f.write("""
proveedor_preferente: "ollama"
permitir_fallback: true
timeout_segundos: 5

ollama:
  host: "http://localhost:11434"
  modelo: "llama3.1:8b"
  temperature: 0.1

gemini:
  modelo: "gemini-2.0-flash"
  temperature: 0.1
""")
        self.analista = AnalistaIA(config_path=self.config_path)

        self.sample_json_response = json.dumps({
            "subrogacion": {
                "detectada": True,
                "num_trabajadores": 8,
                "convenio_colectivo": "Convenio de Hostelería",
                "desglose_salarial_completo": True,
                "coste_estimado_anual": 180000.0,
                "riesgo_evaluado": "MEDIO"
            },
            "revision_precios": {
                "permitida": False,
                "formula_detectada": None,
                "art_103_aplica": False,
                "observaciones": "Sin revisión de precios contemplada"
            },
            "criterios": {
                "peso_precio_formulas": 55,
                "peso_juicio_valor": 45,
                "requiere_memoria_tecnica": True,
                "criterios_desglose": [{"nombre": "Precio", "peso": 55}]
            },
            "dictamen": {
                "recomendacion": "REVISAR_RIESGO",
                "motivos": ["Absorción de 8 empleados"],
                "ajuste_score": -5,
                "resumen_ejecutivo": "Subrogación confirmada de 8 trabajadores."
            },
            "version_esquema": 1
        }, ensure_ascii=False)

    def tearDown(self):
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    @patch('urllib.request.urlopen')
    def test_ollama_provider_exito(self, mock_urlopen):
        """Valida que OllamaProvider parsea correctamente la respuesta HTTP de Ollama."""
        ollama_body = json.dumps({
            "message": {"content": self.sample_json_response},
            "prompt_eval_count": 500,
            "eval_count": 120
        }).encode("utf-8")

        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = ollama_body
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        provider = OllamaProvider(host="http://localhost:11434", modelo="llama3.1:8b")
        res = provider.consultar("Prompt sistema", "Prompt usuario")

        self.assertIn("ollama/llama3.1:8b", res["modelo"])
        self.assertEqual(res["prompt_tokens"], 500)
        self.assertEqual(res["completion_tokens"], 120)
        self.assertIn("Subrogación confirmada", res["raw_response"])

    @patch('urllib.request.urlopen')
    def test_gemini_provider_exito(self, mock_urlopen):
        """Valida que GeminiProvider se comunica con la API Cloud enviando headers JSON."""
        gemini_body = json.dumps({
            "candidates": [
                {
                    "content": {
                        "parts": [{"text": self.sample_json_response}]
                    }
                }
            ],
            "usageMetadata": {
                "promptTokenCount": 650,
                "candidatesTokenCount": 140
            }
        }).encode("utf-8")

        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = gemini_body
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        provider = GeminiProvider(api_key="TEST_API_KEY_FAKE", modelo="gemini-2.0-flash")
        res = provider.consultar("Prompt sistema", "Prompt usuario")

        self.assertIn("gemini/gemini-2.0-flash", res["modelo"])
        self.assertEqual(res["prompt_tokens"], 650)
        self.assertEqual(res["completion_tokens"], 140)

    @patch('urllib.request.urlopen')
    def test_analista_fallback_ollama_a_gemini(self, mock_urlopen):
        """Simula que Ollama falla y verifica que AnalistaIA conmuta automáticamente a Gemini."""
        gemini_body = json.dumps({
            "candidates": [{"content": {"parts": [{"text": self.sample_json_response}]}}],
            "usageMetadata": {"promptTokenCount": 400, "candidatesTokenCount": 100}
        }).encode("utf-8")

        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = gemini_body

        def side_effect(req, timeout=60):
            # Si es llamada a Ollama (localhost), falla
            url = req.full_url if hasattr(req, 'full_url') else str(req)
            if "localhost" in url:
                raise Exception("Ollama servidor offline")
            # Si es llamada a Gemini, devuelve mock_resp
            mock_cm = MagicMock()
            mock_cm.__enter__.return_value = mock_resp
            return mock_cm

        mock_urlopen.side_effect = side_effect

        with patch.dict(os.environ, {"GEMINI_API_KEY": "FAKE_KEY"}):
            dto, metadatos = self.analista.analizar_pliego("Texto de pliego...", expediente_id="EXP-FALLBACK-01")

        self.assertEqual(metadatos["estado_analisis"], "COMPLETADO")
        self.assertIn("gemini", metadatos["modelo_llm"])
        self.assertTrue(dto.subrogacion.detectada)
        self.assertEqual(dto.subrogacion.num_trabajadores, 8)

    @patch('urllib.request.urlopen')
    def test_analista_modo_degradado(self, mock_urlopen):
        """Simula fallo catastrófico en ambos proveedores y verifica que se genera DTO en modo DEGRADADO."""
        mock_urlopen.side_effect = Exception("Sin conectividad a ningun proveedor")

        dto, metadatos = self.analista.analizar_pliego("Texto de pliego...", expediente_id="EXP-DEG-99")

        self.assertEqual(metadatos["estado_analisis"], "DEGRADADO")
        self.assertEqual(metadatos["modelo_llm"], "ninguno/degradado")
        self.assertEqual(dto.dictamen.recomendacion, "REVISAR_RIESGO")
        # El modo degradado se afirma por campo explícito del DTO, no por heurística de
        # cadena sobre el resumen ejecutivo. El esquema subió a v3 al incorporar las tres
        # cláusulas críticas que faltaban (garantía definitiva, penalidades y sociales).
        self.assertTrue(dto.modo_degradado)
        self.assertEqual(dto.version_esquema, 3)

    @patch('urllib.request.urlopen')
    def test_respuesta_json_valida_pero_esquema_invalido_activa_fallback(self, mock_urlopen):
        """
        REGRESIÓN: una respuesta con JSON sintácticamente válido pero esquema equivocado
        NO debe darse por buena. Debe tratarse como fallo del proveedor y conmutar al
        siguiente de la cadena.

        Este era el agujero real: Ollama sólo garantiza JSON válido (`format: json`),
        no la forma correcta, así que devolvía basura estructurada que se persistía
        como análisis COMPLETADO con todos los riesgos a False.
        """
        basura_ollama = json.dumps({"respuesta": "no he podido analizar el documento"})
        gemini_body = json.dumps({
            "candidates": [{"content": {"parts": [{"text": self.sample_json_response}]}}],
            "usageMetadata": {"promptTokenCount": 400, "candidatesTokenCount": 100}
        }).encode("utf-8")

        def side_effect(req, timeout=60):
            url = req.full_url if hasattr(req, 'full_url') else str(req)
            mock_cm = MagicMock()
            resp = MagicMock()
            resp.status = 200
            if "localhost" in url:
                # Ollama responde 200 con JSON válido pero fuera de esquema
                resp.read.return_value = json.dumps({"message": {"content": basura_ollama}}).encode("utf-8")
            else:
                resp.read.return_value = gemini_body
            mock_cm.__enter__.return_value = resp
            return mock_cm

        mock_urlopen.side_effect = side_effect

        with patch.dict(os.environ, {"GEMINI_API_KEY": "FAKE_KEY"}):
            dto, metadatos = self.analista.analizar_pliego("Texto...", expediente_id="EXP-ESQUEMA-01")

        # Debe haber conmutado a Gemini y haber recuperado el análisis real
        self.assertIn("gemini", metadatos["modelo_llm"])
        self.assertEqual(metadatos["estado_analisis"], "COMPLETADO")
        self.assertFalse(dto.modo_degradado)
        self.assertTrue(dto.subrogacion.detectada)
        self.assertEqual(dto.subrogacion.num_trabajadores, 8)

    @patch('urllib.request.urlopen')
    def test_esquema_invalido_en_todos_los_proveedores_termina_degradado(self, mock_urlopen):
        """
        Si NINGÚN proveedor devuelve un esquema válido, el resultado debe ser DEGRADADO,
        nunca un COMPLETADO con los campos de riesgo vacíos (que se leería en el Cockpit
        como 'sin subrogación y sin riesgos').
        """
        basura = json.dumps({"texto": "lo siento, no puedo ayudarte con eso"})

        def side_effect(req, timeout=60):
            mock_cm = MagicMock()
            resp = MagicMock()
            resp.status = 200
            resp.read.return_value = json.dumps({
                "message": {"content": basura},
                "candidates": [{"content": {"parts": [{"text": basura}]}}]
            }).encode("utf-8")
            mock_cm.__enter__.return_value = resp
            return mock_cm

        mock_urlopen.side_effect = side_effect

        with patch.dict(os.environ, {"GEMINI_API_KEY": "FAKE_KEY"}):
            dto, metadatos = self.analista.analizar_pliego("Texto...", expediente_id="EXP-ESQUEMA-02")

        self.assertEqual(metadatos["estado_analisis"], "DEGRADADO")
        self.assertTrue(dto.modo_degradado)
        # Y el dictamen no debe afirmar ausencia de riesgos
        self.assertEqual(dto.dictamen.recomendacion, "REVISAR_RIESGO")

    def test_from_json_estricto_vs_tolerante(self):
        """El parseo estricto (respuestas LLM) eleva; el tolerante (relectura BD) degrada."""
        fuera_de_esquema = json.dumps({"foo": "bar"})

        with self.assertRaises(Exception):
            AnalisisSemanticoDTO.from_json(fuera_de_esquema, estricto=True)

        dto = AnalisisSemanticoDTO.from_json(fuera_de_esquema, estricto=False)
        self.assertTrue(dto.modo_degradado)

        # JSON ilegible
        with self.assertRaises(Exception):
            AnalisisSemanticoDTO.from_json("{esto no es json", estricto=True)
        self.assertTrue(AnalisisSemanticoDTO.from_json("{esto no es json", estricto=False).modo_degradado)

    def test_healthcheck_analista(self):
        """Verifica la respuesta estructurada de healthcheck_analista()."""
        hc = self.analista.healthcheck_analista()
        self.assertIn("status", hc)
        self.assertIn("ollama_status", hc)
        self.assertIn("gemini_status", hc)

if __name__ == "__main__":
    unittest.main()

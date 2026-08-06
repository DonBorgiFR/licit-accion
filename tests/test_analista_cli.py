import os
import sys
import unittest
import json
import tempfile
import shutil
from unittest.mock import patch, MagicMock


from src.memoria import Memoria
from src.analista import AnalistaIA, SubrogacionDTO, RevisionPreciosDTO, CriteriosAdjudicacionDTO, DictamenIA, AnalisisSemanticoDTO, main_cli

class TestAnalistaCLI(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "licitaciones_cli_test.db")
        self.config_path = os.path.join(self.temp_dir, "analista_config.yaml")
        self.prompts_path = os.path.join(self.temp_dir, "prompts_lcsp.yaml")

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
sistema_base: "Sistema de prueba CLI"
""")

        self.memoria = Memoria(db_path=self.db_path)
        self.memoria.setup_db()
        self.analista = AnalistaIA(config_path=self.config_path)

        # Ingestar expediente sintético
        self.exp_id = "EXP-CLI-TEST-01"
        lic = {"id": self.exp_id, "titulo": "Servicio de Limpieza Escolar", "organo": "Consorci d Educacio", "importe": 80000.0, "vec": 160000.0, "fecha_limite": "2026-12-31"}
        eval_data = {"apta": True, "score": 60, "motivos": ["Core"], "sector_detectado": "Servicios", "prioridad": "Media", "garantia_estimada": 4000.0, "pmp_detectado": 30, "ratio_prorrogas": 2.0, "subrogacion_detectada": False, "revision_precios_detectada": True, "dias_restantes": 20}
        self.memoria.upsert_oportunidades_batch([(lic, eval_data)], run_id=1)

        # Guardar DTO semántico inicial
        dto = AnalisisSemanticoDTO(
            subrogacion=SubrogacionDTO(detectada=False, num_trabajadores=None, convenio_colectivo=None, desglose_salarial_completo=True, coste_estimado_anual=None, riesgo_evaluado="BAJO"),
            revision_precios=RevisionPreciosDTO(permitida=True, formula_detectada="IPC", art_103_aplica=True, observaciones="OK"),
            criterios=CriteriosAdjudicacionDTO(peso_precio_formulas=70, peso_juicio_valor=30, requiere_memoria_tecnica=False, criterios_desglose=[]),
            dictamen=DictamenIA(recomendacion="RECOMENDADA", motivos=["Bajo riesgo"], ajuste_score=10, resumen_ejecutivo="Muy favorable")
        )
        self.memoria.guardar_analisis_semantico(self.exp_id, dto, {"modelo_llm": "test/mock", "estado_analisis": "COMPLETADO"})

    def tearDown(self):
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_inspeccionar_expediente(self):
        """Valida que inspeccionar_expediente recupera y renderiza el informe del expediente."""
        raw = self.analista.inspeccionar_expediente(self.memoria, self.exp_id)
        self.assertIsNotNone(raw)
        self.assertEqual(raw["dictamen_recomendacion"], "RECOMENDADA")

    def test_inspeccionar_expediente_inexistente(self):
        """Valida manejo limpio de expedientes no existentes."""
        raw = self.analista.inspeccionar_expediente(self.memoria, "EXP-INEXISTENTE-999")
        self.assertIsNone(raw)

    @patch('urllib.request.urlopen')
    def test_reanalizar_expediente(self, mock_urlopen):
        """Valida el comando de re-análisis individual de licitaciones."""
        mock_resp = MagicMock()
        mock_resp.status = 200
        sample_json = json.dumps({
            "subrogacion": {"detectada": False, "num_trabajadores": None, "convenio_colectivo": None, "desglose_salarial_completo": True, "coste_estimado_anual": None, "riesgo_evaluado": "BAJO"},
            "revision_precios": {"permitida": True, "formula_detectada": "IPC", "art_103_aplica": True, "observaciones": "Reanalizado"},
            "criterios": {"peso_precio_formulas": 70, "peso_juicio_valor": 30, "requiere_memoria_tecnica": False, "criterios_desglose": []},
            "dictamen": {"recomendacion": "RECOMENDADA", "motivos": ["Reanalizado ok"], "ajuste_score": 10, "resumen_ejecutivo": "Reanalizado con éxito"},
            "version_esquema": 1
        })
        mock_resp.read.return_value = json.dumps({"message": {"content": sample_json}}).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        res = self.analista.reanalizar_expediente(self.memoria, self.exp_id)
        self.assertEqual(res["estado_operativo"], "COMPLETADO")
        self.assertEqual(res["recalibracion"]["dictamen_final"], "RECOMENDADA")

if __name__ == "__main__":
    unittest.main()

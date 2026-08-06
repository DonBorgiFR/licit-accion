import os
import sys
import unittest
import tempfile
import shutil


from src.analista import GestorPromptsLCSP

class TestPromptsLCSP(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.yaml_path = os.path.join(self.temp_dir, "prompts_test.yaml")
        with open(self.yaml_path, "w", encoding="utf-8") as f:
            f.write("""
version: "1.2.0"
sistema_base: "Eres un analista experto en LCSP."
ejemplos_few_shot:
  - entrada: "Pliego con subrogacion"
    salida: '{"subrogacion":{"detectada":true}}'
""")
        self.gestor = GestorPromptsLCSP(yaml_path=self.yaml_path)

    def tearDown(self):
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_carga_yaml_prompts(self):
        """Valida que GestorPromptsLCSP lee correctamente la versión y plantillas YAML."""
        self.assertEqual(self.gestor.version, "1.2.0")
        self.assertIn("analista experto en LCSP", self.gestor.sistema_base)
        self.assertEqual(len(self.gestor.ejemplos_few_shot), 1)

    def test_construir_prompt_bilingue(self):
        """Verifica la construcción del prompt del sistema y del usuario en Castellano y Catalán."""
        sys_p, usr_p, ver = self.gestor.construir_prompt("Texto fragmento...", idioma="ca", expediente_id="EXP-CAT-01")
        self.assertEqual(ver, "1.2.0")
        self.assertIn("EJEMPLOS DE REFERENCIA (FEW-SHOT)", sys_p)
        self.assertIn("Idioma detectado: CA", usr_p)
        self.assertIn("EXP-CAT-01", usr_p)

    def test_fallback_prompts_inexistente(self):
        """Si el YAML no existe, conmuta defensivamente al prompt fallback integrado en Python."""
        gestor_fallback = GestorPromptsLCSP(yaml_path=os.path.join(self.temp_dir, "no_existe.yaml"))
        self.assertEqual(gestor_fallback.version, "1.0.0")
        self.assertIn("contratación pública", gestor_fallback.sistema_base)
        
        hc = gestor_fallback.healthcheck_prompts()
        self.assertEqual(hc["status"], "DEGRADADO_FALLBACK")

    def test_healthcheck_prompts(self):
        """Audita el informe de autodiagnóstico del gestor de prompts."""
        hc = self.gestor.healthcheck_prompts()
        self.assertEqual(hc["status"], "OK")
        self.assertTrue(hc["existe"])
        self.assertEqual(hc["num_ejemplos_few_shot"], 1)

if __name__ == "__main__":
    unittest.main()

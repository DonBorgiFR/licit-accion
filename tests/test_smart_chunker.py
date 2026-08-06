import os
import sys
import unittest


from src.analista import SmartLCSPChunker

class TestSmartLCSPChunker(unittest.TestCase):

    def setUp(self):
        self.chunker = SmartLCSPChunker(config_chunker={
            "tamano_ventana_caracteres": 300,
            "max_caracteres_prompt": 15000,
            "min_caracteres_sin_segmentar": 1000
        })

    def test_texto_corto_directo(self):
        """Un texto menor al umbral mínimo se entrega íntegro sin segmentar."""
        texto_corto = "Pliego de cláusulas administrativas para servicio de limpieza. PBL: 50.000 EUR."
        res = self.chunker.segmentar_pliego(texto_corto)
        self.assertEqual(res["estado_segmentacion"], "TEXTO_CORTO_DIRECTO")
        self.assertEqual(res["texto_ensamblado"], texto_corto)

    def test_segmentacion_subrogacion_y_revision(self):
        """Valida que el chunker aísla las cláusulas de subrogación y revisión de precios en un pliego extenso."""
        padding = "Texto administrativo irrelevante de relleno. " * 300  # ~13.000 chars
        texto_pliego = (
            "INICIO DEL PLIEGO DE PRESCRIPCIONES TÉCNICAS.\n" +
            padding[:4000] +
            "\nCLÁUSULA 15. OBLIGACIÓN DE SUBROGACIÓN DE PERSONAL.\n"
            "De acuerdo con el artículo 130 de la Ley de Contratos del Sector Público (LCSP), "
            "el contratista adjudicatario estará obligado a subrogarse en los contratos de trabajo de los 12 empleados de la plantilla actual.\n" +
            padding[4000:9000] +
            "\nCLÁUSULA 28. REVISIÓN DE PRECIOS E INFLACIÓN.\n"
            "En virtud del artículo 103 de la LCSP, se establece la fórmula de revisión de precios basada en el IPC acumulado.\n" +
            padding[9000:]
        )

        res = self.chunker.segmentar_pliego(texto_pliego, expediente_id="EXP-CHUNK-01")

        self.assertEqual(res["estado_segmentacion"], "SEGMENTACION_OK")
        self.assertIn("artículo 130", res["texto_ensamblado"])
        self.assertIn("artículo 103", res["texto_ensamblado"])
        self.assertGreater(res["metricas"]["ratio_compresion_porcentaje"], 50.0)

    def test_segmentacion_bilingue_catalan(self):
        """Verifica la detección de cláusulas contractuales en catalán."""
        padding = "Text administratiu general sense clausules d'interes. " * 100
        texto_catalan = (
            "DOCUMENT D'ESPECIFICACIONS TÈCNIQUES.\n" +
            padding[:2000] +
            "\nCLÀUSULA 10. SUBROGACIÓ DE PERSONAL.\n"
            "De conformitat amb la normativa vigent, l'empresa adjudicatària haurà d'assumir la subrogació del personal afectat.\n" +
            padding[2000:]
        )

        res = self.chunker.segmentar_pliego(texto_catalan)
        self.assertEqual(res["estado_segmentacion"], "SEGMENTACION_OK")
        self.assertIn("SUBROGACIÓ DE PERSONAL", res["texto_ensamblado"])

    def test_fusion_intervalos_superpuestos(self):
        """Valida que dos términos cercanos combinan sus ventanas sin duplicar texto."""
        intervalos = [(100, 500), (400, 800), (1200, 1500)]
        fusionados = SmartLCSPChunker._fusionar_intervalos(intervalos)
        self.assertEqual(len(fusionados), 2)
        self.assertEqual(fusionados[0], (100, 800))
        self.assertEqual(fusionados[1], (1200, 1500))

    def test_fallback_sin_coincidencias(self):
        """Si un pliego extenso no tiene términos clave regex, entra en fallback de truncado plano."""
        texto_sin_keywords = "Texto sin ninguna palabra clave relevante. " * 200  # ~8.600 chars
        res = self.chunker.segmentar_pliego(texto_sin_keywords)
        self.assertEqual(res["estado_segmentacion"], "SEGMENTACION_FALLBACK")
        self.assertIn("[AVISO: Sin coincidencia explícita de cláusulas LCSP", res["texto_ensamblado"])

if __name__ == "__main__":
    unittest.main()

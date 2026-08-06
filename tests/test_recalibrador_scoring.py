import os
import sys
import unittest


from src.analista import (
    RecalibradorScoring, AnalisisSemanticoDTO, SubrogacionDTO,
    RevisionPreciosDTO, CriteriosAdjudicacionDTO, DictamenIA
)

class TestRecalibradorScoring(unittest.TestCase):

    def setUp(self):
        self.recalibrador = RecalibradorScoring(config_recalibracion={
            "umbral_recomendada": 65.0,
            "umbral_descartada": 40.0,
            "ajustes": {
                "subrogacion_critica": -25,
                "subrogacion_alta": -15,
                "subrogacion_baja_o_nula": 5,
                "revision_precios_ok": 10,
                "sin_revision_plurianual": -10,
                "precio_dominante": -10
            }
        })

    def test_recalibracion_bonificacion_alta(self):
        """Un pliego limpio sin subrogación y con fórmula de revisión obtiene bonificación y dictamen RECOMENDADA."""
        dto = AnalisisSemanticoDTO(
            subrogacion=SubrogacionDTO(detectada=False, riesgo_evaluado="BAJO"),
            revision_precios=RevisionPreciosDTO(permitida=True, formula_detectada="Formula polinómica IPC"),
            criterios=CriteriosAdjudicacionDTO(peso_precio_formulas=70, peso_juicio_valor=30),
            dictamen=DictamenIA(recomendacion="RECOMENDADA", ajuste_score=0)
        )

        res = self.recalibrador.recalibrar(score_cuantitativo=60.0, dto=dto, expediente_id="EXP-REC-01")

        # Score original: 60. +5 (sin subrogación) +10 (revisión) -10 (precio >60%) = 65.0.
        self.assertEqual(res["score_recalibrado"], 65.0)
        self.assertEqual(res["dictamen_final"], "RECOMENDADA")
        self.assertFalse(res["veto_activado"])

    def test_veto_subrogacion_critica(self):
        """Subrogación de personal con riesgo CRÍTICO activa veto y dictamen DESCARTADA_POR_RIESGO."""
        dto = AnalisisSemanticoDTO(
            subrogacion=SubrogacionDTO(detectada=True, num_trabajadores=30, riesgo_evaluado="CRITICO"),
            revision_precios=RevisionPreciosDTO(permitida=False),
            criterios=CriteriosAdjudicacionDTO(peso_precio_formulas=50, peso_juicio_valor=50),
            dictamen=DictamenIA(recomendacion="REVISAR_RIESGO", ajuste_score=0)
        )

        res = self.recalibrador.recalibrar(score_cuantitativo=75.0, dto=dto, expediente_id="EXP-VETO-01")

        self.assertTrue(res["veto_activado"])
        self.assertEqual(res["dictamen_final"], "DESCARTADA_POR_RIESGO")
        self.assertEqual(res["score_recalibrado"], 50.0)

    def test_penalizacion_sin_revision_plurianual(self):
        """Contrato de 36 meses sin revisión de precios recibe penalización."""
        dto = AnalisisSemanticoDTO(
            subrogacion=SubrogacionDTO(detectada=False, riesgo_evaluado="BAJO"),
            revision_precios=RevisionPreciosDTO(permitida=False),
            criterios=CriteriosAdjudicacionDTO(peso_precio_formulas=50, peso_juicio_valor=50),
            dictamen=DictamenIA(recomendacion="REVISAR_RIESGO", ajuste_score=0)
        )

        res = self.recalibrador.recalibrar(score_cuantitativo=60.0, dto=dto, duracion_meses=36)

        # Score original 60 + 5 (sin subrogacion) - 10 (sin revision plurianual) = 55.0
        self.assertEqual(res["score_recalibrado"], 55.0)
        self.assertIn("contrato plurianual", " ".join(res["motivos_recalibracion"]))

    def test_modo_degradado_indemne(self):
        """Si el DTO está en modo DEGRADADO, el score cuantitativo se conserva intacto sin ajustes."""
        dto = AnalisisSemanticoDTO(
            subrogacion=SubrogacionDTO(),
            revision_precios=RevisionPreciosDTO(),
            criterios=CriteriosAdjudicacionDTO(),
            dictamen=DictamenIA(resumen_ejecutivo="Análisis IA degradado por fallo LLM")
        )

        res = self.recalibrador.recalibrar(score_cuantitativo=62.5, dto=dto)

        self.assertEqual(res["score_recalibrado"], 62.5)
        self.assertEqual(res["ajuste_semantico"], 0)
        self.assertEqual(res["dictamen_final"], "REVISAR_RIESGO")

    def test_acotacion_rango_score(self):
        """El score recalibrado se acota estrictamente dentro del intervalo [0.0, 100.0]."""
        dto_alto = AnalisisSemanticoDTO(
            subrogacion=SubrogacionDTO(detectada=False, riesgo_evaluado="BAJO"),
            revision_precios=RevisionPreciosDTO(permitida=True, formula_detectada="IPC"),
            criterios=CriteriosAdjudicacionDTO(peso_precio_formulas=80, peso_juicio_valor=20),
            dictamen=DictamenIA(recomendacion="RECOMENDADA", ajuste_score=15)
        )

        res = self.recalibrador.recalibrar(score_cuantitativo=95.0, dto=dto_alto)
        self.assertEqual(res["score_recalibrado"], 100.0)

    def test_ajuste_propuesto_por_llm_no_duplica_scoring(self):
        """El LLM explica riesgos, pero no modifica una puntuación comercial determinista."""
        dto = AnalisisSemanticoDTO(
            subrogacion=SubrogacionDTO(detectada=True, riesgo_evaluado="CRITICO"),
            revision_precios=RevisionPreciosDTO(permitida=False),
            criterios=CriteriosAdjudicacionDTO(),
            dictamen=DictamenIA(recomendacion="DESCARTADA_POR_RIESGO", ajuste_score=-25),
        )
        res = self.recalibrador.recalibrar(score_cuantitativo=70, dto=dto)
        self.assertEqual(res["ajuste_semantico"], -25)
        self.assertIn("no aplicado", " ".join(res["motivos_recalibracion"]))

if __name__ == "__main__":
    unittest.main()

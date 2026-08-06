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
                "subrogacion_baja_documentada": 2,
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

    def test_subrogacion_acotada_y_documentada_recibe_bonificacion_intermedia(self):
        """
        Criterio de negocio validado el 2026-08-06: una subrogación de 1 a 5 personas CON el
        desglose del Art. 130.1 es un riesgo acotado y presupuestable. Debe puntuar por encima
        del tramo MEDIO (0 pts) y por debajo de no tener subrogación ninguna (+5 pts).
        """
        def dto_con(riesgo, detectada):
            return AnalisisSemanticoDTO(
                subrogacion=SubrogacionDTO(detectada=detectada, riesgo_evaluado=riesgo),
                revision_precios=RevisionPreciosDTO(permitida=False),
                criterios=CriteriosAdjudicacionDTO(peso_precio_formulas=50, peso_juicio_valor=50),
                dictamen=DictamenIA(recomendacion="REVISAR_RIESGO", ajuste_score=0),
            )

        sin_subrogacion = self.recalibrador.recalibrar(60.0, dto_con("BAJO", False))["score_recalibrado"]
        baja_documentada = self.recalibrador.recalibrar(60.0, dto_con("BAJO", True))["score_recalibrado"]
        tramo_medio = self.recalibrador.recalibrar(60.0, dto_con("MEDIO", True))["score_recalibrado"]

        self.assertEqual(sin_subrogacion, 65.0)
        self.assertEqual(baja_documentada, 62.0)
        self.assertEqual(tramo_medio, 60.0)
        self.assertLess(baja_documentada, sin_subrogacion)
        self.assertGreater(baja_documentada, tramo_medio)

    def test_falta_de_desglose_penaliza_pero_no_veta(self):
        """
        Criterio de negocio validado el 2026-08-06: la ausencia de la relación de personal del
        Art. 130.1 eleva el riesgo a ALTO pero NO descarta, porque el desglose suele obtenerse
        solicitándolo al órgano de contratación. Antes era CRÍTICO y descartaba automáticamente,
        dejando fuera concursos ganables.
        """
        dto = AnalisisSemanticoDTO(
            subrogacion=SubrogacionDTO(
                detectada=True, num_trabajadores=6,
                desglose_salarial_completo=False, riesgo_evaluado="ALTO"
            ),
            revision_precios=RevisionPreciosDTO(permitida=False),
            criterios=CriteriosAdjudicacionDTO(peso_precio_formulas=50, peso_juicio_valor=50),
            dictamen=DictamenIA(recomendacion="REVISAR_RIESGO", ajuste_score=0),
        )

        res = self.recalibrador.recalibrar(score_cuantitativo=75.0, dto=dto)

        self.assertFalse(res["veto_activado"])
        self.assertNotEqual(res["dictamen_final"], "DESCARTADA_POR_RIESGO")
        self.assertEqual(res["score_recalibrado"], 60.0)


class TestMatrizSubrogacionConfigurada(unittest.TestCase):
    """
    La matriz de riesgo es política comercial, no un detalle de implementación: vive en
    config/prompts_lcsp.yaml y la lee el modelo. Estas comprobaciones impiden que se revierta
    en silencio al editar el YAML.
    """

    def setUp(self):
        import re
        from src import ruta_proyecto
        with open(ruta_proyecto("config/prompts_lcsp.yaml"), encoding="utf-8") as f:
            self.texto = f.read()
        # Cada regla se declara como "  a) BAJO  -> ...". Se extrae el nivel y su enunciado,
        # que abarca hasta la siguiente regla.
        marcas = list(re.finditer(r"^\s+([a-g])\)\s+(BAJO|MEDIO|ALTO|CRÍTICO)\s+->", self.texto, re.M))
        self.reglas = {}
        for i, m in enumerate(marcas):
            fin = marcas[i + 1].start() if i + 1 < len(marcas) else m.end() + 600
            self.reglas[m.group(1)] = (m.group(2), self.texto[m.start():fin])

    def test_la_matriz_declara_las_siete_reglas_con_su_nivel_vigente(self):
        """
        Antes: c) era CRÍTICO por tamaño y b) CRÍTICO por falta de desglose. Ahora sólo el
        tamaño veta. Si alguien revierte el YAML, este mapeo deja de cuadrar.
        """
        niveles = {letra: nivel for letra, (nivel, _) in self.reglas.items()}
        self.assertEqual(niveles, {
            "a": "BAJO", "b": "CRÍTICO", "c": "ALTO", "d": "ALTO",
            "e": "ALTO", "f": "MEDIO", "g": "BAJO",
        })

    def test_el_unico_veto_es_el_del_tamano_de_plantilla(self):
        criticas = [letra for letra, (nivel, _) in self.reglas.items() if nivel == "CRÍTICO"]
        self.assertEqual(criticas, ["b"], "Sólo debe existir una regla CRÍTICA, y ha de evaluarse antes que las de riesgo ALTO")
        self.assertIn("num_trabajadores > 40", self.reglas["b"][1])

    def test_la_falta_de_desglose_es_alto_y_no_descarta(self):
        nivel, enunciado = self.reglas["c"]
        self.assertEqual(nivel, "ALTO")
        self.assertIn("Art. 130.1", enunciado)
        self.assertIn("órgano de contratación", enunciado)

    def test_el_ejemplo_few_shot_ensena_la_regla_vigente(self):
        """Un ejemplo desalineado con la matriz enseña al modelo la regla equivocada."""
        self.assertNotIn('"desglose_salarial_completo":false,"coste_estimado_anual":null,"riesgo_evaluado":"CRITICO"', self.texto)


if __name__ == "__main__":
    unittest.main()

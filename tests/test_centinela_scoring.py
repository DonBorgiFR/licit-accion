"""
tests/test_centinela_scoring.py — Pruebas Unitarias del Evaluador de Scoring y Priorización (Capa 6 - Paso 6)
Ecosistema Automático de Licitaciones (bfr_incoop)
"""

import pytest
from src.centinela import (
    AlertaBoletinDTO,
    DictamenCentinelaDTO,
    EvaluadorScoringCentinela,
    CentinelaScoringError
)

def crear_alerta_con_score(score_base: int = 40, dictamen: DictamenCentinelaDTO = None) -> AlertaBoletinDTO:
    return AlertaBoletinDTO(
        fuente="DOGC",
        num_boletin="123",
        fecha_publicacion="2026-07-26T08:00:00Z",
        organo_emisor="Ajuntament Test",
        municipio="Barcelona",
        titulo_anuncio="Aprovació inicial del pressupost 2027",
        seccion_boletin="Anuncis",
        url_anuncio="https://example.com/123",
        texto_sumario="Aprobación inicial",
        score_temprano=score_base,
        motivos_score=["REGLA: Presupuestos (+40 pts)"],
        dictamen_ia=dictamen,
        estado_operativo="NUEVA_FASE_TEMPRANA"
    )


def test_evaluar_alerta_bonificacion_alta():
    """Verifica bonificación +30 pts por dictamen IA de Interés ALTO."""
    dictamen_alto = DictamenCentinelaDTO(
        es_oportunidad_temprana=True,
        nivel_interes="ALTO",
        categoria_fase_temprana="PRESUPUESTO",
        resumen_ejecutivo="Oportunidad prioritaria",
        acciones_recomendadas=["Preparar oferta"]
    )
    evaluador = EvaluadorScoringCentinela()
    alerta = crear_alerta_con_score(score_base=40, dictamen=dictamen_alto)

    alerta_evaluada = evaluador.evaluar_alerta(alerta)

    assert alerta_evaluada.score_temprano == 70  # 40 + 30
    assert alerta_evaluada.estado_operativo == "NUEVA_FASE_TEMPRANA"
    assert any("Interés ALTO" in m for m in alerta_evaluada.motivos_score)


def test_evaluar_alerta_penalizacion_nulo():
    """Verifica penalización -30 pts por dictamen IA de Interés NULO que provoca descarte."""
    dictamen_nulo = DictamenCentinelaDTO(
        es_oportunidad_temprana=False,
        nivel_interes="NULO",
        categoria_fase_temprana="OTROS",
        resumen_ejecutivo="No relevante para el sector social",
        acciones_recomendadas=[]
    )
    evaluador = EvaluadorScoringCentinela()
    alerta = crear_alerta_con_score(score_base=40, dictamen=dictamen_nulo)

    alerta_evaluada = evaluador.evaluar_alerta(alerta)

    assert alerta_evaluada.score_temprano == 10  # 40 - 30
    assert alerta_evaluada.estado_operativo == "DESCARTADA_POR_REGLAS"
    assert any("Interés NULO" in m for m in alerta_evaluada.motivos_score)


def test_evaluar_alerta_modo_diferido_resiliente():
    """Verifica que alertas en modo diferido (sin LLM) conservan su score de reglas duras."""
    evaluador = EvaluadorScoringCentinela()
    alerta = crear_alerta_con_score(score_base=50, dictamen=None)
    alerta.estado_operativo = "ANALISIS_DIFERIDO_BOLETIN"

    alerta_evaluada = evaluador.evaluar_alerta(alerta)

    assert alerta_evaluada.score_temprano == 50
    assert alerta_evaluada.estado_operativo == "ANALISIS_DIFERIDO_BOLETIN"


def test_evaluar_lote_centinela():
    """Verifica la evaluación en lote y generación de métricas."""
    dictamen_alto = DictamenCentinelaDTO(es_oportunidad_temprana=True, nivel_interes="ALTO", categoria_fase_temprana="PRESUPUESTO", resumen_ejecutivo="OK")
    dictamen_nulo = DictamenCentinelaDTO(es_oportunidad_temprana=False, nivel_interes="NULO", categoria_fase_temprana="OTROS", resumen_ejecutivo="KO")

    evaluador = EvaluadorScoringCentinela()
    lote = [
        crear_alerta_con_score(40, dictamen_alto),  # Final 70 (Alta Prio)
        crear_alerta_con_score(40, dictamen_nulo)   # Final 10 (Descartada)
    ]

    evaluadas, metricas = evaluador.evaluar_lote(lote)

    assert len(evaluadas) == 2
    assert metricas["total_evaluadas"] == 2
    assert metricas["alta_prioridad"] == 1
    assert metricas["descartadas"] == 1


def test_healthcheck_scoring_centinela():
    """Verifica el autodiagnóstico del evaluador de scoring."""
    evaluador = EvaluadorScoringCentinela()
    hc = evaluador.healthcheck_scoring_centinela()

    assert hc["status"] == "OK"
    assert hc["score_prioridad_alta"] == 70
    assert hc["score_minimo_alerta"] == 30


def test_dictamen_degradado_no_altera_el_score():
    """
    Regresión del contrato de Modo Degradado (Bloque 2, regla 4): un análisis que no
    llegó a producirse no puede mover la puntuación en ninguna dirección.

    Antes, el fallback declaraba nivel_interes="MEDIO" y el evaluador lo bonificaba con
    +15 pts: una alerta que la IA nunca leyó subía de prioridad. Y si el parseo fallaba,
    el dictamen se rellenaba con "NULO" y restaba 30 pts, haciéndola desaparecer.
    """
    evaluador = EvaluadorScoringCentinela()

    dictamen_degradado = DictamenCentinelaDTO(
        es_oportunidad_temprana=True,
        nivel_interes="DESCONOCIDO",
        categoria_fase_temprana="OTROS",
        resumen_ejecutivo="Modo Degradado: sin proveedor LLM disponible.",
        modo_degradado=True
    )

    sin_dictamen = evaluador.evaluar_alerta(crear_alerta_con_score(40, dictamen=None))
    degradada = evaluador.evaluar_alerta(crear_alerta_con_score(40, dictamen=dictamen_degradado))

    assert degradada.score_temprano == sin_dictamen.score_temprano
    assert any("Modo Degradado" in m for m in degradada.motivos_score)


def test_alerta_degradada_sigue_llegando_al_cockpit():
    """
    La alerta cuyo análisis falló conserva su score de reglas duras y NO se descarta:
    debe llegar al Cockpit marcada, no desaparecer en silencio (Convención C3).
    """
    evaluador = EvaluadorScoringCentinela()

    dictamen_degradado = DictamenCentinelaDTO(
        es_oportunidad_temprana=True,
        nivel_interes="DESCONOCIDO",
        categoria_fase_temprana="OTROS",
        resumen_ejecutivo="Modo Degradado: error del proveedor.",
        modo_degradado=True
    )

    alerta = crear_alerta_con_score(40, dictamen=dictamen_degradado)
    alerta.estado_operativo = "ANALISIS_DIFERIDO_BOLETIN"
    resultado = evaluador.evaluar_alerta(alerta)

    assert resultado.estado_operativo != "DESCARTADA_POR_REGLAS"
    assert resultado.dictamen_ia.modo_degradado is True

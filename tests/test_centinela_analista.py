"""
tests/test_centinela_analista.py — Pruebas Unitarias del Analista IA de Boletines (Capa 6 - Paso 5)
Ecosistema Automático de Licitaciones (bfr_incoop)
"""

from unittest.mock import MagicMock
import pytest
from src.centinela import (
    AlertaBoletinDTO,
    DictamenCentinelaDTO,
    AnalistaBoletinesIA
)

def crear_alerta_fase_temprana() -> AlertaBoletinDTO:
    return AlertaBoletinDTO(
        fuente="DOGC",
        num_boletin="SUMARI-123",
        fecha_publicacion="2026-07-26T08:00:00Z",
        organo_emisor="Departament d'Educació",
        municipio="Catalunya",
        titulo_anuncio="Pla estratègic de subvencions per a casals d'estiu 2027",
        seccion_boletin="Subvencions",
        url_anuncio="https://dogc.gencat.cat/doc/123",
        texto_sumario="Subvencions per a entitats sense ànim de lucre per a la gestió de lleure infantil.",
        score_temprano=40,
        motivos_score=["REGLA: Coincidencia en Subvenciones (+40 pts)"],
        estado_operativo="NUEVA_FASE_TEMPRANA"
    )


def test_construir_prompt_analisis():
    """Verifica que la plantilla del prompt se genera correctamente."""
    analista = AnalistaBoletinesIA(proveedor_llm=MagicMock())
    alerta = crear_alerta_fase_temprana()

    prompt = analista.construir_prompt_analisis(alerta)
    assert "DOGC" in prompt
    assert "Departament d'Educació" in prompt
    assert "Pla estratègic de subvencions" in prompt


def test_analizar_alerta_exito_mock_llm():
    """Verifica el análisis semántico exitoso convirtiendo JSON del LLM en DictamenCentinelaDTO."""
    mock_llm = MagicMock()
    json_resp = """
    ```json
    {
      "es_oportunidad_temprana": true,
      "nivel_interes": "ALTO",
      "categoria_fase_temprana": "SUBVENCION",
      "resumen_ejecutivo": "Oportunidad estratégica de subvención para proyectos educativos de infancia.",
      "acciones_recomendadas": ["Preparar propuesta metodológica", "Contactar entidades locales"],
      "estimacion_meses_hasta_licitacion": 4
    }
    ```
    """
    mock_llm.consultar.return_value = {"raw_response": json_resp, "modelo": "mock-llm"}

    analista = AnalistaBoletinesIA(proveedor_llm=mock_llm)
    alerta = crear_alerta_fase_temprana()

    alerta_analizada = analista.analizar_alerta(alerta)

    assert alerta_analizada.estado_operativo == "ANALIZADA_IA"
    assert alerta_analizada.dictamen_ia is not None
    assert alerta_analizada.dictamen_ia.es_oportunidad_temprana is True
    assert alerta_analizada.dictamen_ia.nivel_interes == "ALTO"
    assert alerta_analizada.dictamen_ia.categoria_fase_temprana == "SUBVENCION"
    assert alerta_analizada.dictamen_ia.estimacion_meses_hasta_licitacion == 4


def test_analizar_alerta_modo_degradado_sin_llm():
    """Verifica la degradación ordenada (ANALISIS_DIFERIDO_BOLETIN) cuando no hay modelo LLM disponible."""
    # `autoinicializar_proveedor=False` es la única forma de expresar "sin LLM" desde
    # que la factoría funciona: pasar proveedor_llm=None construiría un proveedor real.
    analista = AnalistaBoletinesIA(proveedor_llm=None, autoinicializar_proveedor=False)
    alerta = crear_alerta_fase_temprana()

    alerta_degradada = analista.analizar_alerta(alerta)

    assert alerta_degradada.estado_operativo == "ANALISIS_DIFERIDO_BOLETIN"
    assert alerta_degradada.dictamen_ia is not None
    # El dictamen degradado no finge un veredicto: ni "MEDIO" (que bonificaba +15 pts)
    # ni "NULO" (que penalizaba -30 pts).
    assert alerta_degradada.dictamen_ia.nivel_interes == "DESCONOCIDO"
    assert alerta_degradada.dictamen_ia.modo_degradado is True
    assert "Modo Degradado" in alerta_degradada.dictamen_ia.resumen_ejecutivo


def test_analizar_alerta_modo_degradado_error_json():
    """Verifica que un fallo de sintaxis en la respuesta del LLM degrada ordenadamente la alerta sin lanzar excepción."""
    mock_llm = MagicMock()
    mock_llm.consultar.return_value = {"raw_response": "No soy capaz de procesar este anuncio en JSON.", "modelo": "mock-llm"}

    analista = AnalistaBoletinesIA(proveedor_llm=mock_llm)
    alerta = crear_alerta_fase_temprana()

    alerta_degradada = analista.analizar_alerta(alerta)

    assert alerta_degradada.estado_operativo == "ANALISIS_DIFERIDO_BOLETIN"
    assert alerta_degradada.dictamen_ia is not None
    assert alerta_degradada.dictamen_ia.nivel_interes == "DESCONOCIDO"
    assert alerta_degradada.dictamen_ia.modo_degradado is True


def test_respuesta_llm_incompleta_no_se_acepta_como_dictamen():
    """
    Regresión del defecto de fondo: una respuesta que es JSON válido pero está vacía o
    incompleta se aceptaba y los huecos se rellenaban con nivel_interes="NULO". El
    evaluador restaba entonces 30 pts y descartaba la alerta, sin que nada distinguiera
    ese descarte de un veredicto real de la IA.
    """
    mock_llm = MagicMock()
    mock_llm.consultar.return_value = {"raw_response": "{}", "modelo": "mock-llm"}

    analista = AnalistaBoletinesIA(proveedor_llm=mock_llm)
    alerta_degradada = analista.analizar_alerta(crear_alerta_fase_temprana())

    assert alerta_degradada.estado_operativo == "ANALISIS_DIFERIDO_BOLETIN"
    assert alerta_degradada.dictamen_ia.modo_degradado is True
    assert alerta_degradada.dictamen_ia.nivel_interes == "DESCONOCIDO"

    # Y el DTO rechaza esa forma directamente, no sólo a través del analista.
    with pytest.raises(Exception):
        DictamenCentinelaDTO.from_json("{}", estricto=True)


def test_analizar_lote_alertas():
    """Verifica el procesamiento en lote con el Analista IA."""
    mock_llm = MagicMock()
    json_resp = '{"es_oportunidad_temprana": true, "nivel_interes": "ALTO", "categoria_fase_temprana": "PRESUPUESTO", "resumen_ejecutivo": "OK", "acciones_recomendadas": [], "estimacion_meses_hasta_licitacion": 3}'
    mock_llm.consultar.return_value = {"raw_response": json_resp, "modelo": "mock-llm"}

    analista = AnalistaBoletinesIA(proveedor_llm=mock_llm)
    lote = [crear_alerta_fase_temprana(), crear_alerta_fase_temprana()]

    resultado = analista.analizar_lote_alertas(lote)

    assert len(resultado) == 2
    assert all(a.estado_operativo == "ANALIZADA_IA" for a in resultado)




def test_healthcheck_analista_centinela():
    """Verifica el informe de autodiagnóstico del Analista IA."""
    analista = AnalistaBoletinesIA(proveedor_llm=MagicMock())
    hc = analista.healthcheck_analista_centinela()

    assert hc["status"] == "OK"
    assert hc["proveedor_llm_disponible"] is True

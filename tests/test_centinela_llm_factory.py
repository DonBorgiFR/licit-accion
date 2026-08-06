"""
tests/test_centinela_llm_factory.py — Prueba de la factoría LLM real del Centinela (Convención C4)
Ecosistema Automático de Licitaciones (bfr_incoop)
"""

import pytest
from src.centinela import AnalistaBoletinesIA, AlertaBoletinDTO, DictamenCentinelaDTO
from src.analista import LLMProvider, GeminiProvider, proveedor_llm_factory

def test_proveedor_llm_factory_instanciacion():
    """
    Verifica que proveedor_llm_factory() devuelva una instancia válida de LLMProvider
    según la configuración activa (sin inyección).
    """
    provider = proveedor_llm_factory("config/analista_config.yaml")
    assert provider is not None
    assert isinstance(provider, LLMProvider)
    assert isinstance(provider, GeminiProvider)
    assert provider.modelo == "gemini-3.1-flash-lite"

def test_analista_boletines_ia_inicializacion_sin_inyeccion():
    """
    Verifica que AnalistaBoletinesIA() instancie correctamente su proveedor LLM real
    sin requerir la inyección manual de proveedor_llm (Convención C4).
    """
    analista = AnalistaBoletinesIA()
    assert analista.proveedor_llm is not None
    assert isinstance(analista.proveedor_llm, LLMProvider)

def test_analista_boletines_ia_analizar_alerta_mock_provider():
    """
    Verifica el correcto parseo del DictamenCentinelaDTO cuando el proveedor responde estructuradamente.
    """
    class MockProvider(LLMProvider):
        def consultar(self, prompt_sistema: str, prompt_usuario: str, timeout: int = 60):
            return {
                "raw_response": '{"es_oportunidad_temprana": true, "nivel_interes": "ALTO", "categoria_fase_temprana": "PRESUPUESTO", "resumen_ejecutivo": "Oportunidad presupuestaria en educación", "acciones_recomendadas": ["Revisar borrador"], "estimacion_meses_hasta_licitacion": 4}',
                "modelo": "mock-test",
                "prompt_tokens": 100,
                "completion_tokens": 50,
                "tiempo_seg": 0.1
            }

    analista = AnalistaBoletinesIA(proveedor_llm=MockProvider())
    alerta = AlertaBoletinDTO(
        fuente="DOGC",
        num_boletin="123",
        fecha_publicacion="2026-07-27T08:00:00Z",
        organo_emisor="Ajuntament de Terrassa",
        municipio="Terrassa",
        titulo_anuncio="Presupuesto municipal para casals d'estiu",
        seccion_boletin="Anuncios",
        url_anuncio="https://dogc.cat/123",
        texto_sumario="Servicios educativos"
    )

    alerta_analizada = analista.analizar_alerta(alerta)

    assert alerta_analizada.estado_operativo == "ANALIZADA_IA"
    assert alerta_analizada.dictamen_ia is not None
    assert alerta_analizada.dictamen_ia.es_oportunidad_temprana is True
    assert alerta_analizada.dictamen_ia.nivel_interes == "ALTO"
    assert alerta_analizada.dictamen_ia.categoria_fase_temprana == "PRESUPUESTO"
    assert alerta_analizada.dictamen_ia.estimacion_meses_hasta_licitacion == 4

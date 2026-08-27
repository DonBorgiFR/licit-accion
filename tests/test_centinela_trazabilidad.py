"""
tests/test_centinela_trazabilidad.py — Pruebas Unitarias de Trazabilidad JSONL y Resiliencia (Capa 6 - Paso 7)
Ecosistema Automático de Licitaciones (bfr_incoop)
"""

import os
import json
import pytest
from src.centinela import (
    GestorTrazabilidadCentinela,
    ejecutar_pipeline_centinela_resiliente,
    IngestorBoletines,
    FiltroBoletinesReglas,
    AnalistaBoletinesIA,
    EvaluadorScoringCentinela,
    AlertaBoletinDTO
)

def test_registrar_evento_jsonl(tmp_path):
    """Verifica que GestorTrazabilidadCentinela escribe eventos estructurados en JSONL."""
    log_file = os.path.join(str(tmp_path), "test_pipeline.jsonl")
    gestor = GestorTrazabilidadCentinela(log_path=log_file)

    gestor.registrar_evento("test_event", {"param": 123}, estado="INFO")

    # Igual que en la Capa 7: se comprueba por el lector canónico del Paso 9 de la Capa 10.
    from src.rastro import EstadoEvento, Gramatica, leer_rastro

    assert os.path.exists(log_file)
    resultado = leer_rastro(ruta=log_file)
    assert resultado.lineas_totales == 1
    evento = resultado.eventos[0]
    assert evento.gramatica is Gramatica.CANONICA
    assert evento.componente == "centinela"
    assert evento.evento == "test_event"
    assert evento.estado is EstadoEvento.INFO
    assert evento.datos["param"] == 123
    assert evento.instante is not None


def test_healthcheck_trazabilidad_centinela(tmp_path):
    """Verifica el autodiagnóstico del gestor de trazabilidad (Regla 6)."""
    log_file = os.path.join(str(tmp_path), "health_test.jsonl")
    gestor = GestorTrazabilidadCentinela(log_path=log_file)

    hc = gestor.healthcheck_trazabilidad_centinela()

    assert hc["status"] == "OK"
    assert hc["permiso_escritura"] is True


def test_ejecutar_pipeline_centinela_resiliente_exito(tmp_path, monkeypatch):
    """Verifica la orquestación resiliente del pipeline con trazabilidad."""
    db_file = os.path.join(str(tmp_path), "licitaciones_test.db")
    
    # Mock Ingestor con 1 alerta
    alerta_mock = AlertaBoletinDTO(
        fuente="DOGC",
        num_boletin="999",
        fecha_publicacion="2026-07-26T08:00:00Z",
        organo_emisor="Ajuntament Test",
        municipio="Barcelona",
        titulo_anuncio="Aprovació inicial del pressupost 2027",
        seccion_boletin="Anuncis",
        url_anuncio="https://example.com/999",
        texto_sumario="Presupuestos"
    )

    class MockIngestor(IngestorBoletines):
        def ejecutar_ingesta_completa(self):
            return [alerta_mock]

    ingestor = MockIngestor()
    filtro = FiltroBoletinesReglas()
    # Sin proveedor real: la suite no debe salir a la red (Convención C5).
    analista = AnalistaBoletinesIA(autoinicializar_proveedor=False)
    evaluador = EvaluadorScoringCentinela()

    alertas_res, metricas = ejecutar_pipeline_centinela_resiliente(
        ingestor=ingestor,
        filtro=filtro,
        analista=analista,
        evaluador=evaluador,
        db_path=db_file
    )

    assert len(alertas_res) == 1
    assert metricas["ingresadas"] == 1
    assert metricas["modo_degradado"] is False


def test_ejecutar_pipeline_centinela_resiliente_degradado(tmp_path, monkeypatch):
    """Verifica la degradación ordenada cuando falla la persistencia en base de datos."""
    db_file = os.path.join(str(tmp_path), "invalid_dir/licitaciones_test.db")

    class MockIngestor(IngestorBoletines):
        def ejecutar_ingesta_completa(self):
            return []

    ingestor = MockIngestor()
    filtro = FiltroBoletinesReglas()
    # Sin proveedor real: la suite no debe salir a la red (Convención C5).
    analista = AnalistaBoletinesIA(autoinicializar_proveedor=False)
    evaluador = EvaluadorScoringCentinela()

    # Forzar error global en ingestor
    def mock_ingesta_error():
        raise RuntimeError("Fallo simulado de red en ingestor")

    monkeypatch.setattr(ingestor, "ejecutar_ingesta_completa", mock_ingesta_error)

    alertas_res, metricas = ejecutar_pipeline_centinela_resiliente(
        ingestor=ingestor,
        filtro=filtro,
        analista=analista,
        evaluador=evaluador,
        db_path=db_file
    )

    assert len(alertas_res) == 0
    assert metricas["modo_degradado"] is True

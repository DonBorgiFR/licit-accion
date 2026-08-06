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

    assert os.path.exists(log_file)
    with open(log_file, "r", encoding="utf-8") as f:
        lineas = f.readlines()
        assert len(lineas) == 1
        data = json.loads(lineas[0])
        assert data["modulo"] == "centinela"
        assert data["tipo_evento"] == "test_event"
        assert data["estado"] == "INFO"
        assert data["payload"]["param"] == 123
        assert "timestamp" in data


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
    analista = AnalistaBoletinesIA()
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
    analista = AnalistaBoletinesIA()
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

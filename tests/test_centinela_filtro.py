"""
tests/test_centinela_filtro.py — Pruebas Unitarias del Motor de Filtrado por Reglas Duras (Capa 6 - Paso 4)
Ecosistema Automático de Licitaciones (bfr_incoop)
"""

import os
import pytest
from src.centinela import (
    AlertaBoletinDTO,
    FiltroBoletinesReglas,
    CentinelaFilterError
)

def crear_alerta_test(titulo: str, sumario: str = "", fuente: str = "DOGC") -> AlertaBoletinDTO:
    return AlertaBoletinDTO(
        fuente=fuente,
        num_boletin="12345",
        fecha_publicacion="2026-07-26T08:00:00Z",
        organo_emisor="Ajuntament de Prueba",
        municipio="Barcelona",
        titulo_anuncio=titulo,
        seccion_boletin="Anuncis",
        url_anuncio="https://example.com/anuncio/12345",
        texto_sumario=sumario
    )


def test_filtro_veto_palabras_prohibidas():
    """Verifica que palabras de veto como 'multa', 'sanció' o 'licència menor' provocan veto inmediato con score 0."""
    filtro = FiltroBoletinesReglas()
    alerta_vetada = crear_alerta_test("Notificació de multa de tràfic per compareixença")

    aceptada, score, motivos = filtro.evaluar_alerta(alerta_vetada)

    assert aceptada is False
    assert score == 0
    assert any("VETO:" in m for m in motivos)

    # Mutación mediante filtrar_alerta
    alerta_mutada = filtro.filtrar_alerta(alerta_vetada)
    assert alerta_mutada.estado_operativo == "DESCARTADA_POR_REGLAS"
    assert alerta_mutada.score_temprano == 0


def test_filtro_scoring_presupuesto_municipal():
    """Verifica la asignación de puntuación (+40 pts) para anuncios de presupuestos municipales."""
    filtro = FiltroBoletinesReglas()
    alerta_presupuesto = crear_alerta_test("Ajuntament de Girona - Aprovació inicial del pressupost per a l'exercici 2027")

    aceptada, score, motivos = filtro.evaluar_alerta(alerta_presupuesto)

    assert aceptada is True
    assert score >= 40
    assert any("Presupuestos" in m for m in motivos)

    alerta_mutada = filtro.filtrar_alerta(alerta_presupuesto)
    assert alerta_mutada.estado_operativo == "NUEVA_FASE_TEMPRANA"
    assert alerta_mutada.score_temprano == score


def test_filtro_scoring_consulta_preliminar_art115():
    """Verifica la asignación de puntuación máxima (+50 pts) para consultas preliminares de mercado (Art. 115 LCSP)."""
    filtro = FiltroBoletinesReglas()
    alerta_consulta = crear_alerta_test("Anunci de consultes preliminars del mercat de conformitat amb l'Art. 115 LCSP per a serveis d'atenció domiciliària")

    aceptada, score, motivos = filtro.evaluar_alerta(alerta_consulta)

    assert aceptada is True
    assert score >= 50
    assert any("Art. 115 LCSP" in m for m in motivos)


def test_filtro_descarte_por_score_insuficiente():
    """Verifica el descarte de anuncios irrelevantes sin palabras de veto pero sin keywords tempranas de impacto."""
    filtro = FiltroBoletinesReglas()
    alerta_irrelevante = crear_alerta_test("Convocatòria d'examen per a la borsa de treball d'administratius")

    aceptada, score, motivos = filtro.evaluar_alerta(alerta_irrelevante)

    assert aceptada is False
    assert score < 30
    assert any("DESCARTE:" in m for m in motivos)


def test_filtrar_lote_boletines_y_trazabilidad():
    """Verifica el filtrado en lote y el cálculo de métricas agregadas."""
    filtro = FiltroBoletinesReglas()
    lote = [
        crear_alerta_test("Aprovació inicial del pressupost 2027", fuente="DOGC"),  # Aceptada (+40)
        crear_alerta_test("Notificació de multa de tràfic", fuente="BOPB"),         # Veto (0)
        crear_alerta_test("Anunci d'examen d'auxiliar de biblioteca", fuente="BOPB") # Descarte score (0)
    ]

    aceptadas, metricas = filtro.filtrar_lote_boletines(lote)

    assert len(aceptadas) == 1
    assert metricas["total_ingresadas"] == 3
    assert metricas["aceptadas"] == 1
    assert metricas["descartadas_veto"] == 1
    assert metricas["descartadas_score"] == 1


def test_healthcheck_filtro_centinela():
    """Verifica el informe de autodiagnóstico del filtro por reglas duras."""
    filtro = FiltroBoletinesReglas()
    hc = filtro.healthcheck_filtro_centinela()

    assert hc["status"] == "OK"
    assert hc["categorias_cargadas"] > 0
    assert hc["palabras_descarte_cargadas"] > 0
    assert hc["umbral_minimo"] == 30

"""
tests/test_blindaje_ecosistema.py — Pruebas del Plan de Blindaje y Mejora Arquitectónica
Ecosistema Automático de Licitaciones (bfr_incoop)
"""

import os
import pytest
from src.pmp_service import PMPService
from src.centinela import (
    AlertaBoletinDTO,
    FiltroBoletinesReglas,
    EvaluadorScoringCentinela
)

def test_pmp_service_matching_municipios():
    """Verifica la normalización de municipios y consulta de PMP en config/pmp_ayuntamientos.csv."""
    pmp_svc = PMPService()

    # Barcelona (22d) -> BAJO
    pmp_barcelona, pen_bcn, clas_bcn = pmp_svc.evaluar_riesgo_pmp("Ajuntament de Barcelona")
    assert pmp_barcelona == 22
    assert pen_bcn == 0
    assert clas_bcn == "BAJO"

    # Badalona (78d) -> ALTO (-25 pts)
    pmp_badalona, pen_bad, clas_bad = pmp_svc.evaluar_riesgo_pmp("Ayuntamiento de Badalona")
    assert pmp_badalona == 78
    assert pen_bad == -25
    assert clas_bad == "ALTO"

    # Municipio no registrado -> Default 30d
    pmp_desconocido, pen_desc, clas_desc = pmp_svc.evaluar_riesgo_pmp("Ajuntament de Vallirana")
    assert pmp_desconocido == 30
    assert pen_desc == 0


def test_veto_contextual_negativo():
    """Verifica que frases de excepción como 'no incluye obras' evitan el veto erróneo."""
    filtro = FiltroBoletinesReglas()
    
    # Anuncio con palabra de veto pero en contexto negativo ("no incluye obras")
    alerta_limpieza = AlertaBoletinDTO(
        fuente="BOPB",
        num_boletin="100",
        fecha_publicacion="2026-07-26T08:00:00Z",
        organo_emisor="Ajuntament de Terrassa",
        municipio="Terrassa",
        titulo_anuncio="Aprovació inicial del pressupost per a serveis de neteja (no incluye obras)",
        seccion_boletin="Anuncis",
        url_anuncio="https://example.com/100",
        texto_sumario="Servicio de limpieza municipal"
    )

    aceptada, score, motivos = filtro.evaluar_alerta(alerta_limpieza)

    assert aceptada is True
    assert score >= 40
    assert not any("VETO:" in m for m in motivos)


def test_evaluador_scoring_con_penalizacion_pmp():
    """Verifica que el Periodo Medio de Pago (PMP) alto penaliza la puntuación final."""
    evaluador = EvaluadorScoringCentinela()
    
    # Alerta en Badalona (PMP = 78d -> -25 pts) con score base de reglas de 40 pts
    alerta_badalona = AlertaBoletinDTO(
        fuente="BOPB",
        num_boletin="200",
        fecha_publicacion="2026-07-26T08:00:00Z",
        organo_emisor="Ayuntamiento de Badalona",
        municipio="Badalona",
        titulo_anuncio="Aprovació inicial del pressupost de Badalona 2027",
        seccion_boletin="Anuncis",
        url_anuncio="https://example.com/200",
        texto_sumario="Presupuestos",
        score_temprano=40,
        motivos_score=["REGLA: Presupuestos (+40 pts)"]
    )

    alerta_evaluada = evaluador.evaluar_alerta(alerta_badalona)

    # Score base 40 - 25 (Penalización PMP Badalona 78d) = 15 pts -> DESCARTADA (< 40)
    assert alerta_evaluada.score_temprano == 15
    assert alerta_evaluada.estado_operativo == "DESCARTADA_POR_REGLAS"
    assert any("FINANCIERO: Penalización por PMP de 78 días" in m for m in alerta_evaluada.motivos_score)


def test_prompts_lcsp_matriz_cuantitativa():
    """
    Verifica los invariantes de la matriz de riesgo de config/prompts_lcsp.yaml.

    Se comprueban propiedades, no cadenas literales de encabezado: la auditoría del
    2026-07-27 detectó que la matriz v1 dejaba sin cubrir el caso "más de 15 trabajadores
    CON desglose salarial", por lo que cada modelo LLM improvisaba un nivel de riesgo
    distinto para el mismo pliego (ALTO frente a MEDIO), alterando el scoring comercial.
    """
    yaml_path = "config/prompts_lcsp.yaml"
    assert os.path.exists(yaml_path)

    import yaml
    with open(yaml_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    sistema_base = data.get("sistema_base", "")

    # 1. Los cuatro niveles de riesgo siguen definidos
    for nivel in ("BAJO", "MEDIO", "ALTO", "CRÍTICO"):
        assert nivel in sistema_base, f"Falta el nivel de riesgo {nivel}"

    # 2. La matriz de subrogación cubre los tramos por número de trabajadores.
    #    Sin estos umbrales vuelve el hueco que provocaba dictámenes no deterministas.
    assert "SUBROGACIÓN" in sistema_base
    for umbral in ("40", "21", "20", "6", "5"):
        assert umbral in sistema_base, f"Falta el umbral de plantilla '{umbral}'"

    # 3. Regla anti-alucinación: el modelo no debe inferir datos ausentes del texto
    assert "null" in sistema_base
    assert "PROHIBIDO INFERIR" in sistema_base

    # 4. El PMP NO debe evaluarse en el prompt de pliegos: no consta en el documento y
    #    ya se calcula de forma determinista en la Capa 2 desde config/pmp_ayuntamientos.csv.
    assert "Periodo Medio de Pago" not in sistema_base, \
        "El prompt de pliegos no debe pedir al LLM que evalúe el PMP"

    # 5. El prompt del Centinela sí recibe el PMP inyectado como dato
    assert "{pmp_dias}" in data.get("centinela_boletines", "")

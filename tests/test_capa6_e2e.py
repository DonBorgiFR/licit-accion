"""
tests/test_capa6_e2e.py — Pruebas de Integración End-to-End (E2E) y Cierre de Capa 6
Ecosistema Automático de Licitaciones (bfr_incoop)
"""

import os
import csv
import json
import pytest
from src.memoria import Memoria
from src.centinela import (
    AlertaBoletinDTO,
    DictamenCentinelaDTO,
    IngestorBoletines,
    FiltroBoletinesReglas,
    AnalistaBoletinesIA,
    EvaluadorScoringCentinela,
    ejecutar_pipeline_centinela_resiliente,
    exportar_reporte_centinela_csv
)

def test_capa6_e2e_flujo_completo(tmp_path):
    """
    Prueba E2E completa de la Capa 6:
    Ingesta -> Filtro por veto negativo -> Análisis LLM / Fallback -> Scoring con PMP -> SQLite v5 -> CSV Export.
    """
    db_path = os.path.join(str(tmp_path), "e2e_licitaciones.db")
    csv_path = os.path.join(str(tmp_path), "e2e_alertas_tempranas.csv")

    # 1. Base de datos SQLite v5
    memoria = Memoria(db_path=db_path)
    memoria.setup_db()

    # 2. Mock Ingestor con 3 anuncios que cubren las tres salidas posibles del pipeline:
    #    - Barcelona (PMP 22d, riesgo BAJO): supera el umbral y llega al Cockpit.
    #    - Badalona (PMP 78d, riesgo ALTO): la penalización financiera lo baja del umbral.
    #    - Girona (obras): vetado por reglas duras antes de llegar al análisis.
    #
    # Badalona se guardaba antes porque el dictamen degradado fingía interés "MEDIO" y le
    # regalaba +15 pts, justo los que necesitaba para alcanzar el mínimo de 30. Retirado
    # ese bonus fantasma, queda en 15 pts y se descarta por su PMP real. Esa es la
    # diferencia entre puntuar un análisis que ocurrió y uno que no.
    alerta_barcelona = AlertaBoletinDTO(
        fuente="DOGC",
        num_boletin="2026-100",
        fecha_publicacion="2026-07-26T08:00:00Z",
        organo_emisor="Ajuntament de Barcelona",
        municipio="Barcelona",
        titulo_anuncio="Aprovació inicial del pressupost per a serveis educatius (no incluye obras)",
        seccion_boletin="Anuncis",
        url_anuncio="https://dogc.cat/100",
        texto_sumario="Presupuestos municipales para servicios de educación"
    )

    alerta_badalona = AlertaBoletinDTO(
        fuente="DOGC",
        num_boletin="2026-101",
        fecha_publicacion="2026-07-26T08:00:00Z",
        organo_emisor="Ayuntamiento de Badalona",
        municipio="Badalona",
        titulo_anuncio="Aprovació inicial del pressupost per a serveis de neteja de centres escolars (no incluye obras)",
        seccion_boletin="Anuncis",
        url_anuncio="https://dogc.cat/101",
        texto_sumario="Presupuestos municipales para servicios de educación"
    )

    alerta_vetada = AlertaBoletinDTO(
        fuente="BOPB",
        num_boletin="2026-202",
        fecha_publicacion="2026-07-26T08:00:00Z",
        organo_emisor="Ajuntament de Girona",
        municipio="Girona",
        titulo_anuncio="Llicència d'obres i construcció d'edificis",
        seccion_boletin="Anuncis",
        url_anuncio="https://bopb.cat/202",
        texto_sumario="Obras mayores de edificación"
    )

    class MockIngestor(IngestorBoletines):
        def ejecutar_ingesta_completa(self):
            return [alerta_barcelona, alerta_badalona, alerta_vetada]

    ingestor = MockIngestor()
    filtro = FiltroBoletinesReglas()
    # Sin proveedor real: la suite no debe salir a la red ni consumir cuota de la API.
    # El e2e verifica el flujo completo con el análisis semántico degradado, que es el
    # escenario que debe seguir entregando alertas al Cockpit.
    analista = AnalistaBoletinesIA(autoinicializar_proveedor=False)
    evaluador = EvaluadorScoringCentinela()

    # 3. Ejecución del Pipeline Resiliente E2E
    alertas_finales, metricas = ejecutar_pipeline_centinela_resiliente(
        ingestor=ingestor,
        filtro=filtro,
        analista=analista,
        evaluador=evaluador,
        db_path=db_path
    )

    assert metricas["ingresadas"] == 3
    assert metricas["aceptadas_filtro"] == 2  # Barcelona y Badalona; Girona queda vetada
    assert metricas["modo_degradado"] is False

    # El análisis se degradó (no hay proveedor), y eso no puede inventar puntuación:
    # ninguna alerta debe llevar bonificación ni penalización por dictamen.
    for alerta in alertas_finales:
        assert alerta.dictamen_ia.modo_degradado is True
        assert not any("Interés" in motivo for motivo in alerta.motivos_score)

    # 4. Verificar persistencia en SQLite v5: sólo llega la que supera el umbral
    alertas_db = memoria.listar_alertas_tempranas()
    assert len(alertas_db) == 1
    alerta_guardada = alertas_db[0]
    assert alerta_guardada.municipio == "Barcelona"

    # 5. Generación y validación del reporte comercial CSV
    csv_gen = exportar_reporte_centinela_csv(db_path=db_path, output_csv=csv_path)
    assert os.path.exists(csv_gen)

    with open(csv_path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f, delimiter=";")
        rows = list(reader)
        assert len(rows) == 1
        assert rows[0]["pmp_dias"] == "22"  # PMP real Barcelona
        assert rows[0]["fuente"] == "DOGC"


def test_capa6_e2e_vinculacion_expediente_pscp(tmp_path):
    """
    Prueba E2E de vinculación y correlación entre alerta temprana y expediente formal de la PSCP.
    """
    db_path = os.path.join(str(tmp_path), "e2e_vinculacion.db")
    memoria = Memoria(db_path=db_path)
    memoria.setup_db()

    alerta = AlertaBoletinDTO(
        fuente="DOGC",
        num_boletin="500",
        fecha_publicacion="2026-07-26T08:00:00Z",
        organo_emisor="Ajuntament de Sabadell",
        municipio="Sabadell",
        titulo_anuncio="Consulta preliminar de mercat per a serveis educatius",
        seccion_boletin="Anuncis",
        url_anuncio="https://dogc.cat/500",
        texto_sumario="Consulta preliminar",
        score_temprano=85,
        estado_operativo="NUEVA_FASE_TEMPRANA"
    )
    memoria.guardar_alerta_boletin(alerta)

    # Insertar expediente en expedientes para cumplir la clave foránea
    with memoria.conectar() as conn:
        with conn:
            conn.execute(
                "INSERT INTO expedientes (id, titulo, organo, fecha_ingesta) VALUES (?, ?, ?, ?);",
                ("EXP-2026-SABADELL-01", "Licitació de serveis educatius", "Ajuntament de Sabadell", "2026-07-26T08:00:00Z")
            )

    # Vincular alerta a expediente "EXP-2026-SABADELL-01"
    exito = memoria.vincular_alerta_a_expediente(alerta.id_alerta, "EXP-2026-SABADELL-01")

    assert exito is True

    alerta_recup = memoria.obtener_alerta_boletin(alerta.id_alerta)
    assert alerta_recup.expediente_licitacion_vinculado == "EXP-2026-SABADELL-01"
    assert alerta_recup.estado_operativo == "CONVERTIDA_A_LICITACION"

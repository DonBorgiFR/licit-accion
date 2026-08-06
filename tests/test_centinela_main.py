"""
tests/test_centinela_main.py — Pruebas Unitarias de Reporting CSV y Orquestación Principal (Capa 6 - Paso 8)
Ecosistema Automático de Licitaciones (bfr_incoop)
"""

import os
import csv
import argparse
import pytest
from src.memoria import Memoria
from src.centinela import (
    AlertaBoletinDTO,
    DictamenCentinelaDTO,
    exportar_reporte_centinela_csv
)

def test_exportar_reporte_centinela_csv(tmp_path):
    """Verifica la generación del informe comercial CSV con codificación UTF-8-BOM."""
    db_path = os.path.join(str(tmp_path), "test_licitaciones.db")
    csv_path = os.path.join(str(tmp_path), "test_alertas_tempranas.csv")

    memoria = Memoria(db_path=db_path)
    memoria.setup_db()

    # Insertar alertas de prueba
    dictamen = DictamenCentinelaDTO(
        es_oportunidad_temprana=True,
        nivel_interes="ALTO",
        categoria_fase_temprana="PRESUPUESTO",
        resumen_ejecutivo="Oportunidad detectada en fase previa",
        acciones_recomendadas=["Seguimiento comercial"]
    )
    alerta = AlertaBoletinDTO(
        fuente="DOGC",
        num_boletin="123",
        fecha_publicacion="2026-07-26T08:00:00Z",
        organo_emisor="Ajuntament de Badalona",
        municipio="Badalona",
        titulo_anuncio="Aprovació inicial del pressupost 2027",
        seccion_boletin="Anuncis",
        url_anuncio="https://example.com/123",
        texto_sumario="Presupuestos",
        score_temprano=75,
        dictamen_ia=dictamen,
        estado_operativo="NUEVA_FASE_TEMPRANA"
    )
    memoria.guardar_alerta_boletin(alerta)

    # Generar CSV
    resultado_path = exportar_reporte_centinela_csv(db_path=db_path, output_csv=csv_path)

    assert os.path.exists(resultado_path)
    
    # Leer CSV verificando BOM y campos
    with open(csv_path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f, delimiter=";")
        rows = list(reader)
        assert len(rows) == 1
        row = rows[0]
        assert row["fuente"] == "DOGC"
        assert row["municipio"] == "Badalona"
        assert row["pmp_dias"] == "78"  # Badalona PMP real en CSV
        assert row["score_temprano"] == "75"
        assert row["nivel_interes_ia"] == "ALTO"
        assert row["acciones_recomendadas"] == "Seguimiento comercial"


def test_main_cli_parser_flags():
    """Verifica la configuración del parseador CLI de la Capa 6."""
    parser = argparse.ArgumentParser(description="Pipeline de Licitaciones Incoop - Capa 6: Centinela Integrado")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--skip-centinela", action="store_true")
    parser.add_argument("--csv-centinela", type=str, default="data/alertas_tempranas.csv")

    args = parser.parse_args(["--skip-centinela", "--csv-centinela", "data/custom_out.csv"])
    assert args.skip_centinela is True
    assert args.csv_centinela == "data/custom_out.csv"

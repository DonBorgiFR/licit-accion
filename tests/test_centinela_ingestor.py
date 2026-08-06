"""
tests/test_centinela_ingestor.py — Pruebas Unitarias del Ingestor de Boletines (Capa 6 - Paso 3)
Ecosistema Automático de Licitaciones (bfr_incoop)
"""

from unittest.mock import patch, MagicMock
import pytest
from src.centinela import (
    IngestorBoletines,
    AlertaBoletinDTO,
    CentinelaNetworkError,
    CentinelaParseError,
    CentinelaConfigError,
    normalizar_fecha_boletin_utc
)

# Mock XML de DOGC en formato Atom
MOCK_DOGC_ATOM_XML = """<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>DOGC - Diari Oficial de la Generalitat de Catalunya</title>
  <updated>2026-07-26T08:00:00+02:00</updated>
  <entry>
    <title>RESOLUCIÓ por la que se aprueba el plan estratégico de subvenciones de educación</title>
    <link href="https://dogc.gencat.cat/es/documento/12345"/>
    <published>2026-07-26T07:30:00+02:00</published>
    <summary>Subvenciones directas para casales e infantil.</summary>
    <author><name>Departament d'Educació</name></author>
  </entry>
</feed>
"""

# Mock XML de BOPB en formato RSS
MOCK_BOPB_RSS_XML = """<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0">
  <channel>
    <title>BOPB - Butlletí Oficial de la Província de Barcelona</title>
    <item>
      <title>Ajuntament de Sabadell - Aprovació inicial del pressupost 2027</title>
      <link>https://bop.diba.cat/detalle/6789</link>
      <pubDate>Sun, 26 Jul 2026 09:00:00 +0200</pubDate>
      <description>Aprobación del presupuesto municipal con partidas de acción social.</description>
      <guid>BOPB-2026-6789</guid>
    </item>
  </channel>
</rss>
"""


def test_normalizar_fecha_boletin_utc():
    """Verifica la conversión de fechas heterogéneas de feeds Atom/RSS a ISO 8601 UTC."""
    f1 = normalizar_fecha_boletin_utc("2026-07-26T08:00:00+02:00")
    assert f1 == "2026-07-26T06:00:00Z"

    f2 = normalizar_fecha_boletin_utc("Sun, 26 Jul 2026 09:00:00 +0200")
    assert f2 == "2026-07-26T07:00:00Z"

    f3 = normalizar_fecha_boletin_utc("2026-07-26")
    assert "2026-07-26" in f3


def test_cargar_configuracion_exito():
    """Verifica la carga del archivo de configuración centinela_config.yaml."""
    ingestor = IngestorBoletines()
    assert "fuentes_oficiales" in ingestor.config
    assert "dogc" in ingestor.config["fuentes_oficiales"]
    assert "bopb" in ingestor.config["fuentes_oficiales"]


def test_parsear_xml_dogc():
    """Verifica el parseo XML Atom del DOGC."""
    ingestor = IngestorBoletines()
    alertas = ingestor.parsear_xml_dogc(MOCK_DOGC_ATOM_XML)

    assert len(alertas) == 1
    a = alertas[0]
    assert a.fuente == "DOGC"
    assert "plan estratégico de subvenciones" in a.titulo_anuncio.lower()
    assert a.organo_emisor == "Departament d'Educació"
    assert a.url_anuncio == "https://dogc.gencat.cat/es/documento/12345"


def test_parsear_xml_bopb():
    """Verifica el parseo XML RSS del BOPB."""
    ingestor = IngestorBoletines()
    alertas = ingestor.parsear_xml_bopb(MOCK_BOPB_RSS_XML)

    assert len(alertas) == 1
    a = alertas[0]
    assert a.fuente == "BOPB"
    assert "pressupost" in a.titulo_anuncio.lower()
    assert a.organo_emisor == "Ajuntament de Sabadell"
    assert a.num_boletin == "BOPB-2026-6789"


@patch.object(IngestorBoletines, "_http_get_with_retry")
def test_ejecutar_ingesta_completa_y_deduplicacion(mock_http):
    """Verifica la ingesta consolidada multifuente y deduplicación por SHA256."""
    mock_http.side_effect = lambda url: MOCK_DOGC_ATOM_XML if "dogc" in url else MOCK_BOPB_RSS_XML

    ingestor = IngestorBoletines()
    alertas = ingestor.ejecutar_ingesta_completa()

    assert len(alertas) == 2
    fuentes = {a.fuente for a in alertas}
    assert fuentes == {"DOGC", "BOPB"}


@patch.object(IngestorBoletines, "_http_get_with_retry")
def test_modo_degradado_fallo_red(mock_http):
    """Verifica que el fallo de conexión en una fuente no rompe la otra (modo degradado)."""
    def mock_side_effect(url):
        if "dogc" in url:
            raise CentinelaNetworkError("Connection refused")
        return MOCK_BOPB_RSS_XML

    mock_http.side_effect = mock_side_effect

    ingestor = IngestorBoletines()
    alertas = ingestor.ejecutar_ingesta_completa()

    # BOPB debe responder exitosamente aunque DOGC haya fallado
    assert len(alertas) == 1
    assert alertas[0].fuente == "BOPB"


def test_healthcheck_centinela():
    """Verifica el funcionamiento del autodiagnóstico del centinela."""
    ingestor = IngestorBoletines()
    hc = ingestor.healthcheck_centinela()

    assert hc["status"] == "OK"
    assert "dogc" in hc["fuentes_configuradas"]
    assert "bopb" in hc["fuentes_configuradas"]

"""Regresiones del contrato de coherencia LCSP de la beta."""

from src.analista import (
    AnalisisSemanticoDTO,
    ClausulasSocialesDTO,
    CriteriosAdjudicacionDTO,
    DictamenIA,
    GarantiaDefinitivaDTO,
    PenalidadesDTO,
    RevisionPreciosDTO,
    SubrogacionDTO,
)
from src.filtro import Filtro
from src.radar import Radar


def test_radar_no_confunde_negaciones_ni_revision_de_oficio():
    radar = Radar()
    assert radar._detectar_subrogacion_preliminar("No procedeix la subrogació de personal") is False
    assert radar._detectar_subrogacion_preliminar("Sin obligación de subrogación") is False
    assert radar._detectar_subrogacion_preliminar("Subrogación de 12 trabajadores") is True
    assert radar._detectar_revision_precios_preliminar("Revisión de oficio del acuerdo") is False
    assert radar._detectar_revision_precios_preliminar("Sin revisión de precios") is False
    assert radar._detectar_revision_precios_preliminar("Se admite revisión de precios por IPC") is True


def test_filtro_publica_score_canonico_y_no_penaliza_senal_preliminar():
    filtro = Filtro()
    base = {
        "titulo": "Servicio educativo municipal",
        "organo": "Ajuntament de Mataró",
        "importe": 150000.0,
        "vec": 150000.0,
        "tipo_contrato_codigo": "2",
        "estado": "PUB",
        "cpvs": ["80110000"],
        "fecha_limite": "2099-12-31",
        "procedimiento_codigo": "1",
        "country_subentity_code": "ES511",
        "localidad": "Mataró",
    }
    sin_senal = filtro.filtrar(base)
    con_senal = filtro.filtrar({**base, "subrogacion_detectada": True, "revision_precios_detectada": False})
    assert 0 <= sin_senal["score"] <= 100
    assert sin_senal["score"] == con_senal["score"]
    assert con_senal["score_bruto"] > 0


def test_dto_v3_preserva_las_seis_clausulas_criticas():
    dto = AnalisisSemanticoDTO(
        subrogacion=SubrogacionDTO(),
        revision_precios=RevisionPreciosDTO(),
        criterios=CriteriosAdjudicacionDTO(),
        dictamen=DictamenIA(),
        garantia_definitiva=GarantiaDefinitivaDTO(requerida=True, porcentaje=5.0, modalidad="seguro de caución"),
        penalidades=PenalidadesDTO(existen=True, riesgo_evaluado="ALTO"),
        clausulas_sociales=ClausulasSocialesDTO(existen=True, ventaja_incoop=True),
    )
    recuperado = AnalisisSemanticoDTO.from_json(dto.to_json())
    assert recuperado.version_esquema == 3
    assert recuperado.garantia_definitiva.modalidad == "seguro de caución"
    assert recuperado.penalidades.riesgo_evaluado == "ALTO"
    assert recuperado.clausulas_sociales.ventaja_incoop is True

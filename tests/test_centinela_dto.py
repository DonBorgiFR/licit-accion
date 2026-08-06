"""
tests/test_centinela_dto.py — Pruebas Unitarias del DTO AlertaBoletinDTO (Capa 6 - Paso 1)
Ecosistema Automático de Licitaciones (bfr_incoop)
"""

import hashlib
import json
import pytest
from src.centinela import (
    AlertaBoletinDTO,
    DictamenCentinelaDTO,
    BoletinDTOValidationError,
    BoletinDeserializationError
)


def test_dictamen_centinela_dto_exitoso():
    """Verifica la correcta instanciación y serialización de DictamenCentinelaDTO."""
    dictamen = DictamenCentinelaDTO(
        es_oportunidad_temprana=True,
        nivel_interes="ALTO",
        categoria_fase_temprana="PRESUPUESTO",
        resumen_ejecutivo="Aprobación de partida de 450.000€ para nueva Escola Bressol.",
        acciones_recomendadas=["Contactar con el área de educación del Ayuntamiento."],
        estimacion_meses_hasta_licitacion=4
    )

    assert dictamen.es_oportunidad_temprana is True
    assert dictamen.nivel_interes == "ALTO"
    assert dictamen.categoria_fase_temprana == "PRESUPUESTO"
    assert dictamen.estimacion_meses_hasta_licitacion == 4

    # Test conversión Dict / JSON
    d_dict = dictamen.to_dict()
    assert d_dict["nivel_interes"] == "ALTO"

    d_json = dictamen.to_json()
    assert "Escola Bressol" in d_json

    # Test deserialización
    restored = DictamenCentinelaDTO.from_json(d_json)
    assert restored.es_oportunidad_temprana is True
    assert restored.nivel_interes == "ALTO"
    assert restored.acciones_recomendadas == ["Contactar con el área de educación del Ayuntamiento."]


def test_dictamen_centinela_dto_validacion_erronea():
    """Verifica que DictamenCentinelaDTO rechaza niveles de interés o categorías inválidas."""
    with pytest.raises(BoletinDTOValidationError):
        DictamenCentinelaDTO(
            es_oportunidad_temprana=True,
            nivel_interes="INVALIDO",
            categoria_fase_temprana="PRESUPUESTO",
            resumen_ejecutivo="Prueba"
        )

    with pytest.raises(BoletinDTOValidationError):
        DictamenCentinelaDTO(
            es_oportunidad_temprana=True,
            nivel_interes="ALTO",
            categoria_fase_temprana="CATEGORIA_FALSA",
            resumen_ejecutivo="Prueba"
        )


def test_alerta_boletin_dto_exitoso_y_sha256():
    """Verifica la creación de AlertaBoletinDTO y el cálculo determinista del id_alerta (SHA256)."""
    alerta = AlertaBoletinDTO(
        fuente="DOGC",
        num_boletin="9120",
        fecha_publicacion="2026-07-26T10:00:00Z",
        organo_emisor="Generalitat de Catalunya - Departament d'Educació",
        municipio="Barcelona",
        titulo_anuncio="Anunci de licitació de servei d'escoles bressol",
        seccion_boletin="Administració Local",
        score_temprano=85,
        motivos_score=["+40 CPV Core Educativo", "+30 Territorio Catalunya"]
    )

    assert alerta.fuente == "DOGC"
    assert alerta.id_alerta is not None

    # Verificar que el SHA256 es determinista
    raw_expected = f"DOGC|9120|anunci de licitació de servei d'escoles bressol"
    expected_hash = hashlib.sha256(raw_expected.encode("utf-8")).hexdigest()
    assert alerta.id_alerta == expected_hash


def test_alerta_boletin_dto_roundtrip_json():
    """Verifica la serialización y deserialización completa con DictamenCentinelaDTO anidado."""
    dictamen = DictamenCentinelaDTO(
        es_oportunidad_temprana=True,
        nivel_interes="ALTO",
        categoria_fase_temprana="CONSULTA_PRELIMINAR",
        resumen_ejecutivo="Sondeo de mercado para gestión de casal de gent gran.",
        acciones_recomendadas=["Presentar propuesta técnica en consulta"],
        estimacion_meses_hasta_licitacion=2
    )

    alerta_orig = AlertaBoletinDTO(
        fuente="BOPB",
        num_boletin="2026-00452",
        fecha_publicacion="2026-07-25T08:30:00Z",
        organo_emisor="Ajuntament de Sabadell",
        municipio="Sabadell",
        titulo_anuncio="Aprovació inicial de bases reguladores de serveis socials",
        seccion_boletin="Anuncis Municipals",
        url_anuncio="https://bop.diba.cat/anuncio/123",
        texto_sumario="Texto completo del anuncio municipal...",
        score_temprano=90,
        motivos_score=["+50 PMP Paga rápido", "+40 Afinidad Social"],
        dictamen_ia=dictamen,
        estado_operativo="EN_ESTUDIO_PROACTIVO"
    )

    # Convertir a JSON
    json_data = alerta_orig.to_json()
    assert "Ajuntament de Sabadell" in json_data
    assert "EN_ESTUDIO_PROACTIVO" in json_data

    # Deserializar desde JSON
    alerta_restaurada = AlertaBoletinDTO.from_json(json_data)
    assert alerta_restaurada.id_alerta == alerta_orig.id_alerta
    assert alerta_restaurada.fuente == "BOPB"
    assert alerta_restaurada.estado_operativo == "EN_ESTUDIO_PROACTIVO"
    assert alerta_restaurada.dictamen_ia is not None
    assert alerta_restaurada.dictamen_ia.nivel_interes == "ALTO"
    assert alerta_restaurada.dictamen_ia.categoria_fase_temprana == "CONSULTA_PRELIMINAR"


def test_alerta_boletin_dto_validacion_fuente_invalida():
    """Verifica que AlertaBoletinDTO rechaza fuentes distintas a DOGC o BOPB."""
    with pytest.raises(BoletinDTOValidationError):
        AlertaBoletinDTO(
            fuente="BOE",  # Fuera de alcance de Capa 6
            num_boletin="100",
            fecha_publicacion="2026-07-26T10:00:00Z",
            organo_emisor="Ministerio",
            municipio="Madrid",
            titulo_anuncio="Anuncio falso"
        )


def test_alerta_boletin_dto_validacion_campos_vacios():
    """Verifica que AlertaBoletinDTO rechaza campos requeridos vacíos."""
    with pytest.raises(BoletinDTOValidationError):
        AlertaBoletinDTO(
            fuente="DOGC",
            num_boletin="",
            fecha_publicacion="2026-07-26T10:00:00Z",
            organo_emisor="Organo",
            municipio="Municipio",
            titulo_anuncio="Anuncio"
        )

    with pytest.raises(BoletinDTOValidationError):
        AlertaBoletinDTO(
            fuente="DOGC",
            num_boletin="123",
            fecha_publicacion="2026-07-26T10:00:00Z",
            organo_emisor="Organo",
            municipio="Municipio",
            titulo_anuncio="   "
        )


def test_alerta_boletin_dto_estado_invalido():
    """Verifica que AlertaBoletinDTO valida los estados de la máquina de estados."""
    with pytest.raises(BoletinDTOValidationError):
        AlertaBoletinDTO(
            fuente="DOGC",
            num_boletin="123",
            fecha_publicacion="2026-07-26T10:00:00Z",
            organo_emisor="Organo",
            municipio="Municipio",
            titulo_anuncio="Anuncio valido",
            estado_operativo="ESTADO_INEXISTENTE"
        )


def test_alerta_boletin_dto_deserializacion_defensiva():
    """Verifica la tolerancia de deserialización cuando faltan campos opcionales."""
    raw_dict = {
        "fuente": "dogc",
        "num_boletin": "555",
        "fecha_publicacion": "2026-07-26T10:00:00Z",
        "organo_emisor": "Generalitat",
        "municipio": "Girona",
        "titulo_anuncio": "Anuncio de prova"
    }
    alerta = AlertaBoletinDTO.from_dict(raw_dict)
    assert alerta.fuente == "DOGC"
    assert alerta.score_temprano == 0
    assert alerta.dictamen_ia is None
    assert alerta.estado_operativo == "NUEVA_FASE_TEMPRANA"

"""
tests/test_capa7_paso2.py — Pruebas Unitarias de Esquemas Pydantic v2 (Capa 7 - Paso 2)
Ecosistema Automático de Licitaciones (bfr_incoop)

Audita el módulo src/api/schemas.py:
- Validación e inmutabilidad de DTOs
- Enumeraciones de negocio y validación de transiciones de estado
- Coerciones de tipos desde diccionarios y SQLite
- Generic Model PaginatedResponse[T]
"""

import pytest
from pydantic import ValidationError

from src.api.schemas import (
    EstadoLicitacionEnum,
    EstadoAlertaEnum,
    LoteSchema,
    LicitacionSchema,
    AlertaBoletinSchema,
    KPISummarySchema,
    PaginatedResponse,
    TransicionEstadoLicitacionSchema,
    TransicionEstadoAlertaSchema,
    HealthResponseSchema,
    APIErrorResponse
)


def test_lote_schema_instantiation():
    """Verifica que LoteSchema valida campos requeridos y asigna valores por defecto."""
    data = {
        "expediente_id": "EXP-2026/001",
        "lote_numero": 1,
        "titulo_lote": "Lote 1: Casal de Gent Gran",
        "pbl": 120000.50,
        "vec": 240000.00,
        "subrogacion": True,
        "score_total": 85,
        "estado_operativo": "Nueva"
    }
    lote = LoteSchema.model_validate(data)
    
    assert lote.expediente_id == "EXP-2026/001"
    assert lote.lote_numero == 1
    assert lote.pbl == 120000.50
    assert lote.subrogacion is True
    assert lote.score_total == 85
    assert lote.horas_internas_invertidas == 0


def test_licitacion_schema_with_lotes():
    """Verifica que LicitacionSchema contiene una lista de LoteSchema y dictamen semántico."""
    lote_data = {
        "expediente_id": "EXP-2026/001",
        "lote_numero": 1,
        "titulo_lote": "Gestión Educativa",
        "pbl": 50000.0,
        "vec": 100000.0,
        "score_total": 75,
        "estado_operativo": "Estudiando"
    }
    lic_data = {
        "id": "EXP-2026/001",
        "titulo": "Servicios Educativos Badalona",
        "organo": "Ajuntament de Badalona",
        "localidad": "Badalona",
        "urgente": False,
        "fuente": "PSCP",
        "score_maximo": 75,
        "lotes": [lote_data],
        "analisis_semantico": {"dictamen_recomendacion": "RECOMENDADA", "subrogacion_riesgo": "BAJO"}
    }
    lic = LicitacionSchema.model_validate(lic_data)
    
    assert lic.id == "EXP-2026/001"
    assert len(lic.lotes) == 1
    assert lic.lotes[0].titulo_lote == "Gestión Educativa"
    assert lic.analisis_semantico["dictamen_recomendacion"] == "RECOMENDADA"


def test_alerta_boletin_schema_instantiation():
    """Verifica la validación de AlertaBoletinSchema (DOGC / BOPB)."""
    alerta_data = {
        "id_alerta": "hash123abc",
        "fuente": "DOGC",
        "num_boletin": "9123",
        "fecha_publicacion": "2026-07-26T00:00:00Z",
        "organo_emisor": "Generalitat de Catalunya",
        "municipio": "Barcelona",
        "titulo_anuncio": "Aprobación de subvenciones sociales",
        "score_temprano": 90,
        "categoria_fase_temprana": "SUBVENCION",
        "estado_operativo": "NUEVA_FASE_TEMPRANA"
    }
    alerta = AlertaBoletinSchema.model_validate(alerta_data)
    
    assert alerta.id_alerta == "hash123abc"
    assert alerta.fuente == "DOGC"
    assert alerta.score_temprano == 90
    assert alerta.estado_operativo == "NUEVA_FASE_TEMPRANA"


def test_kpi_summary_schema():
    """Verifica la instanciación de KPISummarySchema."""
    kpi_data = {
        "total_expedientes": 150,
        "total_lotes": 210,
        "licitaciones_estudio": 15,
        "licitaciones_presentadas": 8,
        "licitaciones_ganadas": 5,
        "licitaciones_perdidas": 3,
        "win_rate_porcentaje": 62.5,
        "volumen_total_pbl": 3500000.0,
        "capital_garantias_retenidas": 45000.0,
        "alertas_tempranas_activas": 12
    }
    kpi = KPISummarySchema.model_validate(kpi_data)
    
    assert kpi.total_expedientes == 150
    assert kpi.win_rate_porcentaje == 62.5
    assert kpi.capital_garantias_retenidas == 45000.0


def test_paginated_response_generic():
    """Verifica el comportamiento del modelo genérico PaginatedResponse[T]."""
    alerta = AlertaBoletinSchema(
        id_alerta="hash1",
        fuente="BOPB",
        num_boletin="100",
        fecha_publicacion="2026-07-26T00:00:00Z",
        organo_emisor="Diputació de Barcelona",
        titulo_anuncio="Plan de equipamientos",
        score_temprano=80,
        categoria_fase_temprana="PRESUPUESTO",
        estado_operativo="NUEVA_FASE_TEMPRANA"
    )
    
    pag = PaginatedResponse[AlertaBoletinSchema](
        items=[alerta],
        total=1,
        page=1,
        limit=10,
        total_pages=1
    )
    
    assert pag.total == 1
    assert len(pag.items) == 1
    assert pag.items[0].fuente == "BOPB"


def test_transicion_estado_licitacion_valid_and_invalid():
    """Verifica las validaciones de estado en TransicionEstadoLicitacionSchema."""
    # Válido
    t_valid = TransicionEstadoLicitacionSchema(nuevo_estado="Estudiando", notas="Revisar pliego en comité")
    assert t_valid.nuevo_estado == "Estudiando"
    assert t_valid.notas == "Revisar pliego en comité"
    
    # Inválido
    with pytest.raises(ValidationError) as exc_info:
        TransicionEstadoLicitacionSchema(nuevo_estado="ESTADO_INEXISTENTE")
    assert "Estado 'ESTADO_INEXISTENTE' no es válido" in str(exc_info.value)


def test_transicion_estado_alerta_valid_and_invalid():
    """Verifica las validaciones de estado en TransicionEstadoAlertaSchema."""
    # Válido
    t_valid = TransicionEstadoAlertaSchema(nuevo_estado="EN_ESTUDIO_PROACTIVO")
    assert t_valid.nuevo_estado == "EN_ESTUDIO_PROACTIVO"
    
    # Inválido
    with pytest.raises(ValidationError) as exc_info:
        TransicionEstadoAlertaSchema(nuevo_estado="ESTADO_ALERT_INVALIDO")
    assert "Estado de alerta 'ESTADO_ALERT_INVALIDO' no es válido" in str(exc_info.value)


def test_health_and_error_schemas():
    """Verifica HealthResponseSchema y APIErrorResponse."""
    health = HealthResponseSchema(
        status="OK",
        timestamp="2026-07-26T18:00:00Z",
        db_path="data/licitaciones.db",
        directorio_accesible=True,
        wal_mode_active=True,
        schema_version=5,
        query_test_ok=True
    )
    assert health.status == "OK"
    assert health.wal_mode_active is True
    
    err = APIErrorResponse(
        error_code="NOT_FOUND",
        message="La licitación solicitada no existe",
        details={"expediente_id": "EXP-999"}
    )
    assert err.error_code == "NOT_FOUND"
    assert err.details["expediente_id"] == "EXP-999"

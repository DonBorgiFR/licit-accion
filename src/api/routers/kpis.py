"""
src/api/routers/kpis.py — Router RESTful Analítico de KPIs
Ecosistema Automático de Licitaciones (bfr_incoop)

Endpoint principal de analítica financiera y operativa del Funnel (/api/v1/kpis).
Proporciona el resumen agregado de expedientes, win-rate, working capital e inmovilizado.
"""

import sqlite3
from fastapi import APIRouter, Depends, HTTPException, status
from src.api.schemas import KPISummarySchema, APIErrorResponse
from src.api.dependencies import get_db, trazabilidad_api
from src.memoria import Memoria

router = APIRouter(tags=["KPIs y Analítica"])


@router.get(
    "/kpis",
    response_model=KPISummarySchema,
    responses={
        200: {"model": KPISummarySchema, "description": "Resumen de KPIs ejecutivos del Funnel"},
        503: {"model": APIErrorResponse, "description": "Error calculando agregaciones en SQLite"}
    },
    summary="Resumen de KPIs Ejecutivos del Funnel Comercial",
    description="Calcula y agrega en tiempo real el resumen de expedientes, lotes por estado, win-rate, PBL acumulado y avales retenidos."
)
def get_kpi_summary(db: sqlite3.Connection = Depends(get_db)):
    """
    Retorna el resumen consolidado de KPIs ejecutivos para el Cockpit Visual (Capa 8).
    """
    try:
        memoria = Memoria()
        resumen_dict = memoria.obtener_resumen_kpis(conn=db)
        trazabilidad_api.registrar_evento(
            "API_KPIS_FETCHED",
            {"total_expedientes": resumen_dict.get("total_expedientes"), "total_lotes": resumen_dict.get("total_lotes")},
            estado="INFO"
        )
        return KPISummarySchema.model_validate(resumen_dict)
    except Exception as e:
        trazabilidad_api.registrar_evento("API_KPIS_FAILED", {"error": str(e)}, estado="ERROR")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Fallo calculando resumen de KPIs: {e}"
        )

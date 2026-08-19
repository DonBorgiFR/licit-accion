"""
src/api/routers/kpis.py — Router RESTful Analítico de KPIs
Ecosistema Automático de Licitaciones (bfr_incoop)

Endpoint principal de analítica financiera y operativa del Funnel (/api/v1/kpis).
Proporciona el resumen agregado de expedientes, win-rate, working capital e inmovilizado.
"""

import sqlite3
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from src import AMBITOS, AmbitoDesconocido
from src.api.schemas import KPISummarySchema, APIErrorResponse
from src.api.dependencies import get_db, trazabilidad_api
from src.memoria import Memoria

router = APIRouter(tags=["KPIs y Analítica"])


@router.get(
    "/kpis",
    response_model=KPISummarySchema,
    responses={
        200: {"model": KPISummarySchema, "description": "Resumen de KPIs ejecutivos del Funnel"},
        400: {"model": APIErrorResponse, "description": "Ámbito territorial no reconocido"},
        503: {"model": APIErrorResponse, "description": "Error calculando agregaciones en SQLite"}
    },
    summary="Resumen de KPIs Ejecutivos del Funnel Comercial",
    description="Calcula y agrega en tiempo real el resumen de expedientes, lotes por estado, win-rate, PBL acumulado y avales retenidos."
)
def get_kpi_summary(
    ambito: Optional[str] = Query(
        None,
        description=f"Ámbito territorial ({', '.join(sorted(AMBITOS))}). Sin valor, no filtra."
    ),
    db: sqlite3.Connection = Depends(get_db)
):
    """
    Retorna el resumen consolidado de KPIs ejecutivos para el Cockpit Visual (Capa 8).

    `ambito` llega **sin valor por defecto**: sin pedirlo, la API devuelve todo. Quien decide
    mostrar sólo Catalunya es la pantalla, con su interruptor puesto de inicio. Es lo
    contrario que `incluir_archivadas`, y a propósito: lo archivado es un concepto de negocio
    —qué está en el canal principal—, mientras el ámbito es una preferencia de quien mira.
    """
    try:
        memoria = Memoria()
        resumen_dict = memoria.obtener_resumen_kpis(ambito=ambito, conn=db)
        trazabilidad_api.registrar_evento(
            "API_KPIS_FETCHED",
            {"total_expedientes": resumen_dict.get("total_expedientes"),
             "total_lotes": resumen_dict.get("total_lotes"),
             "ambito": resumen_dict.get("ambito"),
             "version_ambito": resumen_dict.get("version_ambito")},
            estado="INFO"
        )
        return KPISummarySchema.model_validate(resumen_dict)
    except AmbitoDesconocido as e:
        # 400 y no 503, y desde luego no «devolver todo»: un ámbito mal escrito es un error
        # del que pide, y responder con la población entera bajo el rótulo equivocado sería
        # exactamente la degradación silenciosa que prohíbe la Convención C2.
        trazabilidad_api.registrar_evento(
            "API_KPIS_AMBITO_INVALIDO", {"ambito": ambito, "error": str(e)}, estado="WARNING"
        )
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        trazabilidad_api.registrar_evento("API_KPIS_FAILED", {"error": str(e)}, estado="ERROR")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Fallo calculando resumen de KPIs: {e}"
        )

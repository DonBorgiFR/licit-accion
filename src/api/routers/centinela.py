"""
src/api/routers/centinela.py — Router RESTful del Canal Proactivo Centinela (DOGC / BOPB)
Ecosistema Automático de Licitaciones (bfr_incoop)

Endpoints principales para la consulta paginada, filtrado por fuente y detalle completo
de las alertas de boletines oficiales detectadas en fase temprana (Capa 7).
"""

import math
import sqlite3
from typing import Optional
from fastapi import APIRouter, Depends, Query, HTTPException, status

from src.api.schemas import (AlertaBoletinSchema, PaginatedResponse, APIErrorResponse,
                             EstadoFuenteSchema, TransicionEstadoAlertaSchema)
from src.diagnostico import estado_de_las_fuentes
from src.api.dependencies import get_db, trazabilidad_api
from src.memoria import Memoria

router = APIRouter(prefix="/alertas-tempranas", tags=["Canal Proactivo Centinela"])


@router.get(
    "",
    response_model=PaginatedResponse[AlertaBoletinSchema],
    responses={
        200: {"model": PaginatedResponse[AlertaBoletinSchema], "description": "Listado paginado de alertas de boletín devuelto correctamente"},
        503: {"model": APIErrorResponse, "description": "Error al consultar la base de datos SQLite"}
    },
    summary="Listado Paginado de Alertas Tempranas de Boletines (DOGC/BOPB)",
    description="Permite buscar, paginar y filtrar alertas tempranas por texto, fuente oficial (DOGC/BOPB), score proactivo, categoría LCSP y estado."
)
def list_alertas_tempranas(
    page: int = Query(1, ge=1, description="Número de página actual (1-indexed)"),
    limit: int = Query(10, ge=1, le=100, description="Cantidad de alertas por página"),
    search: Optional[str] = Query(None, description="Búsqueda por texto en título, ID, órgano o municipio"),
    fuente: Optional[str] = Query(None, description="Filtrar por fuente oficial (DOGC o BOPB)"),
    min_score: Optional[int] = Query(None, ge=0, le=100, description="Score proactivo mínimo (0-100)"),
    categoria: Optional[str] = Query(None, description="Categoría de fase temprana (PRESUPUESTO, SUBVENCION, CONVENIO, CONSULTA_PRELIMINAR, OTROS)"),
    estado: Optional[str] = Query(None, description="Filtrar por estado operativo proactivo"),
    db: sqlite3.Connection = Depends(get_db)
):
    """
    Consulta paginada de alertas proactivas para el Cockpit Visual (Capa 8).
    """
    try:
        memoria = Memoria()
        items_dict, total_count = memoria.listar_alertas_boletin_paginadas(
            page=page,
            limit=limit,
            search=search,
            fuente=fuente,
            min_score=min_score,
            categoria=categoria,
            estado=estado,
            conn=db
        )
        
        # Validación fila a fila: una alerta corrupta se descarta y se audita, pero
        # NO invalida el resto de la página (ver nota equivalente en licitaciones.py).
        items_schema = []
        descartados = []
        for item in items_dict:
            try:
                items_schema.append(AlertaBoletinSchema.model_validate(item))
            except Exception as e_row:
                descartados.append({"id_alerta": item.get("id_alerta"), "error": str(e_row)})

        if descartados:
            trazabilidad_api.registrar_evento(
                "API_CENTINELA_ROWS_SKIPPED",
                {"page": page, "descartados": descartados},
                estado="WARNING"
            )

        total_pages = math.ceil(total_count / limit) if total_count > 0 else 0

        trazabilidad_api.registrar_evento(
            "API_CENTINELA_ALERTAS_LISTED",
            {"page": page, "limit": limit, "search": search, "fuente": fuente, "returned_items": len(items_schema),
             "total_count": total_count, "filas_descartadas": len(descartados)},
            estado="INFO"
        )
        
        return PaginatedResponse[AlertaBoletinSchema](
            items=items_schema,
            total=total_count,
            page=page,
            limit=limit,
            total_pages=total_pages
        )
    except Exception as e:
        trazabilidad_api.registrar_evento("API_CENTINELA_ALERTAS_LIST_FAILED", {"error": str(e)}, estado="ERROR")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Fallo en la consulta de alertas tempranas: {e}"
        )


# ORDEN IMPORTANTE: esta ruta se declara **antes** de `/{id_alerta:path}`. FastAPI resuelve
# por orden de declaracion y `:path` es un convertidor codicioso, asi que puesta despues
# `fuentes` se toma por un identificador de alerta y el endpoint devuelve un 404 con un
# mensaje que no tiene nada que ver. Ocurrio al escribirlo, el 2026-08-27.
@router.get(
    "/fuentes",
    response_model=list[EstadoFuenteSchema],
    summary="Qué pasó la última vez que se consultó cada fuente oficial",
    description="Permite distinguir en pantalla las tres causas de un canal vacío: que no haya "
                "novedades, que no se hayan podido consultar las fuentes, o que una fuente esté "
                "desactivada a propósito. Antes se veían las tres igual (H-45).",
)
def get_estado_fuentes():
    """H-45, cara pantalla: un canal vacío tiene que decir **por qué** lo está.

    Las fuentes esperadas salen de `config/centinela_config.yaml`, no de una lista escrita aquí:
    una fuente que se añada mañana al fichero tiene que aparecer sola, y si no consta ninguna
    consulta suya debe salir como `SIN_DATOS` en vez de no salir.
    """
    from src.centinela import IngestorBoletines

    esperadas = []
    try:
        esperadas = list(IngestorBoletines().config.get("fuentes_oficiales", {}).keys())
    except Exception as exc:
        # Sin la configuración se informa igual de lo que diga el rastro. Que no se pueda leer
        # el YAML no puede dejar la pantalla sin la mitad honesta que este endpoint aporta.
        trazabilidad_api.registrar_evento(
            "API_CENTINELA_FUENTES_SIN_CONFIG", {"error": str(exc)}, estado="WARNING"
        )

    fuentes = estado_de_las_fuentes(fuentes_esperadas=esperadas)
    trazabilidad_api.registrar_evento(
        "API_CENTINELA_FUENTES",
        {"total": len(fuentes), "degradadas": sum(1 for f in fuentes if f.estado != "OK")},
        estado="INFO",
    )
    return [EstadoFuenteSchema.model_validate(f) for f in fuentes]


@router.get(
    "/{id_alerta:path}",
    response_model=AlertaBoletinSchema,
    responses={
        200: {"model": AlertaBoletinSchema, "description": "Detalle completo de la alerta de boletín"},
        404: {"model": APIErrorResponse, "description": "Alerta temprana no encontrada"},
        503: {"model": APIErrorResponse, "description": "Error al consultar la base de datos SQLite"}
    },
    summary="Detalle Completo de una Alerta Temprana de Boletín",
    description="Recupera una alerta de fase temprana por su identificador único (id_alerta SHA256), incluyendo motivos de scoring y dictamen IA."
)
def get_alerta_by_id(
    id_alerta: str,
    db: sqlite3.Connection = Depends(get_db)
):
    """
    Retorna la información completa de una alerta temprana de boletín.
    """
    try:
        memoria = Memoria()
        alerta_dict = memoria.obtener_alerta_boletin_completa(id_alerta=id_alerta, conn=db)
        
        if not alerta_dict:
            trazabilidad_api.registrar_evento("API_CENTINELA_ALERTA_NOT_FOUND", {"id_alerta": id_alerta}, estado="WARNING")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Alerta temprana con ID '{id_alerta}' no encontrada en el sistema."
            )
            
        trazabilidad_api.registrar_evento("API_CENTINELA_ALERTA_FETCHED", {"id_alerta": id_alerta}, estado="INFO")
        return AlertaBoletinSchema.model_validate(alerta_dict)
        
    except HTTPException:
        raise
    except Exception as e:
        trazabilidad_api.registrar_evento("API_CENTINELA_ALERTA_FETCH_FAILED", {"id_alerta": id_alerta, "error": str(e)}, estado="ERROR")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Fallo obteniendo detalle de la alerta '{id_alerta}': {e}"
        )


@router.put(
    "/{id_alerta:path}/estado",
    response_model=AlertaBoletinSchema,
    responses={
        200: {"model": AlertaBoletinSchema, "description": "Estado y/o notas de la alerta temprana actualizadas correctamente"},
        400: {"model": APIErrorResponse, "description": "Estado solicitado no válido para la transición"},
        404: {"model": APIErrorResponse, "description": "Alerta temprana no encontrada"},
        503: {"model": APIErrorResponse, "description": "Error al actualizar la base de datos SQLite"}
    },
    summary="Mutación Transaccional del Estado de una Alerta Temprana",
    description="Actualiza el estado operativo y/o las notas de seguimiento de una alerta proactiva de boletín oficial con auditoría JSONL."
)
def update_alerta_estado(
    id_alerta: str,
    payload: TransicionEstadoAlertaSchema,
    db: sqlite3.Connection = Depends(get_db)
):
    """
    Actualiza el estado proactivo y notas de una alerta de boletín.
    """
    try:
        memoria = Memoria()
        exito, estado_anterior, alerta_dict = memoria.mutar_estado_alerta_boletin_transaccional(
            id_alerta=id_alerta,
            nuevo_estado=payload.nuevo_estado,
            notas=payload.notas,
            conn=db
        )

        if not exito:
            trazabilidad_api.registrar_evento("API_CENTINELA_ALERTA_MUTATE_NOT_FOUND", {"id_alerta": id_alerta}, estado="WARNING")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Alerta temprana con ID '{id_alerta}' no encontrada en el sistema."
            )

        trazabilidad_api.registrar_evento(
            "API_CENTINELA_ALERTA_MUTATED",
            {
                "id_alerta": id_alerta,
                "estado_anterior": estado_anterior,
                "nuevo_estado": payload.nuevo_estado,
                "notas_actualizadas": payload.notas is not None
            },
            estado="INFO"
        )

        return AlertaBoletinSchema.model_validate(alerta_dict)

    except HTTPException:
        raise
    except Exception as e:
        trazabilidad_api.registrar_evento("API_CENTINELA_ALERTA_MUTATE_FAILED", {"id_alerta": id_alerta, "error": str(e)}, estado="ERROR")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Fallo al actualizar la alerta temprana '{id_alerta}': {e}"
        )



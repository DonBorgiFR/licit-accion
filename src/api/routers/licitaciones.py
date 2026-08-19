"""
src/api/routers/licitaciones.py — Router RESTful del Funnel Reactivo PSCP / PCSP
Ecosistema Automático de Licitaciones (bfr_incoop)

Endpoints principales para la consulta paginada, filtrado multinivel y detalle completo
de las licitaciones públicas procesadas por el Radar, Filtro y Analista IA (Capa 7).
"""

import math
import sqlite3
from typing import Optional
from fastapi import APIRouter, Depends, Query, HTTPException, status

from src import AMBITOS, AmbitoDesconocido
from src.api.schemas import LicitacionSchema, PaginatedResponse, APIErrorResponse, TransicionEstadoLicitacionSchema
from src.api.dependencies import get_db, trazabilidad_api
from src.memoria import Memoria

router = APIRouter(prefix="/licitaciones", tags=["Funnel Licitaciones PSCP"])


@router.get(
    "",
    response_model=PaginatedResponse[LicitacionSchema],
    responses={
        200: {"model": PaginatedResponse[LicitacionSchema], "description": "Listado paginado de licitaciones devuelto correctamente"},
        400: {"model": APIErrorResponse, "description": "Ámbito territorial no reconocido"},
        503: {"model": APIErrorResponse, "description": "Error al consultar la base de datos SQLite"}
    },
    summary="Listado Paginado y Filtrable de Licitaciones (PSCP/PCSP)",
    description="Permite buscar, paginar y filtrar licitaciones por término de texto, score comercial mínimo, PMP máximo de ayuntamiento, subrogación y estado."
)
def list_licitaciones(
    page: int = Query(1, ge=1, description="Número de página actual (1-indexed)"),
    limit: int = Query(10, ge=1, le=100, description="Cantidad de expedientes por página"),
    search: Optional[str] = Query(None, description="Búsqueda por texto en título, ID, órgano o localidad"),
    min_score: Optional[int] = Query(None, ge=0, le=100, description="Score comercial mínimo (0-100)"),
    pmp_max: Optional[int] = Query(None, description="PMP máximo del municipio (días)"),
    subrogacion_critica: Optional[bool] = Query(None, description="Filtrar por presencia de subrogación de personal"),
    estado: Optional[str] = Query(None, description="Filtrar por estado operativo del lote"),
    incluir_archivadas: bool = Query(
        False,
        description="Incluir los expedientes que el Depurador sacó del canal principal (auditoría y rescate)"
    ),
    ambito: Optional[str] = Query(
        None,
        description=f"Ámbito territorial ({', '.join(sorted(AMBITOS))}). Sin valor, no filtra."
    ),
    db: sqlite3.Connection = Depends(get_db)
):
    """
    Consulta paginada de expedientes con filtrado multinivel para el Cockpit Visual (Capa 8).

    `incluir_archivadas` es la única vía desde la interfaz para llegar a lo archivado. Por
    defecto no se incluyen: el Funnel decide a qué concurso presentarse y no debe arrastrar
    histórico. Las filas devueltas viajan marcadas con `archivada` (Capa 9, H-32).

    `ambito` filtra por territorio (H-47) y **llega sin valor por defecto**: sin pedirlo, la
    API devuelve todo. Quien decide mostrar sólo Catalunya es la pantalla, con el interruptor
    puesto de inicio. Es deliberadamente lo contrario que `incluir_archivadas`, porque lo
    archivado es un concepto de negocio y el ámbito una preferencia de quien mira.
    """
    try:
        memoria = Memoria()
        items_dict, total_count = memoria.listar_expedientes_paginados(
            page=page,
            limit=limit,
            search=search,
            min_score=min_score,
            pmp_max=pmp_max,
            subrogacion_critica=subrogacion_critica,
            estado=estado,
            incluir_archivadas=incluir_archivadas,
            ambito=ambito,
            conn=db
        )
        
        # Validación fila a fila: un registro corrupto se descarta y se audita, pero
        # NO invalida el resto de la página. Antes, al validarse dentro de una
        # comprensión de lista, un único expediente defectuoso devolvía 503 y dejaba
        # al equipo sin ver ninguna licitación del funnel.
        items_schema = []
        descartados = []
        for item in items_dict:
            try:
                items_schema.append(LicitacionSchema.model_validate(item))
            except Exception as e_row:
                descartados.append({"id": item.get("id"), "error": str(e_row)})

        if descartados:
            trazabilidad_api.registrar_evento(
                "API_LICITACIONES_ROWS_SKIPPED",
                {"page": page, "descartados": descartados},
                estado="WARNING"
            )

        total_pages = math.ceil(total_count / limit) if total_count > 0 else 0

        trazabilidad_api.registrar_evento(
            "API_LICITACIONES_LISTED",
            {"page": page, "limit": limit, "search": search, "returned_items": len(items_schema),
             "total_count": total_count, "filas_descartadas": len(descartados),
             "incluir_archivadas": incluir_archivadas, "ambito": ambito},
            estado="INFO"
        )
        
        return PaginatedResponse[LicitacionSchema](
            items=items_schema,
            total=total_count,
            page=page,
            limit=limit,
            total_pages=total_pages
        )
    except AmbitoDesconocido as e:
        # 400 y no 503, y desde luego no «devolver todo»: un ámbito mal escrito es un error
        # del que pide, y responder con la población entera bajo el rótulo equivocado sería
        # exactamente la degradación silenciosa que prohíbe la Convención C2.
        trazabilidad_api.registrar_evento(
            "API_LICITACIONES_AMBITO_INVALIDO", {"ambito": ambito, "error": str(e)}, estado="WARNING"
        )
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        trazabilidad_api.registrar_evento("API_LICITACIONES_LIST_FAILED", {"error": str(e)}, estado="ERROR")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Fallo en la consulta de licitaciones: {e}"
        )


@router.get(
    "/{id:path}",
    response_model=LicitacionSchema,
    responses={
        200: {"model": LicitacionSchema, "description": "Detalle completo de la licitación y sus lotes"},
        404: {"model": APIErrorResponse, "description": "Licitación no encontrada en la base de datos"},
        503: {"model": APIErrorResponse, "description": "Error al consultar la base de datos SQLite"}
    },
    summary="Detalle Completo de un Expediente de Licitación",
    description="Recupera un expediente por su identificador único (ID), incluyendo todos sus lotes asociados y el dictamen cualitativo de la IA."
)
def get_licitacion_by_id(
    id: str,
    db: sqlite3.Connection = Depends(get_db)
):
    """
    Retorna la información completa de una licitación concreta.
    """
    try:
        memoria = Memoria()
        exp_dict = memoria.obtener_expediente_completo(expediente_id=id, conn=db)
        
        if not exp_dict:
            trazabilidad_api.registrar_evento("API_LICITACION_NOT_FOUND", {"id": id}, estado="WARNING")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Licitación con ID '{id}' no encontrada en el sistema."
            )
            
        trazabilidad_api.registrar_evento("API_LICITACION_FETCHED", {"id": id}, estado="INFO")
        return LicitacionSchema.model_validate(exp_dict)
        
    except HTTPException:
        raise
    except Exception as e:
        trazabilidad_api.registrar_evento("API_LICITACION_FETCH_FAILED", {"id": id, "error": str(e)}, estado="ERROR")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Fallo obteniendo detalle de la licitación '{id}': {e}"
        )


@router.put(
    "/{id:path}/estado",
    response_model=LicitacionSchema,
    responses={
        200: {"model": LicitacionSchema, "description": "Estado y/o notas de la licitación actualizadas correctamente"},
        400: {"model": APIErrorResponse, "description": "Estado solicitado no válido para la transición"},
        404: {"model": APIErrorResponse, "description": "Licitación o lote no encontrado"},
        503: {"model": APIErrorResponse, "description": "Error al actualizar la base de datos SQLite"}
    },
    summary="Mutación Transaccional del Estado de una Licitación",
    description="Actualiza el estado operativo y/o las notas internas de una licitación/lote con validación de la Máquina de Estados y auditoría JSONL."
)
def update_licitacion_estado(
    id: str,
    payload: TransicionEstadoLicitacionSchema,
    lote_numero: Optional[int] = Query(None, ge=1, description="Compatibilidad temporal: preferir lote_numero en el cuerpo"),
    db: sqlite3.Connection = Depends(get_db)
):
    """
    Actualiza el estado operativo y notas de una licitación/lote.
    """
    try:
        memoria = Memoria()
        lote_objetivo = lote_numero if lote_numero is not None else payload.lote_numero
        exito, estado_anterior, exp_dict = memoria.mutar_estado_lote_transaccional(
            expediente_id=id,
            lote_numero=lote_objetivo,
            nuevo_estado=payload.nuevo_estado,
            notas=payload.notas,
            conn=db
        )

        if not exito:
            trazabilidad_api.registrar_evento("API_LICITACION_MUTATE_NOT_FOUND", {"id": id, "lote_numero": lote_objetivo}, estado="WARNING")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Licitación con ID '{id}' (Lote {lote_objetivo}) no encontrada en el sistema."
            )

        trazabilidad_api.registrar_evento(
            "API_LICITACION_MUTATED",
            {
                "expediente_id": id,
                "lote_numero": lote_objetivo,
                "estado_anterior": estado_anterior,
                "nuevo_estado": payload.nuevo_estado,
                "notas_actualizadas": payload.notas is not None
            },
            estado="INFO"
        )

        return LicitacionSchema.model_validate(exp_dict)

    except HTTPException:
        raise
    except Exception as e:
        trazabilidad_api.registrar_evento("API_LICITACION_MUTATE_FAILED", {"id": id, "error": str(e)}, estado="ERROR")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Fallo al actualizar el estado de la licitación '{id}': {e}"
        )

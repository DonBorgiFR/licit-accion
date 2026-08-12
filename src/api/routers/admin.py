"""
src/api/routers/admin.py — Router Administrativo de Lectura (Capa 9, Paso 7)

Los cuatro endpoints con los que se **mira antes de decidir**. Ninguno altera estado: son
la mitad honesta de la purga en dos tiempos que exige el diseño de la capa —previsualizar y
sólo entonces confirmar—, y sin ellos el Paso 8 sería un botón que borra a ciegas.

Una excepción de matiz: `/purga/previsualizacion` no cambia ni un dato, pero **no es
anónima**. Emite `DEPURADOR_PURGA_PREVISUALIZADA` porque el contrato pide que conste quién
miró: en una operación irreversible, saber quién la estudió y cuándo forma parte del rastro.
"""

import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Query, status

from src import normalizar_estado_operativo
from src.api.dependencies import get_db, trazabilidad_api
from src.api.schemas import (
    AlmacenamientoSchema,
    APIErrorResponse,
    EjecucionSchema,
    EstadoLicitacionEnum,
    PaginatedResponse,
    PoliticaRetencionSchema,
    PrevisualizacionPurgaSchema,
    PurgaDocumentalPreviaSchema,
)
from src.depurador import Depurador, medir_almacenamiento
from src.memoria import Memoria
from src.retencion import PoliticaRetencionInvalida, cargar_politica

router = APIRouter(prefix="/admin", tags=["Administración y Depurador"])

#: Grafía canónica de cada estado, indexada por su forma normalizada. La política guarda los
#: estados en minúsculas porque **toda comparación se hace normalizada** (H-27), pero servir
#: esa forma a la interfaz pintaría "nueva" junto a los "Nueva" del Funnel. La fuente de la
#: grafía visible es el enum, no una capitalización improvisada: `Anulada_Administracion`
#: tiene dos mayúsculas y `.capitalize()` se comería la segunda.
_GRAFIA_CANONICA = {normalizar_estado_operativo(e.value): e.value for e in EstadoLicitacionEnum}


def _politica_o_503():
    """Carga la política y traduce su ausencia al error tipado del contrato.

    `PoliticaRetencionInvalida` es 503 y no 500: no es un fallo del servidor sino una
    negativa deliberada a operar sin criterio declarado. Nunca se sustituye por plazos
    por defecto (lección de H-18).
    """
    try:
        return cargar_politica()
    except PoliticaRetencionInvalida as exc:
        trazabilidad_api.registrar_evento(
            "API_ADMIN_POLITICA_INVALIDA", {"error": str(exc)}, estado="ERROR"
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Política de retención no utilizable, de modo que no se purga nada: {exc}",
        )


@router.get(
    "/almacenamiento",
    response_model=AlmacenamientoSchema,
    responses={503: {"model": APIErrorResponse, "description": "No se pudo inspeccionar el disco"}},
    summary="Cuánto ocupa cada cosa",
    description="Inventario en bytes de la base, los pliegos descargados, las copias de "
                "seguridad y el registro de trazabilidad, distinguiendo lo purgable de lo "
                "que no lo es. La base de datos nunca es purgable: sus filas son la memoria "
                "comercial.",
)
def get_almacenamiento():
    try:
        medicion = medir_almacenamiento()
        trazabilidad_api.registrar_evento("API_ADMIN_ALMACENAMIENTO", medicion, estado="INFO")
        return AlmacenamientoSchema.model_validate(medicion)
    except OSError as exc:
        trazabilidad_api.registrar_evento(
            "API_ADMIN_ALMACENAMIENTO_FAILED", {"error": str(exc)}, estado="ERROR"
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"No se pudo inspeccionar el almacenamiento: {exc}",
        )


@router.get(
    "/retencion",
    response_model=PoliticaRetencionSchema,
    responses={503: {"model": APIErrorResponse, "description": "Política ausente o incoherente"}},
    summary="Política de retención vigente y su versión",
    description="Devuelve los plazos bajo los que se ejecutaría una purga hoy. Un bloque "
                "ausente significa que esa operación no se ejecuta, nunca que se ejecute "
                "con un plazo por defecto.",
)
def get_retencion():
    politica = _politica_o_503()

    archivado = None
    if politica.archivado:
        archivado = {
            "dias_tras_fecha_limite": politica.archivado.dias_tras_fecha_limite,
            "estados_archivables": [
                _GRAFIA_CANONICA.get(estado, estado)
                for estado in politica.archivado.estados_archivables
            ],
            "archivar_expediente_con_todos_sus_lotes":
                politica.archivado.archivar_expediente_con_todos_sus_lotes,
        }

    return PoliticaRetencionSchema.model_validate(
        {
            "version": politica.version,
            "documentos_dias": politica.documentos_dias,
            "backups_dias": politica.backups_dias,
            "archivado": archivado,
            "eliminacion": politica.eliminacion.__dict__ if politica.eliminacion else None,
        }
    )


@router.get(
    "/purga/previsualizacion",
    response_model=PrevisualizacionPurgaSchema,
    responses={503: {"model": APIErrorResponse, "description": "Política ausente o incoherente"}},
    summary="Qué desaparecería si se purgara ahora",
    description="Ensayo completo de las dos purgas sin ejecutar ninguna: los documentos que "
                "perderían fichero y texto, y los expedientes eliminables **junto a los "
                "protegidos con su motivo**. No altera nada, pero deja constancia de la "
                "consulta.",
)
def get_previsualizacion_purga(
    solicitado_por: str = Query("cockpit", description="Quién realiza la consulta, para el rastro"),
):
    politica = _politica_o_503()
    depurador = Depurador(memoria=Memoria(), politica=politica)

    documental = depurador.previsualizar_purga_documental()
    eliminacion = depurador.previsualizar_eliminacion(solicitado_por=solicitado_por)

    # Una degradación en cualquiera de las dos mitades se dice, no se disfraza de cero
    # (Convención C2): "no hay nada que purgar" y "no he podido mirar" son cosas distintas.
    degradado = documental.motivo_degradacion or eliminacion.motivo_degradacion

    return PrevisualizacionPurgaSchema(
        version_politica=politica.version,
        documental=PurgaDocumentalPreviaSchema(
            documentos_candidatos=documental.documentos_purgados,
            ficheros_en_disco=documental.ficheros_borrados,
            bytes_estimados=documental.bytes_liberados,
            corte_utc=documental.corte_utc,
        ),
        eliminables=eliminacion.eliminables,
        bloqueados=eliminacion.bloqueados,
        degradado=degradado,
    )


@router.get(
    "/ejecuciones",
    response_model=PaginatedResponse[EjecucionSchema],
    responses={503: {"model": APIErrorResponse, "description": "Error consultando el historial"}},
    summary="Historial de prospecciones con sus métricas",
    description="Qué encontró cada corrida del pipeline: expedientes nuevos y actualizados, "
                "lotes evaluados, documentos descargados, análisis realizados, alertas y "
                "errores, con la versión de scoring y de política bajo la que se ejecutó. "
                "Más reciente primero.",
)
def get_ejecuciones(
    page: int = Query(1, ge=1, description="Número de página (1-indexed)"),
    limit: int = Query(25, ge=1, le=100, description="Registros por página"),
    db: sqlite3.Connection = Depends(get_db),
):
    try:
        items, total = Memoria().listar_ejecuciones(page=page, limit=limit)
    except sqlite3.Error as exc:
        trazabilidad_api.registrar_evento(
            "API_ADMIN_EJECUCIONES_FAILED", {"error": str(exc)}, estado="ERROR"
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Fallo consultando el historial de ejecuciones: {exc}",
        )

    total_pages = (total + limit - 1) // limit if total else 0
    trazabilidad_api.registrar_evento(
        "API_ADMIN_EJECUCIONES", {"page": page, "limit": limit, "total": total}, estado="INFO"
    )
    return PaginatedResponse[EjecucionSchema](
        items=[EjecucionSchema.model_validate(item) for item in items],
        total=total,
        page=page,
        limit=limit,
        total_pages=total_pages,
    )

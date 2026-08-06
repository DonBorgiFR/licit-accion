"""
src/api/routers/health.py — Router RESTful de Autodiagnóstico y Salud
Ecosistema Automático de Licitaciones (bfr_incoop)

Endpoint principal de monitoreo operativo (/api/v1/health). Evalúa el estado del servidor
API, el modo WAL de SQLite v5, la integridad del esquema relacional y el acceso a disco.
"""

from fastapi import APIRouter, Response, status
from src.api.schemas import HealthResponseSchema, APIErrorResponse
from src.api.dependencies import healthcheck_api_dependencies

router = APIRouter(tags=["Salud y Autodiagnóstico"])


@router.get(
    "/health",
    response_model=HealthResponseSchema,
    responses={
        200: {"model": HealthResponseSchema, "description": "Sistema plenamente operativo (SQLite WAL activo)"},
        503: {"model": HealthResponseSchema, "description": "Servicio degradado o no disponible (Fallo en SQLite/WAL)"}
    },
    summary="Autodiagnóstico del Servidor API y SQLite v5 WAL",
    description="Evalúa la conectividad, permisos de escritura en disco, modo WAL e integridad del esquema relacional SQLite v5."
)
def get_health(response: Response):
    """
    Ejecuta el autodiagnóstico de dependencias de la API.
    Retorna 200 OK si status == 'OK', o 503 Service Unavailable si status == 'ERROR'.
    """
    diagnostico = healthcheck_api_dependencies()
    health_data = HealthResponseSchema.model_validate(diagnostico)
    
    if diagnostico.get("status") != "OK":
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        
    return health_data

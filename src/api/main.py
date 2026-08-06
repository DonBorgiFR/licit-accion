"""
src/api/main.py — Aplicación Principal FastAPI (Pasarela API RESTful)
Ecosistema Automático de Licitaciones (bfr_incoop)

Servidor de aplicación local-first en Python que expone la API RESTful para conectar
el Cockpit Visual (Capa 8) con la base de datos de persistencia SQLite v5 en modo WAL.
"""

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from datetime import datetime, timezone
from fastapi import FastAPI, Request, HTTPException, status
from fastapi.responses import JSONResponse
from fastapi.exception_handlers import http_exception_handler

from fastapi.middleware.cors import CORSMiddleware
from src.api.schemas import APIErrorResponse
from src.api.dependencies import APIDependencyError, trazabilidad_api
from src.api.middleware import TrazabilidadMiddleware
from src.api.routers import health, kpis, licitaciones, centinela


from contextlib import asynccontextmanager
from src.memoria import Memoria


# ==============================================================================
# Evento Lifespan de Inicialización / Auto-Migración de BD
# ==============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Asegura que la BD local SQLite está creada y migrada al esquema v5 al arrancar la API."""
    try:
        Memoria().setup_db()
    except Exception as e:
        print(f"[!] Advertencia en setup_db durante arranque de la API: {e}")
    yield


# ==============================================================================
# Instanciación de la Aplicación FastAPI
# ==============================================================================

app = FastAPI(
    title="Incoop Licitaciones API",
    description="Pasarela RESTful de Micro-Servicios para el Ecosistema Automático de Licitaciones (bfr_incoop)",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan
)

# Configuración de Middlewares de Seguridad y Trazabilidad
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(TrazabilidadMiddleware)


# ==============================================================================
# Manejadores Globales de Excepciones
# ==============================================================================

@app.exception_handler(HTTPException)
async def custom_http_exception_handler(request: Request, exc: HTTPException):
    """Preserva la propagación limpia de HTTPExceptions hacia el cliente."""
    return await http_exception_handler(request, exc)

@app.exception_handler(APIDependencyError)
async def api_dependency_exception_handler(request: Request, exc: APIDependencyError):
    """Manejador para errores de dependencias y base de datos de la API."""
    error_payload = APIErrorResponse(
        error_code="DATABASE_ERROR",
        message="Fallo operativo en la base de datos local SQLite.",
        details={"path": str(request.url), "error": str(exc)}
    )
    trazabilidad_api.registrar_evento(
        "API_EXCEPTION_DATABASE",
        {"path": str(request.url), "error": str(exc)},
        estado="ERROR"
    )
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content=error_payload.model_dump()
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Manejador defensivo global para excepciones no capturadas."""
    error_payload = APIErrorResponse(
        error_code="INTERNAL_SERVER_ERROR",
        message="Se ha producido un error interno no controlado en el servidor API.",
        details={"path": str(request.url), "error": str(exc)}
    )
    trazabilidad_api.registrar_evento(
        "API_EXCEPTION_UNHANDLED",
        {"path": str(request.url), "error": str(exc)},
        estado="ERROR"
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=error_payload.model_dump()
    )


# ==============================================================================
# Registro de Routers
# ==============================================================================

app.include_router(health.router, prefix="/api/v1")
app.include_router(kpis.router, prefix="/api/v1")
app.include_router(licitaciones.router, prefix="/api/v1")
app.include_router(centinela.router, prefix="/api/v1")


# ==============================================================================
# Endpoint Raíz de Bienvenida
# ==============================================================================

@app.get("/", tags=["General"], summary="Información del Servidor API")
def read_root():
    """Retorna información básica de bienvenida y enlace a la documentación Swagger."""
    return {
        "app": "Incoop Licitaciones API",
        "version": "1.0.0",
        "status": "online",
        "docs_url": "/docs",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

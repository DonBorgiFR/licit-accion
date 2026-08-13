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

import os
from datetime import datetime, timezone
from fastapi import FastAPI, Request, HTTPException, status
from fastapi.responses import FileResponse, JSONResponse
from fastapi.exception_handlers import http_exception_handler
from fastapi.staticfiles import StaticFiles

from fastapi.middleware.cors import CORSMiddleware
from src import ruta_proyecto
from src.api.schemas import APIErrorResponse
from src.api.dependencies import APIDependencyError, trazabilidad_api
from src.api.middleware import TrazabilidadMiddleware
from src.api.routers import admin, health, kpis, licitaciones, centinela


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
app.include_router(admin.router, prefix="/api/v1")


# ==============================================================================
# Endpoint de Bienvenida de la API
# ==============================================================================
#
# ⚠️ CAMBIO DE CONTRATO DE LA CAPA 7, introducido por la Capa 10 Paso 4 (2026-08-13).
#
# Este JSON vivía en la raíz `/`. Ahora la raíz sirve el Cockpit, porque servir el bundle
# desde FastAPI elimina Node.js y un segundo servidor de cada PC de la cooperativa. El JSON
# se conserva íntegro aquí, bajo el prefijo que le corresponde.
#
# Se declaró por adelantado en `.agents/CONTRATO_CAPA_10.md` en vez de descubrirse: es un
# cambio visible para cualquier cliente de la API.

@app.get("/api/v1/", tags=["General"], summary="Información del Servidor API")
def read_root():
    """Retorna información básica de bienvenida y enlace a la documentación Swagger."""
    return {
        "app": "Incoop Licitaciones API",
        "version": "1.0.0",
        "status": "online",
        "docs_url": "/docs",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


# ==============================================================================
# El Cockpit servido por FastAPI (Capa 10, Paso 4)
# ==============================================================================
#
# Se registra AL FINAL del fichero a propósito, y no es un detalle de estilo: Starlette
# resuelve las rutas por orden de registro, así que montar los estáticos en `/` antes de
# los routers se tragaría `/api/v1/*`, `/docs` y `/openapi.json` sin avisar. El orden ES
# la protección, y por eso la regresión que lo cubre no comprueba que el Cockpit se sirva,
# sino que la documentación de la API sigue viva después de montarlo.

#: Prefijos que NUNCA se reenvían al Cockpit. Un reenvío en bloque convertiría una errata
#: como `/api/v1/licitacionse` en un **200 con HTML** en lugar de un 404: la aplicación
#: contestaría que todo va bien mientras el cliente no recibe ni un dato. Es la familia de
#: H-21, H-22 y H-23 —no rompe, miente— y la razón de que el reenvío vaya acotado.
PREFIJOS_RESERVADOS = ("api/", "docs", "redoc", "openapi.json", "favicon.ico")


def _directorio_bundle() -> str:
    """Ruta del Cockpit compilado, anclada a la raíz del proyecto (lección de H-18)."""
    return ruta_proyecto(os.path.join("frontend", "dist"))


def _hay_bundle() -> bool:
    return os.path.isfile(os.path.join(_directorio_bundle(), "index.html"))


#: Diagnóstico único para el bundle ausente. Es el primer síntoma que verá quien clone el
#: repositorio sin compilar, y merece decir qué hacer en vez de un 404 desnudo.
DIAGNOSTICO_SIN_BUNDLE = {
    "error_code": "COCKPIT_NO_COMPILADO",
    "message": (
        "El Cockpit no está compilado: falta frontend/dist/index.html. "
        "Ejecutar «npm install && npm run build» dentro de frontend/. "
        "Node.js hace falta para compilar, no para usar el sistema."
    ),
    "details": {"ruta_esperada": os.path.join("frontend", "dist", "index.html")},
}


@app.get("/", include_in_schema=False)
def servir_cockpit():
    """La raíz sirve el Cockpit. El JSON de bienvenida vive ahora en `/api/v1/`."""
    if not _hay_bundle():
        return JSONResponse(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                            content=DIAGNOSTICO_SIN_BUNDLE)
    return FileResponse(os.path.join(_directorio_bundle(), "index.html"))


if _hay_bundle():
    # `html=True` resuelve `index.html` en las peticiones de directorio. El montaje sólo
    # se hace si el bundle existe: `StaticFiles` con `check_dir=True` reventaría al
    # importar el módulo, convirtiendo "falta compilar" en "la API no arranca".
    app.mount("/", StaticFiles(directory=_directorio_bundle(), html=True), name="cockpit")
else:
    @app.get("/{ruta_spa:path}", include_in_schema=False)
    def cockpit_no_compilado(ruta_spa: str):
        """Sin bundle, cualquier ruta del Cockpit explica qué falta — salvo las de la API,
        que siguen contestando su propio 404 y no un diagnóstico de compilación."""
        if ruta_spa.startswith(PREFIJOS_RESERVADOS):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recurso no encontrado")
        return JSONResponse(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                            content=DIAGNOSTICO_SIN_BUNDLE)

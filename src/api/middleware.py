"""
src/api/middleware.py — Middlewares de Trazabilidad HTTP y Seguridad
Ecosistema Automático de Licitaciones (bfr_incoop)

Proporciona el middleware custom TrazabilidadMiddleware para:
- Asignar e inyectar un identificador X-Request-ID (UUIDv4) en respuestas HTTP.
- Medir la latencia de procesamiento de peticiones en milisegundos.
- Registrar eventos deterministas API_HTTP_REQUEST_PROCESSED en data/pipeline.jsonl.
"""

import time
import uuid
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from src.api.dependencies import trazabilidad_api


class TrazabilidadMiddleware(BaseHTTPMiddleware):
    """
    Middleware global para medir tiempos de respuesta y auditar peticiones HTTP en pipeline.jsonl.
    """
    async def dispatch(self, request: Request, call_next) -> Response:
        start_time = time.perf_counter()
        
        request_id = request.headers.get("X-Request-ID")
        if not request_id:
            request_id = str(uuid.uuid4())
            
        response: Response = await call_next(request)
        
        latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
        response.headers["X-Request-ID"] = request_id
        
        client_host = request.client.host if request.client else "unknown"
        
        trazabilidad_api.registrar_evento(
            "API_HTTP_REQUEST_PROCESSED",
            {
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "client_host": client_host,
                "latency_ms": latency_ms
            },
            estado="INFO" if response.status_code < 400 else ("WARNING" if response.status_code < 500 else "ERROR")
        )
        
        return response

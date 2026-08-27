"""
src/api/routers/admin.py — Router Administrativo de Lectura (Capa 9, Paso 7)

Los cuatro endpoints con los que se **mira antes de decidir**. Ninguno altera estado: son
la mitad honesta de la purga en dos tiempos que exige el diseño de la capa —previsualizar y
sólo entonces confirmar—, y sin ellos el Paso 8 sería un botón que borra a ciegas.

Una excepción de matiz: `/purga/previsualizacion` no cambia ni un dato, pero **no es
anónima**. Emite `DEPURADOR_PURGA_PREVISUALIZADA` porque el contrato pide que conste quién
miró: en una operación irreversible, saber quién la estudió y cuándo forma parte del rastro.
"""

import os
import secrets
import signal
import sqlite3
import threading
import time
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field

from src import normalizar_estado_operativo
from src.diagnostico import diagnosticar
from src.lanzador import leer_marca_servidor
from src.api.dependencies import get_db, trazabilidad_api
from src.api.schemas import (
    AlmacenamientoSchema,
    APIErrorResponse,
    DiagnosticoProspeccionSchema,
    EjecucionSchema,
    EstadoLicitacionEnum,
    PaginatedResponse,
    PoliticaRetencionSchema,
    PrevisualizacionPurgaSchema,
    PurgaDocumentalPreviaSchema,
    ResultadoBackupSchema,
    ResultadoPurgaSchema,
    SolicitudPurgaSchema,
    SolicitudRescateSchema,
)
from src.depurador import (
    ConfirmacionRequerida,
    CopiaSeguridadFallida,
    Depurador,
    PurgaBloqueadaPorIntegridad,
    medir_almacenamiento,
)
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


# =======================================================================================
# Mutación (Capa 9, Paso 8)
#
# Aquí empieza lo que sí altera. Las precondiciones del motor no se relajan al exponerlo:
# la confirmación viaja en el cuerpo y no tiene valor por defecto, la lista de expedientes
# nunca se deduce, y cada error tipado del contrato tiene su código HTTP.
# =======================================================================================

@router.post(
    "/purga",
    response_model=ResultadoPurgaSchema,
    responses={
        400: {"model": APIErrorResponse, "description": "Falta la confirmación explícita"},
        409: {"model": APIErrorResponse, "description": "Integridad referencial"},
        503: {"model": APIErrorResponse, "description": "Modo degradado: política o copia de seguridad"},
    },
    summary="Ejecuta una purga",
    description="`tipo='documental'` libera peso en disco y no toca ninguna fila de negocio. "
                "`tipo='eliminacion'` borra expedientes que nunca llegaron a ser negocio, "
                "exige la lista explícita y crea una copia de seguridad previa. Los "
                "expedientes protegidos se devuelven con su motivo, no se silencian.",
)
def post_purga(solicitud: SolicitudPurgaSchema):
    if not solicitud.confirmar:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La purga exige confirmación explícita. Previsualice primero en "
                   "GET /api/v1/admin/purga/previsualizacion.",
        )

    politica = _politica_o_503()
    depurador = Depurador(memoria=Memoria(), politica=politica)

    if solicitud.tipo == "documental":
        resultado = depurador.purgar_documentos(solicitado_por=solicitud.solicitado_por)
        trazabilidad_api.registrar_evento(
            "API_ADMIN_PURGA_DOCUMENTAL",
            {"ejecutado": resultado.ejecutado, "documentos": resultado.documentos_purgados,
             "bytes": resultado.bytes_liberados, "solicitado_por": solicitud.solicitado_por},
            estado="INFO" if resultado.ejecutado else "ERROR",
        )
        if not resultado.ejecutado:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Purga documental no ejecutada: {resultado.motivo_degradacion}",
            )
        return ResultadoPurgaSchema(
            ejecutado=True,
            tipo="documental",
            version_politica=resultado.version_politica,
            documentos_purgados=resultado.documentos_purgados,
            ficheros_borrados=resultado.ficheros_borrados,
            bytes_liberados=resultado.bytes_liberados,
        )

    if not solicitud.expedientes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La eliminación exige la lista explícita de expedientes. Nunca se deduce.",
        )

    try:
        resultado = depurador.eliminar_expedientes(
            solicitud.expedientes, confirmado=True, solicitado_por=solicitud.solicitado_por
        )
    except ConfirmacionRequerida as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except CopiaSeguridadFallida as exc:
        # 503 y no 500: no es un fallo del servidor sino la negativa deliberada a borrar
        # sin red. La degradación correcta de una operación irreversible es no hacer nada.
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))
    except PurgaBloqueadaPorIntegridad as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))

    trazabilidad_api.registrar_evento(
        "API_ADMIN_ELIMINACION",
        {"eliminados": resultado.expedientes_eliminados,
         "bloqueados": len(resultado.bloqueados),
         "solicitado_por": solicitud.solicitado_por},
        estado="INFO" if resultado.ejecutado else "ERROR",
    )
    if not resultado.ejecutado:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Eliminación no ejecutada: {resultado.motivo_degradacion}",
        )

    # Que todo quedara bloqueado **no es un error**: es la invariante funcionando, y el
    # cliente necesita ver el motivo de cada uno. Devolverlo como 409 escondería la
    # información justo cuando más falta hace.
    return ResultadoPurgaSchema(
        ejecutado=True,
        tipo="eliminacion",
        version_politica=resultado.version_politica,
        documentos_purgados=resultado.documentos_eliminados,
        ficheros_borrados=resultado.ficheros_borrados,
        bytes_liberados=resultado.bytes_liberados,
        expedientes_eliminados=resultado.expedientes_eliminados,
        bloqueados=resultado.bloqueados,
        backup_asociado=resultado.backup_asociado,
    )


@router.post(
    "/backup",
    response_model=ResultadoBackupSchema,
    responses={503: {"model": APIErrorResponse, "description": "No se pudo crear la copia"}},
    summary="Copia de seguridad bajo demanda",
    description="Copia transaccional en caliente de la base, con verificación de "
                "consistencia. Es la red que conviene tender antes de tocar nada.",
)
def post_backup(solicitado_por: str = Query("cockpit", description="Quién la pide, para el rastro")):
    try:
        ruta = Memoria().realizar_backup(run_id=0)
    except Exception as exc:
        trazabilidad_api.registrar_evento(
            "API_ADMIN_BACKUP_FAILED", {"error": str(exc)}, estado="ERROR"
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"No se pudo crear la copia de seguridad: {exc}",
        )

    tamano = os.path.getsize(ruta) if os.path.exists(ruta) else 0
    trazabilidad_api.registrar_evento(
        "API_ADMIN_BACKUP", {"ruta": ruta, "bytes": tamano, "solicitado_por": solicitado_por},
        estado="INFO",
    )
    return ResultadoBackupSchema(
        ruta=ruta, bytes=tamano, creado_at=datetime.now(timezone.utc).isoformat()
    )


@router.post(
    "/expedientes/rescatar",
    response_model=dict,
    responses={503: {"model": APIErrorResponse, "description": "Fallo escribiendo en la base"}},
    summary="Devuelve expedientes archivados al canal principal",
    description="La transición ARCHIVADO → VIVO. Existe, pero **siempre la pide una "
                "persona**: si un criterio automático archivara y otro desarchivara, el "
                "sistema oscilaría sin que nadie se enterase. El rescate deja marca, de modo "
                "que la corrida siguiente no vuelve a archivar lo que alguien devolvió. No "
                "altera el estado comercial: recuperar visibilidad no es cambiar de situación.",
)
def post_rescatar(solicitud: SolicitudRescateSchema):
    try:
        rescatados = Depurador(memoria=Memoria()).rescatar(
            solicitud.expedientes, solicitado_por=solicitud.solicitado_por
        )
    except sqlite3.Error as exc:
        trazabilidad_api.registrar_evento(
            "API_ADMIN_RESCATE_FAILED", {"error": str(exc)}, estado="ERROR"
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"No se pudo completar el rescate: {exc}",
        )

    trazabilidad_api.registrar_evento(
        "API_ADMIN_RESCATE",
        {"rescatados": rescatados, "expedientes": solicitud.expedientes,
         "solicitado_por": solicitud.solicitado_por},
        estado="INFO",
    )
    return {"rescatados": rescatados, "expedientes": solicitud.expedientes}


# ==============================================================================
# Apagado ordenado (Capa 10, Paso 5)
# ==============================================================================
#
# El **nivel 1** de los tres del contrato, y el único que garantiza terminar las peticiones
# en curso, devolver el cerrojo y ejecutar el `lifespan`. También el único que funciona
# **sin consola**, que es justo el caso del lanzador silencioso: sin ventana no hay a quién
# enviarle un CTRL_BREAK desde fuera del grupo.
#
# Dos cerrojos lo protegen, y ninguno sobra:
#
#   1. **Sólo escucha en la máquina.** Una petición que no venga de 127.0.0.1 se rechaza.
#   2. **Exige el testigo** que el lanzador generó al arrancar y guardó en `data/lanzador.pid`.
#      Sin él, cualquier página abierta en el navegador podría apagar el servidor con un
#      formulario: el Cockpit no tiene autenticación, así que la única credencial posible es
#      algo que viva en el disco de quien lo lanzó.
#
# **Si no hay fichero de marca, el endpoint no apaga nada.** Una API levantada a mano para
# desarrollar no la arrancó el lanzador, así que nadie tiene su testigo — y ese es
# exactamente el caso en que el contrato prohíbe apagar (transición prohibida nº 4).

class SolicitudApagado(BaseModel):
    """El testigo viaja en el cuerpo y **no tiene valor por defecto**.

    Mismo criterio que la confirmación de la purga del Paso 8 de la Capa 9: un campo con
    valor por defecto convierte "se me olvidó enviarlo" en "sí, adelante".
    """

    testigo: str = Field(..., min_length=1, description="El que el lanzador guardó en data/lanzador.pid")


def _detener_servidor_desde_dentro():
    """Pide a uvicorn que se cierre por su propio manejador de señal.

    Se hace en un hilo con un respiro para que la respuesta HTTP llegue a salir: si se
    levantara la señal dentro del manejador, quien pidió el apagado recibiría una conexión
    cortada y no podría distinguir "se está apagando" de "no me ha hecho caso".
    """
    def _senal():
        time.sleep(0.3)
        signal.raise_signal(signal.SIGINT)

    threading.Thread(target=_senal, daemon=True).start()


@router.post(
    "/apagar",
    summary="Apagado ordenado del servidor (sólo local y con testigo)",
    responses={
        403: {"model": APIErrorResponse, "description": "Petición no local, o testigo ausente/incorrecto"},
        409: {"model": APIErrorResponse, "description": "Este servidor no lo arrancó el lanzador"},
    },
)
def post_apagar(solicitud: SolicitudApagado, request: Request):
    if request.client is None or request.client.host not in ("127.0.0.1", "::1", "localhost"):
        trazabilidad_api.registrar_evento(
            "API_ADMIN_APAGADO_RECHAZADO",
            {"motivo": "origen_no_local", "origen": getattr(request.client, "host", "?")},
            estado="ERROR",
        )
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="El apagado sólo se acepta desde la propia máquina.")

    marca = leer_marca_servidor()
    if marca is None:
        # Sin marca no consta que este servidor lo arrancara el lanzador. Es un 409 y no un
        # 403 a propósito: no es que la credencial esté mal, es que aquí no hay nada que
        # apagar de forma ordenada — quien lo levantó a mano lo cierra con Ctrl-C.
        trazabilidad_api.registrar_evento(
            "API_ADMIN_APAGADO_RECHAZADO", {"motivo": "sin_marca_de_lanzador"}, estado="ERROR"
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Este servidor no lo arrancó el lanzador: no hay data/lanzador.pid.",
        )

    if not secrets.compare_digest(solicitud.testigo, marca.testigo):
        # Comparación en tiempo constante: es una credencial, y compararla con `==` filtra
        # por el tiempo de respuesta cuántos caracteres iniciales se acertaron.
        trazabilidad_api.registrar_evento(
            "API_ADMIN_APAGADO_RECHAZADO", {"motivo": "testigo_incorrecto"}, estado="ERROR"
        )
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Testigo incorrecto.")

    trazabilidad_api.registrar_evento("API_ADMIN_APAGADO", {"pid": marca.pid}, estado="INFO")
    _detener_servidor_desde_dentro()
    return {"apagando": True, "pid": marca.pid}


@router.get(
    "/prospeccion/diagnostico",
    response_model=DiagnosticoProspeccionSchema,
    summary="Qué le pasó a la última prospección",
    description="El estado de la última corrida y **por qué**: lo último que llegó a escribir y "
                "qué no pudo hacer. Existe porque `/admin/ejecuciones` sirve el estado de la "
                "fila y nada más, y una corrida puede constar COMPLETED con errores=0 habiendo "
                "sido incapaz de consultar sus fuentes.",
)
def get_diagnostico_prospeccion(db: sqlite3.Connection = Depends(get_db)):
    """El tercer canal del contrato de la Capa 10, servido a la pantalla.

    **No devuelve 5xx cuando el rastro está roto.** Es la transición prohibida nº 4 del contrato
    del Paso 9: el canal de diagnóstico no puede tumbar aquello que diagnostica. Si el rastro no
    se deja leer, se responde igual con lo que diga la tabla y se declara en `rastro_legible`.
    """
    from src.memoria import Memoria

    memoria = Memoria()
    try:
        items, _ = memoria.listar_ejecuciones(page=1, limit=1)
    except sqlite3.Error as exc:
        trazabilidad_api.registrar_evento(
            "API_PROSPECCION_DIAGNOSTICO_FAILED", {"error": str(exc)}, estado="ERROR"
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Fallo consultando la última prospección: {exc}",
        )

    # El rastro se lee **junto a la base que se acaba de consultar**, no en `ruta_datos()`.
    # Es donde lo escribe `Memoria.registrar_log_json()` (`os.path.dirname(self.db_path)`), y en
    # producción son el mismo sitio. Pero pueden divergir si `DB_PATH_INCOOP` apunta a otro
    # lado, y entonces el diagnóstico leería el rastro de una base distinta de la que juzga:
    # es la familia de H-28, resolver una ruta contra el sitio equivocado.
    ruta_rastro = os.path.join(os.path.dirname(memoria.db_path), "pipeline.jsonl")
    diagnostico = diagnosticar(items[0] if items else None, ruta_rastro=ruta_rastro)

    if diagnostico.rastro_degradado or not diagnostico.rastro_legible:
        # Evento del contrato (sección I). Sin él, un diagnóstico servido sobre un fichero con
        # agujeros sería indistinguible de uno servido sobre un fichero íntegro.
        trazabilidad_api.registrar_evento(
            "RASTRO_LEIDO_DEGRADADO",
            {"lineas_ilegibles": diagnostico.rastro_lineas_ilegibles,
             "legible": diagnostico.rastro_legible},
            estado="DEGRADADO",
        )

    trazabilidad_api.registrar_evento(
        "API_PROSPECCION_DIAGNOSTICO",
        {"estado": diagnostico.estado.value, "degradaciones": len(diagnostico.degradaciones)},
        estado="INFO",
    )
    return DiagnosticoProspeccionSchema.model_validate(diagnostico)

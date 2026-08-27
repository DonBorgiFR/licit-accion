"""
src/api/schemas.py — Modelado de Esquemas Base con Pydantic v2
Ecosistema Automático de Licitaciones (bfr_incoop)

Módulo responsable de definir los esquemas de datos inmutables y fuertemente tipados (DTOs)
para la Pasarela API RESTful (Capa 7). Garantiza la validación en tiempo de ejecución,
la serialización limpia a JSON y la integración automática con OpenAPI 3.1 (/docs).
"""

from enum import Enum
from datetime import datetime, timezone
from typing import Generic, TypeVar, List, Optional, Dict, Any
from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator, model_validator

from src import estado_lectura_pliego, titulo_legible


# ==============================================================================
# Tolerancia a NULL en la frontera de la API
# ==============================================================================
#
# El DDL de SQLite (src/memoria.py) declara con `DEFAULT` — pero SIN `NOT NULL` —
# columnas que estos esquemas modelan como obligatorias (`organo`, `fuente`, `pbl`,
# `estado_operativo`...). Un `DEFAULT` de SQLite sólo actúa cuando la columna se omite
# en el INSERT: no impide almacenar un NULL explícito.
#
# Pydantic rechaza `None` para un campo tipado `str`/`float`/`bool` aunque tenga valor
# por defecto, porque el defecto sólo aplica si la clave está AUSENTE, no si vale None.
# Resultado observado en auditoría: un único expediente con `organo` a NULL devolvía 503
# en su ficha y, por validarse dentro de una comprensión de lista, tumbaba la página
# entera del funnel.
#
# Criterio: en la frontera de lectura, un dato incompleto debe degradarse a su valor por
# defecto, nunca romper la pantalla. La integridad se exige al escribir, no al leer.

def _sustituir_nulos(data: Any, defectos: Dict[str, Any]) -> Any:
    """Reemplaza por su valor por defecto las claves presentes con valor None."""
    if not isinstance(data, dict):
        return data
    normalizado = dict(data)
    for campo, defecto in defectos.items():
        if normalizado.get(campo, defecto) is None:
            normalizado[campo] = defecto
    return normalizado


# ==============================================================================
# Excepciones Tipadas de Esquemas API (Capa 7 - Paso 2)
# ==============================================================================

class APISchemaError(Exception):
    """Excepción base para errores de validación de esquemas de la API."""
    pass


class SchemaValidationError(APISchemaError):
    """Error emitido cuando falla la validación de estructura o tipos de Pydantic v2."""
    pass


class EstadoInvalidoError(APISchemaError):
    """Error emitido cuando se solicita una transición hacia un estado no permitido."""
    pass


# ==============================================================================
# Enumeraciones de Negocio Restringidas
# ==============================================================================

class EstadoLicitacionEnum(str, Enum):
    NUEVA = "Nueva"
    ESTUDIANDO = "Estudiando"
    PRESENTADA = "Presentada"
    ADJUDICADA = "Adjudicada"
    PERDIDA = "Perdida"
    DESCARTADA = "Descartada"
    ANULADA_ADMINISTRACION = "Anulada_Administracion"
    INACTIVA = "Inactiva"


class EstadoAlertaEnum(str, Enum):
    NUEVA_FASE_TEMPRANA = "NUEVA_FASE_TEMPRANA"
    EN_ESTUDIO_PROACTIVO = "EN_ESTUDIO_PROACTIVO"
    CONVERTIDA = "CONVERTIDA_A_LICITACION"
    # Descarte decidido por una persona desde el Cockpit.
    DESCARTADA = "DESCARTADA_TEMPRANA"
    # Descarte automático del pipeline por no alcanzar el umbral. Se persiste para poder
    # auditarlo y reevaluarlo, pero queda fuera del canal principal de alertas.
    DESCARTADA_POR_REGLAS = "DESCARTADA_POR_REGLAS"
    ANALISIS_DIFERIDO = "ANALISIS_DIFERIDO_BOLETIN"


class PrioridadEnum(str, Enum):
    ALTA = "Alta"
    MEDIA = "Media"
    BAJA = "Baja"


class FuenteBoletinEnum(str, Enum):
    DOGC = "DOGC"
    BOPB = "BOPB"


class CategoriaFaseTempranaEnum(str, Enum):
    PRESUPUESTO = "PRESUPUESTO"
    SUBVENCION = "SUBVENCION"
    CONVENIO = "CONVENIO"
    CONSULTA_PRELIMINAR = "CONSULTA_PRELIMINAR"
    OTROS = "OTROS"


# ==============================================================================
# Esquemas Base y DTOs de Licitaciones (Funnel PSCP/PCSP)
# ==============================================================================

class LoteSchema(BaseModel):
    """Esquema de representación de un Lote individual dentro de un Expediente de Licitación."""
    id: Optional[int] = Field(None, description="Identificador autoincremental del lote")
    expediente_id: str = Field(..., description="ID del expediente al que pertenece el lote")
    lote_numero: int = Field(..., description="Número ordinal de lote")
    titulo_lote: str = Field(..., description="Título o descripción específica del lote")
    cpvs: Optional[str] = Field(None, description="Códigos CPV asociados")
    pbl: float = Field(0.0, description="Presupuesto Base de Licitación sin IVA")
    vec: float = Field(0.0, description="Valor Estimado del Contrato con prórrogas")
    garantia_definitiva: Optional[float] = Field(0.0, description="Importe estimado del 5% del PBL para aval")
    subrogacion: bool = Field(False, description="Flag de obligación de subrogación de personal")
    revision_precios: bool = Field(False, description="Flag de cláusula de revisión de precios")
    dias_restantes: Optional[int] = Field(None, description="Días disponibles hasta la fecha límite")
    score_total: int = Field(0, description="Puntuación comercial otorgada (0-100)")
    motivos_scoring: Optional[str] = Field(None, description="Desglose explicativo de la puntuación")
    sector: Optional[str] = Field(None, description="Sector de actividad identificado")
    prioridad: Optional[str] = Field("Baja", description="Prioridad comercial (Alta, Media, Baja)")
    pmp_dias: Optional[int] = Field(None, description="Periodo Medio de Pago del ayuntamiento")
    ratio_prorrogas: Optional[float] = Field(None, description="Ratio VEC / PBL")
    estado_operativo: str = Field("Nueva", description="Estado comercial operativo del lote")
    notas_usuario: Optional[str] = Field(None, description="Notas internas del equipo de Incoop")
    empresa_adjudicataria: Optional[str] = Field(None, description="Empresa adjudicataria post-licitación")
    importe_adjudicacion: Optional[float] = Field(None, description="Importe final de cierre")
    dinero_en_la_mesa: Optional[float] = Field(None, description="Diferencia monetaria con la oferta ganadora")
    horas_internas_invertidas: Optional[int] = Field(0, description="Horas invertidas por el equipo (CAC)")
    costes_externos: Optional[float] = Field(0.0, description="Gastos externos invertidos (CAC)")
    importe_garantia_retenida: Optional[float] = Field(0.0, description="Aval real depositado en caja")
    fecha_devolucion_garantia: Optional[str] = Field(None, description="Fecha estimada de retorno de aval")
    updated_at: Optional[str] = Field(None, description="Timestamp UTC del último cambio")
    updated_by: Optional[str] = Field(None, description="Usuario o sistema que realizó la última modificación")
    # Ciclo de vida (Capa 9). Un lote archivado sigue siendo editable —archivar gobierna la
    # visibilidad en el canal principal, no la editabilidad—, pero la pantalla tiene que
    # poder decir que lo está y por qué. Sin distintivo, se decidiría sobre él como si
    # siguiera vivo (Convención C3).
    deleted_at: Optional[str] = Field(None, description="Fecha de archivado; nulo si el lote sigue vivo")
    deleted_reason: Optional[str] = Field(None, description="Motivo por el que se archivó")

    model_config = ConfigDict(from_attributes=True)

    # Columnas de `lotes` con DEFAULT pero sin NOT NULL en el DDL.
    @model_validator(mode="before")
    @classmethod
    def _tolerar_nulos(cls, data: Any) -> Any:
        return _sustituir_nulos(data, {
            "titulo_lote": "(sin título)",
            "pbl": 0.0,
            "vec": 0.0,
            "subrogacion": False,
            "revision_precios": False,
            "score_total": 0,
            "estado_operativo": "Nueva",
            "lote_numero": 1,
        })


class AnalisisSemanticoResumenSchema(BaseModel):
    """Esquema resumido del dictamen semántico de la IA (Capa 5)."""
    subrogacion_detectada: bool = False
    subrogacion_riesgo: Optional[str] = "BAJO"
    revision_precios_permitida: bool = False
    criterios_peso_formulas: Optional[int] = 50
    criterios_peso_juicio_valor: Optional[int] = 50
    dictamen_recomendacion: Optional[str] = "REVISAR_RIESGO"
    dictamen_resumen: Optional[str] = None
    # Trazabilidad del origen del dictamen: permite al Cockpit advertir cuando el
    # análisis NO procede de una lectura real del pliego (Regla 5 - Modo Degradado).
    estado_analisis: Optional[str] = Field("COMPLETADO", description="COMPLETADO | DEGRADADO | ANALISIS_DIFERIDO")
    modo_degradado: bool = Field(False, description="True si el dictamen no proviene de una lectura real del pliego")
    modelo_llm: Optional[str] = Field(None, description="Proveedor y modelo que emitió el dictamen")
    error_detalle: Optional[str] = Field(None, description="Causa de la degradación, si la hubo")
    subrogacion: Optional[Dict[str, Any]] = None
    revision_precios: Optional[Dict[str, Any]] = None
    criterios: Optional[Dict[str, Any]] = None
    garantia_definitiva: Optional[Dict[str, Any]] = None
    penalidades: Optional[Dict[str, Any]] = None
    clausulas_sociales: Optional[Dict[str, Any]] = None

    model_config = ConfigDict(from_attributes=True)


class LicitacionSchema(BaseModel):
    """Esquema principal de un Expediente de Licitación de la PSCP / PCSP."""
    id: str = Field(..., description="Número de expediente o código de licitación")
    titulo: str = Field(..., description="Título del anuncio o licitación, íntegro tal como llegó de la fuente")
    organo: str = Field(..., description="Órgano de contratación emisor")
    localidad: Optional[str] = Field(None, description="Municipio o localidad de ejecución")
    nuts: Optional[str] = Field(None, description="Código NUTS territorial")
    procedimiento: Optional[str] = Field(None, description="Tipo de procedimiento LCSP")
    urgente: bool = Field(False, description="Flag de tramitación urgente")
    fuente: str = Field("PSCP", description="Portal de origen (PSCP / PCSP)")
    link: Optional[str] = Field(None, description="URL oficial de la licitación")
    fecha_publicacion: Optional[str] = Field(None, description="Fecha de publicación ISO 8601 UTC")
    fecha_limite: Optional[str] = Field(None, description="Fecha límite de presentación ISO 8601 UTC")
    fecha_ingesta: Optional[str] = Field(None, description="Fecha de ingesta ISO 8601 UTC")
    alerta_modificacion: bool = Field(False, description="Flag de modificación pospublicación")
    log_cambios: Optional[str] = Field(None, description="Historial de rectificaciones")
    score_maximo: Optional[int] = Field(0, description="Puntuación máxima entre sus lotes")
    # Ciclo de vida (Capa 9). `archivada` es la señal que la tabla necesita para marcar la
    # fila: es cierta cuando ninguno de sus lotes sigue vivo. `deleted_at` sólo lo tiene el
    # expediente archivado en cascada por el Depurador.
    archivada: bool = Field(False, description="El expediente está fuera del canal principal")
    deleted_at: Optional[str] = Field(None, description="Fecha de archivado del expediente")
    deleted_reason: Optional[str] = Field(None, description="Motivo por el que se archivó")
    lotes: List[LoteSchema] = Field(default_factory=list, description="Listado de lotes asociados")
    analisis_semantico: Optional[Dict[str, Any]] = Field(None, description="Dictamen detallado de la IA")

    model_config = ConfigDict(from_attributes=True)

    @computed_field(
        description="Título derivado para leer en pantalla. El completo sigue en `titulo`"
    )
    @property
    def titulo_corto(self) -> str:
        """El que se pinta en la tabla; `titulo` conserva el original íntegro.

        Se deriva **al servir** y no se guarda en la base a propósito: la regla se va a afinar
        cuando se vea sobre datos reales, y una columna persistida obligaría a rebackfillar en
        cada retoque. Además la búsqueda del Funnel debe seguir operando sobre el título
        completo, para que una licitación se encuentre por una palabra de su cuerpo.
        Ver `.agents/CONTRATO_BLOQUE_3.md`, apartado B.
        """
        return titulo_legible(self.titulo)

    @computed_field(
        description="De dónde viene el dictamen: LEIDO | SIN_ANALIZAR | DEGRADADO"
    )
    @property
    def estado_lectura(self) -> str:
        """Los tres estados del análisis semántico, resueltos en el servidor.

        **Se calcula aquí y no en el Cockpit a propósito.** La clasificación estaba escrita
        dos veces en el frontend —tabla y ficha— con la misma cadena de tres condiciones, y
        el frontend no tiene suite: un error ahí sólo se ve mirando la pantalla. Resuelto en
        la API, los tres estados quedan cubiertos por regresiones.

        Y fundía dos casos distintos en uno: *no se intentó* y *se intentó y salió mal*
        pintaban la misma etiqueta. Ver `.agents/CONTRATO_BLOQUE_3.md`, apartado F.
        """
        return estado_lectura_pliego(self.analisis_semantico)

    # Columnas de `expedientes` con DEFAULT pero sin NOT NULL en el DDL.
    @model_validator(mode="before")
    @classmethod
    def _tolerar_nulos(cls, data: Any) -> Any:
        return _sustituir_nulos(data, {
            "titulo": "(sin título)",
            "organo": "No informado",
            "fuente": "PSCP",
            "urgente": False,
            "alerta_modificacion": False,
            "score_maximo": 0,
            "lotes": [],
        })


# ==============================================================================
# Esquemas de Canal Proactivo (Centinela de Boletines DOGC / BOPB)
# ==============================================================================

class AlertaBoletinSchema(BaseModel):
    """Esquema de representación de una Alerta de Boletín Oficial (Capa 6)."""
    id_alerta: str = Field(..., description="Hash SHA256 identificador único de la alerta")
    fuente: str = Field(..., description="Boletín emisor (DOGC o BOPB)")
    num_boletin: str = Field(..., description="Número / Referencia del boletín oficial")
    fecha_publicacion: str = Field(..., description="Fecha de publicación ISO 8601 UTC")
    organo_emisor: str = Field(..., description="Ente u órgano emisor")
    municipio: Optional[str] = Field(None, description="Municipio de ejecución")
    titulo_anuncio: str = Field(..., description="Título o disposición del anuncio")
    seccion_boletin: Optional[str] = Field(None, description="Sección oficial del boletín")
    url_anuncio: Optional[str] = Field(None, description="URL de la disposición oficial")
    url_pdf: Optional[str] = Field(None, description="URL del archivo PDF oficial")
    texto_sumario: Optional[str] = Field(None, description="Extracto de texto del anuncio")
    score_temprano: int = Field(0, description="Puntuación de viabilidad temprana (0-100)")
    motivos_score: Optional[str] = Field(None, description="Desglose explicativo de la puntuación")
    categoria_fase_temprana: str = Field("OTROS", description="Categoría LCSP de fase temprana")
    dictamen_ia_json: Optional[Dict[str, Any]] = Field(None, description="Dictamen cualitativo de la IA")
    estado_operativo: str = Field("NUEVA_FASE_TEMPRANA", description="Estado operativo proactivo")
    expediente_licitacion_vinculado: Optional[str] = Field(None, description="ID del expediente PSCP vinculado")
    notas_usuario: Optional[str] = Field(None, description="Notas internas del equipo")
    fecha_ingesta: Optional[str] = Field(None, description="Fecha de ingesta ISO 8601 UTC")
    updated_at: Optional[str] = Field(None, description="Timestamp UTC de actualización")

    model_config = ConfigDict(from_attributes=True)

    # Columnas de `boletines_alertas` con DEFAULT pero sin NOT NULL en el DDL.
    @model_validator(mode="before")
    @classmethod
    def _tolerar_nulos(cls, data: Any) -> Any:
        return _sustituir_nulos(data, {
            "score_temprano": 0,
            "categoria_fase_temprana": "OTROS",
            "estado_operativo": "NUEVA_FASE_TEMPRANA",
        })


# ==============================================================================
# Esquemas Analíticos de KPIs (Dashboard Header / Summary)
# ==============================================================================

class KPISummarySchema(BaseModel):
    """Esquema de métricas globales agregadas para el Cockpit Visual (Capa 8)."""
    total_expedientes: int = Field(0, description="Total de expedientes en base de datos")
    total_lotes: int = Field(0, description="Total de lotes gestionados")
    licitaciones_estudio: int = Field(0, description="Licitaciones actualmente en estudio")
    licitaciones_presentadas: int = Field(0, description="Licitaciones presentadas pendientes de fallo")
    licitaciones_ganadas: int = Field(0, description="Licitaciones adjudicadas a Incoop")
    licitaciones_perdidas: int = Field(0, description="Licitaciones adjudicadas a la competencia")
    win_rate_porcentaje: float = Field(0.0, description="Porcentaje de éxito (Ganadas / Presentadas)")
    volumen_total_pbl: float = Field(0.0, description="Importe total acumulado en PBL (€)")
    capital_garantias_retenidas: float = Field(0.0, description="Avales inmovilizados en caja (€)")
    alertas_tempranas_activas: int = Field(0, description="Alertas proactivas de boletines vigentes")
    #: Ámbito territorial sobre el que se han calculado estas cifras. `None` es «todo».
    #: Viaja en la respuesta para que la pantalla pueda rotular la población de la que
    #: habla y, sobre todo, para que un día en que la API ignorase el parámetro se pueda
    #: notar: sin este campo, el Cockpit enseñaría los expedientes de toda España bajo el
    #: rótulo de Catalunya sin que nada chirriase.
    ambito: Optional[str] = Field(None, description="Ámbito territorial aplicado (None = sin filtro)")
    version_ambito: str = Field("", description="Versión del criterio de ámbito (Regla 4)")

    model_config = ConfigDict(from_attributes=True)


# ==============================================================================
# Esquema Genérico de Paginación
# ==============================================================================

T = TypeVar("T")

class PaginatedResponse(BaseModel, Generic[T]):
    """Esquema genérico contenedor para listados paginados."""
    items: List[T] = Field(..., description="Lista de elementos devueltos en la página actual")
    total: int = Field(..., description="Total de registros coincidentes en base de datos")
    page: int = Field(..., description="Número de página actual (1-indexed)")
    limit: int = Field(..., description="Cantidad de registros por página")
    total_pages: int = Field(..., description="Total de páginas calculadas")

    model_config = ConfigDict(from_attributes=True)


# ==============================================================================
# Esquemas de Administración y Depurador (Capa 9, Pasos 7 y 8)
# ==============================================================================

class AlmacenamientoSchema(BaseModel):
    """Dónde está el peso. Separa lo purgable de lo que no lo es, que es la decisión."""
    base_datos_bytes: int = Field(..., description="Tamaño del fichero SQLite. NO es purgable: sus filas son la memoria comercial")
    documentos_bytes: int = Field(..., description="Pliegos y anexos descargados en data/documents/")
    documentos_ficheros: int = Field(..., description="Número de ficheros documentales en disco")
    copias_bytes: int = Field(..., description="Copias de seguridad en data/backups/")
    copias_ficheros: int = Field(..., description="Número de copias de seguridad conservadas")
    registros_bytes: int = Field(..., description="Tamaño del registro de trazabilidad pipeline.jsonl")
    total_bytes: int = Field(..., description="Suma de todo lo anterior")
    purgable_bytes: int = Field(..., description="Lo que una purga podría liberar: documentos y copias, nunca la base")


class PoliticaArchivadoSchema(BaseModel):
    dias_tras_fecha_limite: int
    estados_archivables: List[str]
    archivar_expediente_con_todos_sus_lotes: bool


class PoliticaEliminacionSchema(BaseModel):
    dias_archivado_minimo: int


class PoliticaRetencionSchema(BaseModel):
    """La política vigente y su versión, tal y como se lee de config/retencion.yaml."""
    version: str = Field(..., description="Versión de la política bajo la que se ejecuta cada purga")
    documentos_dias: int = Field(..., description="Días que se conservan los pliegos, contados desde la fecha límite")
    backups_dias: int = Field(..., description="Días que se conservan las copias de seguridad")
    archivado: Optional[PoliticaArchivadoSchema] = Field(None, description="Ausente significa que no se archiva nada")
    eliminacion: Optional[PoliticaEliminacionSchema] = Field(None, description="Ausente significa que no se elimina nada")


class ExpedienteEvaluadoSchema(BaseModel):
    """Veredicto sobre un expediente. El motivo del bloqueo importa tanto como el borrado."""
    expediente_id: str
    eliminable: bool
    motivo: Optional[str] = None
    detalle_motivo: Optional[str] = None
    lotes: int = 0
    documentos: int = 0

    model_config = ConfigDict(from_attributes=True)


class PurgaDocumentalPreviaSchema(BaseModel):
    documentos_candidatos: int = Field(..., description="Documentos que perderían su fichero y su texto")
    ficheros_en_disco: int = Field(..., description="Cuántos de ellos tienen todavía fichero que borrar")
    bytes_estimados: int = Field(..., description="Espacio que se liberaría, medido en disco")
    corte_utc: Optional[str] = Field(None, description="Fecha de corte aplicada según la política")


class PrevisualizacionPurgaSchema(BaseModel):
    """Qué desaparecería si se purgara ahora. **No altera nada, pero consta quién miró.**"""
    version_politica: Optional[str] = None
    documental: PurgaDocumentalPreviaSchema
    eliminables: List[ExpedienteEvaluadoSchema] = Field(default_factory=list, description="Expedientes que nunca llegaron a ser negocio")
    bloqueados: List[ExpedienteEvaluadoSchema] = Field(default_factory=list, description="Protegidos, con el motivo exacto de cada uno")
    degradado: Optional[str] = Field(None, description="Causa por la que no se ha podido evaluar, si la hay")


class SolicitudPurgaSchema(BaseModel):
    """Cuerpo de `POST /admin/purga`. La confirmación es explícita y no tiene valor por defecto.

    `confirmar` no lleva `= True` a propósito: un campo con valor por defecto convierte
    "olvidé enviarlo" en "sí, adelante", que es justo lo que el contrato prohíbe.
    """
    tipo: str = Field(..., description="'documental' (libera peso) o 'eliminacion' (borra filas)")
    confirmar: bool = Field(..., description="Debe ser true de forma expresa. Sin ella, 400")
    expedientes: List[str] = Field(default_factory=list, description="Obligatorio para 'eliminacion': nunca se deduce")
    solicitado_por: str = Field("cockpit", description="Quién lo pide, para el rastro de auditoría")

    @field_validator("tipo")
    @classmethod
    def validar_tipo(cls, v: str) -> str:
        if v not in ("documental", "eliminacion"):
            raise ValueError("tipo debe ser 'documental' o 'eliminacion'")
        return v


class ResultadoPurgaSchema(BaseModel):
    """Lo que hizo una purga, o lo que decidió no hacer y por qué."""
    ejecutado: bool
    tipo: str
    version_politica: Optional[str] = None
    documentos_purgados: int = 0
    ficheros_borrados: int = 0
    bytes_liberados: int = 0
    expedientes_eliminados: int = 0
    bloqueados: List[ExpedienteEvaluadoSchema] = Field(default_factory=list)
    backup_asociado: Optional[str] = None
    degradado: Optional[str] = Field(None, description="Causa por la que no se ejecutó, si no se ejecutó")


class SolicitudRescateSchema(BaseModel):
    """Cuerpo del rescate `ARCHIVADO → VIVO`, que siempre lo pide una persona."""
    expedientes: List[str] = Field(..., min_length=1, description="Expedientes a devolver al canal principal")
    solicitado_por: str = Field("cockpit", description="Quién lo pide, para el rastro")


class ResultadoBackupSchema(BaseModel):
    """Copia de seguridad creada bajo demanda."""
    ruta: str = Field(..., description="Fichero .bak generado")
    bytes: int = Field(..., description="Tamaño de la copia")
    creado_at: str = Field(..., description="Timestamp ISO 8601 UTC")


class EjecucionSchema(BaseModel):
    """Una corrida del pipeline con lo que encontró (esquema v6)."""
    id: int
    start_time: str
    end_time: Optional[str] = None
    estado: str
    expedientes_nuevos: Optional[int] = 0
    expedientes_actualizados: Optional[int] = 0
    lotes_evaluados: Optional[int] = 0
    documentos_descargados: Optional[int] = 0
    analisis_realizados: Optional[int] = 0
    alertas_generadas: Optional[int] = 0
    errores: Optional[int] = 0
    version_scoring: Optional[str] = None
    version_politica_retencion: Optional[str] = None

    #: ¿Sigue vivo el proceso dueño de una corrida `RUNNING`? (Capa 10, Paso 7 — H-43.)
    #: `True` en curso de verdad, `False` interrumpida, `None` no se puede saber. Sólo tiene
    #: sentido preguntado **desde la máquina que ejecuta el pipeline**, que es el diseño de
    #: hoy —API y pipeline conviven en 127.0.0.1—; el día que se separen (Capa 11), este
    #: campo tendrá que responderlo quien corra el pipeline, no quien sirva la pantalla.
    duenyo_vivo: Optional[bool] = None

    model_config = ConfigDict(from_attributes=True)


# ==============================================================================
# Esquemas de Mutación / Transición de Estado (PUT Body)
# ==============================================================================

class TransicionEstadoLicitacionSchema(BaseModel):
    """DTO para actualizar el estado operativo y notas de una licitación/lote."""
    nuevo_estado: str = Field(..., description="Nuevo estado operativo solicitado")
    lote_numero: int = Field(1, ge=1, description="Número de lote exacto al que se aplica la mutación")
    notas: Optional[str] = Field(None, description="Notas internas opcionales enviadas por el usuario")

    @field_validator("nuevo_estado")
    @classmethod
    def validar_estado(cls, v: str) -> str:
        estados_validos = [e.value for e in EstadoLicitacionEnum]
        if v not in estados_validos:
            raise ValueError(f"Estado '{v}' no es válido. Estados permitidos: {estados_validos}")
        return v


class TransicionEstadoAlertaSchema(BaseModel):
    """DTO para actualizar el estado operativo y notas de una alerta temprana del Centinela."""
    nuevo_estado: str = Field(..., description="Nuevo estado proactivo solicitado")
    notas: Optional[str] = Field(None, description="Notas internas opcionales")

    @field_validator("nuevo_estado")
    @classmethod
    def validar_estado(cls, v: str) -> str:
        estados_validos = [e.value for e in EstadoAlertaEnum]
        if v not in estados_validos:
            raise ValueError(f"Estado de alerta '{v}' no es válido. Estados permitidos: {estados_validos}")
        return v


# ==============================================================================
# Esquemas de Operación, Salud y Errores
# ==============================================================================

class HealthResponseSchema(BaseModel):
    """Esquema de respuesta del endpoint GET /api/v1/health."""
    status: str = Field(..., description="Estado de salud general (OK / ERROR)")
    timestamp: str = Field(..., description="Timestamp ISO 8601 UTC")
    db_path: str = Field(..., description="Ruta a la base de datos SQLite")
    directorio_accesible: bool = Field(..., description="Permiso de escritura en disco")
    wal_mode_active: bool = Field(..., description="Estado activo del diario WAL")
    schema_version: Optional[int] = Field(None, description="Versión actual del esquema SQLite")
    query_test_ok: bool = Field(..., description="Resultado de la consulta SQL de prueba")
    error: Optional[str] = Field(None, description="Detalle del error si status == ERROR")

    model_config = ConfigDict(from_attributes=True)


class APIErrorResponse(BaseModel):
    """Esquema estandarizado de respuesta para excepciones y errores HTTP en la API."""
    error_code: str = Field(..., description="Código técnico identificador del error")
    message: str = Field(..., description="Mensaje explicativo del error para el usuario")
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat(), description="Timestamp UTC del error")
    details: Optional[Dict[str, Any]] = Field(None, description="Detalles contextuales adicionales")

    model_config = ConfigDict(from_attributes=True)


# ==============================================================================
# Diagnóstico de la prospección (Capa 10, Paso 9 — el tercer canal de la capa)
# ==============================================================================

class DegradacionSchema(BaseModel):
    """Algo que la corrida no pudo hacer, con quién no pudo y por qué."""
    componente: str
    evento: str
    detalle: str = ""
    cuando: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class DiagnosticoProspeccionSchema(BaseModel):
    """Lo que el sistema puede afirmar de su última prospección, y con qué respaldo.

    Es el **tercer canal** del contrato de la Capa 10: cuando el Cockpit ya está en marcha, el
    aviso va a la pantalla y no a un diálogo. Existe porque `GET /admin/ejecuciones` sirve el
    estado de la fila y nada más, y una corrida puede constar `COMPLETED` con `errores = 0`
    habiendo sido incapaz de consultar sus fuentes — que es lo que ocurrió el 2026-08-27.
    """
    estado: str
    ejecucion_id: Optional[int] = None
    inicio: Optional[str] = None
    fin: Optional[str] = None
    motivo: str = ""
    ultimo_evento: Optional[str] = None
    ultimo_evento_cuando: Optional[str] = None
    degradaciones: List[DegradacionSchema] = []
    errores_registrados: int = 0

    #: El rastro traía líneas ilegibles (H-55). **Del fichero entero, no de esta corrida**: una
    #: línea partida no conserva su fecha. Lo que se afirma es sobre qué se construyó el
    #: diagnóstico, no cuánto daño tuvo la corrida.
    rastro_degradado: bool = False
    rastro_lineas_ilegibles: int = 0

    #: `False` si el rastro no se pudo abrir. **El diagnóstico se sirve igual**, con lo que diga
    #: la tabla: el canal de diagnóstico no puede tumbar aquello que diagnostica.
    rastro_legible: bool = True

    model_config = ConfigDict(from_attributes=True)

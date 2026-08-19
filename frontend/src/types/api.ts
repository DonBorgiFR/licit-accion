/**
 * frontend/src/types/api.ts — Espejo de Tipos TypeScript (Capa 8 - Paso 2)
 * Ecosistema Automático de Licitaciones (bfr_incoop)
 *
 * Módulo que refleja 1-a-1 los DTOs e interfaces de Pydantic v2 (src/api/schemas.py)
 * garantizando la indemnidad de tipos, autocompletado y validación tsc.
 */

// ==============================================================================
// Enumeraciones de Negocio Restringidas (Erasable Syntax Compatible)
// ==============================================================================

export const EstadoLicitacion = {
  NUEVA: 'Nueva',
  ESTUDIANDO: 'Estudiando',
  PRESENTADA: 'Presentada',
  ADJUDICADA: 'Adjudicada',
  PERDIDA: 'Perdida',
  DESCARTADA: 'Descartada',
  ANULADA_ADMINISTRACION: 'Anulada_Administracion',
  INACTIVA: 'Inactiva',
} as const;

export type EstadoLicitacion = (typeof EstadoLicitacion)[keyof typeof EstadoLicitacion];

export const EstadoAlerta = {
  NUEVA_FASE_TEMPRANA: 'NUEVA_FASE_TEMPRANA',
  EN_ESTUDIO_PROACTIVO: 'EN_ESTUDIO_PROACTIVO',
  CONVERTIDA: 'CONVERTIDA_A_LICITACION',
  /** Descarte decidido por una persona desde el Cockpit. */
  DESCARTADA: 'DESCARTADA_TEMPRANA',
  /** Descarte automático del pipeline por no alcanzar el umbral: se guarda para auditoría
   *  y reevaluación, pero no aparece en el canal principal de alertas. */
  DESCARTADA_POR_REGLAS: 'DESCARTADA_POR_REGLAS',
  ANALISIS_DIFERIDO: 'ANALISIS_DIFERIDO_BOLETIN',
} as const;

export type EstadoAlerta = (typeof EstadoAlerta)[keyof typeof EstadoAlerta];

export const Prioridad = {
  ALTA: 'Alta',
  MEDIA: 'Media',
  BAJA: 'Baja',
} as const;

export type Prioridad = (typeof Prioridad)[keyof typeof Prioridad];

export const FuenteBoletin = {
  DOGC: 'DOGC',
  BOPB: 'BOPB',
} as const;

export type FuenteBoletin = (typeof FuenteBoletin)[keyof typeof FuenteBoletin];

export const CategoriaFaseTemprana = {
  PRESUPUESTO: 'PRESUPUESTO',
  SUBVENCION: 'SUBVENCION',
  CONVENIO: 'CONVENIO',
  CONSULTA_PRELIMINAR: 'CONSULTA_PRELIMINAR',
  OTROS: 'OTROS',
} as const;

export type CategoriaFaseTemprana = (typeof CategoriaFaseTemprana)[keyof typeof CategoriaFaseTemprana];

// ==============================================================================
// DTOs de Licitaciones (Funnel PSCP / PCSP)
// ==============================================================================

export interface Lote {
  id?: number | null;
  expediente_id: string;
  lote_numero: number;
  titulo_lote: string;
  cpvs?: string | null;
  pbl: number;
  vec: number;
  garantia_definitiva?: number | null;
  subrogacion: boolean;
  revision_precios: boolean;
  dias_restantes?: number | null;
  score_total: number;
  motivos_scoring?: string | null;
  sector?: string | null;
  prioridad?: Prioridad | string | null;
  pmp_dias?: number | null;
  ratio_prorrogas?: number | null;
  estado_operativo: EstadoLicitacion | string;
  notas_usuario?: string | null;
  empresa_adjudicataria?: string | null;
  importe_adjudicacion?: number | null;
  dinero_en_la_mesa?: number | null;
  horas_internas_invertidas?: number | null;
  costes_externos?: number | null;
  importe_garantia_retenida?: number | null;
  fecha_devolucion_garantia?: string | null;
  updated_at?: string | null;
  updated_by?: string | null;
  /**
   * Ciclo de vida (Capa 9). Un lote archivado está fuera del canal principal pero
   * sigue siendo editable: archivar gobierna la visibilidad, no la editabilidad.
   * La pantalla debe marcarlo — mostrarlo sin distintivo llevaría a decidir sobre él
   * como si siguiera vivo (Convención C3).
   */
  deleted_at?: string | null;
  deleted_reason?: string | null;
}

export interface AnalisisSemanticoResumen {
  subrogacion_detectada: boolean;
  subrogacion_riesgo?: string | null;
  revision_precios_permitida: boolean;
  criterios_peso_formulas?: number | null;
  criterios_peso_juicio_valor?: number | null;
  dictamen_recomendacion?: string | null;
  dictamen_resumen?: string | null;
  /**
   * Trazabilidad del origen del dictamen (Capa 5, Regla 5 - Modo Degradado).
   * COMPLETADO = el pliego se leyó realmente.
   * DEGRADADO / ANALISIS_DIFERIDO = no hubo lectura real: los campos de riesgo
   * contienen valores por defecto y NO deben interpretarse como ausencia de riesgo.
   */
  estado_analisis?: EstadoAnalisis | string | null;
  modo_degradado?: boolean | null;
  modelo_llm?: string | null;
  error_detalle?: string | null;
  subrogacion?: Record<string, unknown> | null;
  revision_precios?: Record<string, unknown> | null;
  criterios?: Record<string, unknown> | null;
  garantia_definitiva?: Record<string, unknown> | null;
  penalidades?: Record<string, unknown> | null;
  clausulas_sociales?: Record<string, unknown> | null;
}

export const EstadoAnalisis = {
  COMPLETADO: 'COMPLETADO',
  DEGRADADO: 'DEGRADADO',
  ANALISIS_DIFERIDO: 'ANALISIS_DIFERIDO',
} as const;

export type EstadoAnalisis = (typeof EstadoAnalisis)[keyof typeof EstadoAnalisis];

export interface Licitacion {
  id: string;
  /** El título íntegro tal como llegó de la fuente. Puede traer el anuncio entero:
   *  el más largo de la base mide 1.663 caracteres. Es lo que se muestra en la ficha. */
  titulo: string;
  /** El derivado para leer en la tabla, que sirve la API (Bloque 3, Paso 2). Se calcula
   *  al servir y no se guarda: `titulo` conserva siempre el original. */
  titulo_corto: string;
  organo: string;
  localidad?: string | null;
  nuts?: string | null;
  procedimiento?: string | null;
  urgente: boolean;
  fuente: string;
  link?: string | null;
  fecha_publicacion?: string | null;
  fecha_limite?: string | null;
  fecha_ingesta?: string | null;
  alerta_modificacion: boolean;
  log_cambios?: string | null;
  score_maximo?: number | null;
  /** Ciclo de vida (Capa 9): cierto cuando ninguno de sus lotes sigue vivo. */
  archivada?: boolean;
  deleted_at?: string | null;
  deleted_reason?: string | null;
  lotes: Lote[];
  analisis_semantico?: AnalisisSemanticoResumen | null;
}

// ==============================================================================
// DTOs de Canal Proactivo (Centinela de Boletines DOGC / BOPB)
// ==============================================================================

export interface AlertaBoletin {
  id_alerta: string;
  fuente: FuenteBoletin | string;
  num_boletin: string;
  fecha_publicacion: string;
  organo_emisor: string;
  municipio?: string | null;
  titulo_anuncio: string;
  seccion_boletin?: string | null;
  url_anuncio?: string | null;
  url_pdf?: string | null;
  texto_sumario?: string | null;
  score_temprano: number;
  motivos_score?: string | null;
  categoria_fase_temprana: CategoriaFaseTemprana | string;
  dictamen_ia_json?: Record<string, any> | null;
  estado_operativo: EstadoAlerta | string;
  expediente_licitacion_vinculado?: string | null;
  notas_usuario?: string | null;
  fecha_ingesta?: string | null;
  updated_at?: string | null;
}

// ==============================================================================
// DTOs Analíticos de KPIs (Dashboard Summary)
// ==============================================================================

export interface KPISummary {
  total_expedientes: number;
  total_lotes: number;
  licitaciones_estudio: number;
  licitaciones_presentadas: number;
  licitaciones_ganadas: number;
  licitaciones_perdidas: number;
  win_rate_porcentaje: number;
  volumen_total_pbl: number;
  capital_garantias_retenidas: number;
  alertas_tempranas_activas: number;
  /**
   * Ámbito territorial sobre el que se han calculado estas cifras. `null` es «todo».
   * Viaja en la respuesta para que la pantalla rotule la población de la que habla: sin
   * él, una API que ignorase el parámetro enseñaría toda España bajo el rótulo de
   * Catalunya sin que nada chirriase.
   */
  ambito: string | null;
  version_ambito: string;
}

// ==============================================================================
// Esquema Genérico de Paginación
// ==============================================================================

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  limit: number;
  total_pages: number;
}

// ==============================================================================
// DTOs de Mutación / Transición de Estado (PUT Body)
// ==============================================================================

export interface TransicionEstadoLicitacion {
  nuevo_estado: EstadoLicitacion | string;
  lote_numero: number;
  notas?: string | null;
}

export interface TransicionEstadoAlerta {
  nuevo_estado: EstadoAlerta | string;
  notas?: string | null;
}

// ==============================================================================
// Interfaces de Parámetros de Consulta (Query Params)
// ==============================================================================

export interface LicitacionesQueryParams {
  page?: number;
  limit?: number;
  search?: string;
  min_score?: number;
  pmp_max?: number;
  subrogacion_critica?: boolean;
  estado?: string;
  /**
   * Única vía desde el Cockpit para llegar a lo que el Depurador sacó del canal
   * principal (Capa 9). Por defecto no se incluyen: el Funnel es la tabla con la que
   * se decide a qué concurso presentarse y no debe arrastrar histórico.
   */
  incluir_archivadas?: boolean;
  /**
   * Ámbito territorial (H-47). Sin valor, la API devuelve todo: quien decide mostrar sólo
   * Catalunya es la pantalla, con el interruptor puesto de inicio. Es deliberadamente lo
   * contrario que `incluir_archivadas`, porque lo archivado es un concepto de negocio y el
   * ámbito una preferencia de quien mira.
   */
  ambito?: string;
}

export interface AlertasQueryParams {
  page?: number;
  limit?: number;
  search?: string;
  fuente?: string;
  min_score?: number;
  estado?: string;
}

// ==============================================================================
// DTOs de Operación, Salud y Errores HTTP
// ==============================================================================

export interface HealthResponse {
  status: 'OK' | 'ERROR' | string;
  timestamp: string;
  db_path: string;
  directorio_accesible: boolean;
  wal_mode_active: boolean;
  schema_version?: number | null;
  query_test_ok: boolean;
  error?: string | null;
}

export interface APIErrorResponse {
  error_code: string;
  message: string;
  timestamp?: string;
  details?: Record<string, any> | null;
}

// ==============================================================================
// Administración y Depurador (Capa 9, Pasos 7 y 8)
// ==============================================================================

export interface Almacenamiento {
  base_datos_bytes: number;
  documentos_bytes: number;
  documentos_ficheros: number;
  copias_bytes: number;
  copias_ficheros: number;
  registros_bytes: number;
  total_bytes: number;
  /** Documentos y copias. La base NUNCA entra: sus filas son la memoria comercial. */
  purgable_bytes: number;
}

export interface PoliticaArchivado {
  dias_tras_fecha_limite: number;
  estados_archivables: string[];
  archivar_expediente_con_todos_sus_lotes: boolean;
}

export interface PoliticaRetencion {
  version: string;
  documentos_dias: number;
  backups_dias: number;
  archivado: PoliticaArchivado | null;
  eliminacion: { dias_archivado_minimo: number } | null;
}

export interface ExpedienteEvaluado {
  expediente_id: string;
  eliminable: boolean;
  /** 'memoria_comercial' | 'cuarentena_no_cumplida' | 'no_archivado' */
  motivo: string | null;
  detalle_motivo: string | null;
  lotes: number;
  documentos: number;
}

export interface PrevisualizacionPurga {
  version_politica: string | null;
  documental: {
    documentos_candidatos: number;
    ficheros_en_disco: number;
    bytes_estimados: number;
    corte_utc: string | null;
  };
  eliminables: ExpedienteEvaluado[];
  /** Lo protegido, con su motivo. Se pinta a propósito: hay que poder ver que no está en riesgo. */
  bloqueados: ExpedienteEvaluado[];
  degradado: string | null;
}

export interface SolicitudPurga {
  tipo: 'documental' | 'eliminacion';
  confirmar: boolean;
  expedientes?: string[];
  solicitado_por?: string;
}

export interface ResultadoPurga {
  ejecutado: boolean;
  tipo: string;
  version_politica: string | null;
  documentos_purgados: number;
  ficheros_borrados: number;
  bytes_liberados: number;
  expedientes_eliminados: number;
  bloqueados: ExpedienteEvaluado[];
  backup_asociado: string | null;
  degradado: string | null;
}

export interface ResultadoBackup {
  ruta: string;
  bytes: number;
  creado_at: string;
}

export interface Ejecucion {
  id: number;
  start_time: string;
  end_time: string | null;
  estado: string;
  expedientes_nuevos: number | null;
  expedientes_actualizados: number | null;
  lotes_evaluados: number | null;
  documentos_descargados: number | null;
  analisis_realizados: number | null;
  alertas_generadas: number | null;
  errores: number | null;
  version_scoring: string | null;
  version_politica_retencion: string | null;
  /** ¿Vive el proceso dueño de una corrida RUNNING? null = no se puede saber (H-43). */
  duenyo_vivo: boolean | null;
}

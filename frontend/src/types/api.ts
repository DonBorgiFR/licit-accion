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
  DESCARTADA: 'DESCARTADA_TEMPRANA',
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
  titulo: string;
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

/**
 * frontend/src/lib/api-client.ts — Cliente API HTTP Centralizado (Capa 8 - Paso 2)
 * Ecosistema Automático de Licitaciones (bfr_incoop)
 *
 * Cliente HTTP resiliente basado en fetch nativo para comunicarse con la Pasarela API
 * RESTful de FastAPI (Capa 7). Inyecta X-Request-ID para trazabilidad en pipeline.jsonl
 * y parsea de forma defensiva las estructuras APIErrorResponse.
 */

import type {
  DiagnosticoProspeccion,
  HealthResponse,
  KPISummary,
  Licitacion,
  AlertaBoletin,
  PaginatedResponse,
  TransicionEstadoLicitacion,
  TransicionEstadoAlerta,
  LicitacionesQueryParams,
  AlertasQueryParams,
  APIErrorResponse,
  Almacenamiento,
  PoliticaRetencion,
  PrevisualizacionPurga,
  SolicitudPurga,
  ResultadoPurga,
  ResultadoBackup,
  Ejecucion,
} from '../types/api';

// URL **relativa al propio origen**, no absoluta a 127.0.0.1:8000 (H-38).
//
// Con la URL absoluta incrustada, el puerto quedaba fijado en el bundle compilado: desde
// que `config/lanzador.yaml` permite declarar el puerto (Capa 10, Paso 3), arrancar en
// cualquier otro habría servido el Cockpit correctamente y dejado que **todas** sus
// llamadas de datos fueran al 8000. El fallo más incómodo posible: las pantallas cargan,
// el sistema parece vivo y no hay ni un dato.
//
// Relativa funciona en los dos modos y sin configurar nada:
//   · desarrollo — `npm run dev` en el 5173, con el proxy `/api` de vite.config.ts.
//   · producción — FastAPI sirve el bundle y la API desde el mismo origen (Paso 4).
//
// `VITE_API_BASE_URL` se conserva para apuntar a un backend en otra máquina.
const BASE_URL =
  (import.meta as any).env?.VITE_API_BASE_URL || '/api/v1';

// ==============================================================================
// Excepción Personalizada de Error del Cliente API
// ==============================================================================

export class APIClientError extends Error {
  public readonly statusCode: number;
  public readonly errorCode: string;
  public readonly details: Record<string, any> | null;
  public readonly requestId: string;

  constructor(
    statusCode: number,
    errorCode: string,
    message: string,
    details: Record<string, any> | null = null,
    requestId: string = ''
  ) {
    super(message);
    this.name = 'APIClientError';
    this.statusCode = statusCode;
    this.errorCode = errorCode;
    this.details = details;
    this.requestId = requestId;
  }
}

// ==============================================================================
// Helper de Trazabilidad y Peticiones Fetch
// ==============================================================================

function generateRequestId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }
  return `req-${Date.now()}-${Math.random().toString(36).substring(2, 9)}`;
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const requestId = generateRequestId();
  const url = `${BASE_URL}${path}`;

  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    'X-Request-ID': requestId,
    ...(options.headers as Record<string, string> | undefined),
  };

  try {
    const response = await fetch(url, {
      ...options,
      headers,
    });

    if (!response.ok) {
      let errorBody: APIErrorResponse | null = null;
      try {
        errorBody = await response.json();
      } catch {
        // En caso de que el error no devuelva un JSON estructurado
      }

      const errorCode = errorBody?.error_code || `HTTP_${response.status}`;
      const message =
        errorBody?.message ||
        `Error en la petición a la API (${response.status} ${response.statusText})`;
      const details = errorBody?.details || null;

      throw new APIClientError(response.status, errorCode, message, details, requestId);
    }

    // 204 No Content
    if (response.status === 204) {
      return {} as T;
    }

    return (await response.json()) as T;
  } catch (error) {
    if (error instanceof APIClientError) {
      throw error;
    }
    // Errores de red o de conexión del navegador
    const networkMsg =
      error instanceof Error
        ? error.message
        : 'Error de red o servidor API inalcanzable';
    throw new APIClientError(0, 'NETWORK_ERROR', networkMsg, null, requestId);
  }
}

function buildQueryString(params: Record<string, any>): string {
  const query = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') {
      query.append(key, String(value));
    }
  });
  const str = query.toString();
  return str ? `?${str}` : '';
}

// ==============================================================================
// Métodos Exportados del Cliente API
// ==============================================================================

/**
 * Realiza un autodiagnóstico de salud contra GET /api/v1/health.
 */
export async function getHealth(): Promise<HealthResponse> {
  return request<HealthResponse>('/health');
}

/**
 * Obtiene el resumen analítico de KPIs globales contra GET /api/v1/kpis.
 */
export async function getKPIs(ambito?: string): Promise<KPISummary> {
  return request<KPISummary>(`/kpis${buildQueryString({ ambito })}`);
}

/**
 * Obtiene el listado paginado y filtrable de expedientes de licitación contra GET /api/v1/licitaciones.
 */
export async function getLicitaciones(
  params: LicitacionesQueryParams = {}
): Promise<PaginatedResponse<Licitacion>> {
  const queryStr = buildQueryString(params);
  return request<PaginatedResponse<Licitacion>>(`/licitaciones${queryStr}`);
}

/**
 * Obtiene el detalle completo de una licitación por ID contra GET /api/v1/licitaciones/{id}.
 */
export async function getLicitacionById(id: string): Promise<Licitacion> {
  const encodedId = encodeURIComponent(id);
  return request<Licitacion>(`/licitaciones/${encodedId}`);
}

/**
 * Mutación transaccional del estado operativo de una licitación contra PUT /api/v1/licitaciones/{id}/estado.
 */
export async function updateEstadoLicitacion(
  id: string,
  payload: TransicionEstadoLicitacion
): Promise<Licitacion> {
  const encodedId = encodeURIComponent(id);
  return request<Licitacion>(`/licitaciones/${encodedId}/estado`, {
    method: 'PUT',
    body: JSON.stringify(payload),
  });
}

/**
 * Obtiene el listado paginado de alertas tempranas del Centinela contra GET /api/v1/alertas-tempranas.
 */
export async function getAlertasTempranas(
  params: AlertasQueryParams = {}
): Promise<PaginatedResponse<AlertaBoletin>> {
  const queryStr = buildQueryString(params);
  return request<PaginatedResponse<AlertaBoletin>>(`/alertas-tempranas${queryStr}`);
}

/**
 * Obtiene el detalle de una alerta temprana por ID contra GET /api/v1/alertas-tempranas/{id_alerta}.
 */
export async function getAlertaById(id_alerta: string): Promise<AlertaBoletin> {
  const encodedId = encodeURIComponent(id_alerta);
  return request<AlertaBoletin>(`/alertas-tempranas/${encodedId}`);
}

/**
 * Mutación transaccional del estado de una alerta temprana contra PUT /api/v1/alertas-tempranas/{id_alerta}/estado.
 */
export async function updateEstadoAlerta(
  id_alerta: string,
  payload: TransicionEstadoAlerta
): Promise<AlertaBoletin> {
  const encodedId = encodeURIComponent(id_alerta);
  return request<AlertaBoletin>(`/alertas-tempranas/${encodedId}/estado`, {
    method: 'PUT',
    body: JSON.stringify(payload),
  });
}

// ==============================================================================
// Administración y Depurador (Capa 9, Pasos 7 y 8)
// ==============================================================================

export async function getAlmacenamiento(): Promise<Almacenamiento> {
  return request<Almacenamiento>('/admin/almacenamiento');
}

export async function getPoliticaRetencion(): Promise<PoliticaRetencion> {
  return request<PoliticaRetencion>('/admin/retencion');
}

/** Ensayo sin efectos. Deja constancia en el rastro de quién consultó qué se borraría. */
export async function getPrevisualizacionPurga(
  solicitadoPor = 'cockpit'
): Promise<PrevisualizacionPurga> {
  return request<PrevisualizacionPurga>(
    `/admin/purga/previsualizacion?solicitado_por=${encodeURIComponent(solicitadoPor)}`
  );
}

export async function getEjecuciones(
  page = 1,
  limit = 10
): Promise<PaginatedResponse<Ejecucion>> {
  return request<PaginatedResponse<Ejecucion>>(`/admin/ejecuciones?page=${page}&limit=${limit}`);
}

export async function getDiagnosticoProspeccion(): Promise<DiagnosticoProspeccion> {
  return request<DiagnosticoProspeccion>('/admin/prospeccion/diagnostico');
}

export async function ejecutarPurga(solicitud: SolicitudPurga): Promise<ResultadoPurga> {
  return request<ResultadoPurga>('/admin/purga', {
    method: 'POST',
    body: JSON.stringify(solicitud),
  });
}

export async function crearBackup(): Promise<ResultadoBackup> {
  return request<ResultadoBackup>('/admin/backup', { method: 'POST' });
}

export async function rescatarExpedientes(
  expedientes: string[],
  solicitadoPor = 'cockpit'
): Promise<{ rescatados: number; expedientes: string[] }> {
  return request<{ rescatados: number; expedientes: string[] }>('/admin/expedientes/rescatar', {
    method: 'POST',
    body: JSON.stringify({ expedientes, solicitado_por: solicitadoPor }),
  });
}

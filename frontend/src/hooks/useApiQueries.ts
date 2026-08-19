/**
 * frontend/src/hooks/useApiQueries.ts — Custom React Query Hooks (Capa 8 - Paso 3)
 * Ecosistema Automático de Licitaciones (bfr_incoop)
 *
 * Hooks de React para el consumo asíncrono y reactivo de la Pasarela API RESTful (Capa 7).
 * Incorporan Smart Polling, preservación de datos anteriores en paginación y caching.
 */

import { useQuery, keepPreviousData } from '@tanstack/react-query';
import { QUERY_KEYS } from '../lib/react-query';
import {
  getHealth,
  getKPIs,
  getLicitaciones,
  getLicitacionById,
  getAlertasTempranas,
  getAlertaById,
  getEjecuciones,
} from '../lib/api-client';
import type { LicitacionesQueryParams, AlertasQueryParams } from '../types/api';

/**
 * Hook para monitorizar el estado de salud del backend FastAPI y SQLite v5.
 * Smart Polling reducido a 15 segundos.
 */
/**
 * Estado de la última prospección, para el indicador de la cabecera (Capa 10, Paso 7).
 *
 * El sondeo se acelera mientras hay una corrida en marcha —5 s frente a 60 s— porque es el
 * único momento en que el dato cambia y el único en que alguien lo está mirando: quien acaba
 * de hacer doble clic espera ver que el sistema termina. Fuera de ese rato, preguntar cada
 * cinco segundos sería ruido sobre la misma base que el pipeline está escribiendo.
 */
export function useUltimaProspeccionQuery() {
  return useQuery({
    queryKey: QUERY_KEYS.ultimaProspeccion,
    queryFn: () => getEjecuciones(1, 1),
    refetchInterval: (query) =>
      query.state.data?.items?.[0]?.estado === 'RUNNING' ? 5 * 1000 : 60 * 1000,
  });
}

export function useHealthQuery() {
  return useQuery({
    queryKey: QUERY_KEYS.health,
    queryFn: getHealth,
    refetchInterval: 15 * 1000,
  });
}

/**
 * Hook para obtener el resumen global de métricas del Funnel comercial y Working Capital.
 * Smart Polling cada 30 segundos.
 */
export function useKPIsQuery(ambito?: string) {
  return useQuery({
    queryKey: QUERY_KEYS.kpis(ambito),
    queryFn: () => getKPIs(ambito),
    refetchInterval: 30 * 1000,
    placeholderData: keepPreviousData, // Evita el parpadeo al mover el interruptor de ámbito
  });
}

/**
 * Hook para consultar la tabla paginada y filtrable de expedientes de licitación (PSCP).
 */
export function useLicitacionesQuery(params: LicitacionesQueryParams = {}) {
  return useQuery({
    queryKey: QUERY_KEYS.licitaciones(params),
    queryFn: () => getLicitaciones(params),
    placeholderData: keepPreviousData, // Evita parpadeos al cambiar de página o aplicar filtros
  });
}

/**
 * Hook para consultar el detalle completo de una licitación individual (con dictamen semántico IA).
 */
export function useLicitacionDetailQuery(id: string | null | undefined) {
  return useQuery({
    queryKey: QUERY_KEYS.licitacionDetail(id || ''),
    queryFn: () => getLicitacionById(id!),
    enabled: Boolean(id), // Solo ejecuta la consulta si el ID es válido
  });
}

/**
 * Hook para consultar la tabla paginada de alertas tempranas de boletines (DOGC/BOPB).
 */
export function useAlertasTempranasQuery(params: AlertasQueryParams = {}) {
  return useQuery({
    queryKey: QUERY_KEYS.alertas(params),
    queryFn: () => getAlertasTempranas(params),
    placeholderData: keepPreviousData,
  });
}

/**
 * Hook para consultar el detalle completo de una alerta temprana del Centinela.
 */
export function useAlertaDetailQuery(id_alerta: string | null | undefined) {
  return useQuery({
    queryKey: QUERY_KEYS.alertaDetail(id_alerta || ''),
    queryFn: () => getAlertaById(id_alerta!),
    enabled: Boolean(id_alerta),
  });
}

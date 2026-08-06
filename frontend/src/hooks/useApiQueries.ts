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
} from '../lib/api-client';
import type { LicitacionesQueryParams, AlertasQueryParams } from '../types/api';

/**
 * Hook para monitorizar el estado de salud del backend FastAPI y SQLite v5.
 * Smart Polling reducido a 15 segundos.
 */
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
export function useKPIsQuery() {
  return useQuery({
    queryKey: QUERY_KEYS.kpis,
    queryFn: getKPIs,
    refetchInterval: 30 * 1000,
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

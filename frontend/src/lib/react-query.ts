/**
 * frontend/src/lib/react-query.ts — Configuración Global de TanStack Query v5 (Capa 8 - Paso 3)
 * Ecosistema Automático de Licitaciones (bfr_incoop)
 *
 * Instancia del QueryClient con políticas de caché, Smart Polling (30s)
 * y llaves de consulta (QUERY_KEYS) centralizadas e inmutables.
 */

import { QueryClient } from '@tanstack/react-query';
import type { LicitacionesQueryParams, AlertasQueryParams } from '../types/api';

// ==============================================================================
// Instancia Global del QueryClient
// ==============================================================================

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 10 * 1000, // 10 segundos antes de considerar los datos obsoletos
      refetchInterval: 30 * 1000, // Smart Polling cada 30 segundos
      refetchIntervalInBackground: false, // Solo en ventanas/pestañas enfocadas
      refetchOnWindowFocus: true, // Revalidación al volver a enfocar la ventana
      retry: 2, // 2 reintentos defensivos en caso de error puntual de red
    },
    mutations: {
      retry: 0, // Las mutaciones no se reintentan automáticamente para evitar duplicidad
    },
  },
});

// ==============================================================================
// Definición Centralizada de Query Keys
// ==============================================================================

export const QUERY_KEYS = {
  health: ['health'] as const,
  // El ámbito forma parte de la clave: sin él, cambiar el interruptor devolvería la caché
  // de la población anterior y el Dashboard enseñaría las cifras de toda España bajo el
  // rótulo de Catalunya. Es el mismo motivo por el que `licitaciones` lleva sus filtros.
  kpis: (ambito?: string) => ['kpis', ambito ?? null] as const,
  //: Prefijo para invalidar **todas** las variantes de ámbito a la vez tras una mutación.
  //: `kpis(undefined)` sólo alcanzaría a la de «sin filtro», y el Dashboard se quedaría con
  //: las cifras viejas justo en el estado en que el usuario lo mira: con Catalunya puesta.
  kpisTodos: ['kpis'] as const,
  // Administración y Depurador (Capa 9, Paso 9)
  almacenamiento: ['admin', 'almacenamiento'] as const,
  retencion: ['admin', 'retencion'] as const,
  previsualizacionPurga: ['admin', 'purga', 'previsualizacion'] as const,
  ejecuciones: (page: number) => ['admin', 'ejecuciones', page] as const,
  // Clave propia y no `ejecuciones(1)`: el indicador de la cabecera pide una sola fila
  // y sondea cada pocos segundos, mientras que la pantalla de Administración pide diez
  // y no debe repintarse sola. Compartir clave haría que una consulta pisara a la otra.
  ultimaProspeccion: ['admin', 'ejecuciones', 'ultima'] as const,
  licitaciones: (params: LicitacionesQueryParams = {}) =>
    ['licitaciones', params] as const,
  licitacionDetail: (id: string) => ['licitaciones', 'detail', id] as const,
  alertas: (params: AlertasQueryParams = {}) =>
    ['alertas-tempranas', params] as const,
  alertaDetail: (id_alerta: string) => ['alertas-tempranas', 'detail', id_alerta] as const,
};

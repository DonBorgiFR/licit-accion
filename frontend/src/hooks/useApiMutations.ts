/**
 * frontend/src/hooks/useApiMutations.ts — Custom React Mutation Hooks (Capa 8 - Paso 3)
 * Ecosistema Automático de Licitaciones (bfr_incoop)
 *
 * Hooks de mutación con actualizaciones optimistas (Optimistic Updates),
 * captura defensiva de errores, rollback atómico de la caché y revalidación de KPIs.
 */

import { useMutation, useQueryClient } from '@tanstack/react-query';
import { QUERY_KEYS } from '../lib/react-query';
import { updateEstadoLicitacion, updateEstadoAlerta, APIClientError } from '../lib/api-client';
import type {
  TransicionEstadoLicitacion,
  TransicionEstadoAlerta,
  Licitacion,
  AlertaBoletin,
  PaginatedResponse,
} from '../types/api';

export interface MutationOptions<TData, TError, TVariables> {
  onSuccess?: (data: TData, variables: TVariables) => void;
  onError?: (error: TError, variables: TVariables, context: any) => void;
}

/**
 * Hook de mutación para cambiar el estado operativo de una licitación (PSCP).
 * Implementa actualización optimista instantánea y rollback atómico en caso de error.
 */
export function useMutateEstadoLicitacion(
  options?: MutationOptions<Licitacion, APIClientError, { id: string; payload: TransicionEstadoLicitacion }>
) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: TransicionEstadoLicitacion }) =>
      updateEstadoLicitacion(id, payload),

    onMutate: async ({ id, payload }) => {
      // 1. Cancelar peticiones salientes para no sobrescribir la actualización optimista
      await queryClient.cancelQueries({ queryKey: ['licitaciones'] });

      // 2. Guardar snapshots de detalle y listas para rollback realmente atómico.
      const detailKey = QUERY_KEYS.licitacionDetail(id);
      const previousDetail = queryClient.getQueryData<Licitacion>(detailKey);
      const previousLists = queryClient.getQueriesData<PaginatedResponse<Licitacion>>({ queryKey: ['licitaciones'] });

      // 3. Aplicar actualización optimista en la vista de detalle si existe en caché
      if (previousDetail) {
        queryClient.setQueryData<Licitacion>(detailKey, {
          ...previousDetail,
          lotes: previousDetail.lotes.map((lote) => lote.lote_numero === payload.lote_numero ? {
            ...lote,
            estado_operativo: payload.nuevo_estado,
            notas_usuario: payload.notas !== undefined ? payload.notas : lote.notas_usuario,
          } : lote),
        });
      }

      // 4. Actualizar optimistamente en las listas paginadas activas
      queryClient.setQueriesData<PaginatedResponse<Licitacion>>(
        { queryKey: ['licitaciones'] },
        (oldData) => {
          if (!oldData) return oldData;
          return {
            ...oldData,
            items: oldData.items.map((item) => {
              if (item.id === id) {
                return {
                  ...item,
                  lotes: item.lotes.map((lote) => lote.lote_numero === payload.lote_numero ? {
                    ...lote,
                    estado_operativo: payload.nuevo_estado,
                    notas_usuario: payload.notas !== undefined ? payload.notas : lote.notas_usuario,
                  } : lote),
                };
              }
              return item;
            }),
          };
        }
      );

      return { previousDetail, previousLists };
    },

    onError: (err, variables, context) => {
      // Rollback al estado previo si falla la API
      if (context?.previousDetail) {
        queryClient.setQueryData(QUERY_KEYS.licitacionDetail(variables.id), context.previousDetail);
      }
      context?.previousLists?.forEach(([key, value]: [unknown, PaginatedResponse<Licitacion> | undefined]) => {
        queryClient.setQueryData(key as readonly unknown[], value);
      });
      options?.onError?.(err as APIClientError, variables, context);
    },

    onSuccess: (data, variables) => {
      options?.onSuccess?.(data, variables);
    },

    onSettled: () => {
      // Revalidar tablas y resumen de KPIs
      queryClient.invalidateQueries({ queryKey: ['licitaciones'] });
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.kpis });
    },
  });
}

/**
 * Hook de mutación para cambiar el estado operativo de una alerta temprana (DOGC/BOPB).
 * Implementa actualización optimista instantánea y rollback atómico.
 */
export function useMutateEstadoAlerta(
  options?: MutationOptions<AlertaBoletin, APIClientError, { id_alerta: string; payload: TransicionEstadoAlerta }>
) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ id_alerta, payload }: { id_alerta: string; payload: TransicionEstadoAlerta }) =>
      updateEstadoAlerta(id_alerta, payload),

    onMutate: async ({ id_alerta, payload }) => {
      await queryClient.cancelQueries({ queryKey: ['alertas-tempranas'] });

      const detailKey = QUERY_KEYS.alertaDetail(id_alerta);
      const previousDetail = queryClient.getQueryData<AlertaBoletin>(detailKey);

      if (previousDetail) {
        queryClient.setQueryData<AlertaBoletin>(detailKey, {
          ...previousDetail,
          estado_operativo: payload.nuevo_estado,
          notas_usuario: payload.notas !== undefined ? payload.notas : previousDetail.notas_usuario,
        });
      }

      queryClient.setQueriesData<PaginatedResponse<AlertaBoletin>>(
        { queryKey: ['alertas-tempranas'] },
        (oldData) => {
          if (!oldData) return oldData;
          return {
            ...oldData,
            items: oldData.items.map((item) => {
              if (item.id_alerta === id_alerta) {
                return {
                  ...item,
                  estado_operativo: payload.nuevo_estado,
                  notas_usuario: payload.notas !== undefined ? payload.notas : item.notas_usuario,
                };
              }
              return item;
            }),
          };
        }
      );

      return { previousDetail };
    },

    onError: (err, variables, context) => {
      if (context?.previousDetail) {
        queryClient.setQueryData(QUERY_KEYS.alertaDetail(variables.id_alerta), context.previousDetail);
      }
      options?.onError?.(err as APIClientError, variables, context);
    },

    onSuccess: (data, variables) => {
      options?.onSuccess?.(data, variables);
    },

    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ['alertas-tempranas'] });
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.kpis });
    },
  });
}

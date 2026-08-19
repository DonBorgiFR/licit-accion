/**
 * frontend/src/components/HealthIndicator.tsx — Sensor de Salud de la API en Tiempo Real (Capa 8 - Paso 5)
 * Ecosistema Automático de Licitaciones (bfr_incoop)
 */

import React, { useState } from 'react';
import { Activity, Database, CheckCircle, AlertTriangle, XCircle, Info } from 'lucide-react';
import { useHealthQuery } from '../hooks/useApiQueries';
import { Badge } from './ui/Badge';
import { formatDate } from '../lib/utils';

export const HealthIndicator: React.FC = () => {
  const { data, isLoading, isError } = useHealthQuery();
  const [showTooltip, setShowTooltip] = useState(false);

  let statusType: 'online' | 'degraded' | 'offline' = 'offline';
  let statusText = 'API Offline';
  let badgeVariant: 'success' | 'warning' | 'danger' = 'danger';

  if (isLoading) {
    statusType = 'degraded';
    statusText = 'Verificando...';
    badgeVariant = 'warning';
  } else if (!isError && data?.status === 'OK' && data?.query_test_ok && data?.wal_mode_active) {
    statusType = 'online';
    statusText = 'API Online (WAL)';
    badgeVariant = 'success';
  } else if (!isError && data?.status === 'OK') {
    statusType = 'degraded';
    statusText = 'API Degradada';
    badgeVariant = 'warning';
  } else {
    statusType = 'offline';
    statusText = 'API Desconectada';
    badgeVariant = 'danger';
  }

  return (
    <div className="relative inline-block text-left">
      <div
        onMouseEnter={() => setShowTooltip(true)}
        onMouseLeave={() => setShowTooltip(false)}
        onClick={() => setShowTooltip(!showTooltip)}
        className="cursor-pointer"
      >
        <Badge
          variant={badgeVariant}
          className="px-3 py-1 gap-2 shadow-xs hover:shadow-sm transition-all"
        >
          {/* Status Dot with Pulse Animation */}
          <span className="relative flex h-2 w-2">
            {statusType === 'online' && (
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-conforme opacity-75"></span>
            )}
            <span
              className={`relative inline-flex rounded-full h-2 w-2 ${
                statusType === 'online'
                  ? 'bg-conforme'
                  : statusType === 'degraded'
                  ? 'bg-atencion'
                  : 'bg-alarma'
              }`}
            ></span>
          </span>
          <Activity className="w-3.5 h-3.5 text-current opacity-80" />
          <span className="font-mono text-xs font-semibold">{statusText}</span>
        </Badge>
      </div>

      {/* Tooltip Diagnóstico Flotante */}
      {showTooltip && (
        <div className="absolute right-0 mt-2 w-72 bg-surface rounded-xl border border-line shadow-xl p-4 z-50 text-xs animate-in fade-in zoom-in-95 duration-150">
          <div className="flex items-center justify-between border-b border-line-soft pb-2.5 mb-3">
            <div className="flex items-center gap-1.5 font-bold text-ink">
              <Database className="w-4 h-4 text-acento" />
              {/* La versión se lee del propio healthcheck. Estaba codificada como "v5" y
                  siguió anunciando v5 después de migrar a v6: un panel de diagnóstico que
                  afirma una versión distinta de la real es peor que no decir ninguna. */}
              <span>Autodiagnóstico SQLite{data?.schema_version ? ` v${data.schema_version}` : ''}</span>
            </div>
            <Info className="w-3.5 h-3.5 text-ink-faint" />
          </div>

          <div className="space-y-2 text-ink-dim font-mono">
            <div className="flex items-center justify-between">
              <span className="text-ink-faint">Estado API:</span>
              <span className="font-semibold text-ink">{data?.status || 'N/A'}</span>
            </div>

            <div className="flex items-center justify-between">
              <span className="text-ink-faint">Esquema DB:</span>
              <span className="font-semibold text-acento">
                v{data?.schema_version ?? '?'}
              </span>
            </div>

            <div className="flex items-center justify-between">
              <span className="text-ink-faint">Diario WAL:</span>
              <span className="flex items-center gap-1">
                {data?.wal_mode_active ? (
                  <>
                    <CheckCircle className="w-3.5 h-3.5 text-conforme" />
                    <span className="text-conforme font-semibold">Activo</span>
                  </>
                ) : (
                  <>
                    <AlertTriangle className="w-3.5 h-3.5 text-atencion" />
                    <span className="text-atencion font-semibold">Inactivo</span>
                  </>
                )}
              </span>
            </div>

            <div className="flex items-center justify-between">
              <span className="text-ink-faint">Permiso Disco:</span>
              <span className="flex items-center gap-1">
                {data?.directorio_accesible ? (
                  <CheckCircle className="w-3.5 h-3.5 text-conforme" />
                ) : (
                  <XCircle className="w-3.5 h-3.5 text-alarma" />
                )}
                <span>{data?.directorio_accesible ? 'Escritura OK' : 'Error Disco'}</span>
              </span>
            </div>

            <div className="flex items-center justify-between">
              <span className="text-ink-faint">Consulta Test:</span>
              <span className="flex items-center gap-1">
                {data?.query_test_ok ? (
                  <CheckCircle className="w-3.5 h-3.5 text-conforme" />
                ) : (
                  <XCircle className="w-3.5 h-3.5 text-alarma" />
                )}
                <span>{data?.query_test_ok ? 'OK' : 'Fallo SQL'}</span>
              </span>
            </div>

            <div className="pt-2 border-t border-line-soft text-[10px] text-ink-faint flex items-center justify-between">
              <span>Último pulso UTC:</span>
              <span>{formatDate(data?.timestamp)}</span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

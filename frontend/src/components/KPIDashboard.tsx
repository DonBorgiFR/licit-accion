/**
 * frontend/src/components/KPIDashboard.tsx — Dashboard Analítico de KPIs y Tesorería (Capa 8 - Paso 6)
 * Ecosistema Automático de Licitaciones (bfr_incoop)
 */

import React from 'react';
import {
  TrendingUp,
  Briefcase,
  Layers,
  Award,
  Lock,
  Radio,
  RefreshCw,
  AlertCircle,
  CheckCircle2,
  FileCheck,
  Building,
} from 'lucide-react';
import { useKPIsQuery } from '../hooks/useApiQueries';
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from './ui/Card';
import { Badge } from './ui/Badge';
import { Button } from './ui/Button';
import { Skeleton } from './ui/Skeleton';
import { formatCurrency, formatPercent } from '../lib/utils';

interface KPIDashboardProps {
  /** Ámbito territorial en vigor (H-47). `undefined` es «todo el Estado». */
  ambito?: string;
}

export const KPIDashboard: React.FC<KPIDashboardProps> = ({ ambito }) => {
  const { data, isLoading, isError, refetch, isFetching } = useKPIsQuery(ambito);

  if (isLoading) {
    return (
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <Skeleton className="h-8 w-64" />
          <Skeleton className="h-9 w-32" />
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          <Skeleton className="h-32 rounded-xl" />
          <Skeleton className="h-32 rounded-xl" />
          <Skeleton className="h-32 rounded-xl" />
          <Skeleton className="h-32 rounded-xl" />
        </div>
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <Skeleton className="h-72 rounded-xl" />
          <Skeleton className="h-72 rounded-xl" />
        </div>
      </div>
    );
  }

  if (isError) {
    return (
      <Card className="border-alarma/35 bg-alarma/6">
        <CardContent className="p-8 text-center space-y-4">
          <div className="w-12 h-12 rounded-full bg-alarma/18 text-alarma flex items-center justify-center mx-auto">
            <AlertCircle className="w-6 h-6" />
          </div>
          <div>
            <h3 className="text-base font-bold text-ink">
              Error de Conexión con la Pasarela API
            </h3>
            <p className="text-xs text-ink-faint mt-1 max-w-md mx-auto">
              No se han podido cargar las métricas en tiempo real. Verifica que el servidor FastAPI está en ejecución.
            </p>
          </div>
          <Button variant="danger" size="sm" onClick={() => refetch()} isLoading={isFetching}>
            <RefreshCw className="w-4 h-4 mr-1.5" /> Reintentar Consulta
          </Button>
        </CardContent>
      </Card>
    );
  }

  const winRate = data?.win_rate_porcentaje || 0;

  return (
    <div className="space-y-6">
      {/* Encabezado y Control de Refresco Manual */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold text-ink tracking-tight flex items-center gap-2">
            <span>Control de Gestión & Tesorería</span>
            {isFetching && (
              <span className="inline-flex items-center gap-1 text-[10px] font-mono text-acento bg-acento/10 px-2 py-0.5 rounded-full border border-acento/25">
                <RefreshCw className="w-3 h-3 animate-spin" /> Actualizando...
              </span>
            )}
          </h2>
          <p className="text-xs text-ink-faint mt-0.5">
            {/* Sin número de versión: aquí era decorativo y quedó desfasado al migrar a v6.
                La versión real se consulta en el autodiagnóstico de la cabecera.

                El ámbito se lee de la RESPUESTA y no del estado de la pantalla, a propósito:
                así el rótulo declara la población que de verdad se ha contado. Si un día la
                API ignorase el parámetro, aquí se vería —y no al revés, que es como estos
                defectos llegan a producción (H-08, H-21). */}
            Métricas consolidadas en tiempo real desde SQLite (WAL Mode)
            {data?.ambito === 'catalunya'
              ? ' · Ámbito: Catalunya'
              : ' · Ámbito: todo el Estado'}
            .
          </p>
        </div>

        <Button
          variant="outline"
          size="sm"
          onClick={() => refetch()}
          isLoading={isFetching}
          leftIcon={<RefreshCw className="w-3.5 h-3.5" />}
        >
          Sincronizar
        </Button>
      </div>

      {/* Grid Superior de 4 Tarjetas Métricas Principales */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* Card 1: Volumen Total PBL */}
        <Card className="border-acento/25 bg-gradient-to-br from-surface to-acento/5">
          <CardContent className="p-5">
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold uppercase tracking-wider text-acento">
                Volumen Total Licitado
              </span>
              <div className="w-9 h-9 rounded-lg bg-acento/15 text-acento flex items-center justify-center">
                <TrendingUp className="w-5 h-5" />
              </div>
            </div>
            <div className="mt-3">
              <div className="text-2xl font-bold text-ink font-mono tabular-nums">
                {formatCurrency(data?.volumen_total_pbl)}
              </div>
              <p className="text-[11px] text-ink-faint mt-1 flex items-center gap-1">
                <span>PBL acumulado sin IVA</span>
              </p>
            </div>
          </CardContent>
        </Card>

        {/* Card 2: Capital de Avales Retenidos (Working Capital) */}
        <Card className="border-conforme/25 bg-gradient-to-br from-surface to-conforme/5">
          <CardContent className="p-5">
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold uppercase tracking-wider text-conforme">
                Working Capital (Avales)
              </span>
              <div className="w-9 h-9 rounded-lg bg-conforme/18 text-conforme flex items-center justify-center">
                <Lock className="w-5 h-5" />
              </div>
            </div>
            <div className="mt-3">
              <div className="text-2xl font-bold text-ink font-mono tabular-nums">
                {formatCurrency(data?.capital_garantias_retenidas)}
              </div>
              <p className="text-[11px] text-conforme font-medium mt-1">
                Garantías definitivas (5% PBL)
              </p>
            </div>
          </CardContent>
        </Card>

        {/* Card 3: Win-Rate % (Tasa de Éxito) */}
        <Card className="border-atencion/25 bg-gradient-to-br from-surface to-atencion/5">
          <CardContent className="p-5">
            <div className="flex items-center justify-between">
              {/* Población histórica: cuenta también lo archivado (Capa 9). La memoria
                  comercial no caduca ni desaparece del indicador porque el Depurador saque
                  el expediente del canal principal. Se etiqueta explícitamente para que no
                  se lea sobre la misma población que la cartera viva de abajo. */}
              <span className="text-xs font-semibold uppercase tracking-wider text-atencion">
                Ratio de Éxito (Win-Rate histórico)
              </span>
              <div className="w-9 h-9 rounded-lg bg-atencion/18 text-atencion flex items-center justify-center">
                <Award className="w-5 h-5" />
              </div>
            </div>
            <div className="mt-3">
              <div className="flex items-baseline justify-between">
                <div className="text-2xl font-bold text-ink font-mono tabular-nums">
                  {formatPercent(winRate)}
                </div>
                <Badge variant={winRate >= 30 ? 'success' : 'warning'} className="font-mono">
                  {data?.licitaciones_ganadas || 0} ganadas
                </Badge>
              </div>
              {/* Progress bar visual */}
              <div className="w-full bg-line rounded-full h-1.5 mt-2 overflow-hidden">
                <div
                  className="bg-atencion h-full rounded-full transition-all duration-500"
                  style={{ width: `${Math.min(100, Math.max(0, winRate))}%` }}
                />
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Card 4: Alertas Tempranas Activas */}
        <Card className="border-marca-cian/25 bg-gradient-to-br from-surface to-marca-cian/5">
          <CardContent className="p-5">
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold uppercase tracking-wider text-acento">
                Canal Centinela
              </span>
              <div className="w-9 h-9 rounded-lg bg-marca-cian/20 text-acento flex items-center justify-center">
                <Radio className="w-5 h-5" />
              </div>
            </div>
            <div className="mt-3">
              <div className="text-2xl font-bold text-ink font-mono tabular-nums">
                {data?.alertas_tempranas_activas || 0}
              </div>
              <p className="text-[11px] text-acento font-medium mt-1">
                Boletines oficiales (DOGC/BOPB)
              </p>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Grid Secundario de 2 Columnas de Desglose Profundo */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Bloque 1: Funnel de Conversión PSCP */}
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Briefcase className="w-5 h-5 text-acento" />
                <CardTitle>Funnel Comercial PSCP / PCSP</CardTitle>
              </div>
              <Badge variant="indigo">{data?.total_expedientes || 0} Expedientes</Badge>
            </div>
            <CardDescription>
              Desglose por estado del ciclo de licitación formal.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid grid-cols-2 gap-3">
              <div className="p-3.5 rounded-xl bg-surface-2 border border-line/80">
                {/* Cartera viva: excluye lo archivado, igual que la tabla del Funnel. No
                    cuadra con "ganadas" y "perdidas" de abajo, y no debe: aquéllas cuentan
                    todo el histórico. Nombrar cada población evita el error de sumarlas
                    —el mismo que costó H-08 y H-21—. */}
                <span className="text-xs text-ink-faint block">Lotes en el canal principal</span>
                <span className="text-lg font-bold text-ink font-mono tabular-nums">
                  {data?.total_lotes || 0}
                </span>
              </div>
              <div className="p-3.5 rounded-xl bg-atencion/7 border border-atencion/21">
                <span className="text-xs text-atencion block font-medium">En Estudio Técnico</span>
                <span className="text-lg font-bold text-atencion font-mono tabular-nums">
                  {data?.licitaciones_estudio || 0}
                </span>
              </div>
            </div>

            <div className="space-y-2.5 pt-2">
              <div className="flex items-center justify-between p-3 rounded-lg border border-line-soft bg-surface">
                <div className="flex items-center gap-2.5">
                  <FileCheck className="w-4 h-4 text-acento" />
                  <span className="text-xs font-semibold text-ink-dim">Presentadas (En Evaluación)</span>
                </div>
                <span className="font-mono font-bold text-ink">{data?.licitaciones_presentadas || 0}</span>
              </div>

              <div className="flex items-center justify-between p-3 rounded-lg border border-conforme/25 bg-conforme/5">
                <div className="flex items-center gap-2.5">
                  <CheckCircle2 className="w-4 h-4 text-conforme" />
                  <span className="text-xs font-semibold text-conforme">Adjudicadas (Ganadas)</span>
                </div>
                <span className="font-mono font-bold text-conforme">{data?.licitaciones_ganadas || 0}</span>
              </div>

              <div className="flex items-center justify-between p-3 rounded-lg border border-alarma/25 bg-alarma/5">
                <div className="flex items-center gap-2.5">
                  <Layers className="w-4 h-4 text-alarma" />
                  <span className="text-xs font-semibold text-alarma">Perdidas (Competencia)</span>
                </div>
                <span className="font-mono font-bold text-alarma">{data?.licitaciones_perdidas || 0}</span>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Bloque 2: Inteligencia de Tesorería & Working Capital */}
        <Card>
          <CardHeader>
            <div className="flex items-center gap-2">
              <Building className="w-5 h-5 text-acento" />
              <CardTitle>Impacto Financiero & Caja</CardTitle>
            </div>
            <CardDescription>
              Seguimiento del capital inmovilizado y retorno estimado de avales depositados.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="p-4 rounded-xl bg-surface-2 border border-line space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-xs text-ink-dim font-medium">Capacidad de Inmovilizado en Avales</span>
                <span className="text-xs font-mono font-semibold text-acento">5% PBL Normativo</span>
              </div>
              <div className="text-xl font-bold text-ink font-mono tabular-nums">
                {formatCurrency(data?.capital_garantias_retenidas)}
              </div>
              <p className="text-[11px] text-ink-faint leading-relaxed">
                Importe estimado en caja o cauciones que permanecen inmovilizadas durante la ejecución de los contratos vigentes.
              </p>
            </div>

            <div className="p-4 rounded-xl bg-acento/5 border border-acento/25 space-y-2">
              <span className="text-xs font-semibold text-acento block">
                💡 Consejo para el Controller
              </span>
              <p className="text-xs text-acento/90 leading-relaxed">
                Al solicitar seguros de caución en lugar de depósitos en efectivo en la Caja General de Depósitos, Incoop evita congelar liquidez directa de su cuenta bancaria.
              </p>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
};

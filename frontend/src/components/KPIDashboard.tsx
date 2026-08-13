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

export const KPIDashboard: React.FC = () => {
  const { data, isLoading, isError, refetch, isFetching } = useKPIsQuery();

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
      <Card className="border-rose-200 bg-rose-50/50">
        <CardContent className="p-8 text-center space-y-4">
          <div className="w-12 h-12 rounded-full bg-rose-100 text-rose-600 flex items-center justify-center mx-auto">
            <AlertCircle className="w-6 h-6" />
          </div>
          <div>
            <h3 className="text-base font-bold text-slate-900">
              Error de Conexión con la Pasarela API
            </h3>
            <p className="text-xs text-slate-500 mt-1 max-w-md mx-auto">
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
          <h2 className="text-xl font-bold text-slate-900 tracking-tight flex items-center gap-2">
            <span>Control de Gestión & Tesorería</span>
            {isFetching && (
              <span className="inline-flex items-center gap-1 text-[10px] font-mono text-indigo-600 bg-indigo-50 px-2 py-0.5 rounded-full border border-indigo-100">
                <RefreshCw className="w-3 h-3 animate-spin" /> Actualizando...
              </span>
            )}
          </h2>
          <p className="text-xs text-slate-500 mt-0.5">
            {/* Sin número de versión: aquí era decorativo y quedó desfasado al migrar a v6.
                La versión real se consulta en el autodiagnóstico de la cabecera. */}
            Métricas consolidadas en tiempo real desde SQLite (WAL Mode).
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
        <Card className="border-indigo-100 bg-gradient-to-br from-white to-indigo-50/30">
          <CardContent className="p-5">
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold uppercase tracking-wider text-indigo-700">
                Volumen Total Licitado
              </span>
              <div className="w-9 h-9 rounded-lg bg-indigo-100 text-indigo-600 flex items-center justify-center">
                <TrendingUp className="w-5 h-5" />
              </div>
            </div>
            <div className="mt-3">
              <div className="text-2xl font-bold text-slate-900 font-mono tabular-nums">
                {formatCurrency(data?.volumen_total_pbl)}
              </div>
              <p className="text-[11px] text-slate-500 mt-1 flex items-center gap-1">
                <span>PBL acumulado sin IVA</span>
              </p>
            </div>
          </CardContent>
        </Card>

        {/* Card 2: Capital de Avales Retenidos (Working Capital) */}
        <Card className="border-emerald-100 bg-gradient-to-br from-white to-emerald-50/30">
          <CardContent className="p-5">
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold uppercase tracking-wider text-emerald-700">
                Working Capital (Avales)
              </span>
              <div className="w-9 h-9 rounded-lg bg-emerald-100 text-emerald-600 flex items-center justify-center">
                <Lock className="w-5 h-5" />
              </div>
            </div>
            <div className="mt-3">
              <div className="text-2xl font-bold text-slate-900 font-mono tabular-nums">
                {formatCurrency(data?.capital_garantias_retenidas)}
              </div>
              <p className="text-[11px] text-emerald-700 font-medium mt-1">
                Garantías definitivas (5% PBL)
              </p>
            </div>
          </CardContent>
        </Card>

        {/* Card 3: Win-Rate % (Tasa de Éxito) */}
        <Card className="border-amber-100 bg-gradient-to-br from-white to-amber-50/30">
          <CardContent className="p-5">
            <div className="flex items-center justify-between">
              {/* Población histórica: cuenta también lo archivado (Capa 9). La memoria
                  comercial no caduca ni desaparece del indicador porque el Depurador saque
                  el expediente del canal principal. Se etiqueta explícitamente para que no
                  se lea sobre la misma población que la cartera viva de abajo. */}
              <span className="text-xs font-semibold uppercase tracking-wider text-amber-700">
                Ratio de Éxito (Win-Rate histórico)
              </span>
              <div className="w-9 h-9 rounded-lg bg-amber-100 text-amber-600 flex items-center justify-center">
                <Award className="w-5 h-5" />
              </div>
            </div>
            <div className="mt-3">
              <div className="flex items-baseline justify-between">
                <div className="text-2xl font-bold text-slate-900 font-mono tabular-nums">
                  {formatPercent(winRate)}
                </div>
                <Badge variant={winRate >= 30 ? 'success' : 'warning'} className="font-mono">
                  {data?.licitaciones_ganadas || 0} ganadas
                </Badge>
              </div>
              {/* Progress bar visual */}
              <div className="w-full bg-slate-200 rounded-full h-1.5 mt-2 overflow-hidden">
                <div
                  className="bg-amber-500 h-full rounded-full transition-all duration-500"
                  style={{ width: `${Math.min(100, Math.max(0, winRate))}%` }}
                />
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Card 4: Alertas Tempranas Activas */}
        <Card className="border-cyan-100 bg-gradient-to-br from-white to-cyan-50/30">
          <CardContent className="p-5">
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold uppercase tracking-wider text-cyan-700">
                Canal Centinela
              </span>
              <div className="w-9 h-9 rounded-lg bg-cyan-100 text-cyan-600 flex items-center justify-center">
                <Radio className="w-5 h-5" />
              </div>
            </div>
            <div className="mt-3">
              <div className="text-2xl font-bold text-slate-900 font-mono tabular-nums">
                {data?.alertas_tempranas_activas || 0}
              </div>
              <p className="text-[11px] text-cyan-700 font-medium mt-1">
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
                <Briefcase className="w-5 h-5 text-indigo-600" />
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
              <div className="p-3.5 rounded-xl bg-slate-50 border border-slate-200/80">
                {/* Cartera viva: excluye lo archivado, igual que la tabla del Funnel. No
                    cuadra con "ganadas" y "perdidas" de abajo, y no debe: aquéllas cuentan
                    todo el histórico. Nombrar cada población evita el error de sumarlas
                    —el mismo que costó H-08 y H-21—. */}
                <span className="text-xs text-slate-500 block">Lotes en el canal principal</span>
                <span className="text-lg font-bold text-slate-900 font-mono tabular-nums">
                  {data?.total_lotes || 0}
                </span>
              </div>
              <div className="p-3.5 rounded-xl bg-amber-50/60 border border-amber-200/60">
                <span className="text-xs text-amber-700 block font-medium">En Estudio Técnico</span>
                <span className="text-lg font-bold text-amber-900 font-mono tabular-nums">
                  {data?.licitaciones_estudio || 0}
                </span>
              </div>
            </div>

            <div className="space-y-2.5 pt-2">
              <div className="flex items-center justify-between p-3 rounded-lg border border-slate-100 bg-white">
                <div className="flex items-center gap-2.5">
                  <FileCheck className="w-4 h-4 text-cyan-600" />
                  <span className="text-xs font-semibold text-slate-700">Presentadas (En Evaluación)</span>
                </div>
                <span className="font-mono font-bold text-slate-900">{data?.licitaciones_presentadas || 0}</span>
              </div>

              <div className="flex items-center justify-between p-3 rounded-lg border border-emerald-100 bg-emerald-50/30">
                <div className="flex items-center gap-2.5">
                  <CheckCircle2 className="w-4 h-4 text-emerald-600" />
                  <span className="text-xs font-semibold text-emerald-900">Adjudicadas (Ganadas)</span>
                </div>
                <span className="font-mono font-bold text-emerald-700">{data?.licitaciones_ganadas || 0}</span>
              </div>

              <div className="flex items-center justify-between p-3 rounded-lg border border-rose-100 bg-rose-50/30">
                <div className="flex items-center gap-2.5">
                  <Layers className="w-4 h-4 text-rose-600" />
                  <span className="text-xs font-semibold text-rose-900">Perdidas (Competencia)</span>
                </div>
                <span className="font-mono font-bold text-rose-700">{data?.licitaciones_perdidas || 0}</span>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Bloque 2: Inteligencia de Tesorería & Working Capital */}
        <Card>
          <CardHeader>
            <div className="flex items-center gap-2">
              <Building className="w-5 h-5 text-indigo-600" />
              <CardTitle>Impacto Financiero & Caja</CardTitle>
            </div>
            <CardDescription>
              Seguimiento del capital inmovilizado y retorno estimado de avales depositados.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="p-4 rounded-xl bg-slate-50 border border-slate-200 space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-xs text-slate-600 font-medium">Capacidad de Inmovilizado en Avales</span>
                <span className="text-xs font-mono font-semibold text-indigo-600">5% PBL Normativo</span>
              </div>
              <div className="text-xl font-bold text-slate-900 font-mono tabular-nums">
                {formatCurrency(data?.capital_garantias_retenidas)}
              </div>
              <p className="text-[11px] text-slate-500 leading-relaxed">
                Importe estimado en caja o cauciones que permanecen inmovilizadas durante la ejecución de los contratos vigentes.
              </p>
            </div>

            <div className="p-4 rounded-xl bg-indigo-50/40 border border-indigo-100 space-y-2">
              <span className="text-xs font-semibold text-indigo-900 block">
                💡 Consejo para el Controller
              </span>
              <p className="text-xs text-indigo-800/90 leading-relaxed">
                Al solicitar seguros de caución en lugar de depósitos en efectivo en la Caja General de Depósitos, Incoop evita congelar liquidez directa de su cuenta bancaria.
              </p>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
};

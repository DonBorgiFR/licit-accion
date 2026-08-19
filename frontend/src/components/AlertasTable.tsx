/**
 * frontend/src/components/AlertasTable.tsx — Tabla del Canal Proactivo Centinela (Capa 8 - Paso 8)
 * Ecosistema Automático de Licitaciones (bfr_incoop)
 */

import React, { useState } from 'react';
import {
  Search,
  Radio,
  ExternalLink,
  Eye,
  Building,
  Calendar,
  AlertCircle,
  ChevronLeft,
  ChevronRight,
} from 'lucide-react';
import { useAlertasTempranasQuery } from '../hooks/useApiQueries';
import { useMutateEstadoAlerta } from '../hooks/useApiMutations';
import { Card } from './ui/Card';
import { Badge, ScoreBadge } from './ui/Badge';
import { Button } from './ui/Button';
import { Input } from './ui/Input';
import { Select } from './ui/Select';
import { Skeleton } from './ui/Skeleton';
import { useToast } from './ui/Toast';
import { formatDate } from '../lib/utils';
import { EstadoAlerta, FuenteBoletin, CategoriaFaseTemprana, type AlertaBoletin } from '../types/api';

interface AlertasTableProps {
  onSelectAlerta?: (id_alerta: string) => void;
}

export const AlertasTable: React.FC<AlertasTableProps> = ({ onSelectAlerta }) => {
  const { toast } = useToast();

  // Estados de Filtros y Paginación Server-Side
  const [page, setPage] = useState<number>(1);
  const [limit] = useState<number>(10);
  const [search, setSearch] = useState<string>('');
  const [fuente, setFuente] = useState<string>('');
  const [minScore, setMinScore] = useState<number>(0);
  const [estado, setEstado] = useState<string>('');

  // Consulta Server-Side
  const { data, isLoading, isError, isFetching, refetch } = useAlertasTempranasQuery({
    page,
    limit,
    search: search.trim() || undefined,
    fuente: fuente || undefined,
    min_score: minScore > 0 ? minScore : undefined,
    estado: estado || undefined,
  });

  // Mutación Optimista de Estado Proactivo
  const { mutate: cambiarEstado, isPending: isMutating } = useMutateEstadoAlerta({
    onSuccess: (_, variables) => {
      toast({
        type: 'success',
        title: 'Alerta Actualizada',
        description: `El estado de la alerta ha cambiado a ${variables.payload.nuevo_estado}.`,
      });
    },
    onError: (err) => {
      toast({
        type: 'error',
        title: 'Error de Actualización',
        description: err.message || 'No se pudo cambiar el estado de la alerta.',
      });
    },
  });

  const handleEstadoChange = (alertaId: string, nuevoEstado: string) => {
    cambiarEstado({
      id_alerta: alertaId,
      payload: { nuevo_estado: nuevoEstado },
    });
  };

  const handleResetFilters = () => {
    setSearch('');
    setFuente('');
    setMinScore(0);
    setEstado('');
    setPage(1);
  };

  const totalPages = data?.total_pages || 1;
  const totalItems = data?.total || 0;

  const renderCategoriaBadge = (cat: string) => {
    switch (cat) {
      case CategoriaFaseTemprana.PRESUPUESTO:
        return <Badge variant="indigo">Presupuesto Municipal</Badge>;
      case CategoriaFaseTemprana.SUBVENCION:
        return <Badge variant="success">Subvención / Convenio</Badge>;
      case CategoriaFaseTemprana.CONVENIO:
        return <Badge variant="warning">Convenio / Encomienda</Badge>;
      case CategoriaFaseTemprana.CONSULTA_PRELIMINAR:
        return <Badge variant="danger">Consulta Mercado (Art.115)</Badge>;
      default:
        return <Badge variant="outline">{cat || 'Otros'}</Badge>;
    }
  };

  return (
    <div className="space-y-4">
      {/* Barra Superior de Filtros del Centinela */}
      <Card className="p-4 bg-surface border-line">
        <div className="flex flex-col lg:flex-row items-center justify-between gap-4">
          {/* Búsqueda por Texto Libre */}
          <div className="w-full lg:w-72">
            <Input
              placeholder="Buscar disposición, municipio o ente..."
              value={search}
              onChange={(e) => {
                setSearch(e.target.value);
                setPage(1);
              }}
              leftIcon={<Search className="w-4 h-4 text-ink-faint" />}
            />
          </div>

          {/* Filtros de Boletín y Categoría */}
          <div className="flex flex-wrap items-center gap-3 w-full lg:w-auto">
            {/* Selector de Fuente Oficial */}
            <div className="w-36">
              <Select
                value={fuente}
                onChange={(e) => {
                  setFuente(e.target.value);
                  setPage(1);
                }}
                options={[
                  { value: '', label: 'Todas las Fuentes' },
                  { value: FuenteBoletin.DOGC, label: 'DOGC (Generalitat)' },
                  { value: FuenteBoletin.BOPB, label: 'BOPB (Dip. Barcelona)' },
                ]}
              />
            </div>

            {/* Selector de Estado Proactivo */}
            <div className="w-44">
              <Select
                value={estado}
                onChange={(e) => {
                  setEstado(e.target.value);
                  setPage(1);
                }}
                options={[
                  // "Todos los Estados" no incluye los descartes automáticos: la API los
                  // excluye salvo que se filtren expresamente. Se guardan para poder
                  // auditarlos y reevaluarlos, no para ocupar el canal proactivo.
                  { value: '', label: 'Todos los Estados' },
                  { value: EstadoAlerta.NUEVA_FASE_TEMPRANA, label: 'Nueva Fase Temprana' },
                  { value: EstadoAlerta.EN_ESTUDIO_PROACTIVO, label: 'En Estudio Proactivo' },
                  { value: EstadoAlerta.CONVERTIDA, label: 'Convertida a Licitación' },
                  { value: EstadoAlerta.DESCARTADA, label: 'Descartada Temprana' },
                  // Único acceso desde el Cockpit a lo que descartó el pipeline por no
                  // alcanzar el umbral. Es la vista que hay que revisar tras bajar un umbral
                  // o actualizar los PMP.
                  { value: EstadoAlerta.DESCARTADA_POR_REGLAS, label: 'Descartada por Reglas (auditoría)' },
                ]}
              />
            </div>

            {/* Selector de Score Mínimo */}
            <div className="w-36">
              <Select
                value={String(minScore)}
                onChange={(e) => {
                  setMinScore(Number(e.target.value));
                  setPage(1);
                }}
                options={[
                  { value: '0', label: 'Cualquier Score' },
                  { value: '70', label: 'Alta Viabilidad (≥70)' },
                  { value: '50', label: 'Media Viabilidad (≥50)' },
                  { value: '30', label: 'Baja Viabilidad (≥30)' },
                ]}
              />
            </div>

            {/* Botón Reset */}
            {(search || fuente || estado || minScore > 0) && (
              <Button
                variant="ghost"
                size="sm"
                onClick={handleResetFilters}
                className="text-ink-faint hover:text-ink"
              >
                Limpiar Filtros
              </Button>
            )}
          </div>
        </div>
      </Card>

      {/* Tabla Server-Side de Alertas Tempranas */}
      <Card className="overflow-hidden border-line">
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="bg-surface-2 border-b border-line text-[11px] font-semibold uppercase tracking-wider text-ink-faint">
                <th className="py-3.5 px-4">Boletín Oficial</th>
                <th className="py-3.5 px-4">Disposición / Ente Emisor</th>
                <th className="py-3.5 px-4 text-center">Categoría LCSP</th>
                <th className="py-3.5 px-4 text-center">Score Temprano</th>
                <th className="py-3.5 px-4 text-center">Estado Proactivo</th>
                <th className="py-3.5 px-4 text-center">Acciones</th>
              </tr>
            </thead>

            <tbody className="divide-y divide-line-soft text-xs">
              {isLoading ? (
                Array.from({ length: 5 }).map((_, idx) => (
                  <tr key={idx} className="animate-pulse">
                    <td className="p-4"><Skeleton className="h-5 w-24" /></td>
                    <td className="p-4"><Skeleton className="h-5 w-64 mb-1" /><Skeleton className="h-3 w-40" /></td>
                    <td className="p-4"><Skeleton className="h-5 w-28 mx-auto" /></td>
                    <td className="p-4"><Skeleton className="h-5 w-16 mx-auto" /></td>
                    <td className="p-4"><Skeleton className="h-6 w-32 mx-auto" /></td>
                    <td className="p-4"><Skeleton className="h-7 w-20 mx-auto" /></td>
                  </tr>
                ))
              ) : isError ? (
                <tr>
                  <td colSpan={6} className="p-8 text-center text-ink-faint">
                    <AlertCircle className="w-8 h-8 text-alarma mx-auto mb-2" />
                    <p className="font-semibold text-ink">Error al cargar el Canal Centinela</p>
                    <p className="text-xs mt-1">Verifica la conexión con la API RESTful.</p>
                    <Button variant="outline" size="sm" onClick={() => refetch()} className="mt-3">
                      Reintentar
                    </Button>
                  </td>
                </tr>
              ) : data?.items.length === 0 ? (
                <tr>
                  <td colSpan={6} className="p-12 text-center text-ink-faint">
                    <Radio className="w-8 h-8 text-ink-faint mx-auto mb-2" />
                    <p className="font-semibold text-ink-dim">No hay alertas tempranas que coincidan</p>
                    <p className="text-xs text-ink-faint mt-1">Prueba ajustando los filtros de búsqueda o fuente.</p>
                  </td>
                </tr>
              ) : (
                data?.items.map((alerta: AlertaBoletin) => {
                  const isDOGC = alerta.fuente === FuenteBoletin.DOGC;

                  return (
                    <tr
                      key={alerta.id_alerta}
                      className="hover:bg-surface-2/80 transition-colors group"
                    >
                      {/* Boletín Oficial */}
                      <td className="p-4 align-top">
                        <div className="flex flex-col gap-1">
                          <div className="flex items-center gap-1.5">
                            <Badge variant={isDOGC ? 'cyan' : 'indigo'} className="font-mono text-[10px]">
                              {alerta.fuente}
                            </Badge>
                            <span className="font-mono text-[11px] text-ink-dim font-semibold">
                              #{alerta.num_boletin}
                            </span>
                          </div>
                          <span className="text-[10px] text-ink-faint flex items-center gap-1 mt-0.5">
                            <Calendar className="w-3 h-3" />
                            {formatDate(alerta.fecha_publicacion)}
                          </span>
                        </div>
                      </td>

                      {/* Disposición / Ente Emisor */}
                      <td className="p-4 align-top max-w-md">
                        <div className="space-y-1">
                          <h4 className="font-semibold text-ink line-clamp-2 leading-snug">
                            {alerta.titulo_anuncio}
                          </h4>
                          <div className="flex items-center gap-3 text-[11px] text-ink-faint">
                            <span className="flex items-center gap-1 truncate max-w-[200px]">
                              <Building className="w-3 h-3 text-ink-faint shrink-0" />
                              {alerta.organo_emisor}
                            </span>
                            {alerta.municipio && (
                              <span className="text-ink-faint truncate">
                                • {alerta.municipio}
                              </span>
                            )}
                          </div>
                        </div>
                      </td>

                      {/* Categoría LCSP */}
                      <td className="p-4 align-top text-center">
                        {renderCategoriaBadge(alerta.categoria_fase_temprana)}
                      </td>

                      {/* Score Temprano */}
                      <td className="p-4 align-top text-center">
                        <ScoreBadge score={alerta.score_temprano || 0} />
                      </td>

                      {/* Estado Proactivo Mutante */}
                      <td className="p-4 align-top text-center">
                        <div className="w-36 mx-auto">
                          <Select
                            value={alerta.estado_operativo || EstadoAlerta.NUEVA_FASE_TEMPRANA}
                            disabled={isMutating}
                            onChange={(e) => handleEstadoChange(alerta.id_alerta, e.target.value)}
                            className="text-xs py-1 px-2 font-medium"
                            options={[
                              // El descarte automático no es una opción que una persona pueda
                              // fijar: si alguien descarta, es DESCARTADA_TEMPRANA. Mantener
                              // separados los dos estados es lo que permite reevaluar sólo lo
                              // que descartó la máquina. Pero sí debe poder MOSTRARSE, o al
                              // filtrar por él el selector saldría en blanco; y desde ahí se
                              // rescata la alerta llevándola a un estado humano.
                              ...(alerta.estado_operativo === EstadoAlerta.DESCARTADA_POR_REGLAS
                                ? [{ value: EstadoAlerta.DESCARTADA_POR_REGLAS, label: 'Descartada por Reglas' }]
                                : []),
                              { value: EstadoAlerta.NUEVA_FASE_TEMPRANA, label: 'Nueva Fase Temprana' },
                              { value: EstadoAlerta.EN_ESTUDIO_PROACTIVO, label: 'Estudio Proactivo' },
                              { value: EstadoAlerta.CONVERTIDA, label: 'Convertida a PSCP' },
                              { value: EstadoAlerta.DESCARTADA, label: 'Descartada' },
                            ]}
                          />
                        </div>
                      </td>

                      {/* Acciones */}
                      <td className="p-4 align-top text-center">
                        <div className="flex items-center justify-center gap-1.5">
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => onSelectAlerta?.(alerta.id_alerta)}
                            leftIcon={<Eye className="w-3.5 h-3.5 text-acento" />}
                            className="px-2.5 py-1 text-xs"
                          >
                            Detalle
                          </Button>
                          {(alerta.url_anuncio || alerta.url_pdf) && (
                            <a
                              href={alerta.url_pdf || alerta.url_anuncio!}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="p-1.5 text-ink-faint hover:text-acento rounded-lg hover:bg-surface-2 transition-colors"
                              title="Ver Disposición Oficial en PDF/Web"
                            >
                              <ExternalLink className="w-4 h-4" />
                            </a>
                          )}
                        </div>
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>

        {/* Paginador Server-Side */}
        <div className="p-4 bg-surface-2 border-t border-line flex items-center justify-between">
          <div className="text-xs text-ink-faint font-mono">
            Mostrando página <span className="font-bold text-ink">{page}</span> de{' '}
            <span className="font-bold text-ink">{totalPages}</span> ({totalItems} alertas proactivas totales)
          </div>

          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              disabled={page <= 1 || isFetching}
              onClick={() => setPage((prev) => Math.max(1, prev - 1))}
              leftIcon={<ChevronLeft className="w-4 h-4" />}
            >
              Anterior
            </Button>
            <Button
              variant="outline"
              size="sm"
              disabled={page >= totalPages || isFetching}
              onClick={() => setPage((prev) => Math.min(totalPages, prev + 1))}
              rightIcon={<ChevronRight className="w-4 h-4" />}
            >
              Siguiente
            </Button>
          </div>
        </div>
      </Card>
    </div>
  );
};

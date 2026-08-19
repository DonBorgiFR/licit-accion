/**
 * frontend/src/components/LicitacionesTable.tsx — Tabla Ejecutiva del Funnel PSCP Server-Side (Capa 8 - Paso 7)
 * Ecosistema Automático de Licitaciones (bfr_incoop)
 */

import React, { useState } from 'react';
import {
  Search,
  Filter,
  ChevronLeft,
  ChevronRight,
  ExternalLink,
  Eye,
  Building,
  AlertCircle,
  Users,
  Archive,
} from 'lucide-react';
import { useLicitacionesQuery } from '../hooks/useApiQueries';
import { useMutateEstadoLicitacion } from '../hooks/useApiMutations';
import { Card } from './ui/Card';
import { Badge, ScoreBadge } from './ui/Badge';
import { Button } from './ui/Button';
import { Input } from './ui/Input';
import { Select } from './ui/Select';
import { Skeleton } from './ui/Skeleton';
import { useToast } from './ui/Toast';
import { formatCurrency } from '../lib/utils';
import { EstadoLicitacion, type Licitacion } from '../types/api';

interface LicitacionesTableProps {
  onSelectLicitacion?: (id: string) => void;
}

/**
 * El sector es CATEGORÍA, no estado: se marca con un punto de color de la marca y no
 * significa nunca «bien» ni «mal». Esa es la regla que separa las capas del sistema de
 * color, porque separarlas por tono resultó imposible —los semánticos quedan a 1-5 grados
 * de los pétalos— y lo que las distingue es la forma: un punto es categoría, un estado
 * lleva palabra. Ver la cabecera de `index.css`.
 *
 * Se normaliza la clave porque la base trae hoy `Consultoria` y `Consultoría` como valores
 * distintos del mismo sector — la familia de H-27, ahora en el vocabulario de sectores.
 * Aquí sólo se unifica lo que se PINTA; el dato sigue como está y su arreglo, si procede,
 * es del Filtro y no de la tabla.
 */
const claveSector = (sector: string): string =>
  sector
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')
    .trim()
    .toLowerCase()
    .replace(/[\s_]+/g, '_');

const COLOR_SECTOR: Record<string, string> = {
  social: 'bg-marca-violeta',
  educativo: 'bg-marca-cian',
  comunitario_asociativo: 'bg-marca-verde',
  cultural: 'bg-marca-amarillo',
  mantenimiento: 'bg-marca-rojo',
  restauracion: 'bg-marca-rojo',
  consultoria: 'bg-ink-faint',
  servicios_generales: 'bg-ink-faint',
};

const ETIQUETA_SECTOR: Record<string, string> = {
  social: 'Social',
  educativo: 'Educativo',
  comunitario_asociativo: 'Comunitario',
  cultural: 'Cultural',
  mantenimiento: 'Mantenimiento',
  restauracion: 'Restauración',
  consultoria: 'Consultoría',
  servicios_generales: 'Servicios generales',
};

const colorSector = (sector: string): string =>
  COLOR_SECTOR[claveSector(sector)] ?? 'bg-ink-faint';

const etiquetaSector = (sector: string): string =>
  ETIQUETA_SECTOR[claveSector(sector)] ?? sector;

export const LicitacionesTable: React.FC<LicitacionesTableProps> = ({
  onSelectLicitacion,
}) => {
  const { toast } = useToast();

  // Estados de Filtros y Paginación Server-Side
  const [page, setPage] = useState<number>(1);
  const [limit] = useState<number>(10);
  const [search, setSearch] = useState<string>('');
  const [minScore, setMinScore] = useState<number>(0);
  const [estado, setEstado] = useState<string>('');
  const [subrogacionCritica, setSubrogacionCritica] = useState<boolean>(false);
  // Acceso a lo que el Depurador sacó del canal principal (Capa 9). Apagado por defecto:
  // esta tabla es con la que se decide a qué concurso presentarse.
  const [incluirArchivadas, setIncluirArchivadas] = useState<boolean>(false);

  // Consulta TanStack Query Server-Side
  const { data, isLoading, isError, isFetching, refetch } = useLicitacionesQuery({
    page,
    limit,
    search: search.trim() || undefined,
    min_score: minScore > 0 ? minScore : undefined,
    subrogacion_critica: subrogacionCritica ? true : undefined,
    estado: estado || undefined,
    incluir_archivadas: incluirArchivadas ? true : undefined,
  });

  // Mutación Optimista de Estado Operativo
  const { mutate: cambiarEstado, isPending: isMutating } = useMutateEstadoLicitacion({
    onSuccess: (_, variables) => {
      toast({
        type: 'success',
        title: 'Estado Actualizado',
        description: `La licitación ${variables.id} ha cambiado a ${variables.payload.nuevo_estado}.`,
      });
    },
    onError: (err) => {
      toast({
        type: 'error',
        title: 'Error de Transición',
        description: err.message || 'No se pudo actualizar el estado de la licitación.',
      });
    },
  });

  const handleEstadoChange = (licitacionId: string, loteNumero: number, nuevoEstado: string) => {
    cambiarEstado({
      id: licitacionId,
      payload: { nuevo_estado: nuevoEstado, lote_numero: loteNumero },
    });
  };

  const handleResetFilters = () => {
    setSearch('');
    setMinScore(0);
    setEstado('');
    setSubrogacionCritica(false);
    setIncluirArchivadas(false);
    setPage(1);
  };

  const totalPages = data?.total_pages || 1;
  const totalItems = data?.total || 0;

  return (
    <div className="space-y-4">
      {/* Barra Superior de Filtros de Negocio */}
      <Card className="p-4 bg-surface border-line">
        <div className="flex flex-col lg:flex-row items-center justify-between gap-4">
          {/* Búsqueda por Texto Libre */}
          <div className="w-full lg:w-72">
            <Input
              placeholder="Buscar título, órgano o ID..."
              value={search}
              onChange={(e) => {
                setSearch(e.target.value);
                setPage(1);
              }}
              leftIcon={<Search className="w-4 h-4 text-ink-faint" />}
            />
          </div>

          {/* Filtros Secundarios */}
          <div className="flex flex-wrap items-center gap-3 w-full lg:w-auto">
            {/* Selector de Estado Operativo */}
            <div className="w-40">
              <Select
                value={estado}
                onChange={(e) => {
                  setEstado(e.target.value);
                  setPage(1);
                }}
                options={[
                  { value: '', label: 'Todos los Estados' },
                  { value: EstadoLicitacion.NUEVA, label: 'Nueva' },
                  { value: EstadoLicitacion.ESTUDIANDO, label: 'Estudiando' },
                  { value: EstadoLicitacion.PRESENTADA, label: 'Presentada' },
                  { value: EstadoLicitacion.ADJUDICADA, label: 'Adjudicada' },
                  { value: EstadoLicitacion.PERDIDA, label: 'Perdida' },
                  { value: EstadoLicitacion.DESCARTADA, label: 'Descartada' },
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
                  { value: '70', label: 'Core (≥ 70 pts)' },
                  { value: '50', label: 'Medio (≥ 50 pts)' },
                  { value: '30', label: 'Baja (≥ 30 pts)' },
                ]}
              />
            </div>

            {/* Toggle de Subrogación Crítica */}
            <Button
              variant={subrogacionCritica ? 'danger' : 'outline'}
              size="sm"
              onClick={() => {
                setSubrogacionCritica(!subrogacionCritica);
                setPage(1);
              }}
              leftIcon={<Users className="w-3.5 h-3.5" />}
            >
              Subrogación
            </Button>

            {/* Acceso al histórico archivado (Capa 9).
                Es la única vía desde el Cockpit para ver lo que el Depurador sacó del
                canal principal, y para poder actuar sobre ello: un lote archivado sigue
                siendo editable —registrar el importe de una adjudicación, por ejemplo—,
                pero antes no había forma de llegar a él. */}
            <Button
              variant={incluirArchivadas ? 'secondary' : 'outline'}
              size="sm"
              onClick={() => {
                setIncluirArchivadas(!incluirArchivadas);
                setPage(1);
              }}
              leftIcon={<Archive className="w-3.5 h-3.5" />}
            >
              Incluir archivadas
            </Button>

            {/* Botón Reset de Filtros */}
            {(search || estado || minScore > 0 || subrogacionCritica || incluirArchivadas) && (
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

      {/* Tabla Server-Side de Licitaciones */}
      <Card className="overflow-hidden border-line">
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="bg-surface-2 border-b border-line text-[11px] font-semibold uppercase tracking-wider text-ink-faint">
                {/* La columna de identificador desaparece y su ancho pasa al título.
                    El identificador no se pierde: baja al pie de la propia fila. Hasta
                    ahora la columna principal era un código como `CONTR 2026 0000156087`
                    y el título iba debajo, pequeño y recortado a dos líneas: se destacaba
                    lo ilegible y se escondía lo legible. */}
                <th className="py-3.5 px-4">Licitación / Órgano Adjudicador</th>
                <th className="py-3.5 px-4 text-right">Presupuesto (PBL / VEC)</th>
                <th className="py-3.5 px-4 text-center">Cláusulas & Riesgo</th>
                <th className="py-3.5 px-4 text-center">Score</th>
                <th className="py-3.5 px-4 text-center">Estado Operativo</th>
                <th className="py-3.5 px-4 text-center">Acciones</th>
              </tr>
            </thead>

            <tbody className="divide-y divide-line-soft text-xs">
              {isLoading ? (
                Array.from({ length: 5 }).map((_, idx) => (
                  <tr key={idx} className="animate-pulse">
                    <td className="p-4"><Skeleton className="h-5 w-24" /></td>
                    <td className="p-4"><Skeleton className="h-5 w-64 mb-1" /><Skeleton className="h-3 w-40" /></td>
                    <td className="p-4"><Skeleton className="h-5 w-24 ml-auto" /></td>
                    <td className="p-4"><Skeleton className="h-5 w-20 mx-auto" /></td>
                    <td className="p-4"><Skeleton className="h-5 w-16 mx-auto" /></td>
                    <td className="p-4"><Skeleton className="h-6 w-28 mx-auto" /></td>
                    <td className="p-4"><Skeleton className="h-7 w-20 mx-auto" /></td>
                  </tr>
                ))
              ) : isError ? (
                <tr>
                  <td colSpan={7} className="p-8 text-center text-ink-faint">
                    <AlertCircle className="w-8 h-8 text-alarma mx-auto mb-2" />
                    <p className="font-semibold text-ink">Error al cargar expedientes</p>
                    <p className="text-xs mt-1">Verifica la conexión con FastAPI RESTful.</p>
                    <Button variant="outline" size="sm" onClick={() => refetch()} className="mt-3">
                      Reintentar
                    </Button>
                  </td>
                </tr>
              ) : data?.items.length === 0 ? (
                <tr>
                  <td colSpan={7} className="p-12 text-center text-ink-faint">
                    <Filter className="w-8 h-8 text-ink-faint mx-auto mb-2" />
                    <p className="font-semibold text-ink-dim">No se encontraron licitaciones</p>
                    <p className="text-xs text-ink-faint mt-1">Prueba ajustando los criterios de búsqueda o filtros.</p>
                  </td>
                </tr>
              ) : (
                data?.items.map((lic: Licitacion) => {
                  const lotePrincipal = lic.lotes?.[0];
                  // La lectura del pliego manda sobre la señal preliminar del Radar. Se leía
                  // sólo el flag del lote, que procede de un rastreo de palabras clave del
                  // título y puede estar sin rellenar aunque exista análisis: el único
                  // expediente analizado de la base mostraba "Sin Subrog. · Sin Revisión"
                  // cuando la IA había leído el documento y encontrado AMBAS cosas. No es una
                  // ausencia inventada por falta de datos: es contradecir un análisis real.
                  const semantico = lic.analisis_semantico;
                  const subrogacion = Boolean(
                    semantico ? semantico.subrogacion_detectada : lotePrincipal?.subrogacion
                  );
                  const revisionPrecios = Boolean(
                    semantico ? semantico.revision_precios_permitida : lotePrincipal?.revision_precios
                  );
                  const pmpDias = lotePrincipal?.pmp_dias;
                  // Los indicadores de riesgo de esta fila no proceden de la lectura del
                  // pliego en dos casos distintos que llevan al mismo error de juicio:
                  //   1. La IA lo intentó y falló (modo degradado).
                  //   2. La IA no llegó a intentarlo: no hay análisis en absoluto.
                  //
                  // El segundo faltaba, y es el caso ABRUMADORAMENTE mayoritario en una base
                  // recién poblada por el Radar. Sin distintivo, la fila mostraba "Sin
                  // Subrog. · Sin Revisión" —derivado de un rastreo de palabras clave del
                  // título— con el mismo aspecto que una lectura verificada del documento.
                  // Convención C3: un dato poco fiable sin distintivo es peor que uno ausente.
                  const analisisDegradado = Boolean(
                    !semantico ||
                      semantico.modo_degradado ||
                      (semantico.estado_analisis && semantico.estado_analisis !== 'COMPLETADO')
                  );

                  // Fuera del canal principal (Capa 9). Sólo puede aparecer si se han
                  // pedido expresamente, pero entonces convive con las vivas en la misma
                  // tabla: sin distintivo se decidiría sobre ella como si siguiera en juego.
                  // Sigue siendo editable — archivar no es congelar (Convención C3, H-32).
                  // La marca es del EXPEDIENTE, no de su primer lote. Mirar
                  // `lotes[0].deleted_at` marcaba como archivado un expediente con un lote
                  // caducado y otro todavía en juego —el caso de los expedientes loteados,
                  // que es lo normal— y lo sacaba visualmente del canal estando dentro.
                  // El backend ya resuelve la pregunta correcta: cierto sólo si ninguno de
                  // sus lotes sigue vivo.
                  const archivada = Boolean(lic.archivada);
                  const motivoArchivado = lic.deleted_reason;

                  return (
                    <tr
                      key={lic.id}
                      className={`hover:bg-surface-2/80 transition-colors group ${
                        archivada ? 'bg-surface-2/60' : ''
                      }`}
                    >
                      {/* Licitación — el título manda y todo lo demás se subordina a él.
                          Tres niveles de jerarquía, de más a menos: qué es (título), quién
                          lo saca y de qué va (órgano, sector), y de dónde salió (id, fuente).
                          El título completo sigue estando: se ve en la ficha de detalle. */}
                      <td className="p-4 align-top max-w-xl">
                        <div className="space-y-1.5">
                          <h4
                            className="font-display text-[15px] font-semibold text-ink leading-snug line-clamp-3 group-hover:text-acento transition-colors"
                            title={lic.titulo}
                          >
                            {lic.titulo_corto || lic.titulo}
                          </h4>

                          <div className="flex items-center gap-2 flex-wrap text-[11.5px] text-ink-dim">
                            <span className="flex items-center gap-1.5 truncate max-w-[280px]">
                              <Building className="w-3 h-3 text-ink-faint shrink-0" />
                              {lic.organo}
                            </span>
                            {lic.localidad && lic.localidad !== 'N/A' && (
                              <>
                                <span className="text-separador">·</span>
                                <span className="truncate">{lic.localidad}</span>
                              </>
                            )}
                            {/* El sector se calcula, se persiste y se sirve desde la Capa 5,
                                y hasta hoy no lo pintaba ninguna pantalla. Es CATEGORÍA, así
                                que se marca con un punto de color y nunca significa "malo". */}
                            {lotePrincipal?.sector && (
                              <>
                                <span className="text-separador">·</span>
                                <span className="inline-flex items-center gap-1.5">
                                  <span
                                    className={`w-1.5 h-1.5 rounded-[2px] shrink-0 ${colorSector(lotePrincipal.sector)}`}
                                    aria-hidden="true"
                                  />
                                  {etiquetaSector(lotePrincipal.sector)}
                                </span>
                              </>
                            )}
                          </div>

                          <div className="flex items-center gap-1.5 flex-wrap pt-0.5">
                            <span className="font-mono text-[10.5px] text-ink-faint">
                              {lic.id}
                            </span>
                            <span className="text-separador text-[10px]">·</span>
                            <span className="font-mono text-[10.5px] text-ink-faint">
                              {lic.fuente || 'PSCP'}
                            </span>
                            {archivada && (
                              <Badge
                                variant="outline"
                                className="text-[10px] py-0 border-line text-ink-dim bg-surface-2"
                                title={motivoArchivado || 'Fuera del canal principal'}
                              >
                                Archivada
                              </Badge>
                            )}
                            {lic.urgente && (
                              <Badge variant="danger" className="text-[10px] py-0">
                                Urgencia
                              </Badge>
                            )}
                            {lic.alerta_modificacion && (
                              <Badge variant="warning" className="text-[10px] py-0" title={lic.log_cambios || ''}>
                                Rectificada
                              </Badge>
                            )}
                            {analisisDegradado && (
                              <Badge
                                variant="warning"
                                className="text-[10px] py-0"
                                title="El pliego no ha podido analizarse por IA. Los riesgos mostrados no incluyen la lectura del documento."
                              >
                                Pliego sin analizar
                              </Badge>
                            )}
                          </div>
                        </div>
                      </td>

                      {/* Presupuesto PBL / VEC */}
                      <td className="p-4 align-top text-right font-mono">
                        <div className="space-y-0.5">
                          <span className="font-bold text-ink text-sm tabular-nums block">
                            {formatCurrency(lotePrincipal?.pbl)}
                          </span>
                          {lotePrincipal?.vec && (
                            <span className="text-[10px] text-ink-faint tabular-nums block">
                              VEC: {formatCurrency(lotePrincipal.vec)}
                            </span>
                          )}
                          {lic.lotes?.length > 1 && (
                            <Badge variant="indigo" className="text-[9px] py-0 mt-0.5">
                              {lic.lotes.length} Lotes
                            </Badge>
                          )}
                        </div>
                      </td>

                      {/* Cláusulas & Riesgo */}
                      <td className="p-4 align-top text-center">
                        <div className="flex flex-col items-center gap-1">
                          {/* Sin lectura del pliego no se afirma la ausencia de una cláusula:
                              "Sin Subrog." es una conclusión, "Sin datos" es la verdad. */}
                          {subrogacion ? (
                            <Badge variant="danger" className="text-[10px]">
                              Subrogación
                            </Badge>
                          ) : analisisDegradado ? (
                            <Badge
                              variant="outline"
                              className="text-[10px] opacity-40 italic"
                              title="El pliego no se ha analizado: no consta si hay subrogación."
                            >
                              Subrogación: sin datos
                            </Badge>
                          ) : (
                            <Badge variant="outline" className="text-[10px] opacity-60">
                              Sin Subrog.
                            </Badge>
                          )}

                          {revisionPrecios ? (
                            <Badge variant="success" className="text-[10px]">
                              Revisión Precios
                            </Badge>
                          ) : analisisDegradado ? (
                            <Badge
                              variant="outline"
                              className="text-[10px] opacity-40 italic"
                              title="El pliego no se ha analizado: no consta si admite revisión de precios."
                            >
                              Revisión: sin datos
                            </Badge>
                          ) : (
                            <Badge variant="outline" className="text-[10px] opacity-60">
                              Sin Revisión
                            </Badge>
                          )}

                          {pmpDias !== undefined && pmpDias !== null && (
                            <span
                              className={`text-[10px] font-mono font-medium px-1.5 py-0.5 rounded ${
                                pmpDias <= 30
                                  ? 'bg-conforme/12 text-conforme'
                                  : pmpDias <= 60
                                  ? 'bg-atencion/12 text-atencion'
                                  : 'bg-alarma/12 text-alarma'
                              }`}
                            >
                              PMP {pmpDias}d
                            </span>
                          )}
                        </div>
                      </td>

                      {/* Score, como magnitud. El acento se reserva a la prioridad Alta,
                          que es un juicio que ya emite el Filtro y no un umbral de pantalla. */}
                      <td className="p-4 align-top text-center">
                        <ScoreBadge
                          score={lic.score_maximo || 0}
                          destacado={lotePrincipal?.prioridad === 'Alta'}
                        />
                      </td>

                      {/* Estado Operativo Mutante */}
                      <td className="p-4 align-top text-center">
                        <div className="w-32 mx-auto">
                          <Select
                            value={lotePrincipal?.estado_operativo || EstadoLicitacion.NUEVA}
                            disabled={isMutating}
                            onChange={(e) => handleEstadoChange(lic.id, lotePrincipal?.lote_numero || 1, e.target.value)}
                            className="text-xs py-1 px-2 font-medium"
                            options={[
                              { value: EstadoLicitacion.NUEVA, label: 'Nueva' },
                              { value: EstadoLicitacion.ESTUDIANDO, label: 'Estudiando' },
                              { value: EstadoLicitacion.PRESENTADA, label: 'Presentada' },
                              { value: EstadoLicitacion.ADJUDICADA, label: 'Adjudicada' },
                              { value: EstadoLicitacion.PERDIDA, label: 'Perdida' },
                              { value: EstadoLicitacion.DESCARTADA, label: 'Descartada' },
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
                            onClick={() => onSelectLicitacion?.(lic.id)}
                            leftIcon={<Eye className="w-3.5 h-3.5 text-acento" />}
                            className="px-2.5 py-1 text-xs"
                          >
                            Detalle
                          </Button>
                          {lic.link && (
                            <a
                              href={lic.link}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="p-1.5 text-ink-faint hover:text-acento rounded-lg hover:bg-surface-2 transition-colors"
                              title="Ver Ficha Oficial en PSCP"
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
            <span className="font-bold text-ink">{totalPages}</span> ({totalItems} expedientes totales)
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

/**
 * frontend/src/components/AdminPanel.tsx — Pantalla de Administración (Capa 9 - Paso 9)
 * Ecosistema Automático de Licitaciones (bfr_incoop)
 *
 * La purga en dos tiempos: **previsualizar y sólo entonces confirmar**. No hay ningún
 * botón que borre a ciegas, y lo intocable se enseña en pantalla junto a lo eliminable —no
 * para informar de que existe, sino para que quien confirma pueda comprobar con sus ojos
 * que la memoria comercial no está en riesgo.
 *
 * Tres decisiones de interfaz que vienen del contrato, no del gusto:
 *
 * 1. El botón de eliminar **nace deshabilitado** y sólo se activa tras previsualizar. Una
 *    purga que se pueda lanzar sin haber mirado es una purga a ciegas con pasos extra.
 * 2. Lo protegido se pinta con el mismo peso visual que lo eliminable. Esconderlo en un
 *    desplegable convertiría la garantía en una nota al pie.
 * 3. Lo que no es purgable —la base de datos— se dice explícitamente en el desglose de
 *    almacenamiento. Es lo que evita que alguien busque espacio donde no lo hay.
 */

import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  AlertTriangle,
  Archive,
  CheckCircle2,
  Database,
  FileText,
  HardDrive,
  History,
  Lock,
  RotateCcw,
  Save,
  ShieldCheck,
  Trash2,
} from 'lucide-react';

import { QUERY_KEYS } from '../lib/react-query';
import {
  crearBackup,
  ejecutarPurga,
  getAlmacenamiento,
  getEjecuciones,
  getPoliticaRetencion,
  getPrevisualizacionPurga,
  APIClientError,
} from '../lib/api-client';
import type { ExpedienteEvaluado } from '../types/api';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from './ui/Card';
import { Button } from './ui/Button';

function formatearBytes(bytes: number): string {
  if (!bytes) return '0 B';
  const unidades = ['B', 'KB', 'MB', 'GB'];
  const i = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), unidades.length - 1);
  return `${(bytes / Math.pow(1024, i)).toFixed(i === 0 ? 0 : 1)} ${unidades[i]}`;
}

const ETIQUETA_MOTIVO: Record<string, string> = {
  memoria_comercial: 'Memoria comercial',
  cuarentena_no_cumplida: 'En cuarentena',
  no_archivado: 'Todavía vivo',
};

export const AdminPanel: React.FC = () => {
  const queryClient = useQueryClient();
  const [previsualizado, setPrevisualizado] = useState(false);
  const [aviso, setAviso] = useState<{ tipo: 'ok' | 'error'; texto: string } | null>(null);

  const almacenamiento = useQuery({
    queryKey: QUERY_KEYS.almacenamiento,
    queryFn: getAlmacenamiento,
    refetchInterval: 60 * 1000,
  });
  const politica = useQuery({ queryKey: QUERY_KEYS.retencion, queryFn: getPoliticaRetencion });
  const ejecuciones = useQuery({
    queryKey: QUERY_KEYS.ejecuciones(1),
    queryFn: () => getEjecuciones(1, 10),
  });

  // La previsualización NO se lanza sola al abrir la pantalla: consultar qué se borraría
  // queda registrado en el rastro de auditoría, y ese registro debe corresponder a que
  // alguien lo pidiera, no a que pasara por aquí.
  const previa = useQuery({
    queryKey: QUERY_KEYS.previsualizacionPurga,
    queryFn: () => getPrevisualizacionPurga('cockpit'),
    enabled: false,
  });

  const refrescar = () => {
    queryClient.invalidateQueries({ queryKey: QUERY_KEYS.almacenamiento });
    queryClient.invalidateQueries({ queryKey: ['admin', 'ejecuciones'] });
    previa.refetch();
  };

  const purgaDocumental = useMutation({
    mutationFn: () => ejecutarPurga({ tipo: 'documental', confirmar: true, solicitado_por: 'cockpit' }),
    onSuccess: (r) => {
      setAviso({
        tipo: 'ok',
        texto: `Purga documental completada: ${r.documentos_purgados} documentos y ${formatearBytes(
          r.bytes_liberados
        )} liberados. Ninguna fila de negocio se ha tocado.`,
      });
      refrescar();
    },
    onError: (e: APIClientError) => setAviso({ tipo: 'error', texto: e.message }),
  });

  const eliminacion = useMutation({
    mutationFn: (expedientes: string[]) =>
      ejecutarPurga({ tipo: 'eliminacion', confirmar: true, expedientes, solicitado_por: 'cockpit' }),
    onSuccess: (r) => {
      setAviso({
        tipo: 'ok',
        texto: `${r.expedientes_eliminados} expedientes eliminados y ${r.bloqueados.length} protegidos. Copia previa: ${
          r.backup_asociado?.split(/[\\/]/).pop() ?? 'sin registrar'
        }.`,
      });
      setPrevisualizado(false);
      refrescar();
    },
    onError: (e: APIClientError) => setAviso({ tipo: 'error', texto: e.message }),
  });

  const backup = useMutation({
    mutationFn: crearBackup,
    onSuccess: (r) =>
      setAviso({ tipo: 'ok', texto: `Copia creada: ${formatearBytes(r.bytes)} en ${r.ruta.split(/[\\/]/).pop()}` }),
    onError: (e: APIClientError) => setAviso({ tipo: 'error', texto: e.message }),
  });

  const alm = almacenamiento.data;
  const eliminables = previa.data?.eliminables ?? [];
  const bloqueados = previa.data?.bloqueados ?? [];
  const puedeEliminar = previsualizado && eliminables.length > 0 && !eliminacion.isPending;

  return (
    <div className="space-y-6">
      {aviso && (
        <div
          className={`flex items-start gap-3 rounded-xl border px-4 py-3 text-sm ${
            aviso.tipo === 'ok'
              ? 'bg-emerald-50 border-emerald-200 text-emerald-800'
              : 'bg-rose-50 border-rose-200 text-rose-800'
          }`}
        >
          {aviso.tipo === 'ok' ? (
            <CheckCircle2 className="w-4 h-4 mt-0.5 shrink-0" />
          ) : (
            <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" />
          )}
          <span>{aviso.texto}</span>
        </div>
      )}

      {/* ---------------------------------------------------------------- Almacenamiento */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <HardDrive className="w-4 h-4 text-indigo-600" /> Ocupación en disco
          </CardTitle>
          <CardDescription>
            Dónde está el peso, y cuánto de él puede recuperarse.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {almacenamiento.isLoading && <p className="text-sm text-slate-500">Midiendo…</p>}
          {alm && (
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <div className="rounded-xl border border-slate-200 p-4">
                <div className="flex items-center gap-2 text-xs font-semibold text-slate-500">
                  <FileText className="w-3.5 h-3.5" /> Pliegos
                </div>
                <p className="mt-1 text-xl font-bold text-slate-900">{formatearBytes(alm.documentos_bytes)}</p>
                <p className="text-xs text-slate-500">{alm.documentos_ficheros} ficheros · purgable</p>
              </div>
              <div className="rounded-xl border border-slate-200 p-4">
                <div className="flex items-center gap-2 text-xs font-semibold text-slate-500">
                  <Save className="w-3.5 h-3.5" /> Copias
                </div>
                <p className="mt-1 text-xl font-bold text-slate-900">{formatearBytes(alm.copias_bytes)}</p>
                <p className="text-xs text-slate-500">{alm.copias_ficheros} copias · purgable</p>
              </div>
              {/* El distintivo importa: sin él, alguien buscaría aquí el espacio a liberar. */}
              <div className="rounded-xl border border-amber-200 bg-amber-50/60 p-4">
                <div className="flex items-center gap-2 text-xs font-semibold text-amber-700">
                  <Lock className="w-3.5 h-3.5" /> Base de datos
                </div>
                <p className="mt-1 text-xl font-bold text-amber-900">{formatearBytes(alm.base_datos_bytes)}</p>
                <p className="text-xs text-amber-700 font-medium">Memoria comercial · no purgable</p>
              </div>
              <div className="rounded-xl border border-slate-200 p-4">
                <div className="flex items-center gap-2 text-xs font-semibold text-slate-500">
                  <Database className="w-3.5 h-3.5" /> Total
                </div>
                <p className="mt-1 text-xl font-bold text-slate-900">{formatearBytes(alm.total_bytes)}</p>
                <p className="text-xs text-slate-500">
                  {formatearBytes(alm.purgable_bytes)} recuperables
                </p>
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {/* -------------------------------------------------------------------- Política */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <ShieldCheck className="w-4 h-4 text-indigo-600" /> Política de retención vigente
          </CardTitle>
          <CardDescription>
            Los plazos bajo los que se purgaría hoy. Cada purga registra bajo qué versión se ejecutó.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {politica.isError && (
            <p className="text-sm text-rose-700">
              No se ha podido leer la política, de modo que <strong>no se purgará nada</strong>.
            </p>
          )}
          {politica.data && (
            <div className="flex flex-wrap gap-x-8 gap-y-2 text-sm">
              <span>
                <span className="text-slate-500">Versión</span>{' '}
                <strong className="font-mono">v{politica.data.version}</strong>
              </span>
              <span>
                <span className="text-slate-500">Pliegos</span>{' '}
                <strong>{politica.data.documentos_dias} días</strong>
              </span>
              <span>
                <span className="text-slate-500">Copias</span>{' '}
                <strong>{politica.data.backups_dias} días</strong>
              </span>
              {politica.data.archivado && (
                <span>
                  <span className="text-slate-500">Archivado</span>{' '}
                  <strong>{politica.data.archivado.dias_tras_fecha_limite} días tras la fecha límite</strong>
                </span>
              )}
              {politica.data.eliminacion && (
                <span>
                  <span className="text-slate-500">Cuarentena</span>{' '}
                  <strong>{politica.data.eliminacion.dias_archivado_minimo} días archivado</strong>
                </span>
              )}
            </div>
          )}
        </CardContent>
      </Card>

      {/* ------------------------------------------------------- Purga en dos tiempos */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Trash2 className="w-4 h-4 text-indigo-600" /> Purga
          </CardTitle>
          <CardDescription>
            Primero se mira qué desaparecería; sólo después se confirma. Nada se borra a ciegas.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-5">
          <div className="flex flex-wrap gap-3">
            <Button
              variant="outline"
              onClick={() => {
                previa.refetch();
                setPrevisualizado(true);
                setAviso(null);
              }}
              disabled={previa.isFetching}
            >
              <Archive className="w-4 h-4 mr-2" />
              {previa.isFetching ? 'Comprobando…' : '1 · Previsualizar'}
            </Button>
            <Button variant="secondary" onClick={() => backup.mutate()} disabled={backup.isPending}>
              <Save className="w-4 h-4 mr-2" />
              {backup.isPending ? 'Copiando…' : 'Copia de seguridad'}
            </Button>
            <Button
              variant="secondary"
              onClick={() => purgaDocumental.mutate()}
              disabled={purgaDocumental.isPending}
            >
              <FileText className="w-4 h-4 mr-2" />
              {purgaDocumental.isPending ? 'Purgando…' : 'Liberar peso documental'}
            </Button>
          </div>

          {previsualizado && previa.data && (
            <div className="space-y-4">
              <div className="rounded-xl border border-slate-200 bg-slate-50/60 p-4 text-sm">
                <p className="font-semibold text-slate-800">Peso documental</p>
                <p className="text-slate-600">
                  {previa.data.documental.documentos_candidatos} documentos perderían su fichero y su
                  texto, liberando {formatearBytes(previa.data.documental.bytes_estimados)}.{' '}
                  <span className="text-slate-500">Ninguna fila de negocio se toca.</span>
                </p>
              </div>

              <div className="grid md:grid-cols-2 gap-4">
                {/* Lo eliminable */}
                <div className="rounded-xl border border-rose-200 bg-rose-50/40 p-4">
                  <p className="text-sm font-semibold text-rose-800 flex items-center gap-2">
                    <Trash2 className="w-3.5 h-3.5" /> Se eliminarían ({eliminables.length})
                  </p>
                  <p className="text-xs text-rose-700/80 mt-0.5 mb-2">
                    Expedientes que caducaron sin que nadie llegara a mirarlos.
                  </p>
                  {eliminables.length === 0 ? (
                    <p className="text-xs text-slate-500">Nada que eliminar ahora mismo.</p>
                  ) : (
                    <ul className="space-y-1 max-h-56 overflow-y-auto">
                      {eliminables.map((e: ExpedienteEvaluado) => (
                        <li key={e.expediente_id} className="text-xs font-mono text-rose-900">
                          {e.expediente_id}{' '}
                          <span className="text-rose-600/70">
                            ({e.lotes} lotes, {e.documentos} docs)
                          </span>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>

                {/* Lo protegido, con el mismo peso visual. No es una nota al pie. */}
                <div className="rounded-xl border border-emerald-200 bg-emerald-50/40 p-4">
                  <p className="text-sm font-semibold text-emerald-800 flex items-center gap-2">
                    <ShieldCheck className="w-3.5 h-3.5" /> Protegidos ({bloqueados.length})
                  </p>
                  <p className="text-xs text-emerald-700/80 mt-0.5 mb-2">
                    No se tocarán. El motivo de cada uno, a la vista.
                  </p>
                  {bloqueados.length === 0 ? (
                    <p className="text-xs text-slate-500">No hay expedientes archivados protegidos.</p>
                  ) : (
                    <ul className="space-y-1 max-h-56 overflow-y-auto">
                      {bloqueados.map((b: ExpedienteEvaluado) => (
                        <li key={b.expediente_id} className="text-xs">
                          <span className="font-mono text-emerald-900">{b.expediente_id}</span>{' '}
                          <span className="px-1.5 py-0.5 rounded bg-emerald-100 text-emerald-800 font-semibold">
                            {ETIQUETA_MOTIVO[b.motivo ?? ''] ?? b.motivo}
                          </span>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              </div>

              <div className="flex items-center gap-3 pt-1">
                <Button
                  variant="danger"
                  disabled={!puedeEliminar}
                  onClick={() => eliminacion.mutate(eliminables.map((e) => e.expediente_id))}
                >
                  <Trash2 className="w-4 h-4 mr-2" />
                  {eliminacion.isPending
                    ? 'Eliminando…'
                    : `2 · Confirmar eliminación de ${eliminables.length}`}
                </Button>
                <span className="text-xs text-slate-500">
                  Se creará una copia de seguridad antes de tocar nada. Si la copia falla, no se
                  elimina.
                </span>
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {/* ------------------------------------------------------------------ Historial */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <History className="w-4 h-4 text-indigo-600" /> Historial de prospecciones
          </CardTitle>
          <CardDescription>Qué encontró cada corrida del pipeline.</CardDescription>
        </CardHeader>
        <CardContent>
          {ejecuciones.data && ejecuciones.data.items.length === 0 && (
            <p className="text-sm text-slate-500">
              Todavía no se ha ejecutado ninguna prospección.
            </p>
          )}
          {ejecuciones.data && ejecuciones.data.items.length > 0 && (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-xs font-semibold text-slate-500 border-b border-slate-200">
                    <th className="py-2 pr-4">Inicio</th>
                    <th className="py-2 pr-4">Estado</th>
                    <th className="py-2 pr-4 text-right">Nuevos</th>
                    <th className="py-2 pr-4 text-right">Lotes</th>
                    <th className="py-2 pr-4 text-right">Docs</th>
                    <th className="py-2 pr-4 text-right">Análisis</th>
                    <th className="py-2 pr-4 text-right">Errores</th>
                    <th className="py-2 pr-4">Scoring</th>
                  </tr>
                </thead>
                <tbody>
                  {ejecuciones.data.items.map((e) => (
                    <tr key={e.id} className="border-b border-slate-100 last:border-0">
                      <td className="py-2 pr-4 font-mono text-xs">{e.start_time?.slice(0, 16).replace('T', ' ')}</td>
                      <td className="py-2 pr-4">{e.estado}</td>
                      <td className="py-2 pr-4 text-right">{e.expedientes_nuevos ?? 0}</td>
                      <td className="py-2 pr-4 text-right">{e.lotes_evaluados ?? 0}</td>
                      <td className="py-2 pr-4 text-right">{e.documentos_descargados ?? 0}</td>
                      <td className="py-2 pr-4 text-right">{e.analisis_realizados ?? 0}</td>
                      <td className={`py-2 pr-4 text-right ${e.errores ? 'text-rose-600 font-semibold' : ''}`}>
                        {e.errores ?? 0}
                      </td>
                      <td className="py-2 pr-4 font-mono text-xs text-slate-500">
                        {e.version_scoring ?? '—'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      <p className="text-xs text-slate-400 flex items-center gap-1.5">
        <RotateCcw className="w-3 h-3" />
        El rescate de un expediente archivado se pide desde su ficha, y nunca ocurre solo.
      </p>
    </div>
  );
};

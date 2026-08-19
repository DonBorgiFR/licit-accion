/**
 * frontend/src/components/DetailDrawer.tsx — Drawer de Detalle Completo y Mutación (Capa 8 - Paso 9)
 * Ecosistema Automático de Licitaciones (bfr_incoop)
 */

import React, { useState, useEffect } from 'react';
import {
  Brain,
  Layers,
  FileText,
  ExternalLink,
  ShieldCheck,
  Award,
  Save,
  Users,
  AlertTriangle,
} from 'lucide-react';
import { useLicitacionDetailQuery, useAlertaDetailQuery } from '../hooks/useApiQueries';
import { useMutateEstadoLicitacion, useMutateEstadoAlerta } from '../hooks/useApiMutations';
import {
  LecturaPliegoBadge,
  normalizarLectura,
  type EstadoLectura,
} from './LecturaPliego';
import { Drawer } from './ui/Drawer';
import { Badge, ScoreBadge, EstadoLicitacionBadge } from './ui/Badge';
import { Button } from './ui/Button';
import { Card, CardHeader, CardContent } from './ui/Card';
import { Select } from './ui/Select';
import { Skeleton } from './ui/Skeleton';
import { useToast } from './ui/Toast';
import { formatCurrency, formatDate } from '../lib/utils';
import { EstadoLicitacion, EstadoAlerta, type Lote } from '../types/api';

interface DetailDrawerProps {
  licitacionId: string | null;
  alertaId: string | null;
  onClose: () => void;
}

export const DetailDrawer: React.FC<DetailDrawerProps> = ({
  licitacionId,
  alertaId,
  onClose,
}) => {
  const { toast } = useToast();
  const isOpen = Boolean(licitacionId || alertaId);
  const [activeTab, setActiveTab] = useState<'ia' | 'lotes' | 'notas'>('ia');
  const [notas, setNotas] = useState<string>('');
  const [loteNumeroSeleccionado, setLoteNumeroSeleccionado] = useState<number>(1);

  // Consultas de detalle
  const { data: licitacion, isLoading: loadingLicitacion } = useLicitacionDetailQuery(licitacionId);
  const { data: alerta, isLoading: loadingAlerta } = useAlertaDetailQuery(alertaId);

  // Mutaciones de Licitación
  const { mutate: cambiarEstadoLicitacion, isPending: mutandoLicitacion } = useMutateEstadoLicitacion({
    onSuccess: () => {
      toast({
        type: 'success',
        title: 'Actualización Guardada',
        description: 'Se ha registrado la mutación de estado/notas correctamente.',
      });
    },
    onError: (err) => {
      toast({
        type: 'error',
        title: 'Error de Guardado',
        description: err.message || 'No se pudo guardar la actualización.',
      });
    },
  });

  // Mutaciones de Alerta
  const { mutate: cambiarEstadoAlerta, isPending: mutandoAlerta } = useMutateEstadoAlerta({
    onSuccess: () => {
      toast({
        type: 'success',
        title: 'Alerta Actualizada',
        description: 'Se han guardado los cambios en la alerta temprana.',
      });
    },
    onError: (err) => {
      toast({
        type: 'error',
        title: 'Error de Guardado',
        description: err.message || 'No se pudo actualizar la alerta.',
      });
    },
  });

  // Sincronizar notas locales al cargar detalle
  useEffect(() => {
    if (licitacion) {
      const loteInicial = licitacion.lotes?.[0];
      setLoteNumeroSeleccionado(loteInicial?.lote_numero || 1);
      setNotas(loteInicial?.notas_usuario || '');
    } else if (alerta) {
      setNotas(alerta.notas_usuario || '');
    }
  }, [licitacion, alerta]);

  const handleSaveNotes = () => {
    if (licitacionId && licitacion) {
      const lote = licitacion.lotes.find((item) => item.lote_numero === loteNumeroSeleccionado) || licitacion.lotes[0];
      const estadoActual = lote?.estado_operativo || EstadoLicitacion.NUEVA;
      cambiarEstadoLicitacion({
        id: licitacionId,
        payload: { nuevo_estado: estadoActual, lote_numero: lote?.lote_numero || 1, notas },
      });
    } else if (alertaId && alerta) {
      const estadoActual = alerta.estado_operativo || EstadoAlerta.NUEVA_FASE_TEMPRANA;
      cambiarEstadoAlerta({
        id_alerta: alertaId!,
        payload: { nuevo_estado: estadoActual, notas },
      });
    }
  };

  const isLoading = (Boolean(licitacionId) && loadingLicitacion) || (Boolean(alertaId) && loadingAlerta);

  // Render de Dictamen IA (Capa 5)
  const renderIASection = () => {
    // Esta sección se reutiliza para dos formas distintas: el dictamen estructurado de
    // licitaciones (AnalisisSemanticoResumen) y el dictamen libre del Centinela
    // (dictamen_ia_json). Se accede de forma laxa a propósito; el tipado fuerte vive
    // en la frontera de la API (types/api.ts).
    const semantico = (licitacion?.analisis_semantico ||
      alerta?.dictamen_ia_json) as Record<string, any> | null | undefined;

    if (!semantico) {
      // ⚠️ Este texto decía: "Puedes ejecutar el motor en CLI con `python src/analista.py`".
      // Era el ORIGEN de que dirección creyera que el análisis había que lanzarlo a mano —el
      // contrato del Bloque 3 lo anota como una creencia equivocada, y resulta que se la
      // estaba dando la propia pantalla—. Y encima ese comando **no funciona**: rompe con
      // `ModuleNotFoundError: No module named 'src'`, porque viola la Convención C1. La forma
      // que sí arranca es `python -m src.analista` (H-50).
      return (
        <Card className="border-dashed border-line bg-surface-2/50">
          <CardContent className="p-6 text-center space-y-3">
            <Brain className="w-8 h-8 text-ink-faint mx-auto" />
            <h4 className="text-sm font-semibold text-ink-dim">Sin analizar</h4>
            <p className="text-xs text-ink-faint max-w-md mx-auto leading-relaxed">
              Todavía no hay dictamen, y <strong className="text-ink-dim">no hay nada que lanzar
              a mano</strong>: el motor semántico se ejecuta solo en cada corrida, sobre los
              expedientes cuyo pliego se ha descargado y cuyo texto se ha extraído. Si aquí no
              hay dictamen es porque la fuente no trajo el pliego —sólo la catalana lo hace de
              forma fiable— o porque todavía no le ha tocado el turno.
            </p>
            <p className="text-[11px] text-ink-faint/90 max-w-md mx-auto">
              Para auditar un dictamen concreto desde la consola:{' '}
              <code className="text-acento font-mono">python -m src.analista --inspeccionar &lt;id&gt;</code>.
              Es la herramienta de inspección, no el motor.
            </p>
          </CardContent>
        </Card>
      );
    }

    const dictamen = semantico.dictamen_recomendacion || semantico.dictamen || 'REVISAR_RIESGO';
    const subrogacion = semantico.subrogacion_personal || semantico.subrogacion || {};
    const revision = semantico.revision_precios || {};
    const criterios = semantico.criterios_adjudicacion || {};

    // Un dictamen degradado NO procede de una lectura real del pliego: sus campos
    // de riesgo son valores por defecto. Mostrarlo sin advertencia llevaría a leer
    // "sin subrogación / sin revisión de precios" como si fuera un hallazgo.
    //
    // Para una licitación la clasificación llega resuelta de la API (`estado_lectura`), que
    // es donde está cubierta por regresiones. La rama de abajo es sólo para el dictamen del
    // Centinela, que tiene otra forma —`dictamen_ia_json`— y no pasa por ese esquema.
    const lectura: EstadoLectura = licitacion
      ? normalizarLectura(licitacion.estado_lectura)
      : semantico.modo_degradado ||
        (semantico.estado_analisis && semantico.estado_analisis !== 'COMPLETADO')
      ? 'DEGRADADO'
      : 'LEIDO';
    const esDegradado = lectura === 'DEGRADADO';

    return (
      <div className="space-y-5">
        {/* De dónde viene el dictamen, dicho antes que el dictamen. Cuando el pliego SÍ se ha
            leído la ficha tampoco lo decía: había aviso para lo malo y silencio para lo bueno,
            así que el trabajo del Analista sólo se notaba por ausencia de advertencia. */}
        <div className="flex items-center justify-between gap-3">
          <LecturaPliegoBadge estado={lectura} />
          {lectura === 'LEIDO' && semantico.modelo_llm && (
            <span className="text-[10px] font-mono text-ink-faint truncate">
              {semantico.modelo_llm}
            </span>
          )}
        </div>

        {/* Aviso de Modo Degradado (Capa 5, Regla 5) */}
        {esDegradado && (
          <div className="p-4 rounded-xl border-2 border-atencion/35 bg-atencion/12 text-atencion flex items-start gap-3.5">
            <div className="p-2 rounded-lg bg-surface/80 shadow-xs shrink-0 mt-0.5">
              <AlertTriangle className="w-5 h-5 text-atencion" />
            </div>
            <div className="flex-1">
              <div className="flex items-center justify-between gap-2">
                <span className="text-xs font-bold uppercase tracking-wider">
                  El pliego no ha podido analizarse
                </span>
                <Badge variant="warning">
                  {semantico.estado_analisis || 'DEGRADADO'}
                </Badge>
              </div>
              <p className="text-xs mt-1.5 leading-relaxed font-medium">
                Los valores que aparecen debajo <strong>no son hallazgos</strong>: son valores por
                defecto. <strong>No interpretes «sin subrogación» o «sin revisión de precios» como
                una conclusión</strong> — el documento no llegó a leerse. Revisa el pliego
                manualmente antes de decidir.
              </p>
              {semantico.error_detalle && (
                <p className="text-[11px] mt-2 text-atencion/90 font-mono break-words">
                  Causa: {semantico.error_detalle}
                </p>
              )}
            </div>
          </div>
        )}

        {/* Banner de Dictamen Semántico */}
        <div
          className={`p-4 rounded-xl border flex items-start gap-3.5 ${
            dictamen === 'RECOMENDADA'
              ? 'bg-conforme/12 border-conforme/35 text-conforme'
              : dictamen === 'DESCARTADA_POR_RIESGO'
              ? 'bg-alarma/12 border-alarma/35 text-alarma'
              : 'bg-atencion/12 border-atencion/35 text-atencion'
          }`}
        >
          <div className="p-2 rounded-lg bg-surface/80 shadow-xs shrink-0 mt-0.5">
            <Brain className="w-5 h-5 text-current" />
          </div>
          <div className="flex-1">
            <div className="flex items-center justify-between">
              <span className="text-xs font-bold uppercase tracking-wider">
                Dictamen del Analista IA (LCSP)
              </span>
              <Badge
                variant={
                  dictamen === 'RECOMENDADA'
                    ? 'success'
                    : dictamen === 'DESCARTADA_POR_RIESGO'
                    ? 'danger'
                    : 'warning'
                }
              >
                {dictamen}
              </Badge>
            </div>
            <p className="text-xs mt-1.5 leading-relaxed font-medium">
              {semantico.resumen_ejecutivo ||
                semantico.dictamen_resumen ||
                (esDegradado
                  ? 'Sin dictamen: el análisis no llegó a completarse.'
                  : 'Análisis de cláusulas críticas completado.')}
            </p>
          </div>
        </div>

        {/* Tarjetas de Cláusulas Críticas LCSP.
            En modo degradado se atenúan para reforzar que no son hallazgos reales. */}
        <div
          className={`grid grid-cols-1 md:grid-cols-3 gap-3 ${
            esDegradado ? 'opacity-50 grayscale' : ''
          }`}
          aria-hidden={esDegradado || undefined}
          title={esDegradado ? 'Valores por defecto: el pliego no se ha analizado' : undefined}
        >
          {/* Subrogación (Art. 130 LCSP) */}
          <Card className="border-line">
            <CardContent className="p-4 space-y-2">
              <div className="flex items-center justify-between text-xs text-ink-faint font-semibold">
                <span className="flex items-center gap-1">
                  <Users className="w-3.5 h-3.5 text-ink-faint" /> Art. 130 Subrogación
                </span>
                <Badge variant={subrogacion.requerida ? 'danger' : 'success'} className="text-[10px]">
                  {subrogacion.requerida ? 'Obligatoria' : 'No Requerida'}
                </Badge>
              </div>
              <p className="text-xs text-ink-dim leading-normal">
                {subrogacion.detalles || subrogacion.motivos || 'Sin absorción contractual de plantilla.'}
              </p>
            </CardContent>
          </Card>

          {/* Revisión Precios (Art. 103 LCSP) */}
          <Card className="border-line">
            <CardContent className="p-4 space-y-2">
              <div className="flex items-center justify-between text-xs text-ink-faint font-semibold">
                <span className="flex items-center gap-1">
                  <ShieldCheck className="w-3.5 h-3.5 text-ink-faint" /> Art. 103 Revisión
                </span>
                <Badge variant={revision.permitida ? 'success' : 'warning'} className="text-[10px]">
                  {revision.permitida ? 'Permitida' : 'No Contemplada'}
                </Badge>
              </div>
              <p className="text-xs text-ink-dim leading-normal">
                {revision.formula || revision.detalles || 'Sin fórmula automática de revisión por IPC.'}
              </p>
            </CardContent>
          </Card>

          {/* Criterios Adjudicación (Art. 145 LCSP) */}
          <Card className="border-line">
            <CardContent className="p-4 space-y-2">
              <div className="flex items-center justify-between text-xs text-ink-faint font-semibold">
                <span className="flex items-center gap-1">
                  <Award className="w-3.5 h-3.5 text-ink-faint" /> Art. 145 Criterios
                </span>
                <span className="font-mono text-[11px] font-bold text-acento">
                  {criterios.peso_formulas || 50}% Form. / {criterios.peso_juicio_valor || 50}% Juicio
                </span>
              </div>
              <p className="text-xs text-ink-dim leading-normal">
                {criterios.resumen || 'Reparto equilibrado entre oferta económica y memoria técnica.'}
              </p>
            </CardContent>
          </Card>
        </div>
      </div>
    );
  };

  // Render de Lotes & Finanzas
  const renderLotesSection = () => {
    const lotes = licitacion?.lotes || [];

    if (lotes.length === 0) {
      return (
        <p className="text-xs text-ink-faint italic p-4 text-center">
          No hay lotes desglosados en este expediente.
        </p>
      );
    }

    return (
      <div className="space-y-4">
        {lotes.map((lote: Lote, idx: number) => (
          <Card key={lote.id || idx} className="border-line">
            <CardHeader className="py-3 px-4 bg-surface-2/60">
              <div className="flex items-center justify-between">
                <span className="text-xs font-bold text-ink">
                  Lote #{lote.lote_numero}: {lote.titulo_lote || 'Lote Único'}
                </span>
                <ScoreBadge score={lote.score_total || 0} />
              </div>
            </CardHeader>
            <CardContent className="p-4 space-y-3">
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs font-mono">
                <div className="p-2.5 rounded-lg bg-surface-2 border border-line-soft">
                  <span className="text-[10px] text-ink-faint block uppercase">PBL sin IVA</span>
                  <span className="font-bold text-ink text-sm">
                    {formatCurrency(lote.pbl)}
                  </span>
                </div>
                <div className="p-2.5 rounded-lg bg-surface-2 border border-line-soft">
                  <span className="text-[10px] text-ink-faint block uppercase">VEC con Prórrogas</span>
                  <span className="font-bold text-ink text-sm">
                    {formatCurrency(lote.vec)}
                  </span>
                </div>
                <div className="p-2.5 rounded-lg bg-conforme/6 border border-conforme/25">
                  <span className="text-[10px] text-conforme block uppercase font-sans font-semibold">
                    Aval Definitivo (5%)
                  </span>
                  <span className="font-bold text-conforme text-sm">
                    {formatCurrency(lote.garantia_definitiva || lote.pbl * 0.05)}
                  </span>
                </div>
                <div className="p-2.5 rounded-lg bg-surface-2 border border-line-soft">
                  <span className="text-[10px] text-ink-faint block uppercase">PMP Ayuntamiento</span>
                  <span className="font-bold text-acento text-sm">
                    {lote.pmp_dias !== undefined && lote.pmp_dias !== null ? `${lote.pmp_dias} días` : '—'}
                  </span>
                </div>
              </div>

              {lote.motivos_scoring && (
                <div className="p-3 rounded-lg bg-surface-2 border border-line-soft text-[11px] text-ink-dim leading-relaxed font-sans">
                  <span className="font-semibold text-ink block mb-1">Desglose de Scoring:</span>
                  {lote.motivos_scoring}
                </div>
              )}
            </CardContent>
          </Card>
        ))}
      </div>
    );
  };

  const lotePrincipal = licitacion?.lotes?.find((lote) => lote.lote_numero === loteNumeroSeleccionado) || licitacion?.lotes?.[0];
  const estadoActual = licitacion
    ? lotePrincipal?.estado_operativo || EstadoLicitacion.NUEVA
    : alerta?.estado_operativo || EstadoAlerta.NUEVA_FASE_TEMPRANA;

  const isMutating = mutandoLicitacion || mutandoAlerta;

  return (
    <Drawer
      isOpen={isOpen}
      onClose={onClose}
      width="2xl"
      title={
        isLoading ? (
          <Skeleton className="h-6 w-80" />
        ) : (
          <div className="flex items-center gap-2">
            <span className="text-base font-bold text-ink truncate max-w-lg">
              {licitacion?.titulo || alerta?.titulo_anuncio || 'Detalle del Registro'}
            </span>
          </div>
        )
      }
      subtitle={
        isLoading ? (
          <Skeleton className="h-4 w-40 mt-1" />
        ) : (
          `ID: ${licitacion?.id || alerta?.id_alerta || ''} • ${licitacion?.organo || alerta?.organo_emisor || ''}`
        )
      }
      footer={
        <div className="flex items-center justify-between w-full">
          <div className="flex items-center gap-2">
            <span className="text-xs font-semibold text-ink-faint">Estado:</span>
            {licitacionId ? (
              <>
              <div className="w-28">
                <Select
                  value={String(lotePrincipal?.lote_numero || 1)}
                  disabled={isMutating}
                  onChange={(e) => {
                    const numero = Number(e.target.value);
                    const lote = licitacion?.lotes.find((item) => item.lote_numero === numero);
                    setLoteNumeroSeleccionado(numero);
                    setNotas(lote?.notas_usuario || '');
                  }}
                  options={(licitacion?.lotes || []).map((lote) => ({ value: String(lote.lote_numero), label: `Lote ${lote.lote_numero}` }))}
                />
              </div>
              <div className="w-36">
                <Select
                  value={estadoActual}
                  disabled={isMutating}
                  onChange={(e) => {
                    cambiarEstadoLicitacion({
                      id: licitacionId,
                      payload: { nuevo_estado: e.target.value, lote_numero: lotePrincipal?.lote_numero || 1, notas },
                    });
                  }}
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
              </>
            ) : (
              <div className="w-40">
                <Select
                  value={estadoActual}
                  disabled={isMutating}
                  onChange={(e) => {
                    cambiarEstadoAlerta({
                      id_alerta: alertaId!,
                      payload: { nuevo_estado: e.target.value, notas },
                    });
                  }}
                  options={[
                    { value: EstadoAlerta.NUEVA_FASE_TEMPRANA, label: 'Nueva Fase Temprana' },
                    { value: EstadoAlerta.EN_ESTUDIO_PROACTIVO, label: 'Estudio Proactivo' },
                    { value: EstadoAlerta.CONVERTIDA, label: 'Convertida a PSCP' },
                    { value: EstadoAlerta.DESCARTADA, label: 'Descartada' },
                  ]}
                />
              </div>
            )}
          </div>

          <div className="flex items-center gap-2">
            <Button
              variant="primary"
              size="sm"
              onClick={handleSaveNotes}
              isLoading={isMutating}
              leftIcon={<Save className="w-3.5 h-3.5" />}
            >
              Guardar Notas
            </Button>
          </div>
        </div>
      }
    >
      {isLoading ? (
        <div className="space-y-4">
          <Skeleton className="h-24 w-full rounded-xl" />
          <Skeleton className="h-40 w-full rounded-xl" />
          <Skeleton className="h-32 w-full rounded-xl" />
        </div>
      ) : (
        <div className="space-y-6">
          {/* Header Banner con Badges */}
          <div className="flex items-center justify-between p-4 bg-surface-2 rounded-xl border border-line">
            <div className="flex items-center gap-3">
              <ScoreBadge score={licitacion?.score_maximo || alerta?.score_temprano || 0} />
              <EstadoLicitacionBadge estado={estadoActual} />
              {(licitacion?.link || alerta?.url_anuncio || alerta?.url_pdf) && (
                <a
                  href={licitacion?.link || alerta?.url_pdf || alerta?.url_anuncio!}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1 text-xs font-semibold text-acento hover:text-acento"
                >
                  <ExternalLink className="w-3.5 h-3.5" /> Ficha Oficial
                </a>
              )}
            </div>
            <span className="text-xs text-ink-faint font-mono">
              Publicado: {formatDate(licitacion?.fecha_publicacion || alerta?.fecha_publicacion)}
            </span>
          </div>

          {/* Navegación por Secciones dentro del Drawer */}
          <div className="flex items-center gap-2 border-b border-line pb-2">
            <button
              onClick={() => setActiveTab('ia')}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all cursor-pointer ${
                activeTab === 'ia'
                  ? 'bg-acento/10 text-acento border border-acento/35'
                  : 'text-ink-dim hover:bg-surface-2'
              }`}
            >
              <Brain className="w-3.5 h-3.5" /> Dictamen Semántico IA
            </button>

            {licitacionId && (
              <button
                onClick={() => setActiveTab('lotes')}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all cursor-pointer ${
                  activeTab === 'lotes'
                    ? 'bg-acento/10 text-acento border border-acento/35'
                    : 'text-ink-dim hover:bg-surface-2'
                }`}
              >
                <Layers className="w-3.5 h-3.5" /> Lotes & Finanzas ({licitacion?.lotes?.length || 0})
              </button>
            )}

            <button
              onClick={() => setActiveTab('notas')}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all cursor-pointer ${
                activeTab === 'notas'
                  ? 'bg-acento/10 text-acento border border-acento/35'
                  : 'text-ink-dim hover:bg-surface-2'
              }`}
            >
              <FileText className="w-3.5 h-3.5" /> Notas & Seguimiento
            </button>
          </div>

          {/* Contenido de Sección Activa */}
          {activeTab === 'ia' && renderIASection()}

          {activeTab === 'lotes' && licitacionId && renderLotesSection()}

          {activeTab === 'notas' && (
            <Card className="border-line">
              <CardContent className="p-4 space-y-3">
                <label className="text-xs font-semibold text-ink block">
                  Notas Internas de Prospección (Incoop)
                </label>
                <textarea
                  value={notas}
                  onChange={(e) => setNotas(e.target.value)}
                  placeholder="Añade observaciones sobre UTEs, reunión con ayuntamiento, subrogación..."
                  className="w-full h-36 p-3 text-xs bg-surface border border-line rounded-lg focus:ring-2 focus:ring-acento focus:border-acento focus:outline-none transition-all placeholder:text-ink-faint"
                />
                <p className="text-[11px] text-ink-faint">
                  Las notas quedan blindadas en SQLite y no se sobrescriben durante la ingesta diaria del Radar.
                </p>
              </CardContent>
            </Card>
          )}
        </div>
      )}
    </Drawer>
  );
};

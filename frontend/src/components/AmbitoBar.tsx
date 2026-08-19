/**
 * frontend/src/components/AmbitoBar.tsx — Interruptor de Ámbito Territorial (Bloque 3 - Paso 5)
 * Ecosistema Automático de Licitaciones (bfr_incoop)
 *
 * H-47: el Funnel ofrecía lo que no es su negocio. La decisión de dirección del 2026-08-18 fue
 * **filtrar en pantalla** —no al ingerir, ni subiendo el umbral del score—, con Catalunya por
 * defecto y un interruptor para ver el resto. Así no se pierde ni un dato y la decisión es
 * reversible: si algún día interesa mirar fuera de zona, sigue estando todo.
 *
 * **Vive fuera de las dos pestañas que gobierna, y a propósito.** El interruptor manda a la vez
 * sobre el Dashboard de KPIs y sobre el Funnel, que son pantallas distintas. Metido dentro de
 * una de ellas parecería un filtro de esa tabla; aquí, entre la cabecera y el contenido, dice
 * con su posición lo que hace: es el alcance de todo lo que hay debajo.
 */

import React from 'react';
import { MapPin } from 'lucide-react';
import { cn } from '../lib/utils';

/**
 * Vocabulario de ámbitos, el mismo que declara `src/__init__.py` (`AMBITOS`).
 *
 * `undefined` es «sin filtro», no un tercer ámbito: es la ausencia del parámetro en la
 * llamada. La API sin `ambito` devuelve todo, y quien decide esconder es esta pantalla.
 */
export const AMBITO_CATALUNYA = 'catalunya';

export type Ambito = typeof AMBITO_CATALUNYA | undefined;

interface AmbitoBarProps {
  ambito: Ambito;
  onChange: (ambito: Ambito) => void;
  /** Expedientes que se están mostrando con el ámbito puesto, para no afirmar a ciegas. */
  visibles?: number;
}

const OPCIONES: Array<{ valor: Ambito; etiqueta: string }> = [
  { valor: AMBITO_CATALUNYA, etiqueta: 'Catalunya' },
  { valor: undefined, etiqueta: 'Todo el Estado' },
];

export const AmbitoBar: React.FC<AmbitoBarProps> = ({ ambito, onChange, visibles }) => {
  const filtrado = ambito === AMBITO_CATALUNYA;

  return (
    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 px-4 py-3 rounded-xl bg-surface border border-line">
      <div className="flex items-center gap-2.5 min-w-0">
        <MapPin className="w-4 h-4 text-ink-faint shrink-0" />
        <div className="min-w-0">
          <span className="text-xs font-semibold text-ink">Ámbito territorial</span>
          {/* Se dice lo que se está escondiendo. Con el filtro puesto el Funnel enseña una
              fracción de lo que hay: es lo correcto y era el objetivo —pasar de parecer lleno
              y ajeno a parecer pertinente—, pero callarlo convertiría un filtro en una laguna.
              Y no se afirma un recuento que no se tenga: `visibles` puede no haber llegado. */}
          <p className="text-[11px] text-ink-dim leading-snug truncate">
            {filtrado
              ? typeof visibles === 'number'
                ? `Se muestran los ${visibles} expedientes de Catalunya. El resto sigue en la base.`
                : 'Se muestran sólo los expedientes de Catalunya. El resto sigue en la base.'
              : 'Se muestra todo lo capturado, dentro y fuera de Catalunya.'}
          </p>
        </div>
      </div>

      <div
        role="group"
        aria-label="Ámbito territorial"
        className="flex items-center p-1 bg-surface-2/90 rounded-lg border border-line/80 shrink-0 self-start sm:self-auto"
      >
        {OPCIONES.map((opcion) => {
          const activa = opcion.valor === ambito;
          return (
            <button
              key={opcion.etiqueta}
              type="button"
              aria-pressed={activa}
              onClick={() => onChange(opcion.valor)}
              className={cn(
                'px-3 py-1.5 rounded-md text-xs font-semibold transition-all cursor-pointer select-none',
                activa
                  ? 'bg-acento/12 text-acento border border-acento/30'
                  : 'text-ink-dim hover:text-ink hover:bg-surface-2 border border-transparent'
              )}
            >
              {opcion.etiqueta}
            </button>
          );
        })}
      </div>
    </div>
  );
};

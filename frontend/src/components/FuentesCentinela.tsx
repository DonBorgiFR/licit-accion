/**
 * frontend/src/components/FuentesCentinela.tsx — Por qué el canal está como está
 * Capa 10, Paso 9, bloque E — repara H-45 en su cara de pantalla
 * Ecosistema Automático de Licitaciones (bfr_incoop)
 *
 * POR QUÉ EXISTE. Un canal vacío tiene tres causas que no se parecen en nada —no hay novedades,
 * no se pudo consultar, nadie está mirando— y hasta el 2026-08-27 en pantalla se veían las tres
 * igual. Medido ese día: **26 descargas degradadas de 27** y `boletines_alertas` con 0 filas,
 * mientras el Cockpit enseñaba un `0` que cualquiera lee como *«no hay oportunidades»*. Lo
 * cierto era *«llevo semanas sin poder mirar»*. Es la familia de H-21: no rompe nada, y una
 * persona decide sobre lo contrario de lo que pasa.
 *
 * QUÉ NO HACE. No pinta nada cuando todas las fuentes están bien. Un aviso permanente en la
 * cabecera de una pantalla acaba formando parte del mobiliario, y el día que tenga algo que
 * decir ya no lo verá nadie — que es exactamente por lo que se desactivó el DOGC en vez de
 * dejarlo fallando cada noche.
 */

import React from 'react';
import { AlertTriangle, EyeOff, HelpCircle } from 'lucide-react';
import { useFuentesCentinelaQuery } from '../hooks/useApiQueries';
import type { EstadoFuente } from '../types/api';

const PRESENTACION: Record<string, { icono: React.ElementType; titulo: string; clase: string }> = {
  DEGRADADA: {
    icono: AlertTriangle,
    titulo: 'no se ha podido consultar',
    clase: 'bg-peligro/10 border-peligro/30 text-peligro',
  },
  OMITIDA: {
    icono: EyeOff,
    titulo: 'está desactivada',
    clase: 'bg-atencion/10 border-atencion/30 text-atencion',
  },
  SIN_DATOS: {
    icono: HelpCircle,
    titulo: 'no consta consultada nunca',
    clase: 'bg-atencion/10 border-atencion/30 text-atencion',
  },
};

export const FuentesCentinela: React.FC = () => {
  const { data, isLoading, isError } = useFuentesCentinelaQuery();

  if (isLoading || isError || !data) return null;

  const problematicas = data.filter((f: EstadoFuente) => f.estado !== 'OK');
  if (problematicas.length === 0) return null;

  const sanas = data.filter((f: EstadoFuente) => f.estado === 'OK');

  return (
    <div className="rounded-lg border border-line bg-surface-2 p-4 space-y-2">
      <p className="text-xs font-semibold text-ink-dim uppercase tracking-wide">
        Estado de las fuentes oficiales
      </p>

      {problematicas.map((fuente: EstadoFuente) => {
        const p = PRESENTACION[fuente.estado] ?? PRESENTACION.SIN_DATOS;
        const Icono = p.icono;
        return (
          <div
            key={fuente.fuente}
            className={`flex items-start gap-2 rounded-md border px-3 py-2 text-xs ${p.clase}`}
          >
            <Icono className="w-4 h-4 mt-0.5 shrink-0" />
            <span>
              <strong className="font-mono">{fuente.fuente}</strong> {p.titulo}
              {fuente.detalle ? <> — {fuente.detalle}</> : null}
            </span>
          </div>
        );
      })}

      {/* Lo que sí funciona también se dice: sin esto, ver un aviso induce a pensar que el canal
          entero está roto, y la conclusión sería tan equivocada como la que había antes. */}
      {sanas.length > 0 && (
        <p className="text-[11px] text-ink-faint">
          {sanas
            .map((f: EstadoFuente) =>
              `${f.fuente}: consultada correctamente${
                f.alertas !== null && f.alertas !== undefined ? ` (${f.alertas} anuncios)` : ''
              }`
            )
            .join(' · ')}
        </p>
      )}
    </div>
  );
};

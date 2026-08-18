/**
 * frontend/src/components/ProspeccionIndicator.tsx — Estado de la prospección (Capa 10, Paso 7)
 * Ecosistema Automático de Licitaciones (bfr_incoop)
 *
 * POR QUÉ EXISTE. Desde el Paso 7, un doble clic abre el Cockpit **y acto seguido lanza la
 * prospección**, que tarda minutos: la corrida real del 2026-08-12 duró 255 s. Sin este
 * indicador, la persona ve los datos de ayer, no tiene forma de saber que hay trabajo en
 * marcha ni cuándo volver a mirar, y concluiría que el sistema no se actualiza. El orden
 * —abrir primero, prospectar después— es lo que evita cuatro minutos de pantalla en blanco;
 * esto es lo que evita que esos cuatro minutos parezcan un sistema parado.
 *
 * QUÉ NO HACE, A PROPÓSITO. **No es el distintivo de fallo del Paso 9.** Cuando la última
 * corrida no está completa lo dice en voz baja y sin diagnóstico: hacerlo hablar como es
 * debido exige decidir antes qué canal cuenta qué (H-39), y eso tiene su propio paso.
 *
 * LO QUE SÍ RESPETA DESDE YA. **Nunca afirma "al día" sobre una corrida que no lo está.** Un
 * indicador en verde sobre una prospección rota no rompería nada y mentiría en pantalla, que
 * es exactamente la familia de H-21, H-22 y H-23.
 */

import React from 'react';
import { AlertTriangle, CheckCircle2, Loader2, Radar } from 'lucide-react';
import { useUltimaProspeccionQuery } from '../hooks/useApiQueries';
import { Badge } from './ui/Badge';
import { formatDate } from '../lib/utils';

export const ProspeccionIndicator: React.FC = () => {
  const { data, isLoading, isError } = useUltimaProspeccionQuery();

  // Mientras no se sepa nada no se pinta nada: un indicador que parpadea en cada carga
  // acabaría ignorándose, y entonces no serviría el día que tenga algo que decir.
  if (isLoading || isError) return null;

  const ultima = data?.items?.[0];

  if (!ultima) {
    return (
      <Badge variant="default" className="px-3 py-1 gap-2 shadow-xs" title="Todavía no consta ninguna prospección en la base">
        <Radar className="w-3.5 h-3.5 opacity-80" />
        <span className="font-mono text-xs font-semibold">Sin prospecciones</span>
      </Badge>
    );
  }

  // Un `RUNNING` no basta para decir "en curso": la fila se queda igual cuando una corrida
  // muere a mitad, y anunciar una prospección viva sobre un cadáver sería un badge girando
  // para siempre (H-43). Quien lo sabe es la API, con el mismo criterio que usa el cerrojo.
  if (ultima.estado === 'RUNNING' && ultima.duenyo_vivo === true) {
    return (
      <Badge
        variant="indigo"
        className="px-3 py-1 gap-2 shadow-xs"
        title={`Prospección iniciada a las ${formatDate(ultima.start_time)}. La pantalla se actualiza sola al terminar.`}
      >
        <Loader2 className="w-3.5 h-3.5 animate-spin" />
        <span className="font-mono text-xs font-semibold">Prospección en curso</span>
      </Badge>
    );
  }

  if (ultima.estado === 'RUNNING') {
    // `false` es una corrida interrumpida; `null`, una fila anterior al esquema v8 sobre la
    // que no se puede afirmar nada. Se distinguen en el texto en vez de elegir por el lector.
    const interrumpida = ultima.duenyo_vivo === false;
    return (
      <Badge
        variant="warning"
        className="px-3 py-1 gap-2 shadow-xs"
        title={
          interrumpida
            ? `La prospección nº ${ultima.id}, iniciada el ${formatDate(ultima.start_time)}, quedó sin terminar: su proceso ya no existe. La siguiente corrida la cerrará.`
            : `La prospección nº ${ultima.id} consta iniciada el ${formatDate(ultima.start_time)} y no se puede comprobar si sigue viva.`
        }
      >
        <AlertTriangle className="w-3.5 h-3.5 opacity-90" />
        <span className="font-mono text-xs font-semibold">
          {interrumpida ? 'Prospección interrumpida' : 'Prospección sin cerrar'}
        </span>
      </Badge>
    );
  }

  if (ultima.estado === 'COMPLETED') {
    return (
      <Badge
        variant="success"
        className="px-3 py-1 gap-2 shadow-xs"
        title={`Última prospección completada el ${formatDate(ultima.end_time)} · ${ultima.expedientes_nuevos ?? 0} expedientes nuevos`}
      >
        <CheckCircle2 className="w-3.5 h-3.5 opacity-90" />
        <span className="font-mono text-xs font-semibold">Datos al día</span>
      </Badge>
    );
  }

  return (
    <Badge
      variant="warning"
      className="px-3 py-1 gap-2 shadow-xs"
      title={`La prospección nº ${ultima.id} consta como ${ultima.estado}. Los datos en pantalla son los de la última corrida completa.`}
    >
      <AlertTriangle className="w-3.5 h-3.5 opacity-90" />
      <span className="font-mono text-xs font-semibold">Prospección incompleta</span>
    </Badge>
  );
};

/**
 * frontend/src/components/ProspeccionIndicator.tsx — Estado de la prospección
 * Capa 10, Paso 7 (nació) · Paso 9 (aprendió a decir por qué)
 * Ecosistema Automático de Licitaciones (bfr_incoop)
 *
 * POR QUÉ EXISTE. Desde el Paso 7, un doble clic abre el Cockpit **y acto seguido lanza la
 * prospección**, que tarda minutos. Sin este indicador, la persona ve los datos de ayer, no
 * tiene forma de saber que hay trabajo en marcha ni cuándo volver a mirar, y concluiría que el
 * sistema no se actualiza.
 *
 * QUÉ CAMBIÓ EN EL PASO 9, Y NO ES COSMÉTICO. Hasta el 2026-08-27 este componente sólo podía
 * leer el estado de la fila de `ejecuciones`, y con eso **decía «Datos al día» sobre corridas
 * ciegas**. La corrida 16 de esa mañana consta `COMPLETED` con `errores: 0`, y dentro de ella
 * el Centinela no pudo consultar ninguna de sus dos fuentes —DOGC 404, BOPB 500—. El
 * distintivo era verde. No era un defecto de esta pantalla: es que nadie transportaba la
 * degradación hasta aquí. Ahora lo hace `GET /admin/prospeccion/diagnostico`, y existe el
 * estado `COMPLETADA_CON_DEGRADACION` para lo que antes no tenía nombre.
 *
 * LA REGLA QUE GOBIERNA EL FICHERO. **Nunca afirmar en verde lo que no se ha podido comprobar.**
 * Un dato poco fiable mostrado sin distintivo es peor que un dato ausente, porque induce a
 * decidir sobre él (Convención C3). De ahí que «terminó» y «terminó pudiendo hacerlo todo» sean
 * dos cosas distintas en pantalla, y que un rastro con agujeros se diga en vez de callarse.
 */

import React from 'react';
import { AlertTriangle, CheckCircle2, Loader2, Radar, ShieldAlert } from 'lucide-react';
import { useDiagnosticoProspeccionQuery } from '../hooks/useApiQueries';
import type { DiagnosticoProspeccion } from '../types/api';
import { Badge } from './ui/Badge';
import { formatDate } from '../lib/utils';

/** El texto emergente: el motivo, lo que no se pudo hacer, y sobre qué se construyó el juicio. */
function detalle(d: DiagnosticoProspeccion): string {
  const lineas = [d.motivo];

  if (d.degradaciones.length > 0) {
    // Se agrupan las idénticas. Detectado mirando la pantalla el 2026-08-27 (Convención C7): las
    // cinco degradaciones de la corrida 18 eran el mismo fallo repetido —una por alerta— y el
    // aviso escupía cinco párrafos iguales. Un texto que hay que leer cinco veces para enterarse
    // de que dice una sola cosa no informa: cansa, y lo que cansa se deja de mirar.
    const veces = new Map<string, number>();
    for (const g of d.degradaciones) {
      const clave = `${g.componente}: ${g.detalle || g.evento}`;
      veces.set(clave, (veces.get(clave) ?? 0) + 1);
    }

    lineas.push('');
    for (const [texto, n] of veces) {
      lineas.push(n > 1 ? `· ${texto}  (×${n})` : `· ${texto}`);
    }
  }

  if (d.ultimo_evento) {
    lineas.push('');
    lineas.push(`Último registro: ${d.ultimo_evento} (${formatDate(d.ultimo_evento_cuando)})`);
  }

  // Se dice, no se calla: un diagnóstico construido sobre un fichero con agujeros no puede
  // presentarse como completo (H-55). Y se dice que es del rastro, no de esta corrida.
  if (!d.rastro_legible) {
    lineas.push('');
    lineas.push('Aviso: el registro de auditoría no se pudo leer, así que esto sale sólo de la base.');
  } else if (d.rastro_degradado) {
    lineas.push('');
    lineas.push(`Aviso: el registro de auditoría tiene ${d.rastro_lineas_ilegibles} líneas ilegibles.`);
  }

  return lineas.join('\n');
}

export const ProspeccionIndicator: React.FC = () => {
  const { data, isLoading, isError } = useDiagnosticoProspeccionQuery();

  // Mientras no se sepa nada no se pinta nada: un indicador que parpadea en cada carga acabaría
  // ignorándose, y entonces no serviría el día que tenga algo que decir.
  if (isLoading || isError || !data) return null;

  const comun = 'px-3 py-1 gap-2 shadow-xs';

  switch (data.estado) {
    case 'SIN_PROSPECCIONES':
      return (
        <Badge variant="default" className={comun} title="Todavía no consta ninguna prospección">
          <Radar className="w-3.5 h-3.5 opacity-80" />
          <span className="font-mono text-xs font-semibold">Sin prospecciones</span>
        </Badge>
      );

    case 'EN_CURSO':
      return (
        <Badge variant="indigo" className={comun} title={detalle(data)}>
          <Loader2 className="w-3.5 h-3.5 animate-spin" />
          <span className="font-mono text-xs font-semibold">Prospección en curso</span>
        </Badge>
      );

    case 'COMPLETADA':
      return (
        <Badge variant="success" className={comun} title={detalle(data)}>
          <CheckCircle2 className="w-3.5 h-3.5 opacity-90" />
          <span className="font-mono text-xs font-semibold">Datos al día</span>
        </Badge>
      );

    // El estado que este paso añade. **No es verde**, y ésa es toda la cuestión: la corrida
    // terminó, así que los datos sirven, pero hubo algo que no se pudo mirar. Decir «al día»
    // aquí es la mentira que el Paso 9 vino a quitar.
    case 'COMPLETADA_CON_DEGRADACION':
      return (
        <Badge variant="warning" className={comun} title={detalle(data)}>
          <ShieldAlert className="w-3.5 h-3.5 opacity-90" />
          <span className="font-mono text-xs font-semibold">
            Al día, con {data.degradaciones.length}{' '}
            {data.degradaciones.length === 1 ? 'aviso' : 'avisos'}
          </span>
        </Badge>
      );

    case 'INTERRUMPIDA_POR_TOPE':
      return (
        <Badge variant="warning" className={comun} title={detalle(data)}>
          <AlertTriangle className="w-3.5 h-3.5 opacity-90" />
          <span className="font-mono text-xs font-semibold">Prospección cortada por tiempo</span>
        </Badge>
      );

    case 'INTERRUMPIDA':
      return (
        <Badge variant="warning" className={comun} title={detalle(data)}>
          <AlertTriangle className="w-3.5 h-3.5 opacity-90" />
          <span className="font-mono text-xs font-semibold">Prospección interrumpida</span>
        </Badge>
      );

    case 'SIN_CERRAR':
      return (
        <Badge variant="warning" className={comun} title={detalle(data)}>
          <AlertTriangle className="w-3.5 h-3.5 opacity-90" />
          <span className="font-mono text-xs font-semibold">Prospección sin cerrar</span>
        </Badge>
      );

    case 'FALLIDA':
      return (
        <Badge variant="danger" className={comun} title={detalle(data)}>
          <AlertTriangle className="w-3.5 h-3.5 opacity-90" />
          <span className="font-mono text-xs font-semibold">Prospección fallida</span>
        </Badge>
      );

    // `DESCONOCIDA` y cualquier cosa futura. No se pinta en verde ni se llama avería: se dice
    // que no se sabe, que es lo que exige la Convención C6 en las dos direcciones.
    default:
      return (
        <Badge variant="warning" className={comun} title={detalle(data)}>
          <AlertTriangle className="w-3.5 h-3.5 opacity-90" />
          <span className="font-mono text-xs font-semibold">Prospección sin diagnosticar</span>
        </Badge>
      );
  }
};

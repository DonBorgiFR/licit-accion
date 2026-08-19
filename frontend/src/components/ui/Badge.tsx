/**
 * frontend/src/components/ui/Badge.tsx — Componente Badge Semántico (Capa 8 - Paso 4)
 * Ecosistema Automático de Licitaciones (bfr_incoop)
 */

import React from 'react';
import { cn } from '../../lib/utils';

export type BadgeVariant =
  | 'default'
  | 'success'
  | 'warning'
  | 'danger'
  | 'indigo'
  | 'cyan'
  | 'outline';

interface BadgeProps extends React.HTMLAttributes<HTMLSpanElement> {
  variant?: BadgeVariant;
  children: React.ReactNode;
}

const variantStyles: Record<BadgeVariant, string> = {
  default: 'bg-surface-2 text-ink-dim border-line',
  success: 'bg-conforme/12 text-conforme border-conforme/28',
  warning: 'bg-atencion/12 text-atencion border-atencion/28',
  danger: 'bg-alarma/12 text-alarma border-alarma/28',
  indigo: 'bg-acento/10 text-acento border-acento/28',
  cyan: 'bg-acento/10 text-acento border-acento/28',
  outline: 'bg-transparent text-ink-dim border-line',
};

export const Badge: React.FC<BadgeProps> = ({
  variant = 'default',
  className,
  children,
  ...props
}) => {
  return (
    <span
      className={cn(
        'inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium border transition-colors',
        variantStyles[variant],
        className
      )}
      {...props}
    >
      {children}
    </span>
  );
};

/**
 * Helper para renderizar un Badge según el estado operativo de una licitación.
 */
export const EstadoLicitacionBadge: React.FC<{ estado: string }> = ({ estado }) => {
  let variant: BadgeVariant = 'default';

  switch (estado) {
    case 'Nueva':
      variant = 'indigo';
      break;
    case 'Estudiando':
      variant = 'warning';
      break;
    case 'Presentada':
      variant = 'cyan';
      break;
    case 'Adjudicada':
      variant = 'success';
      break;
    case 'Perdida':
    case 'Descartada':
    case 'Anulada_Administracion':
    case 'Inactiva':
      variant = 'danger';
      break;
    default:
      variant = 'default';
  }

  return <Badge variant={variant}>{estado}</Badge>;
};

/**
 * Helper para renderizar un Badge de Score Comercial.
 */
/**
 * El score, leído como MAGNITUD y no como semáforo.
 *
 * Antes pintaba verde por encima de 70, ámbar por encima de 45 y rojo por debajo, con lo
 * que cada fila cargaba una píldora de color y **ninguna destacaba** — el diagnóstico
 * literal de dirección: *"todo pesa lo mismo, así que nada destaca"*. Y además mentía: un
 * score de 40 **no es un peligro**, es una oportunidad que encaja poco. El rojo estaba
 * diciendo «cuidado» donde sólo había «esto no es lo tuyo».
 *
 * Ahora la cifra se lee por tamaño y la barra por longitud, en neutro. El acento se
 * reserva a la prioridad **Alta**, que es un juicio que el Filtro ya emite y no un umbral
 * inventado aquí.
 */
export const ScoreBadge: React.FC<{ score: number; destacado?: boolean }> = ({
  score,
  destacado = false,
}) => (
  <div className="w-24 mx-auto" title={`${score} de 100 puntos de encaje comercial`}>
    <div className="flex items-baseline justify-end gap-1">
      <span
        className={`font-mono text-xl font-bold leading-none tabular-nums ${
          destacado ? 'text-acento' : 'text-ink'
        }`}
      >
        {score}
      </span>
      <span className="font-mono text-[10px] text-ink-faint">/100</span>
    </div>
    <div className="h-[3px] mt-1.5 rounded-full bg-surface-2 overflow-hidden">
      <div
        className={`h-full rounded-full ${destacado ? 'bg-acento' : 'bg-ink-faint'}`}
        style={{ width: `${Math.max(0, Math.min(100, score))}%` }}
      />
    </div>
  </div>
);

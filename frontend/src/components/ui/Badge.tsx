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
  default: 'bg-slate-100 text-slate-700 border-slate-200',
  success: 'bg-emerald-50 text-emerald-700 border-emerald-200/80',
  warning: 'bg-amber-50 text-amber-700 border-amber-200/80',
  danger: 'bg-rose-50 text-rose-700 border-rose-200/80',
  indigo: 'bg-indigo-50 text-indigo-700 border-indigo-200/80',
  cyan: 'bg-cyan-50 text-cyan-700 border-cyan-200/80',
  outline: 'bg-transparent text-slate-600 border-slate-300',
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
export const ScoreBadge: React.FC<{ score: number }> = ({ score }) => {
  let variant: BadgeVariant = 'default';

  if (score >= 70) variant = 'success';
  else if (score >= 45) variant = 'warning';
  else variant = 'danger';

  return (
    <Badge variant={variant} className="font-mono font-semibold">
      {score} pts
    </Badge>
  );
};

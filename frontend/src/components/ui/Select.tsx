/**
 * frontend/src/components/ui/Select.tsx — Componente Selector Desplegable (Capa 8 - Paso 4)
 * Ecosistema Automático de Licitaciones (bfr_incoop)
 */

import React from 'react';
import { cn } from '../../lib/utils';

export interface SelectOption {
  value: string;
  label: string;
}

export interface SelectProps extends React.SelectHTMLAttributes<HTMLSelectElement> {
  options: SelectOption[];
  error?: string;
}

export const Select = React.forwardRef<HTMLSelectElement, SelectProps>(
  ({ className, options, error, disabled, ...props }, ref) => {
    return (
      <div className="w-full">
        <select
          ref={ref}
          disabled={disabled}
          className={cn(
            'w-full bg-surface text-ink text-sm border border-line rounded-lg py-2 px-3 focus:outline-none focus:ring-2 focus:ring-acento focus:border-acento transition-all shadow-xs cursor-pointer disabled:bg-surface-2 disabled:opacity-60',
            error && 'border-alarma focus:ring-alarma focus:border-alarma',
            className
          )}
          {...props}
        >
          {options.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
        {error && <p className="text-xs text-alarma mt-1 font-medium">{error}</p>}
      </div>
    );
  }
);

Select.displayName = 'Select';

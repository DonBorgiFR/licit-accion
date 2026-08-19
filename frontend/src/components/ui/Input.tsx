/**
 * frontend/src/components/ui/Input.tsx — Campo de Entrada de Texto (Capa 8 - Paso 4)
 * Ecosistema Automático de Licitaciones (bfr_incoop)
 */

import React from 'react';
import { cn } from '../../lib/utils';

export interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  leftIcon?: React.ReactNode;
  rightIcon?: React.ReactNode;
  error?: string;
}

export const Input = React.forwardRef<HTMLInputElement, InputProps>(
  ({ className, leftIcon, rightIcon, error, disabled, ...props }, ref) => {
    return (
      <div className="w-full">
        <div className="relative flex items-center w-full">
          {leftIcon && (
            <div className="absolute left-3 text-ink-faint pointer-events-none flex items-center justify-center">
              {leftIcon}
            </div>
          )}
          <input
            ref={ref}
            disabled={disabled}
            className={cn(
              'w-full bg-surface text-ink placeholder:text-ink-faint text-sm border border-line rounded-lg py-2 px-3 focus:outline-none focus:ring-2 focus:ring-acento focus:border-acento transition-all shadow-xs disabled:bg-surface-2 disabled:opacity-60',
              leftIcon && 'pl-9',
              rightIcon && 'pr-9',
              error && 'border-alarma focus:ring-alarma focus:border-alarma',
              className
            )}
            {...props}
          />
          {rightIcon && (
            <div className="absolute right-3 text-ink-faint pointer-events-none flex items-center justify-center">
              {rightIcon}
            </div>
          )}
        </div>
        {error && <p className="text-xs text-alarma mt-1 font-medium">{error}</p>}
      </div>
    );
  }
);

Input.displayName = 'Input';

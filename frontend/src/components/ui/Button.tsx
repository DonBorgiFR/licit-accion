/**
 * frontend/src/components/ui/Button.tsx — Componente Botón Interactivo (Capa 8 - Paso 4)
 * Ecosistema Automático de Licitaciones (bfr_incoop)
 */

import React from 'react';
import { cn } from '../../lib/utils';

export type ButtonVariant = 'primary' | 'secondary' | 'outline' | 'ghost' | 'danger';
export type ButtonSize = 'sm' | 'md' | 'lg';

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  isLoading?: boolean;
  leftIcon?: React.ReactNode;
  rightIcon?: React.ReactNode;
}

const variantStyles: Record<ButtonVariant, string> = {
  primary:
    'bg-indigo-600 hover:bg-indigo-700 text-white shadow-sm border border-transparent focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2',
  secondary:
    'bg-slate-100 hover:bg-slate-200 text-slate-800 border border-slate-200 focus:ring-2 focus:ring-slate-400 focus:ring-offset-2',
  outline:
    'bg-white hover:bg-slate-50 text-slate-700 border border-slate-300 shadow-sm focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2',
  ghost:
    'bg-transparent hover:bg-slate-100 text-slate-700 border border-transparent focus:ring-2 focus:ring-slate-300',
  danger:
    'bg-rose-600 hover:bg-rose-700 text-white shadow-sm border border-transparent focus:ring-2 focus:ring-rose-500 focus:ring-offset-2',
};

const sizeStyles: Record<ButtonSize, string> = {
  sm: 'px-2.5 py-1.5 text-xs rounded-md font-medium gap-1.5',
  md: 'px-3.5 py-2 text-sm rounded-lg font-medium gap-2',
  lg: 'px-4.5 py-2.5 text-base rounded-lg font-semibold gap-2.5',
};

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  (
    {
      variant = 'primary',
      size = 'md',
      isLoading = false,
      leftIcon,
      rightIcon,
      className,
      children,
      disabled,
      ...props
    },
    ref
  ) => {
    return (
      <button
        ref={ref}
        disabled={disabled || isLoading}
        className={cn(
          'inline-flex items-center justify-center transition-all duration-150 cursor-pointer select-none active:scale-[0.98] disabled:opacity-60 disabled:pointer-events-none disabled:active:scale-100',
          variantStyles[variant],
          sizeStyles[size],
          className
        )}
        {...props}
      >
        {isLoading ? (
          <svg
            className="animate-spin h-4 w-4 text-current"
            xmlns="http://www.w3.org/2000/svg"
            fill="none"
            viewBox="0 0 24 24"
          >
            <circle
              className="opacity-25"
              cx="12"
              cy="12"
              r="10"
              stroke="currentColor"
              strokeWidth="4"
            ></circle>
            <path
              className="opacity-75"
              fill="currentColor"
              d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
            ></path>
          </svg>
        ) : (
          leftIcon
        )}
        <span>{children}</span>
        {!isLoading && rightIcon}
      </button>
    );
  }
);

Button.displayName = 'Button';

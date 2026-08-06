/**
 * frontend/src/components/ui/Drawer.tsx — Panel Lateral Deslizante (Capa 8 - Paso 4)
 * Ecosistema Automático de Licitaciones (bfr_incoop)
 */

import React, { useEffect } from 'react';
import { X } from 'lucide-react';
import { cn } from '../../lib/utils';
import { Button } from './Button';

export interface DrawerProps {
  isOpen: boolean;
  onClose: () => void;
  title?: React.ReactNode;
  subtitle?: React.ReactNode;
  children: React.ReactNode;
  footer?: React.ReactNode;
  width?: 'md' | 'lg' | 'xl' | '2xl';
}

const widthStyles = {
  md: 'max-w-md',
  lg: 'max-w-lg',
  xl: 'max-w-xl',
  '2xl': 'max-w-2xl',
};

export const Drawer: React.FC<DrawerProps> = ({
  isOpen,
  onClose,
  title,
  subtitle,
  children,
  footer,
  width = 'xl',
}) => {
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && isOpen) {
        onClose();
      }
    };
    if (isOpen) {
      document.body.style.overflow = 'hidden';
      window.addEventListener('keydown', handleKeyDown);
    }
    return () => {
      document.body.style.overflow = 'unset';
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 overflow-hidden">
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-slate-900/30 backdrop-blur-xs transition-opacity duration-300"
        onClick={onClose}
      />

      {/* Drawer Content Panel */}
      <div className="fixed inset-y-0 right-0 max-w-full flex pl-10">
        <div
          className={cn(
            'w-screen bg-white shadow-2xl border-l border-slate-200 flex flex-col transform transition-transform duration-300 ease-in-out',
            widthStyles[width]
          )}
        >
          {/* Header */}
          <div className="p-6 pb-4 border-b border-slate-100 flex items-start justify-between bg-slate-50/50">
            <div className="pr-4">
              {typeof title === 'string' ? (
                <h2 className="text-lg font-bold text-slate-900 leading-snug">{title}</h2>
              ) : (
                title
              )}
              {subtitle && (
                typeof subtitle === 'string' ? (
                  <p className="text-xs text-slate-500 mt-1 font-mono">{subtitle}</p>
                ) : (
                  subtitle
                )
              )}
            </div>
            <Button
              variant="ghost"
              size="sm"
              onClick={onClose}
              className="p-1 text-slate-400 hover:text-slate-700 rounded-full"
            >
              <X className="w-5 h-5" />
            </Button>
          </div>

          {/* Body */}
          <div className="flex-1 overflow-y-auto p-6 space-y-6">{children}</div>

          {/* Footer */}
          {footer && (
            <div className="p-4 px-6 bg-slate-50 border-t border-slate-200/80 flex items-center justify-end gap-3">
              {footer}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

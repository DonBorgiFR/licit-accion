/**
 * frontend/src/components/ui/Toast.tsx — Notificaciones Emergentes (Capa 8 - Paso 4)
 * Ecosistema Automático de Licitaciones (bfr_incoop)
 */

import React, { createContext, useContext, useState, useCallback } from 'react';
import { CheckCircle2, AlertCircle, Info, X } from 'lucide-react';
import { cn } from '../../lib/utils';

export type ToastType = 'success' | 'error' | 'info' | 'warning';

export interface ToastMessage {
  id: string;
  type: ToastType;
  title: string;
  description?: string;
}

interface ToastContextType {
  toast: (message: Omit<ToastMessage, 'id'>) => void;
  success: (title: string, description?: string) => void;
  error: (title: string, description?: string) => void;
}

const ToastContext = createContext<ToastContextType | undefined>(undefined);

export const ToastProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [toasts, setToasts] = useState<ToastMessage[]>([]);

  const removeToast = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const toast = useCallback(
    ({ type, title, description }: Omit<ToastMessage, 'id'>) => {
      const id = Math.random().toString(36).substring(2, 9);
      setToasts((prev) => [...prev, { id, type, title, description }]);
      setTimeout(() => {
        removeToast(id);
      }, 4000);
    },
    [removeToast]
  );

  const success = useCallback(
    (title: string, description?: string) => {
      toast({ type: 'success', title, description });
    },
    [toast]
  );

  const error = useCallback(
    (title: string, description?: string) => {
      toast({ type: 'error', title, description });
    },
    [toast]
  );

  return (
    <ToastContext.Provider value={{ toast, success, error }}>
      {children}
      {/* Toast Container */}
      <div className="fixed bottom-5 right-5 z-50 flex flex-col gap-2 max-w-md w-full pointer-events-none px-4">
        {toasts.map((t) => (
          <div
            key={t.id}
            className={cn(
              'pointer-events-auto flex items-start gap-3 p-4 rounded-xl border shadow-lg animate-in slide-in-from-bottom-5 duration-200 bg-white',
              t.type === 'success' && 'border-emerald-200 text-slate-800',
              t.type === 'error' && 'border-rose-200 text-slate-800',
              t.type === 'info' && 'border-indigo-200 text-slate-800',
              t.type === 'warning' && 'border-amber-200 text-slate-800'
            )}
          >
            {t.type === 'success' && <CheckCircle2 className="w-5 h-5 text-emerald-600 shrink-0 mt-0.5" />}
            {t.type === 'error' && <AlertCircle className="w-5 h-5 text-rose-600 shrink-0 mt-0.5" />}
            {(t.type === 'info' || t.type === 'warning') && <Info className="w-5 h-5 text-indigo-600 shrink-0 mt-0.5" />}
            <div className="flex-1">
              <h4 className="text-sm font-semibold text-slate-900">{t.title}</h4>
              {t.description && <p className="text-xs text-slate-500 mt-0.5">{t.description}</p>}
            </div>
            <button
              onClick={() => removeToast(t.id)}
              className="text-slate-400 hover:text-slate-600 p-0.5 rounded-full"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
};

export function useToast() {
  const context = useContext(ToastContext);
  if (!context) {
    throw new Error('useToast debe usarse dentro de ToastProvider');
  }
  return context;
}

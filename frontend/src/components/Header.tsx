/**
 * frontend/src/components/Header.tsx — Cabecera Ejecutiva y Navegación Principal (Capa 8 - Paso 5)
 * Ecosistema Automático de Licitaciones (bfr_incoop)
 */

import React from 'react';
import { LayoutDashboard, FileText, Radio, Building2, Settings2 } from 'lucide-react';
import { HealthIndicator } from './HealthIndicator';
import { cn } from '../lib/utils';

export type ActiveTab = 'kpis' | 'licitaciones' | 'centinela' | 'admin';

interface HeaderProps {
  activeTab: ActiveTab;
  setActiveTab: (tab: ActiveTab) => void;
}

export const Header: React.FC<HeaderProps> = ({ activeTab, setActiveTab }) => {
  return (
    <header className="sticky top-0 z-40 w-full bg-white/90 backdrop-blur-md border-b border-slate-200/90 shadow-xs">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-16">
          {/* Identidad de Marca Incoop */}
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-indigo-600 to-violet-700 flex items-center justify-center text-white shadow-sm">
              <Building2 className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="text-base font-bold text-slate-900 tracking-tight">
                  Incoop, SCCL
                </span>
                <span className="text-[10px] font-mono font-semibold px-2 py-0.5 rounded-full bg-indigo-50 text-indigo-700 border border-indigo-200">
                  v1.0
                </span>
              </div>
              <p className="text-xs text-slate-500 font-medium">
                Ecosistema de Licitaciones & Control de Gestión
              </p>
            </div>
          </div>

          {/* Selector de Pestañas Navegables */}
          <nav className="flex items-center p-1 bg-slate-100/90 rounded-xl border border-slate-200/80">
            <button
              onClick={() => setActiveTab('kpis')}
              className={cn(
                'flex items-center gap-2 px-3.5 py-1.5 rounded-lg text-xs font-semibold transition-all cursor-pointer select-none',
                activeTab === 'kpis'
                  ? 'bg-white text-indigo-600 shadow-xs border border-slate-200/60'
                  : 'text-slate-600 hover:text-slate-900 hover:bg-white/50'
              )}
            >
              <LayoutDashboard className="w-3.5 h-3.5" />
              <span>Dashboard KPIs</span>
            </button>

            <button
              onClick={() => setActiveTab('licitaciones')}
              className={cn(
                'flex items-center gap-2 px-3.5 py-1.5 rounded-lg text-xs font-semibold transition-all cursor-pointer select-none',
                activeTab === 'licitaciones'
                  ? 'bg-white text-indigo-600 shadow-xs border border-slate-200/60'
                  : 'text-slate-600 hover:text-slate-900 hover:bg-white/50'
              )}
            >
              <FileText className="w-3.5 h-3.5" />
              <span>Funnel PSCP</span>
            </button>

            <button
              onClick={() => setActiveTab('centinela')}
              className={cn(
                'flex items-center gap-2 px-3.5 py-1.5 rounded-lg text-xs font-semibold transition-all cursor-pointer select-none',
                activeTab === 'centinela'
                  ? 'bg-white text-indigo-600 shadow-xs border border-slate-200/60'
                  : 'text-slate-600 hover:text-slate-900 hover:bg-white/50'
              )}
            >
              <Radio className="w-3.5 h-3.5" />
              <span>Centinela (Boletines)</span>
            </button>

            <button
              onClick={() => setActiveTab('admin')}
              className={cn(
                'flex items-center gap-2 px-3.5 py-1.5 rounded-lg text-xs font-semibold transition-all cursor-pointer select-none',
                activeTab === 'admin'
                  ? 'bg-white text-indigo-600 shadow-xs border border-slate-200/60'
                  : 'text-slate-600 hover:text-slate-900 hover:bg-white/50'
              )}
            >
              <Settings2 className="w-3.5 h-3.5" />
              <span>Administración</span>
            </button>
          </nav>

          {/* Sensor de Salud de la API */}
          <div className="flex items-center gap-3">
            <HealthIndicator />
          </div>
        </div>
      </div>
    </header>
  );
};

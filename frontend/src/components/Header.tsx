/**
 * frontend/src/components/Header.tsx — Cabecera Ejecutiva y Navegación Principal (Capa 8 - Paso 5)
 * Ecosistema Automático de Licitaciones (bfr_incoop)
 */

import React from 'react';
import { LayoutDashboard, FileText, Radio, Settings2 } from 'lucide-react';
import { HealthIndicator } from './HealthIndicator';
import { ProspeccionIndicator } from './ProspeccionIndicator';
import { cn } from '../lib/utils';
import isotipo from '../assets/incoop-isotipo.png';

export type ActiveTab = 'kpis' | 'licitaciones' | 'centinela' | 'admin';

interface HeaderProps {
  activeTab: ActiveTab;
  setActiveTab: (tab: ActiveTab) => void;
}

export const Header: React.FC<HeaderProps> = ({ activeTab, setActiveTab }) => {
  return (
    <header className="sticky top-0 z-40 w-full bg-surface/90 backdrop-blur-md border-b border-line/90 shadow-xs">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-16">
          {/* Identidad de marca. El nombre se compone con TEXTO y no con imagen:
              queda nítido a cualquier tamaño, no depende de un PNG de 300 píxeles
              y acompaña al tema. La imagen es sólo el isotipo, que sí es una forma. */}
          <div className="flex items-center gap-3">
            <img
              src={isotipo}
              alt="Incoop"
              className="w-9 h-9 shrink-0"
              width={36}
              height={36}
            />
            <div className="pl-3 border-l border-line">
              <div className="flex items-center gap-2">
                <span className="font-display text-[17px] font-bold text-ink tracking-[0.035em] leading-none">
                  INCOOP
                </span>
                <span className="text-[10px] font-mono font-semibold px-2 py-0.5 rounded-full bg-acento/10 text-acento border border-acento/35">
                  v1.0
                </span>
              </div>
              <p className="text-[9px] font-mono tracking-[0.2em] text-ink-faint mt-1">
                COOPERAR X TRANSFORMAR
              </p>
            </div>
          </div>

          {/* Selector de Pestañas Navegables */}
          <nav className="flex items-center p-1 bg-surface-2/90 rounded-xl border border-line/80">
            <button
              onClick={() => setActiveTab('kpis')}
              className={cn(
                'flex items-center gap-2 px-3.5 py-1.5 rounded-lg text-xs font-semibold transition-all cursor-pointer select-none',
                activeTab === 'kpis'
                  ? 'bg-acento/12 text-acento border border-acento/30'
                  : 'text-ink-dim hover:text-ink hover:bg-surface-2 border border-transparent'
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
                  ? 'bg-acento/12 text-acento border border-acento/30'
                  : 'text-ink-dim hover:text-ink hover:bg-surface-2 border border-transparent'
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
                  ? 'bg-acento/12 text-acento border border-acento/30'
                  : 'text-ink-dim hover:text-ink hover:bg-surface-2 border border-transparent'
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
                  ? 'bg-acento/12 text-acento border border-acento/30'
                  : 'text-ink-dim hover:text-ink hover:bg-surface-2 border border-transparent'
              )}
            >
              <Settings2 className="w-3.5 h-3.5" />
              <span>Administración</span>
            </button>
          </nav>

          {/* Sensor de Salud de la API y estado de la prospección */}
          <div className="flex items-center gap-3">
            <ProspeccionIndicator />
            <HealthIndicator />
          </div>
        </div>
      </div>
    </header>
  );
};

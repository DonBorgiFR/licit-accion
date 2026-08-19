/**
 * frontend/src/App.tsx — Layout Principal del Cockpit Visual (Capa 8 - Paso 9)
 * Ecosistema Automático de Licitaciones (bfr_incoop)
 */

import { useState } from 'react';
import { Header, type ActiveTab } from './components/Header';
import { KPIDashboard } from './components/KPIDashboard';
import { LicitacionesTable } from './components/LicitacionesTable';
import { AlertasTable } from './components/AlertasTable';
import { DetailDrawer } from './components/DetailDrawer';
import { AdminPanel } from './components/AdminPanel';

export function App() {
  const [activeTab, setActiveTab] = useState<ActiveTab>('kpis');
  const [selectedLicitacionId, setSelectedLicitacionId] = useState<string | null>(null);
  const [selectedAlertaId, setSelectedAlertaId] = useState<string | null>(null);

  const handleSelectLicitacion = (id: string) => {
    setSelectedLicitacionId(id);
  };

  const handleSelectAlerta = (id_alerta: string) => {
    setSelectedAlertaId(id_alerta);
  };

  const handleCloseDrawer = () => {
    setSelectedLicitacionId(null);
    setSelectedAlertaId(null);
  };

  return (
    <div className="min-h-screen bg-ground text-ink font-sans">
      {/* Cabecera Ejecutiva Fija con Sensor de Salud */}
      <Header activeTab={activeTab} setActiveTab={setActiveTab} />

      {/* Contenido Principal según Pestaña Activa */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-6">
        {activeTab === 'kpis' && <KPIDashboard />}

        {activeTab === 'licitaciones' && (
          <LicitacionesTable onSelectLicitacion={handleSelectLicitacion} />
        )}

        {activeTab === 'centinela' && (
          <AlertasTable onSelectAlerta={handleSelectAlerta} />
        )}

        {activeTab === 'admin' && <AdminPanel />}
      </main>

      {/* Drawer de Detalle Completo (Licitación o Alerta) */}
      <DetailDrawer
        licitacionId={selectedLicitacionId}
        alertaId={selectedAlertaId}
        onClose={handleCloseDrawer}
      />
    </div>
  );
}

export default App;

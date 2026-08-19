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
import { AmbitoBar, AMBITO_CATALUNYA, type Ambito } from './components/AmbitoBar';
import { useKPIsQuery } from './hooks/useApiQueries';

export function App() {
  const [activeTab, setActiveTab] = useState<ActiveTab>('kpis');

  // El ámbito vive aquí porque gobierna **dos pestañas a la vez** (H-47): el Dashboard de KPIs
  // y el Funnel. Arranca en Catalunya, que es la decisión de dirección del 2026-08-18, y no se
  // recuerda entre recargas: el arranque correcto es siempre el ámbito propio, y una
  // preferencia guardada acabaría escondiendo licitaciones a quien no recordase haberla puesto.
  const [ambito, setAmbito] = useState<Ambito>(AMBITO_CATALUNYA);

  // El recuento que rotula la barra sale de la misma consulta que alimenta el Dashboard
  // —misma clave de caché, así que no cuesta una llamada de más— y de la misma población que
  // cuenta el Funnel. Si algún día dejaran de coincidir, se vería aquí.
  const { data: kpis } = useKPIsQuery(ambito);
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
        {/* El interruptor de ámbito, sólo donde gobierna algo. En Centinela no pinta nada
            —DOGC y BOPB son catalanes de origen— y en Administración tampoco. */}
        {(activeTab === 'kpis' || activeTab === 'licitaciones') && (
          <AmbitoBar
            ambito={ambito}
            onChange={setAmbito}
            visibles={kpis?.total_expedientes}
          />
        )}

        {activeTab === 'kpis' && <KPIDashboard ambito={ambito} />}

        {activeTab === 'licitaciones' && (
          <LicitacionesTable onSelectLicitacion={handleSelectLicitacion} ambito={ambito} />
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

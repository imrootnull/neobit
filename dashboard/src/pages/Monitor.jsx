import { useState, useEffect } from 'react';
import { apiGet } from '../api';
import { useWS } from '../context/WSContext';
import CameraGrid from '../components/CameraGrid';
import AlertFeed from '../components/AlertFeed';
import { Activity, Camera, Bell, Shield, Cpu, Wifi, WifiOff, HardHat, AlertTriangle } from 'lucide-react';

export default function Monitor() {
  const { streams, lastEvent, status } = useWS();
  const [cameras, setCameras]     = useState([]);
  const [system, setSystem]       = useState(null);
  const [eventStats, setEventStats] = useState({});

  useEffect(() => {
    apiGet('/api/cameras/').then(setCameras).catch(console.error);
    apiGet('/api/system').then(setSystem).catch(console.error);
    apiGet('/api/events/stats').then(setEventStats).catch(console.error);
  }, []);

  const activeCams  = streams.filter(s => s.connected).length;
  const totalAlerts = Object.values(eventStats)
    .flatMap(v => Object.values(v))
    .reduce((a, b) => a + b, 0);

  const fallAlerts = (eventStats.fall_detection?.critical || 0)
    + (eventStats.fall_detection?.high || 0);

  const eppViolations = (eventStats.epp_detection?.high || 0)
    + (eventStats.epp_detection?.critical || 0);

  return (
    <>
      <div className="page-header">
        <div>
          <h1 className="page-title">Monitor en Vivo</h1>
          <p className="page-subtitle">
            Visualización en tiempo real — hasta 8 cámaras simultáneas
          </p>
        </div>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <span className={`badge ${status === 'connected' ? 'badge-green' : 'badge-red'}`}>
            {status === 'connected'
              ? <><Wifi size={10} /> Conectado</>
              : <><WifiOff size={10} /> Sin conexión</>
            }
          </span>
          {system?.hardware?.coral && (
            <span className="badge badge-blue">
              <Cpu size={10} /> Coral USB
            </span>
          )}
        </div>
      </div>

      <div className="page-content">
        {/* Stats row */}
        <div className="stats-grid">
          <div className="stat-card">
            <div className="stat-icon blue"><Camera size={20} /></div>
            <div>
              <div className="stat-value">{activeCams}</div>
              <div className="stat-label">Cámaras activas</div>
            </div>
          </div>
          <div className="stat-card">
            <div className="stat-icon amber"><Bell size={20} /></div>
            <div>
              <div className="stat-value">{totalAlerts}</div>
              <div className="stat-label">Alertas totales</div>
            </div>
          </div>
          <div className="stat-card">
            <div className="stat-icon red"><AlertTriangle size={20} /></div>
            <div>
              <div className="stat-value">{fallAlerts}</div>
              <div className="stat-label">Caídas detectadas</div>
            </div>
          </div>
          <div className="stat-card">
            <div className="stat-icon purple"><HardHat size={20} /></div>
            <div>
              <div className="stat-value">{eppViolations}</div>
              <div className="stat-label">Violaciones EPP</div>
            </div>
          </div>
        </div>

        {/* Main layout */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 300px', gap: 16 }}>
          {/* Camera grid */}
          <div className="card">
            <div className="card-header">
              <span className="card-title">
                <Camera size={14} />
                Cámaras ({cameras.length} / 8)
              </span>
            </div>
            <div className="card-body">
              <CameraGrid
                cameras={cameras}
                streams={streams}
                lastEvent={lastEvent}
              />
            </div>
          </div>

          {/* Alert feed */}
          <div className="card">
            <div className="card-header">
              <span className="card-title">
                <Bell size={14} />
                Alertas en vivo
              </span>
            </div>
            <div className="card-body" style={{ padding: '12px 16px' }}>
              <AlertFeed cameras={cameras} />
            </div>
          </div>
        </div>
      </div>
    </>
  );
}

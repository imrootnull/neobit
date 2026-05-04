import { useState, useEffect } from 'react';
import { getMjpegUrl } from '../api';
import { WifiOff, AlertTriangle } from 'lucide-react';
import { ANALYTIC_ICONS } from './Icons';

const GRID_CLASSES = {
  1: 'grid-1', 2: 'grid-2', 3: 'grid-2',
  4: 'grid-4', 5: 'grid-6', 6: 'grid-6',
  7: 'grid-8', 8: 'grid-8',
};

export default function CameraGrid({ cameras, streams, lastEvent, onSelect }) {
  const [selected, setSelected]     = useState(null);
  const [cameraAlerts, setCameraAlerts] = useState({});

  useEffect(() => {
    if (!lastEvent) return;
    const cid = lastEvent.camera_id;
    setCameraAlerts(prev => ({ ...prev, [cid]: lastEvent }));
    const t = setTimeout(() => {
      setCameraAlerts(prev => { const n = { ...prev }; delete n[cid]; return n; });
    }, 5000);
    return () => clearTimeout(t);
  }, [lastEvent]);

  const gridClass = GRID_CLASSES[cameras.length] || 'grid-8';

  const handleSelect = (cam) => {
    setSelected(cam.id === selected ? null : cam.id);
    onSelect?.(cam);
  };

  if (!cameras.length) {
    return (
      <div className="empty-state" style={{ height: 400 }}>
        <WifiOff size={36} style={{ opacity: 0.2 }} />
        <div className="empty-title">Sin cámaras configuradas</div>
        <div className="empty-desc">
          Agrega cámaras desde la sección de Cámaras para comenzar el monitoreo.
        </div>
      </div>
    );
  }

  return (
    <div className={`camera-grid ${gridClass}`}>
      {cameras.map(cam => {
        const info        = streams.find(s => s.camera_id === cam.id);
        const isConnected = info?.connected ?? false;
        const fps         = info?.fps ?? 0;
        const alert       = cameraAlerts[cam.id];

        return (
          <CameraCell
            key={cam.id}
            camera={cam}
            connected={isConnected}
            fps={fps}
            alert={alert}
            selected={selected === cam.id}
            onClick={() => handleSelect(cam)}
          />
        );
      })}
    </div>
  );
}

function CameraCell({ camera, connected, fps, alert, selected, onClick }) {
  const [imgError, setImgError] = useState(false);

  useEffect(() => {
    if (connected) setImgError(false);
  }, [connected]);

  const AlertIcon = alert ? (ANALYTIC_ICONS[alert.analytic_type] || AlertTriangle) : null;

  return (
    <div
      className={`camera-cell ${selected ? 'selected' : ''}`}
      onClick={onClick}
      style={alert
        ? { borderColor: 'var(--accent-amber)', boxShadow: '0 0 16px rgba(245,158,11,0.25)' }
        : {}
      }
    >
      {connected && !imgError ? (
        <img
          src={getMjpegUrl(camera.id)}
          alt={camera.name}
          onError={() => setImgError(true)}
        />
      ) : (
        <div className="camera-no-signal">
          <WifiOff size={28} className="no-signal-icon" />
          <span className="no-signal-text">
            {connected ? 'Error de stream' : 'Sin señal'}
          </span>
        </div>
      )}

      <div className="camera-cell-overlay" />

      <div className="camera-cell-info">
        <span className="camera-cell-name">{camera.name}</span>
        <div className="camera-cell-badges">
          {alert && AlertIcon && (
            <span className="camera-badge alert" title={alert.analytic_type}>
              <AlertIcon size={10} />
            </span>
          )}
          {connected && (
            <span className="camera-badge live">LIVE</span>
          )}
          {connected && fps > 0 && (
            <span className="camera-badge fps">{fps.toFixed(0)} fps</span>
          )}
        </div>
      </div>

      {alert && (
        <div style={{
          position: 'absolute', inset: 0,
          border: '2px solid var(--accent-amber)',
          borderRadius: 'var(--radius-md)',
          pointerEvents: 'none',
          animation: 'pulse 1s infinite',
        }} />
      )}
    </div>
  );
}

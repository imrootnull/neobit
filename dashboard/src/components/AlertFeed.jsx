import { useState, useEffect } from 'react';
import { useWS } from '../context/WSContext';
import { apiPost } from '../api';
import { Bell, X, AlertTriangle, AlertOctagon, XCircle, Info } from 'lucide-react';
import { ANALYTIC_ICONS, SEVERITY_COLORS } from './Icons';

const SEVERITY_ICONS = {
  critical: XCircle,
  high:     AlertTriangle,
  medium:   AlertOctagon,
  low:      Info,
};

const ANALYTIC_LABELS = {
  epp_detection:      'EPP Industrial',
  fall_detection:     'Caída detectada',
  behavior_detection: 'Comportamiento hostil',
  theft_detection:    'Robo detectado',
  person_detection:   'Persona detectada',
  fire_detection:     'Fuego detectado',
  smoke_detection:    'Humo detectado',
  intrusion_detection:'Intrusión',
  line_crossing:      'Cruce de línea',
  weapon_detection:   'Arma detectada',
  vehicle_detection:  'Vehículo detectado',
  lpr_recognition:    'Placa reconocida',
  crowd_detection:    'Aglomeración',
  loitering_detection:'Merodeo',
};

function timeAgo(timestamp) {
  const diff = Date.now() / 1000 - timestamp;
  if (diff < 60)   return `hace ${Math.round(diff)}s`;
  if (diff < 3600) return `hace ${Math.round(diff / 60)}m`;
  return `hace ${Math.round(diff / 3600)}h`;
}

export default function AlertFeed({ maxItems = 30, cameras = [] }) {
  const { lastEvent } = useWS();
  const [events, setEvents] = useState([]);

  useEffect(() => {
    if (!lastEvent) return;
    setEvents(prev => [{ ...lastEvent, _id: Date.now() }, ...prev].slice(0, maxItems));
  }, [lastEvent]);

  const dismiss = (id) => setEvents(prev => prev.filter(e => e._id !== id));

  const getCameraName = (cid) =>
    cameras.find(c => c.id === cid)?.name || `Cámara ${cid}`;

  if (!events.length) {
    return (
      <div className="empty-state" style={{ padding: '32px 16px' }}>
        <Bell size={28} style={{ opacity: 0.2 }} />
        <div className="empty-title" style={{ fontSize: 13 }}>Sin alertas recientes</div>
        <div className="empty-desc" style={{ fontSize: 12 }}>
          Las alertas de IA aparecerán aquí en tiempo real
        </div>
      </div>
    );
  }

  return (
    <div className="alert-feed">
      {events.map(event => {
        const SevIcon  = SEVERITY_ICONS[event.severity]  || Info;
        const AnalIcon = ANALYTIC_ICONS[event.analytic_type] || Bell;
        const sevColor = SEVERITY_COLORS[event.severity] || 'var(--text-muted)';

        return (
          <div key={event._id} className={`alert-item severity-${event.severity}`}>
            {/* Analytic type icon */}
            <span className="alert-icon" style={{ color: sevColor }}>
              <AnalIcon size={18} />
            </span>

            <div className="alert-body">
              <div className="alert-title">
                {ANALYTIC_LABELS[event.analytic_type] || event.analytic_type}
              </div>
              <div className="alert-meta">
                {getCameraName(event.camera_id)}
                {event.confidence &&
                  ` · ${(event.confidence * 100).toFixed(0)}% confianza`}
                {event.description && ` · ${event.description}`}
              </div>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 4 }}>
              <SevIcon size={13} style={{ color: sevColor }} />
              <span className="alert-time">{timeAgo(event.timestamp)}</span>
              <button
                className="btn btn-ghost btn-icon"
                onClick={() => dismiss(event._id)}
                style={{ padding: '2px', minWidth: 'unset' }}
              >
                <X size={12} />
              </button>
            </div>
          </div>
        );
      })}
    </div>
  );
}

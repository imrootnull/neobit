import { useState, useEffect, useCallback } from 'react';
import { useWS } from '../context/WSContext';
import { apiGet } from '../api';
import type { AnalyticEvent } from '../api';
import { Bell, X, AlertTriangle, AlertOctagon, XCircle, Info } from 'lucide-react';
import { ANALYTIC_ICONS, SEVERITY_COLORS } from './Icons';

// ─── Types ────────────────────────────────────────────────────────────────────

interface Camera {
  id: number;
  name: string;
}

interface FeedEvent extends AnalyticEvent {
  /** client-side unique key to allow deduplication when loaded from API + WS */
  _key: string;
}

interface AlertFeedProps {
  maxItems?: number;
  cameras?: Camera[];
}

// ─── Constants ────────────────────────────────────────────────────────────────

const SEVERITY_ICONS: Record<string, typeof Info> = {
  critical: XCircle,
  high:     AlertTriangle,
  medium:   AlertOctagon,
  low:      Info,
};

const ANALYTIC_LABELS: Record<string, string> = {
  epp_detection:       'EPP Industrial',
  fall_detection:      'Caída detectada',
  behavior_detection:  'Comportamiento hostil',
  theft_detection:     'Robo detectado',
  person_detection:    'Persona detectada',
  fire_detection:      'Fuego detectado',
  smoke_detection:     'Humo detectado',
  intrusion_detection: 'Intrusión',
  line_crossing:       'Cruce de línea',
  weapon_detection:    'Arma detectada',
  vehicle_detection:   'Vehículo detectado',
  lpr_recognition:     'Placa reconocida',
  crowd_detection:     'Aglomeración',
  loitering_detection: 'Merodeo',
};

function timeAgo(timestamp: number): string {
  const diff = Date.now() / 1000 - timestamp;
  if (diff < 60)   return `hace ${Math.round(diff)}s`;
  if (diff < 3600) return `hace ${Math.round(diff / 60)}m`;
  return `hace ${Math.round(diff / 3600)}h`;
}

// ─── Component ────────────────────────────────────────────────────────────────

export default function AlertFeed({ maxItems = 30, cameras = [] }: AlertFeedProps) {
  const { lastEvent } = useWS();
  const [events, setEvents] = useState<FeedEvent[]>([]);
  const [seenIds, setSeenIds] = useState<Set<number>>(new Set());

  // Load recent events from the API on mount so they survive page reloads
  useEffect(() => {
    apiGet<AnalyticEvent[]>(`/api/events/?limit=${maxItems}`)
      .then(data => {
        const ids = new Set(data.map(e => e.id));
        const feed: FeedEvent[] = data.map(e => ({ ...e, _key: `api-${e.id}` }));
        setSeenIds(ids);
        setEvents(feed);
      })
      .catch(() => { /* non-fatal — WS events still work */ });
  }, [maxItems]);

  // Prepend new WS events, avoiding duplicates already loaded from API
  useEffect(() => {
    if (!lastEvent) return;
    const ev = lastEvent as AnalyticEvent;
    if (seenIds.has(ev.id)) return;
    setSeenIds(prev => new Set([...prev, ev.id]));
    setEvents(prev => [{ ...ev, _key: `ws-${ev.id}-${Date.now()}` }, ...prev].slice(0, maxItems));
  }, [lastEvent]); // eslint-disable-line react-hooks/exhaustive-deps

  const dismiss = useCallback((key: string) => {
    setEvents(prev => prev.filter(e => e._key !== key));
  }, []);

  const getCameraName = (cid: number): string =>
    cameras.find(c => c.id === cid)?.name ?? `Cámara ${cid}`;

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
        const SevIcon  = SEVERITY_ICONS[event.severity]      ?? Info;
        const AnalIcon = ANALYTIC_ICONS[event.analytic_type] ?? Bell;
        const sevColor = SEVERITY_COLORS[event.severity]     ?? 'var(--text-muted)';

        return (
          <div key={event._key} className={`alert-item severity-${event.severity}`}>
            <span className="alert-icon" style={{ color: sevColor }}>
              <AnalIcon size={18} />
            </span>

            <div className="alert-body">
              <div className="alert-title">
                {ANALYTIC_LABELS[event.analytic_type] ?? event.analytic_type}
              </div>
              <div className="alert-meta">
                {getCameraName(event.camera_id)}
                {event.confidence != null &&
                  ` · ${(event.confidence * 100).toFixed(0)}% confianza`}
                {event.description && ` · ${event.description}`}
              </div>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 4 }}>
              <SevIcon size={13} style={{ color: sevColor }} />
              <span className="alert-time">{timeAgo(event.timestamp)}</span>
              <button
                className="btn btn-ghost btn-icon"
                onClick={() => dismiss(event._key)}
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

import { useState, useEffect } from 'react';
import { apiGet, apiPost, API_BASE } from '../api';
import {
  Bell, CheckCheck, AlertTriangle, AlertOctagon,
  XCircle, Info, Filter, X, Camera, Film,
  Download, ChevronLeft, ChevronRight
} from 'lucide-react';
import { ANALYTIC_ICONS, SEVERITY_COLORS } from '../components/Icons';

const SEVERITY_ICONS = {
  critical: XCircle,
  high:     AlertTriangle,
  medium:   AlertOctagon,
  low:      Info,
};

const SEVERITY_BADGES = {
  critical: 'badge-red',
  high:     'badge-amber',
  medium:   'badge-blue',
  low:      'badge-gray',
};

const SEVERITY_LABELS = {
  critical: 'Crítico', high: 'Alto', medium: 'Medio', low: 'Bajo',
};

const ANALYTIC_LABELS = {
  epp_detection:       'EPP Industrial',
  fall_detection:      'Caída',
  behavior_detection:  'Comportamiento hostil',
  theft_detection:     'Robo',
  person_detection:    'Persona detectada',
  vehicle_detection:   'Vehículo detectado',
  fire_detection:      'Fuego',
  smoke_detection:     'Humo',
  intrusion_detection: 'Intrusión',
  line_crossing:       'Cruce de línea',
  weapon_detection:    'Arma detectada',
  crowd_detection:     'Aglomeración',
  lpr_recognition:     'Placa reconocida',
  loitering_detection: 'Merodeo',
  face_recognition:    'Reconocimiento facial',
  face_blacklist:      'Lista negra facial',
  face_detection:      'Detección facial',
  driver_fatigue:      'Fatiga al volante',
  forklift_safety:     'Seguridad montacargas',
  medical_emergency:   'Emergencia médica',
};

function timeStr(ts) {
  return new Date(ts * 1000).toLocaleString('es-MX', {
    month: 'short', day: 'numeric',
    hour: '2-digit', minute: '2-digit', second: '2-digit',
  });
}

export default function Events() {
  const [events, setEvents]       = useState([]);
  const [filter, setFilter]       = useState({ analytic_type: '', severity: '', acknowledged: '' });
  const [loading, setLoading]     = useState(true);
  const [selected, setSelected]   = useState(null);  // event detail modal

  const loadEvents = async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (filter.analytic_type) params.set('analytic_type', filter.analytic_type);
      if (filter.severity)      params.set('severity', filter.severity);
      if (filter.acknowledged !== '') params.set('acknowledged', filter.acknowledged);
      params.set('limit', 100);
      const data = await apiGet(`/api/events/?${params}`);
      setEvents(data);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { loadEvents(); }, [filter]);

  const ackAll = async () => {
    await apiPost('/api/events/acknowledge-all', {});
    loadEvents();
  };

  const openDetail = (ev) => setSelected(ev);
  const closeDetail = () => setSelected(null);

  // Navigate between events in detail view
  const currentIdx = selected ? events.findIndex(e => e.id === selected.id) : -1;
  const goPrev = () => currentIdx > 0 && setSelected(events[currentIdx - 1]);
  const goNext = () => currentIdx < events.length - 1 && setSelected(events[currentIdx + 1]);

  return (
    <>
      <div className="page-header">
        <div>
          <h1 className="page-title">Historial de Eventos</h1>
          <p className="page-subtitle">Registro completo de alertas generadas por analíticas IA</p>
        </div>
        <button className="btn btn-ghost" onClick={ackAll}>
          <CheckCheck size={14} /> Marcar todos leídos
        </button>
      </div>

      <div className="page-content">
        {/* Filters */}
        <div className="card" style={{
          padding: '12px 20px', marginBottom: 14,
          display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'center',
        }}>
          <Filter size={14} style={{ color: 'var(--text-muted)' }} />
          <select className="form-select" style={{ width: 'auto' }}
            value={filter.analytic_type}
            onChange={e => setFilter(p => ({ ...p, analytic_type: e.target.value }))}>
            <option value="">Todas las analíticas</option>
            {Object.entries(ANALYTIC_LABELS).map(([k, v]) => (
              <option key={k} value={k}>{v}</option>
            ))}
          </select>
          <select className="form-select" style={{ width: 'auto' }}
            value={filter.severity}
            onChange={e => setFilter(p => ({ ...p, severity: e.target.value }))}>
            <option value="">Todas las severidades</option>
            <option value="critical">Crítico</option>
            <option value="high">Alto</option>
            <option value="medium">Medio</option>
            <option value="low">Bajo</option>
          </select>
          <select className="form-select" style={{ width: 'auto' }}
            value={filter.acknowledged}
            onChange={e => setFilter(p => ({ ...p, acknowledged: e.target.value }))}>
            <option value="">Todos</option>
            <option value="false">Sin leer</option>
            <option value="true">Leídos</option>
          </select>
        </div>

        {loading ? (
          <div className="empty-state">
            <div style={{ width: 28, height: 28, borderRadius: '50%', border: '2px solid var(--text-muted)', borderTopColor: 'var(--accent-blue)', animation: 'spin 0.8s linear infinite' }} />
          </div>
        ) : events.length === 0 ? (
          <div className="empty-state card" style={{ padding: 48 }}>
            <Bell size={32} style={{ opacity: 0.15 }} />
            <div className="empty-title">Sin eventos</div>
            <div className="empty-desc">No hay eventos con los filtros seleccionados</div>
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {events.map(ev => {
              const SevIcon  = SEVERITY_ICONS[ev.severity]    || Info;
              const AnalIcon = ANALYTIC_ICONS[ev.analytic_type] || Bell;
              const sevColor = SEVERITY_COLORS[ev.severity]   || 'var(--text-muted)';
              const sevBadge = SEVERITY_BADGES[ev.severity]   || 'badge-gray';
              const hasMedia = ev.snapshot_path || ev.recording_path;

              return (
                <div
                  key={ev.id}
                  className={`alert-item severity-${ev.severity}`}
                  style={{
                    opacity: ev.acknowledged ? 0.55 : 1,
                    cursor: 'pointer',
                    transition: 'background 0.15s, transform 0.1s',
                  }}
                  onClick={() => openDetail(ev)}
                  onMouseEnter={e => e.currentTarget.style.transform = 'translateX(3px)'}
                  onMouseLeave={e => e.currentTarget.style.transform = ''}
                >
                  <span className="alert-icon" style={{ color: sevColor }}>
                    <AnalIcon size={18} />
                  </span>
                  <div className="alert-body">
                    <div className="alert-title" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                      {ANALYTIC_LABELS[ev.analytic_type] || ev.analytic_type}
                      {hasMedia && (
                        <span style={{ display: 'flex', gap: 4 }}>
                          {ev.snapshot_path && <Camera size={11} style={{ color: 'var(--accent-blue)', opacity: 0.8 }} />}
                          {ev.recording_path && <Film size={11} style={{ color: 'var(--accent-green)', opacity: 0.8 }} />}
                        </span>
                      )}
                    </div>
                    <div className="alert-meta">
                      Cámara {ev.camera_id}
                      {ev.confidence && ` · ${(ev.confidence * 100).toFixed(0)}% confianza`}
                      {ev.description && ` · ${ev.description}`}
                    </div>
                  </div>
                  <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 4 }}>
                    <span className={`badge ${sevBadge}`} style={{ fontSize: 10 }}>
                      <SevIcon size={10} /> {SEVERITY_LABELS[ev.severity] || ev.severity}
                    </span>
                    <span className="alert-time">{timeStr(ev.timestamp)}</span>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Event Detail Modal */}
      {selected && (
        <EventDetailModal
          event={selected}
          onClose={closeDetail}
          onPrev={currentIdx > 0 ? goPrev : null}
          onNext={currentIdx < events.length - 1 ? goNext : null}
        />
      )}

      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </>
  );
}

// ─── Event Detail Modal ───────────────────────────────────────────────────────

function EventDetailModal({ event: ev, onClose, onPrev, onNext }) {
  const [tab, setTab]             = useState(ev.snapshot_path ? 'snapshot' : 'clip');
  const [snapError, setSnapError] = useState(false);
  const [clipError, setClipError] = useState(false);

  // Reset state when event changes
  useEffect(() => {
    setTab(ev.snapshot_path ? 'snapshot' : 'clip');
    setSnapError(false);
    setClipError(false);
  }, [ev.id]);

  const SevIcon  = SEVERITY_ICONS[ev.severity]     || Info;
  const AnalIcon = ANALYTIC_ICONS[ev.analytic_type] || Bell;
  const sevColor = SEVERITY_COLORS[ev.severity]    || 'var(--text-muted)';
  const sevBadge = SEVERITY_BADGES[ev.severity]    || 'badge-gray';

  const snapUrl = `${API_BASE}/api/events/${ev.id}/snapshot`;
  const clipUrl = `${API_BASE}/api/events/${ev.id}/clip`;

  const hasSnap = !!ev.snapshot_path;
  const hasClip = !!ev.recording_path;

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div
        className="modal"
        style={{ maxWidth: 720, width: '95vw' }}
        onClick={e => e.stopPropagation()}
      >
        {/* Header */}
        <div className="modal-header">
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <div style={{
              width: 36, height: 36, borderRadius: 9,
              background: sevColor + '18',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              flexShrink: 0,
            }}>
              <AnalIcon size={18} style={{ color: sevColor }} />
            </div>
            <div>
              <div className="modal-title" style={{ fontSize: 15 }}>
                {ANALYTIC_LABELS[ev.analytic_type] || ev.analytic_type}
              </div>
              <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 2 }}>
                Cámara {ev.camera_id} · {timeStr(ev.timestamp)}
              </div>
            </div>
          </div>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            {onPrev && (
              <button className="btn btn-ghost btn-icon btn-sm" onClick={onPrev} title="Evento anterior">
                <ChevronLeft size={15} />
              </button>
            )}
            {onNext && (
              <button className="btn btn-ghost btn-icon btn-sm" onClick={onNext} title="Evento siguiente">
                <ChevronRight size={15} />
              </button>
            )}
            <button className="btn btn-ghost btn-icon" onClick={onClose}>
              <X size={16} />
            </button>
          </div>
        </div>

        {/* Body */}
        <div className="modal-body" style={{ padding: '16px 20px' }}>
          {/* Badges */}
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 14 }}>
            <span className={`badge ${sevBadge}`}>
              <SevIcon size={11} /> {SEVERITY_LABELS[ev.severity] || ev.severity}
            </span>
            {ev.confidence && (
              <span className="badge badge-gray">
                Confianza: {(ev.confidence * 100).toFixed(0)}%
              </span>
            )}
            {hasSnap && <span className="badge badge-blue"><Camera size={10} /> Captura</span>}
            {hasClip && <span className="badge badge-green"><Film size={10} /> Clip</span>}
          </div>

          {/* Description */}
          {ev.description && (
            <div style={{
              padding: '10px 14px', marginBottom: 14,
              background: 'rgba(255,255,255,0.03)',
              border: '1px solid var(--border)',
              borderRadius: 8, fontSize: 13,
            }}>
              {ev.description}
            </div>
          )}

          {/* Media tabs */}
          {(hasSnap || hasClip) ? (
            <>
              {/* Tab bar */}
              {hasSnap && hasClip && (
                <div style={{ display: 'flex', gap: 4, marginBottom: 10 }}>
                  <button
                    className={`btn btn-sm ${tab === 'snapshot' ? 'btn-primary' : 'btn-ghost'}`}
                    onClick={() => setTab('snapshot')}
                  >
                    <Camera size={12} /> Captura
                  </button>
                  <button
                    className={`btn btn-sm ${tab === 'clip' ? 'btn-primary' : 'btn-ghost'}`}
                    onClick={() => setTab('clip')}
                  >
                    <Film size={12} /> Clip de video
                  </button>
                </div>
              )}

              {/* Snapshot */}
              {(tab === 'snapshot' || (!hasClip && hasSnap)) && hasSnap && (
                <div style={{ position: 'relative' }}>
                  {snapError ? (
                    <div style={{
                      height: 240, display: 'flex', flexDirection: 'column',
                      alignItems: 'center', justifyContent: 'center',
                      background: 'rgba(255,255,255,0.03)',
                      borderRadius: 10, border: '1px solid var(--border)',
                      color: 'var(--text-muted)', fontSize: 13, gap: 8,
                    }}>
                      <Camera size={28} style={{ opacity: 0.2 }} />
                      Captura no disponible
                    </div>
                  ) : (
                    <img
                      src={snapUrl}
                      alt="Captura del evento"
                      onError={() => setSnapError(true)}
                      style={{
                        width: '100%', borderRadius: 10,
                        border: '1px solid var(--border)',
                        display: 'block', maxHeight: 380, objectFit: 'contain',
                        background: '#0a0a0f',
                      }}
                    />
                  )}
                  <a
                    href={snapUrl} download={`evento_${ev.id}_snap.jpg`}
                    style={{
                      position: 'absolute', top: 8, right: 8,
                      background: 'rgba(0,0,0,0.6)', backdropFilter: 'blur(4px)',
                      borderRadius: 6, padding: '4px 8px',
                      display: 'flex', gap: 4, alignItems: 'center',
                      fontSize: 11, color: 'white', textDecoration: 'none',
                      border: '1px solid rgba(255,255,255,0.12)',
                    }}
                  >
                    <Download size={11} /> Descargar
                  </a>
                </div>
              )}

              {/* Video clip */}
              {(tab === 'clip' || (!hasSnap && hasClip)) && hasClip && (
                <div style={{ position: 'relative' }}>
                  {clipError ? (
                    <div style={{
                      height: 240, display: 'flex', flexDirection: 'column',
                      alignItems: 'center', justifyContent: 'center',
                      background: 'rgba(255,255,255,0.03)',
                      borderRadius: 10, border: '1px solid var(--border)',
                      color: 'var(--text-muted)', fontSize: 13, gap: 8,
                    }}>
                      <Film size={28} style={{ opacity: 0.2 }} />
                      Clip no disponible
                    </div>
                  ) : (
                    <video
                      src={clipUrl}
                      controls
                      autoPlay
                      muted
                      onError={() => setClipError(true)}
                      style={{
                        width: '100%', borderRadius: 10,
                        border: '1px solid var(--border)',
                        background: '#0a0a0f', maxHeight: 380,
                      }}
                    />
                  )}
                  <a
                    href={clipUrl} download={`evento_${ev.id}_clip.mp4`}
                    style={{
                      position: 'absolute', top: 8, right: 8,
                      background: 'rgba(0,0,0,0.6)', backdropFilter: 'blur(4px)',
                      borderRadius: 6, padding: '4px 8px',
                      display: 'flex', gap: 4, alignItems: 'center',
                      fontSize: 11, color: 'white', textDecoration: 'none',
                      border: '1px solid rgba(255,255,255,0.12)',
                    }}
                  >
                    <Download size={11} /> Descargar
                  </a>
                </div>
              )}
            </>
          ) : (
            <div style={{
              height: 160, display: 'flex', flexDirection: 'column',
              alignItems: 'center', justifyContent: 'center',
              background: 'rgba(255,255,255,0.02)',
              borderRadius: 10, border: '1px dashed var(--border)',
              color: 'var(--text-muted)', fontSize: 13, gap: 8,
            }}>
              <Camera size={28} style={{ opacity: 0.15 }} />
              <span>Sin captura ni clip disponible</span>
              <span style={{ fontSize: 11, opacity: 0.6 }}>
                Los eventos futuros incluirán snapshot y clip de video
              </span>
            </div>
          )}
        </div>

        <div className="modal-footer">
          <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>
            ID de evento #{ev.id}
          </span>
          <button className="btn btn-ghost" onClick={onClose}>Cerrar</button>
        </div>
      </div>
    </div>
  );
}

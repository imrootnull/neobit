/**
 * Semantic Search — CLIP visual + analytic events + video playback modal
 */
import { useState, useEffect, useRef } from 'react';
import { apiGet, apiPost } from '../api';
import {
  Search, Loader, Clock, Camera, X, Play,
  Zap, Eye, AlertTriangle, SlidersHorizontal,
  ChevronDown, Languages, Film,
} from 'lucide-react';

interface SearchResult {
  chroma_id:    string;
  camera_id:    number;
  timestamp:    number;
  score:        number;
  clip_score:   number;
  frame_path:   string | null;
  detections:   string;
  ppe_tags:     string;
  events:       Array<{ type: string; timestamp: number; description: string }>;
  event_clip:   string | null;
  event_snap:   string | null;
}
interface EventResult {
  id: number; camera_id: number; timestamp: number;
  analytic_type: string; description: string;
  recording_path: string | null; snapshot_path: string | null;
  clip_available: boolean;
}

const EXAMPLES = [
  'persona con casco', 'persona sin chaleco', 'persona en el suelo',
  'dos personas', 'persona con camisa roja', 'vehículo blanco',
];
const EVENT_TYPES = [
  { value: '', label: 'Todos los eventos' },
  { value: 'epp_detection', label: 'Violación EPP' },
  { value: 'fall_detection', label: 'Caída detectada' },
  { value: 'person_detection', label: 'Persona detectada' },
  { value: 'face_detection', label: 'Rostro detectado' },
  { value: 'intrusion_detection', label: 'Intrusión' },
];
const ANALYTIC_COLOR: Record<string, string> = {
  epp_detection: '#f59e0b', fall_detection: '#ef4444',
  person_detection: '#0ea5e9', face_detection: '#a855f7', fire_detection: '#ef4444',
};
const ANALYTIC_LABEL: Record<string, string> = {
  epp_detection: 'EPP', fall_detection: 'Caída',
  person_detection: 'Persona', face_detection: 'Rostro', fire_detection: 'Fuego',
};

function fmt(unix: number) {
  return new Date(unix * 1000).toLocaleString('es-MX', {
    month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', second: '2-digit',
  });
}

// ── Video modal ─────────────────────────────────────────────────────────────
function VideoModal({ result, onClose }: { result: SearchResult; onClose: () => void }) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const [clipUrl, setClipUrl] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    if (result.event_clip) {
      setClipUrl(`/api/search/clip-stream?path=${encodeURIComponent(result.event_clip)}`);
      setLoading(false);
    } else {
      // Try to find clip via API
      apiGet(`/api/search/clip-at?camera_id=${result.camera_id}&timestamp=${result.timestamp}&window=120`)
        .then(data => {
          if (data.clip_available) {
            setClipUrl(`/api/search/clip-stream?path=${encodeURIComponent(data.clip_path)}`);
          } else {
            setError('No hay clip de video disponible para este momento.');
          }
        })
        .catch(() => setError('No se encontró un evento cercano con video.'))
        .finally(() => setLoading(false));
    }
  }, [result]);

  return (
    <div
      style={{
        position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.85)',
        zIndex: 9999, display: 'flex', alignItems: 'center', justifyContent: 'center',
        backdropFilter: 'blur(6px)',
      }}
      onClick={onClose}
    >
      <div
        style={{
          width: '90vw', maxWidth: 860, background: 'var(--bg-card)',
          borderRadius: 14, border: '1px solid var(--border)',
          overflow: 'hidden', boxShadow: '0 24px 60px rgba(0,0,0,0.6)',
        }}
        onClick={e => e.stopPropagation()}
      >
        {/* Header */}
        <div style={{
          padding: '12px 16px', borderBottom: '1px solid var(--border)',
          display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        }}>
          <div>
            <div style={{ fontWeight: 700, fontSize: 13 }}>
              <Film size={13} style={{ marginRight: 5, color: '#0ea5e9' }} />
              Cámara {result.camera_id} — {fmt(result.timestamp)}
            </div>
            {result.events[0] && (
              <div style={{ fontSize: 11, color: ANALYTIC_COLOR[result.events[0].type] ?? 'var(--text-muted)', marginTop: 2 }}>
                {result.events[0].description}
              </div>
            )}
          </div>
          <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-muted)' }}>
            <X size={18} />
          </button>
        </div>

        {/* Video */}
        <div style={{ background: '#000', position: 'relative', minHeight: 200 }}>
          {loading && (
            <div style={{ position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <Loader size={28} style={{ color: 'var(--text-muted)', animation: 'spin 1s linear infinite' }} />
            </div>
          )}
          {error && (
            <div style={{ padding: 40, textAlign: 'center', color: 'var(--text-muted)', fontSize: 13 }}>
              <AlertTriangle size={28} style={{ opacity: 0.4, marginBottom: 8 }} />
              <div>{error}</div>
              {result.frame_path && (
                <img src={`/api/search/frame/${encodeURIComponent(result.frame_path)}`}
                  alt="frame" style={{ marginTop: 12, maxWidth: '100%', borderRadius: 6 }} />
              )}
            </div>
          )}
          {clipUrl && (
            <video
              ref={videoRef}
              src={clipUrl}
              controls
              autoPlay
              style={{ width: '100%', display: 'block', maxHeight: '70vh' }}
              onError={() => { setError('Error al cargar el video.'); setClipUrl(null); }}
            />
          )}
        </div>
      </div>
    </div>
  );
}

// ── Result card ─────────────────────────────────────────────────────────────
function VisualCard({ result, onClick }: { result: SearchResult; onClick: () => void }) {
  const pct = Math.round(result.score * 100);
  const color = pct > 60 ? '#22c55e' : pct > 35 ? '#f59e0b' : 'var(--text-muted)';
  const hasClip = !!(result.event_clip);
  const [imgErr, setImgErr] = useState(false);

  return (
    <div
      onClick={onClick}
      style={{
        borderRadius: 10, overflow: 'hidden', cursor: 'pointer',
        border: `1px solid var(--border)`, background: 'var(--bg-card)',
        transition: 'transform 0.15s, box-shadow 0.15s',
      }}
      onMouseEnter={e => {
        (e.currentTarget as HTMLDivElement).style.transform = 'translateY(-2px)';
        (e.currentTarget as HTMLDivElement).style.boxShadow = '0 6px 20px rgba(0,0,0,0.35)';
      }}
      onMouseLeave={e => {
        (e.currentTarget as HTMLDivElement).style.transform = '';
        (e.currentTarget as HTMLDivElement).style.boxShadow = '';
      }}
    >
      <div style={{ position: 'relative', background: '#000' }}>
        {result.frame_path && !imgErr ? (
          <img
            src={`/api/search/frame/${encodeURIComponent(result.frame_path)}`}
            alt="frame"
            style={{ width: '100%', aspectRatio: '16/9', objectFit: 'cover', display: 'block' }}
            onError={() => setImgErr(true)}
          />
        ) : (
          <div style={{ width: '100%', aspectRatio: '16/9', display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'var(--bg-elevated)' }}>
            <Camera size={24} style={{ opacity: 0.2 }} />
          </div>
        )}

        {/* Play overlay */}
        <div style={{
          position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center',
          background: 'rgba(0,0,0,0.3)', opacity: 0, transition: 'opacity 0.15s',
        }}
          className="card-play-overlay"
        >
          <div style={{
            width: 44, height: 44, borderRadius: '50%',
            background: 'rgba(255,255,255,0.15)', border: '2px solid rgba(255,255,255,0.6)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}>
            <Play size={18} color="#fff" />
          </div>
        </div>

        {/* Clip badge */}
        {hasClip && (
          <div style={{ position: 'absolute', top: 5, left: 5, background: 'rgba(14,165,233,0.85)', borderRadius: 4, padding: '1px 5px' }}>
            <Film size={9} color="#fff" />
          </div>
        )}

        {/* Event badges */}
        {result.events.length > 0 && (
          <div style={{ position: 'absolute', top: 5, right: 5, display: 'flex', gap: 3 }}>
            {result.events.slice(0, 2).map((ev, i) => (
              <span key={i} style={{
                background: (ANALYTIC_COLOR[ev.type] ?? '#666') + 'cc',
                color: '#fff', fontSize: 9, fontWeight: 700, padding: '2px 5px', borderRadius: 4,
              }}>
                {ANALYTIC_LABEL[ev.type] ?? ev.type}
              </span>
            ))}
          </div>
        )}
      </div>

      <div style={{ padding: '8px 10px' }}>
        {/* Score bar */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <div style={{ flex: 1, height: 3, borderRadius: 2, background: 'var(--border)', overflow: 'hidden' }}>
            <div style={{ width: `${pct}%`, height: '100%', background: color, transition: 'width 0.3s' }} />
          </div>
          <span style={{ fontSize: 11, fontWeight: 700, color, minWidth: 30 }}>{pct}%</span>
        </div>
        <div style={{ display: 'flex', gap: 5, marginTop: 5, fontSize: 10, color: 'var(--text-muted)' }}>
          <Camera size={9} /><span>Cam {result.camera_id}</span>
          <span style={{ opacity: 0.4 }}>·</span>
          <Clock size={9} /><span>{fmt(result.timestamp)}</span>
        </div>
      </div>
    </div>
  );
}

// ── Event card ──────────────────────────────────────────────────────────────
function EventCard({ ev, onClick }: { ev: EventResult; onClick: () => void }) {
  const color = ANALYTIC_COLOR[ev.analytic_type] ?? 'var(--text-muted)';
  return (
    <div
      onClick={onClick}
      style={{
        borderRadius: 8, border: `1px solid ${color}44`,
        background: color + '11', padding: '10px 14px',
        display: 'flex', gap: 10, alignItems: 'flex-start',
        cursor: ev.clip_available ? 'pointer' : 'default',
        transition: 'background 0.15s',
      }}
    >
      <AlertTriangle size={16} style={{ color, flexShrink: 0, marginTop: 1 }} />
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontWeight: 700, fontSize: 12, color }}>
          {ANALYTIC_LABEL[ev.analytic_type] ?? ev.analytic_type} — Cámara {ev.camera_id}
        </div>
        <div style={{ fontSize: 11, color: 'var(--text-secondary)', marginTop: 2 }}>{ev.description}</div>
        <div style={{ fontSize: 10, color: 'var(--text-muted)', marginTop: 4 }}>{fmt(ev.timestamp)}</div>
      </div>
      {ev.clip_available && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 10, color: '#0ea5e9', flexShrink: 0 }}>
          <Film size={11} /> Ver clip
        </div>
      )}
    </div>
  );
}

// ── Main ────────────────────────────────────────────────────────────────────
export default function SemanticSearch() {
  const [tab,       setTab]       = useState<'visual' | 'events'>('visual');
  const [query,     setQuery]     = useState('');
  const [results,   setResults]   = useState<SearchResult[]>([]);
  const [events,    setEvents]    = useState<EventResult[]>([]);
  const [loading,   setLoading]   = useState(false);
  const [searched,  setSearched]  = useState(false);
  const [topK,      setTopK]      = useState(20);
  const [cameraId,  setCameraId]  = useState('');
  const [dateFrom,  setDateFrom]  = useState('');
  const [dateTo,    setDateTo]    = useState('');
  const [translated,setTranslated]= useState<string | null>(null);
  const [stats,     setStats]     = useState<any>(null);
  const [showFilters, setShowFilters] = useState(false);
  const [eventType, setEventType] = useState('');
  const [modal,     setModal]     = useState<SearchResult | null>(null);
  const [eventModal,setEventModal]= useState<EventResult | null>(null);

  useEffect(() => {
    apiGet('/api/search/stats').then(setStats).catch(() => {});
  }, []);

  const tsFrom = (d: string) => d ? new Date(d).getTime() / 1000 : undefined;

  const doVisualSearch = async (q = query) => {
    if (!q.trim()) return;
    setLoading(true); setSearched(true); setTranslated(null);
    try {
      const data = await apiPost('/api/search/semantic', {
        query: q, top_k: topK,
        camera_id: cameraId ? Number(cameraId) : undefined,
        timestamp_from: tsFrom(dateFrom), timestamp_to: tsFrom(dateTo),
        min_score: 0.0, use_events: true,
      });
      setResults(data.results ?? []);
      setTranslated(data.translated ?? null);
    } catch { setResults([]); }
    finally { setLoading(false); }
  };

  const doEventSearch = async () => {
    setLoading(true); setSearched(true);
    try {
      const p = new URLSearchParams();
      if (eventType) p.set('analytic_type', eventType);
      if (cameraId)  p.set('camera_id', cameraId);
      if (dateFrom)  p.set('timestamp_from', String(tsFrom(dateFrom)));
      if (dateTo)    p.set('timestamp_to',   String(tsFrom(dateTo)));
      p.set('limit', String(topK));
      const data = await apiGet(`/api/search/events?${p}`);
      setEvents(data.results ?? []);
    } catch { setEvents([]); }
    finally { setLoading(false); }
  };

  // Build synthetic SearchResult from EventResult for modal
  const openEventModal = (ev: EventResult) => {
    const sr: SearchResult = {
      chroma_id: '', camera_id: ev.camera_id, timestamp: ev.timestamp,
      score: 1, clip_score: 1, frame_path: ev.snapshot_path,
      detections: '', ppe_tags: '',
      events: [{ type: ev.analytic_type, timestamp: ev.timestamp, description: ev.description }],
      event_clip: ev.recording_path, event_snap: ev.snapshot_path,
    };
    setModal(sr);
  };

  return (
    <>
      <div className="page-header">
        <div>
          <h1 className="page-title">Búsqueda Semántica</h1>
          <p className="page-subtitle">
            Búsqueda visual por descripción o por eventos analíticos
            {stats && <span style={{ color: 'var(--text-muted)' }}> — {stats.indexed_frames?.toLocaleString()} frames indexados</span>}
          </p>
        </div>
      </div>

      <div className="page-content">

        {/* Tabs */}
        <div style={{ display: 'flex', gap: 4, marginBottom: 12 }}>
          {[
            { key: 'visual', icon: <Eye size={13} />, label: 'Búsqueda Visual (CLIP)' },
            { key: 'events', icon: <Zap size={13} />, label: 'Eventos Analíticos' },
          ].map(t => (
            <button key={t.key} onClick={() => { setTab(t.key as any); setSearched(false); }}
              style={{
                display: 'flex', alignItems: 'center', gap: 5,
                padding: '6px 16px', borderRadius: 7, fontSize: 12, fontWeight: 600,
                border: `1px solid ${tab === t.key ? '#0ea5e9' : 'var(--border)'}`,
                background: tab === t.key ? '#0ea5e922' : 'transparent',
                color: tab === t.key ? '#0ea5e9' : 'var(--text-muted)',
                cursor: 'pointer', transition: 'all 0.15s',
              }}>
              {t.icon} {t.label}
            </button>
          ))}
        </div>

        {/* Search box */}
        <div className="card" style={{ padding: '16px 20px', marginBottom: 12 }}>
          {tab === 'visual' ? (
            <>
              <div className="search-container">
                <Search size={16} className="search-icon" />
                <input id="semantic-search-input" className="search-input"
                  placeholder='Ej: "persona con casco amarillo"'
                  value={query} onChange={e => setQuery(e.target.value)}
                  onKeyDown={e => e.key === 'Enter' && doVisualSearch()} />
                <button id="semantic-search-btn" className="btn btn-primary search-btn"
                  onClick={() => doVisualSearch()} disabled={loading || !query.trim()}>
                  {loading ? <><Loader size={13} style={{ animation: 'spin 1s linear infinite' }} /> Buscando...</> : <><Search size={13} /> Buscar</>}
                </button>
              </div>
              {translated && (
                <div style={{ marginTop: 6, fontSize: 11, color: 'var(--text-muted)', display: 'flex', gap: 4 }}>
                  <Languages size={11} />
                  Buscando en inglés: <em style={{ color: 'var(--text-secondary)' }}>"{translated}"</em>
                </div>
              )}
              <div style={{ marginTop: 8, display: 'flex', flexWrap: 'wrap', gap: 5 }}>
                {EXAMPLES.map(q => (
                  <button key={q} className="btn btn-ghost btn-sm" style={{ fontSize: 11 }}
                    onClick={() => { setQuery(q); doVisualSearch(q); }}>{q}</button>
                ))}
              </div>
            </>
          ) : (
            <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'flex-end' }}>
              <div style={{ flex: 1, minWidth: 180 }}>
                <label style={{ fontSize: 11, color: 'var(--text-muted)', display: 'block', marginBottom: 4 }}>Tipo de evento</label>
                <select className="form-input" style={{ fontSize: 12 }} value={eventType} onChange={e => setEventType(e.target.value)}>
                  {EVENT_TYPES.map(t => <option key={t.value} value={t.value}>{t.label}</option>)}
                </select>
              </div>
              <button className="btn btn-primary" onClick={doEventSearch} disabled={loading} style={{ alignSelf: 'flex-end' }}>
                {loading ? <><Loader size={13} style={{ animation: 'spin 1s linear infinite' }} /> Buscando...</> : <><Zap size={13} /> Buscar</>}
              </button>
            </div>
          )}

          {/* Filters toggle */}
          <div style={{ marginTop: 10, borderTop: '1px solid var(--border)', paddingTop: 8 }}>
            <button onClick={() => setShowFilters(f => !f)}
              style={{ display: 'flex', alignItems: 'center', gap: 5, fontSize: 11, color: 'var(--text-muted)', background: 'none', border: 'none', cursor: 'pointer', padding: 0 }}>
              <SlidersHorizontal size={12} /> Filtros
              <ChevronDown size={11} style={{ transform: showFilters ? 'rotate(180deg)' : '', transition: 'transform 0.2s' }} />
            </button>
            {showFilters && (
              <div style={{ marginTop: 8, display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'flex-end' }}>
                <div>
                  <label style={{ fontSize: 11, color: 'var(--text-muted)', display: 'block', marginBottom: 4 }}>Cámara</label>
                  <input className="form-input" style={{ fontSize: 12, width: 80 }} placeholder="ID" value={cameraId} onChange={e => setCameraId(e.target.value)} />
                </div>
                <div>
                  <label style={{ fontSize: 11, color: 'var(--text-muted)', display: 'block', marginBottom: 4 }}>Desde</label>
                  <input type="datetime-local" className="form-input" style={{ fontSize: 12 }} value={dateFrom} onChange={e => setDateFrom(e.target.value)} />
                </div>
                <div>
                  <label style={{ fontSize: 11, color: 'var(--text-muted)', display: 'block', marginBottom: 4 }}>Hasta</label>
                  <input type="datetime-local" className="form-input" style={{ fontSize: 12 }} value={dateTo} onChange={e => setDateTo(e.target.value)} />
                </div>
                <div>
                  <label style={{ fontSize: 11, color: 'var(--text-muted)', display: 'block', marginBottom: 4 }}>Resultados: {topK}</label>
                  <input type="range" min="5" max="50" step="5" value={topK} onChange={e => setTopK(Number(e.target.value))} style={{ width: 100 }} />
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Loading */}
        {loading && (
          <div className="empty-state">
            <Loader size={32} style={{ opacity: 0.4, animation: 'spin 1s linear infinite' }} />
            <div className="empty-title">{tab === 'visual' ? 'Comparando con el índice CLIP...' : 'Buscando eventos...'}</div>
          </div>
        )}

        {/* No results */}
        {!loading && searched && (tab === 'visual' ? results : events).length === 0 && (
          <div className="empty-state">
            <Search size={32} style={{ opacity: 0.2 }} />
            <div className="empty-title">Sin resultados</div>
            <div className="empty-desc">{tab === 'visual' ? 'Intenta con términos más generales.' : 'No hay eventos en el rango seleccionado.'}</div>
          </div>
        )}

        {/* Visual results grid */}
        {!loading && tab === 'visual' && results.length > 0 && (
          <>
            <div style={{ marginBottom: 10, fontSize: 13, color: 'var(--text-muted)' }}>
              <strong style={{ color: 'var(--text-primary)' }}>{results.length}</strong> resultados — click para ver video
            </div>
            <div className="search-results">
              {results.map((r, i) => <VisualCard key={i} result={r} onClick={() => setModal(r)} />)}
            </div>
          </>
        )}

        {/* Event results */}
        {!loading && tab === 'events' && events.length > 0 && (
          <>
            <div style={{ marginBottom: 10, fontSize: 13, color: 'var(--text-muted)' }}>
              <strong style={{ color: 'var(--text-primary)' }}>{events.length}</strong> eventos — click para ver clip
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {events.map((ev, i) => <EventCard key={i} ev={ev} onClick={() => ev.clip_available && openEventModal(ev)} />)}
            </div>
          </>
        )}

        {!searched && (
          <div className="empty-state" style={{ marginTop: 32 }}>
            <Search size={48} style={{ opacity: 0.1 }} />
            <div className="empty-title">Búsqueda semántica de video</div>
            <div className="empty-desc">
              {tab === 'visual' ? 'Describe lo que buscas. Haz click en un resultado para ver el clip.' : 'Filtra por tipo de evento y rango de fechas.'}
            </div>
          </div>
        )}
      </div>

      {/* Video modal */}
      {modal && <VideoModal result={modal} onClose={() => setModal(null)} />}

      <style>{`
        @keyframes spin { to { transform: rotate(360deg); } }
        .card-play-overlay { opacity: 0 !important; }
        div:hover > .card-play-overlay { opacity: 1 !important; }
      `}</style>
    </>
  );
}

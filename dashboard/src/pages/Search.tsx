/**
 * Semantic Search — CLIP visual search + event-based search
 *
 * Features:
 * - Natural language search (auto-translated ES→EN for CLIP)
 * - Date/time range filter
 * - Camera filter
 * - Score threshold slider
 * - Tab: "Visual" (CLIP) vs "Eventos" (analytic events)
 * - Shows translated query for transparency
 * - Event fusion indicator on results
 */
import { useState, useEffect } from 'react';
import { apiGet, apiPost } from '../api';
import {
  Search, Loader, Clock, Camera, Calendar,
  Filter, Zap, Eye, AlertTriangle, ChevronDown,
  Languages, SlidersHorizontal,
} from 'lucide-react';

// ── Types ─────────────────────────────────────────────────────────────────────
interface SearchResult {
  chroma_id:  string;
  camera_id:  number;
  timestamp:  number;
  score:      number;
  clip_score: number;
  frame_path: string | null;
  events:     AnalyticEvent[];
}
interface AnalyticEvent {
  type:        string;
  timestamp:   number;
  description: string;
}
interface EventResult {
  id:            number;
  camera_id:     number;
  timestamp:     number;
  analytic_type: string;
  description:   string;
}
interface Camera { id: number; name: string; }

// ── Constants ─────────────────────────────────────────────────────────────────
const EXAMPLES = [
  'persona con casco',
  'persona sin chaleco',
  'persona en el suelo',
  'dos personas juntas',
  'persona con camisa roja',
  'vehículo blanco',
];

const EVENT_TYPES = [
  { value: '',                    label: 'Todos los eventos' },
  { value: 'epp_detection',       label: 'Violación EPP' },
  { value: 'fall_detection',      label: 'Caída detectada' },
  { value: 'person_detection',    label: 'Persona detectada' },
  { value: 'face_detection',      label: 'Rostro detectado' },
  { value: 'intrusion_detection', label: 'Intrusión' },
];

const ANALYTIC_LABEL: Record<string, string> = {
  epp_detection:       'EPP',
  fall_detection:      'Caída',
  person_detection:    'Persona',
  face_detection:      'Rostro',
  intrusion_detection: 'Intrusión',
  fire_detection:      'Fuego',
};
const ANALYTIC_COLOR: Record<string, string> = {
  epp_detection:    '#f59e0b',
  fall_detection:   '#ef4444',
  person_detection: '#0ea5e9',
  face_detection:   '#a855f7',
  fire_detection:   '#ef4444',
};

function formatTs(unix: number) {
  return new Date(unix * 1000).toLocaleString('es-MX', {
    month: 'short', day: 'numeric',
    hour: '2-digit', minute: '2-digit', second: '2-digit',
  });
}

// ── Score bar ─────────────────────────────────────────────────────────────────
function ScoreBar({ score, clipScore }: { score: number; clipScore: number }) {
  const pct   = Math.round(score * 100);
  const boosted = score > clipScore + 0.01;
  const color = pct > 35 ? '#22c55e' : pct > 25 ? '#f59e0b' : 'var(--text-muted)';
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
      <div style={{
        flex: 1, height: 4, borderRadius: 2,
        background: 'var(--border)',
        overflow: 'hidden',
      }}>
        <div style={{
          width: `${Math.min(pct * 2.5, 100)}%`,
          height: '100%', background: color,
          transition: 'width 0.3s',
        }} />
      </div>
      <span style={{ fontSize: 11, fontWeight: 700, color, minWidth: 32 }}>
        {pct}%
      </span>
      {boosted && (
        <span title="Score aumentado por evento analítico cercano" style={{
          fontSize: 9, background: '#f59e0b22', color: '#f59e0b',
          border: '1px solid #f59e0b44', borderRadius: 4, padding: '1px 4px',
        }}>
          +evento
        </span>
      )}
    </div>
  );
}

// ── Visual result card ────────────────────────────────────────────────────────
function VisualCard({ result, query }: { result: SearchResult; query: string }) {
  const [imgErr, setImgErr] = useState(false);

  return (
    <div style={{
      borderRadius: 10, overflow: 'hidden',
      border: '1px solid var(--border)',
      background: 'var(--bg-card)',
      transition: 'transform 0.15s, box-shadow 0.15s',
    }}
      onMouseEnter={e => {
        (e.currentTarget as HTMLDivElement).style.transform = 'translateY(-2px)';
        (e.currentTarget as HTMLDivElement).style.boxShadow = '0 6px 20px rgba(0,0,0,0.3)';
      }}
      onMouseLeave={e => {
        (e.currentTarget as HTMLDivElement).style.transform = '';
        (e.currentTarget as HTMLDivElement).style.boxShadow = '';
      }}
    >
      {/* Image */}
      <div style={{ position: 'relative', background: '#000' }}>
        {result.frame_path && !imgErr ? (
          <img
            src={`/api/search/frame/${encodeURIComponent(result.frame_path)}`}
            alt="frame"
            style={{ width: '100%', aspectRatio: '16/9', objectFit: 'cover', display: 'block' }}
            onError={() => setImgErr(true)}
          />
        ) : (
          <div style={{
            width: '100%', aspectRatio: '16/9',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            background: 'var(--bg-elevated)',
          }}>
            <Camera size={24} style={{ opacity: 0.2 }} />
          </div>
        )}
        {/* Event badges */}
        {result.events?.length > 0 && (
          <div style={{
            position: 'absolute', top: 6, left: 6,
            display: 'flex', gap: 3, flexWrap: 'wrap',
          }}>
            {result.events.map((ev, i) => (
              <span key={i} style={{
                background: ANALYTIC_COLOR[ev.type] + 'cc' ?? 'rgba(0,0,0,0.7)',
                color: '#fff', fontSize: 9, fontWeight: 700,
                padding: '2px 5px', borderRadius: 4,
              }}>
                {ANALYTIC_LABEL[ev.type] ?? ev.type}
              </span>
            ))}
          </div>
        )}
      </div>

      {/* Meta */}
      <div style={{ padding: '8px 10px' }}>
        <ScoreBar score={result.score} clipScore={result.clip_score ?? result.score} />
        <div style={{ display: 'flex', alignItems: 'center', gap: 5, marginTop: 6, fontSize: 11, color: 'var(--text-muted)' }}>
          <Camera size={10} />
          <span>Cámara {result.camera_id}</span>
          <span style={{ opacity: 0.4 }}>·</span>
          <Clock size={10} />
          <span>{formatTs(result.timestamp)}</span>
        </div>
      </div>
    </div>
  );
}

// ── Event result card ─────────────────────────────────────────────────────────
function EventCard({ ev }: { ev: EventResult }) {
  const color = ANALYTIC_COLOR[ev.analytic_type] ?? 'var(--text-muted)';
  const label = ANALYTIC_LABEL[ev.analytic_type] ?? ev.analytic_type;
  return (
    <div style={{
      borderRadius: 8, border: `1px solid ${color}44`,
      background: color + '11', padding: '10px 14px',
      display: 'flex', gap: 12, alignItems: 'flex-start',
    }}>
      <AlertTriangle size={16} style={{ color, flexShrink: 0, marginTop: 1 }} />
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontWeight: 700, fontSize: 12, color }}>
          {label} — Cámara {ev.camera_id}
        </div>
        <div style={{ fontSize: 11, color: 'var(--text-secondary)', marginTop: 2 }}>
          {ev.description}
        </div>
        <div style={{ fontSize: 10, color: 'var(--text-muted)', marginTop: 4 }}>
          {formatTs(ev.timestamp)}
        </div>
      </div>
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────
export default function SemanticSearch() {
  const [tab,       setTab]      = useState<'visual' | 'events'>('visual');
  const [query,     setQuery]    = useState('');
  const [results,   setResults]  = useState<SearchResult[]>([]);
  const [events,    setEvents]   = useState<EventResult[]>([]);
  const [loading,   setLoading]  = useState(false);
  const [searched,  setSearched] = useState(false);
  const [topK,      setTopK]     = useState(20);
  const [minScore,  setMinScore] = useState(0.15);
  const [cameraId,  setCameraId] = useState<number | null>(null);
  const [cameras,   setCameras]  = useState<Camera[]>([]);
  const [dateFrom,  setDateFrom] = useState('');
  const [dateTo,    setDateTo]   = useState('');
  const [translated,setTranslated] = useState<string | null>(null);
  const [stats,     setStats]    = useState<{ indexed_frames: number; ready: boolean } | null>(null);
  const [showFilters, setShowFilters] = useState(false);
  const [eventType, setEventType] = useState('');

  useEffect(() => {
    apiGet('/api/cameras/').then(r => setCameras(r.cameras ?? [])).catch(() => {});
    apiGet('/api/search/stats').then(setStats).catch(() => {});
  }, []);

  const tsFromDate = (d: string) => d ? new Date(d).getTime() / 1000 : undefined;

  const doVisualSearch = async (q = query) => {
    if (!q.trim()) return;
    setLoading(true); setSearched(true); setTranslated(null);
    try {
      const data = await apiPost('/api/search/semantic', {
        query:          q,
        top_k:          topK,
        camera_id:      cameraId ?? undefined,
        timestamp_from: tsFromDate(dateFrom),
        timestamp_to:   tsFromDate(dateTo),
        min_score:      minScore,
        use_events:     true,
      });
      setResults(data.results ?? []);
      setTranslated(data.translated ?? null);
    } catch { setResults([]); }
    finally { setLoading(false); }
  };

  const doEventSearch = async () => {
    setLoading(true); setSearched(true);
    try {
      const params = new URLSearchParams();
      if (eventType)  params.set('analytic_type', eventType);
      if (cameraId)   params.set('camera_id', String(cameraId));
      if (dateFrom)   params.set('timestamp_from', String(tsFromDate(dateFrom)));
      if (dateTo)     params.set('timestamp_to',   String(tsFromDate(dateTo)));
      params.set('limit', String(topK));
      const data = await apiGet(`/api/search/events?${params}`);
      setEvents(data.results ?? []);
    } catch { setEvents([]); }
    finally { setLoading(false); }
  };

  const doSearch = () => tab === 'visual' ? doVisualSearch() : doEventSearch();
  const currentCount = tab === 'visual' ? results.length : events.length;

  return (
    <>
      <div className="page-header">
        <div>
          <h1 className="page-title">Búsqueda Semántica</h1>
          <p className="page-subtitle">
            Busca en el historial de video por descripción visual o por eventos analíticos
            {stats && <span style={{ color: 'var(--text-muted)' }}> — {stats.indexed_frames.toLocaleString()} frames indexados</span>}
          </p>
        </div>
      </div>

      <div className="page-content">

        {/* ── Mode tabs ── */}
        <div style={{ display: 'flex', gap: 4, marginBottom: 12 }}>
          {[
            { key: 'visual', icon: <Eye size={13} />, label: 'Búsqueda Visual (CLIP)' },
            { key: 'events', icon: <Zap size={13} />, label: 'Eventos Analíticos' },
          ].map(t => (
            <button key={t.key}
              onClick={() => { setTab(t.key as any); setSearched(false); }}
              style={{
                display: 'flex', alignItems: 'center', gap: 5,
                padding: '6px 16px', borderRadius: 7, fontSize: 12, fontWeight: 600,
                border: `1px solid ${tab === t.key ? '#0ea5e9' : 'var(--border)'}`,
                background: tab === t.key ? '#0ea5e922' : 'transparent',
                color: tab === t.key ? '#0ea5e9' : 'var(--text-muted)',
                cursor: 'pointer', transition: 'all 0.15s',
              }}
            >
              {t.icon} {t.label}
            </button>
          ))}
        </div>

        {/* ── Search box ── */}
        <div className="card" style={{ padding: '16px 20px', marginBottom: 12 }}>
          {tab === 'visual' ? (
            <>
              <div className="search-container">
                <Search size={16} className="search-icon" />
                <input
                  id="semantic-search-input"
                  className="search-input"
                  placeholder='Ej: "persona con casco amarillo" o "person wearing helmet"'
                  value={query}
                  onChange={e => setQuery(e.target.value)}
                  onKeyDown={e => e.key === 'Enter' && doVisualSearch()}
                />
                <button id="semantic-search-btn" className="btn btn-primary search-btn"
                  onClick={() => doVisualSearch()} disabled={loading || !query.trim()}>
                  {loading
                    ? <><Loader size={13} style={{ animation: 'spin 1s linear infinite' }} /> Buscando...</>
                    : <><Search size={13} /> Buscar</>}
                </button>
              </div>
              {/* Translation badge */}
              {translated && (
                <div style={{ marginTop: 8, display: 'flex', alignItems: 'center', gap: 5, fontSize: 11, color: 'var(--text-muted)' }}>
                  <Languages size={12} />
                  <span>Buscando en inglés: <em style={{ color: 'var(--text-secondary)' }}>"{translated}"</em></span>
                </div>
              )}
              {/* Examples */}
              <div style={{ marginTop: 10, display: 'flex', flexWrap: 'wrap', gap: 5 }}>
                {EXAMPLES.map(q => (
                  <button key={q} className="btn btn-ghost btn-sm"
                    style={{ fontSize: 11 }}
                    onClick={() => { setQuery(q); doVisualSearch(q); }}>
                    {q}
                  </button>
                ))}
              </div>
            </>
          ) : (
            /* Event search controls */
            <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'flex-end' }}>
              <div style={{ flex: 1, minWidth: 180 }}>
                <label style={{ fontSize: 11, color: 'var(--text-muted)', display: 'block', marginBottom: 4 }}>Tipo de evento</label>
                <select className="form-input" style={{ fontSize: 12 }}
                  value={eventType} onChange={e => setEventType(e.target.value)}>
                  {EVENT_TYPES.map(t => <option key={t.value} value={t.value}>{t.label}</option>)}
                </select>
              </div>
              <button id="event-search-btn" className="btn btn-primary"
                onClick={doEventSearch} disabled={loading}
                style={{ alignSelf: 'flex-end' }}>
                {loading ? <><Loader size={13} style={{ animation: 'spin 1s linear infinite' }} /> Buscando...</> : <><Zap size={13} /> Buscar eventos</>}
              </button>
            </div>
          )}

          {/* ── Filter panel toggle ── */}
          <div style={{ marginTop: 12, borderTop: '1px solid var(--border)', paddingTop: 10 }}>
            <button
              onClick={() => setShowFilters(f => !f)}
              style={{
                display: 'flex', alignItems: 'center', gap: 5,
                fontSize: 11, color: 'var(--text-muted)', background: 'none',
                border: 'none', cursor: 'pointer', padding: 0,
              }}
            >
              <SlidersHorizontal size={12} />
              Filtros avanzados
              <ChevronDown size={11} style={{ transform: showFilters ? 'rotate(180deg)' : '', transition: 'transform 0.2s' }} />
            </button>

            {showFilters && (
              <div style={{ marginTop: 10, display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'flex-end' }}>
                {/* Camera filter */}
                <div>
                  <label style={{ fontSize: 11, color: 'var(--text-muted)', display: 'block', marginBottom: 4 }}>
                    <Camera size={10} style={{ marginRight: 3 }} />Cámara
                  </label>
                  <select className="form-input" style={{ fontSize: 12, minWidth: 120 }}
                    value={cameraId ?? ''} onChange={e => setCameraId(e.target.value ? Number(e.target.value) : null)}>
                    <option value="">Todas</option>
                    {cameras.map(c => <option key={c.id} value={c.id}>Cam {c.id} — {c.name}</option>)}
                  </select>
                </div>
                {/* Date from */}
                <div>
                  <label style={{ fontSize: 11, color: 'var(--text-muted)', display: 'block', marginBottom: 4 }}>
                    <Calendar size={10} style={{ marginRight: 3 }} />Desde
                  </label>
                  <input type="datetime-local" className="form-input" style={{ fontSize: 12 }}
                    value={dateFrom} onChange={e => setDateFrom(e.target.value)} />
                </div>
                {/* Date to */}
                <div>
                  <label style={{ fontSize: 11, color: 'var(--text-muted)', display: 'block', marginBottom: 4 }}>
                    <Calendar size={10} style={{ marginRight: 3 }} />Hasta
                  </label>
                  <input type="datetime-local" className="form-input" style={{ fontSize: 12 }}
                    value={dateTo} onChange={e => setDateTo(e.target.value)} />
                </div>
                {/* Score threshold (visual only) */}
                {tab === 'visual' && (
                  <div>
                    <label style={{ fontSize: 11, color: 'var(--text-muted)', display: 'block', marginBottom: 4 }}>
                      Score mínimo: {Math.round(minScore * 100)}%
                    </label>
                    <input type="range" min="0" max="50" step="1"
                      value={Math.round(minScore * 100)}
                      onChange={e => setMinScore(Number(e.target.value) / 100)}
                      style={{ width: 120 }}
                    />
                  </div>
                )}
                {/* Top K */}
                <div>
                  <label style={{ fontSize: 11, color: 'var(--text-muted)', display: 'block', marginBottom: 4 }}>
                    Resultados: {topK}
                  </label>
                  <input type="range" min="5" max="50" step="5"
                    value={topK} onChange={e => setTopK(Number(e.target.value))}
                    style={{ width: 100 }}
                  />
                </div>
              </div>
            )}
          </div>
        </div>

        {/* ── Loading ── */}
        {loading && (
          <div className="empty-state">
            <Loader size={32} style={{ opacity: 0.4, animation: 'spin 1s linear infinite' }} />
            <div className="empty-title">
              {tab === 'visual' ? 'Comparando con el índice CLIP...' : 'Buscando eventos...'}
            </div>
          </div>
        )}

        {/* ── No results ── */}
        {!loading && searched && currentCount === 0 && (
          <div className="empty-state">
            <Search size={32} style={{ opacity: 0.2 }} />
            <div className="empty-title">Sin resultados</div>
            <div className="empty-desc">
              {tab === 'visual'
                ? 'Intenta con términos más generales o reduce el score mínimo.'
                : 'No hay eventos en el rango seleccionado.'}
            </div>
          </div>
        )}

        {/* ── Visual results ── */}
        {!loading && tab === 'visual' && results.length > 0 && (
          <>
            <div style={{ marginBottom: 10, fontSize: 13, color: 'var(--text-muted)' }}>
              <strong style={{ color: 'var(--text-primary)' }}>{results.length}</strong>
              {' '}resultados para "{query}"
            </div>
            <div className="search-results">
              {results.map((r, i) => <VisualCard key={i} result={r} query={query} />)}
            </div>
          </>
        )}

        {/* ── Event results ── */}
        {!loading && tab === 'events' && events.length > 0 && (
          <>
            <div style={{ marginBottom: 10, fontSize: 13, color: 'var(--text-muted)' }}>
              <strong style={{ color: 'var(--text-primary)' }}>{events.length}</strong> eventos encontrados
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {events.map((ev, i) => <EventCard key={i} ev={ev} />)}
            </div>
          </>
        )}

        {/* ── Initial state ── */}
        {!searched && (
          <div className="empty-state" style={{ marginTop: 32 }}>
            <Search size={48} style={{ opacity: 0.1 }} />
            <div className="empty-title">Búsqueda semántica de video</div>
            <div className="empty-desc">
              {tab === 'visual'
                ? 'Describe lo que buscas. El sistema traduce automáticamente y busca en el historial visual.'
                : 'Selecciona un tipo de evento y rango de fechas para ver incidentes registrados.'}
            </div>
          </div>
        )}
      </div>
      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </>
  );
}

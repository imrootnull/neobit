import { useState, useEffect, useRef } from 'react';
import { apiGet, apiPost } from '../api';
import {
  Film, Image, Download, Search, Calendar, Camera,
  Play, Loader, ChevronLeft, ChevronRight, HardDrive,
  AlertTriangle, CheckCircle, Clock, X, ZoomIn
} from 'lucide-react';

// Relative base — works from any PC on the LAN (no hardcoded IP)
const API = (path: string) => `${window.location.origin}${path}`;


const ANALYTIC_LABELS: Record<string, string> = {
  face_detection: 'Rostro', person_detection: 'Persona',
  epp_detection: 'EPP', fall_detection: 'Caída',
  vehicle_detection: 'Vehículo', intrusion_detection: 'Intrusión',
  crowd_detection: 'Multitud', theft_detection: 'Robo',
};

const ANALYTIC_COLORS: Record<string, string> = {
  face_detection: '#06b6d4', person_detection: '#8b5cf6',
  epp_detection: '#f59e0b', fall_detection: '#ef4444',
  vehicle_detection: '#10b981', intrusion_detection: '#f97316',
};

function fmt(iso: string) {
  return new Date(iso).toLocaleString('es-MX', {
    day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit',
  });
}

// ── Media lightbox ────────────────────────────────────────────────────────────
function Lightbox({ item, onClose }: { item: any; onClose: () => void }) {
  return (
    <div onClick={onClose} style={{
      position: 'fixed', inset: 0, zIndex: 1000,
      background: 'rgba(0,0,0,.88)', display: 'flex',
      alignItems: 'center', justifyContent: 'center',
    }}>
      <div onClick={e => e.stopPropagation()} style={{
        background: 'var(--bg-card)', borderRadius: 12, overflow: 'hidden',
        maxWidth: 900, width: '96vw', border: '1px solid var(--border)',
      }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '12px 16px', borderBottom: '1px solid var(--border)' }}>
          <span style={{ fontWeight: 600, fontSize: 14 }}>
            {ANALYTIC_LABELS[item.analytic] ?? item.analytic} — {fmt(item.timestamp)}
          </span>
          <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-muted)' }}>
            <X size={18} />
          </button>
        </div>
        <div style={{ background: '#000' }}>
          {item.media_type === 'clip'
            ? <video src={API(item.url)} controls autoPlay style={{ width: '100%', maxHeight: 520, display: 'block' }} />
            : <img src={API(item.url)} alt="" style={{ width: '100%', maxHeight: 520, objectFit: 'contain', display: 'block' }} />
          }
        </div>
        <div style={{ padding: '10px 16px', display: 'flex', gap: 8 }}>
          <a href={API(`/api/playback/export?paths=${encodeURIComponent(item.path)}`)}
            download style={{ textDecoration: 'none' }}>
            <button className="btn btn-primary btn-sm" style={{ gap: 5, display: 'flex', alignItems: 'center' }}>
              <Download size={13} /> Exportar
            </button>
          </a>
          <span style={{ fontSize: 12, color: 'var(--text-muted)', lineHeight: '30px' }}>
            Cámara {item.camera_id} · {item.media_type === 'clip' ? 'Clip' : 'Captura'}
          </span>
        </div>
      </div>
    </div>
  );
}

// ── Clip card ─────────────────────────────────────────────────────────────────
function ClipCard({ item, selected, onSelect, onClick }: any) {
  const color = ANALYTIC_COLORS[item.analytic] ?? '#6b7280';
  return (
    <div onClick={onClick} style={{
      background: 'var(--bg-card)', borderRadius: 10,
      border: selected ? `2px solid ${color}` : '1px solid var(--border)',
      overflow: 'hidden', cursor: 'pointer', position: 'relative',
      transition: 'transform .15s, box-shadow .15s',
    }}
      onMouseEnter={e => { (e.currentTarget as HTMLElement).style.transform = 'translateY(-2px)'; (e.currentTarget as HTMLElement).style.boxShadow = '0 6px 24px rgba(0,0,0,.3)'; }}
      onMouseLeave={e => { (e.currentTarget as HTMLElement).style.transform = ''; (e.currentTarget as HTMLElement).style.boxShadow = ''; }}
    >
      {/* Thumbnail */}
      <div style={{ position: 'relative', aspectRatio: '16/9', background: '#0a0a0f' }}>
        {item.media_type === 'snapshot'
          ? <img src={API(item.url)} alt="" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
          : <div style={{ width: '100%', height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <Play size={28} style={{ opacity: .5 }} />
            </div>
        }
        <div style={{ position: 'absolute', top: 5, left: 5, background: color + 'cc', borderRadius: 4, fontSize: 10, padding: '2px 6px', fontWeight: 600, color: '#fff' }}>
          {ANALYTIC_LABELS[item.analytic] ?? item.analytic}
        </div>
        <div style={{ position: 'absolute', top: 5, right: 5, background: 'rgba(0,0,0,.7)', borderRadius: 4, fontSize: 10, padding: '2px 6px', color: '#fff' }}>
          {item.media_type === 'clip' ? <Film size={10} /> : <Image size={10} />}
        </div>
        {/* select checkbox */}
        <div onClick={e => { e.stopPropagation(); onSelect(); }}
          style={{ position: 'absolute', bottom: 5, right: 5, width: 18, height: 18, borderRadius: 4, border: '2px solid #fff', background: selected ? color : 'rgba(0,0,0,.5)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          {selected && <CheckCircle size={12} style={{ color: '#fff' }} />}
        </div>
      </div>
      <div style={{ padding: '8px 10px' }}>
        <div style={{ fontSize: 11, color: 'var(--text-muted)', display: 'flex', gap: 6 }}>
          <Camera size={10} /> Cam {item.camera_id}
          <Clock size={10} style={{ marginLeft: 4 }} /> {fmt(item.timestamp)}
        </div>
        <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 2 }}>
          {item.media_type === 'clip' ? '🎬 Clip' : '📸 Captura'} · {(item.size_bytes / 1024).toFixed(0)} KB
        </div>
      </div>
    </div>
  );
}

// ── Timeline bar ──────────────────────────────────────────────────────────────
function TimelineBar({ timeline, onHourClick }: { timeline: any[]; onHourClick: (h: number) => void }) {
  const max = Math.max(1, ...timeline.map((t: any) => t.events.length));
  return (
    <div style={{ display: 'flex', gap: 2, alignItems: 'flex-end', height: 48, padding: '0 4px' }}>
      {timeline.map((slot: any) => {
        const h = slot.events.length;
        const pct = (h / max) * 100;
        const hasAlert = slot.events.some((e: any) => e.severity === 'high' || e.severity === 'critical');
        return (
          <div key={slot.hour} onClick={() => h > 0 && onHourClick(slot.hour)}
            title={`${slot.hour}:00 — ${h} eventos`}
            style={{
              flex: 1, height: h ? `${Math.max(pct, 8)}%` : '4px',
              background: h === 0 ? 'var(--border)' : hasAlert ? '#ef4444aa' : '#6366f1aa',
              borderRadius: '3px 3px 0 0', cursor: h > 0 ? 'pointer' : 'default',
              transition: 'opacity .15s', minHeight: 4,
            }}
            onMouseEnter={e => { (e.currentTarget as HTMLElement).style.opacity = '.7'; }}
            onMouseLeave={e => { (e.currentTarget as HTMLElement).style.opacity = '1'; }}
          />
        );
      })}
    </div>
  );
}

// ── Semantic search pane ──────────────────────────────────────────────────────
function SearchPane() {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [light, setLight] = useState<any>(null);

  const doSearch = async (q = query) => {
    if (!q.trim()) return;
    setLoading(true);
    try {
      const d = await apiPost('/api/search/semantic', { query: q, top_k: 20 });
      setResults(d.results || []);
    } catch { setResults([]); }
    finally { setLoading(false); }
  };

  const examples = ['persona con casco', 'persona sin chaleco', 'persona en el suelo', 'vehículo blanco', 'persona corriendo'];

  return (
    <div>
      {light && <Lightbox item={{
        ...light,
        url: `/api/search/frame/${encodeURIComponent(light.frame_path)}`,
        media_type: 'snapshot', path: light.frame_path,
      }} onClose={() => setLight(null)} />}

      <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
        <div style={{ flex: 1, position: 'relative' }}>
          <Search size={15} style={{ position: 'absolute', left: 10, top: '50%', transform: 'translateY(-50%)', color: 'var(--text-muted)' }} />
          <input value={query} onChange={e => setQuery(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && doSearch()}
            placeholder='Ej: "persona con casco amarillo"'
            style={{ width: '100%', paddingLeft: 34, paddingRight: 12, height: 36, background: 'var(--bg-input)', border: '1px solid var(--border)', borderRadius: 8, color: 'var(--text-primary)', fontSize: 13, boxSizing: 'border-box' }} />
        </div>
        <button className="btn btn-primary" onClick={() => doSearch()} disabled={loading || !query.trim()} style={{ gap: 6, display: 'flex', alignItems: 'center' }}>
          {loading ? <Loader size={13} style={{ animation: 'spin 1s linear infinite' }} /> : <Search size={13} />} Buscar
        </button>
      </div>

      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 14 }}>
        {examples.map(ex => (
          <button key={ex} className="btn btn-ghost btn-sm" onClick={() => { setQuery(ex); doSearch(ex); }} style={{ fontSize: 11 }}>{ex}</button>
        ))}
      </div>

      {loading && <div style={{ textAlign: 'center', padding: 40, color: 'var(--text-muted)' }}><Loader size={28} style={{ animation: 'spin 1s linear infinite', opacity: .5 }} /></div>}

      {!loading && results.length > 0 && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill,minmax(180px,1fr))', gap: 10 }}>
          {results.map((r, i) => {
            const score = Math.round((r.score || 0) * 100);
            const c = score > 70 ? '#10b981' : score > 50 ? '#f59e0b' : '#6b7280';
            return (
              <div key={i} onClick={() => setLight(r)} style={{ cursor: 'pointer', borderRadius: 8, overflow: 'hidden', border: '1px solid var(--border)', background: 'var(--bg-card)' }}>
                {r.frame_path
                  ? <img src={API(`/api/search/frame/${encodeURIComponent(r.frame_path)}`)} alt="" style={{ width: '100%', aspectRatio: '16/9', objectFit: 'cover', display: 'block' }} />
                  : <div style={{ width: '100%', aspectRatio: '16/9', background: '#0a0a0f', display: 'flex', alignItems: 'center', justifyContent: 'center' }}><ZoomIn size={22} style={{ opacity: .2 }} /></div>
                }
                <div style={{ padding: '6px 8px', fontSize: 11 }}>
                  <span style={{ color: c, fontWeight: 700 }}>{score}% similitud</span>
                  <div style={{ color: 'var(--text-muted)', marginTop: 2 }}>Cam {r.camera_id} · {new Date((r.timestamp || 0) * 1000).toLocaleTimeString('es-MX')}</div>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {!loading && results.length === 0 && (
        <div style={{ textAlign: 'center', padding: 40, color: 'var(--text-muted)' }}>
          <Search size={36} style={{ opacity: .15, marginBottom: 10 }} />
          <div>Describe lo que buscas — CLIP compara contra todos los frames indexados</div>
        </div>
      )}
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────
export default function Playback() {
  const today = new Date().toISOString().slice(0, 10);
  const [date, setDate] = useState(today);
  const [camId, setCamId] = useState<number | null>(null);
  const [analytic, setAnalytic] = useState('');
  const [mediaType, setMediaType] = useState('');
  const [clips, setClips] = useState<any[]>([]);
  const [timeline, setTimeline] = useState<any[]>([]);
  const [stats, setStats] = useState<any>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [light, setLight] = useState<any>(null);
  const [tab, setTab] = useState<'clips' | 'search'>('clips');
  const [loading, setLoading] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const [tl, cl, st] = await Promise.all([
        apiGet(`/api/playback/timeline?date=${date}${camId ? `&camera_id=${camId}` : ''}`),
        apiGet(`/api/playback/clips?limit=200${camId ? `&camera_id=${camId}` : ''}${analytic ? `&analytic=${analytic}` : ''}${mediaType ? `&media_type=${mediaType}` : ''}`),
        apiGet('/api/playback/stats'),
      ]);
      setTimeline(tl.timeline || []);
      setClips(cl.items || []);
      setStats(st);
    } catch (e) { console.error(e); }
    finally { setLoading(false); }
  };

  useEffect(() => { load(); }, [date, camId, analytic, mediaType]);

  const toggleSelect = (path: string) => {
    setSelected(prev => {
      const s = new Set(prev);
      s.has(path) ? s.delete(path) : s.add(path);
      return s;
    });
  };

  const exportSelected = () => {
    const paths = Array.from(selected).join(',');
    window.open(API(`/api/playback/export?paths=${encodeURIComponent(paths)}`), '_blank');
  };

  const prevDay = () => setDate(d => { const dt = new Date(d); dt.setDate(dt.getDate() - 1); return dt.toISOString().slice(0, 10); });
  const nextDay = () => { if (date < today) setDate(d => { const dt = new Date(d); dt.setDate(dt.getDate() + 1); return dt.toISOString().slice(0, 10); }); };

  return (
    <>
      {light && <Lightbox item={light} onClose={() => setLight(null)} />}
      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>

      <div className="page-header">
        <div>
          <h1 className="page-title">Reproducción NVR</h1>
          <p className="page-subtitle">Historial de video, línea de tiempo y búsqueda inteligente</p>
        </div>
        {selected.size > 0 && (
          <button className="btn btn-primary" onClick={exportSelected} style={{ gap: 7, display: 'flex', alignItems: 'center' }}>
            <Download size={15} /> Exportar {selected.size} archivos
          </button>
        )}
      </div>

      <div className="page-content">
        {/* Stats row */}
        {stats && (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(140px,1fr))', gap: 12, marginBottom: 20 }}>
            {[
              { icon: <Film size={16} />, label: 'Clips', value: stats.total_clips, color: '#6366f1' },
              { icon: <Image size={16} />, label: 'Capturas', value: stats.total_snapshots, color: '#06b6d4' },
              { icon: <AlertTriangle size={16} />, label: 'Eventos', value: stats.total_events, color: '#f59e0b' },
              { icon: <HardDrive size={16} />, label: 'Almacenado', value: `${stats.used_gb} GB`, color: '#10b981' },
            ].map(s => (
              <div key={s.label} className="card" style={{ padding: '14px 16px', display: 'flex', alignItems: 'center', gap: 12 }}>
                <div style={{ color: s.color }}>{s.icon}</div>
                <div>
                  <div style={{ fontSize: 18, fontWeight: 700, color: 'var(--text-primary)' }}>{s.value}</div>
                  <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>{s.label}</div>
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Timeline */}
        <div className="card" style={{ padding: '16px 20px', marginBottom: 16 }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontWeight: 600, fontSize: 14 }}>
              <Calendar size={15} /> Línea de tiempo
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <button className="btn btn-ghost btn-sm" onClick={prevDay}><ChevronLeft size={14} /></button>
              <input type="date" value={date} max={today} onChange={e => setDate(e.target.value)}
                style={{ background: 'var(--bg-input)', border: '1px solid var(--border)', borderRadius: 6, color: 'var(--text-primary)', padding: '4px 8px', fontSize: 13 }} />
              <button className="btn btn-ghost btn-sm" onClick={nextDay} disabled={date >= today}><ChevronRight size={14} /></button>
            </div>
          </div>
          {timeline.length > 0
            ? <TimelineBar timeline={timeline} onHourClick={() => {}} />
            : <div style={{ height: 48, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-muted)', fontSize: 13 }}>Sin eventos este día</div>
          }
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 10, color: 'var(--text-muted)', marginTop: 4 }}>
            <span>00:00</span><span>06:00</span><span>12:00</span><span>18:00</span><span>23:59</span>
          </div>
        </div>

        {/* Tab switcher */}
        <div style={{ display: 'flex', gap: 4, marginBottom: 16 }}>
          {(['clips', 'search'] as const).map(t => (
            <button key={t} onClick={() => setTab(t)}
              style={{ padding: '8px 18px', borderRadius: 8, border: 'none', cursor: 'pointer', fontWeight: 600, fontSize: 13,
                background: tab === t ? 'var(--accent)' : 'var(--bg-card)',
                color: tab === t ? '#fff' : 'var(--text-muted)',
              }}>
              {t === 'clips' ? <><Film size={13} style={{ display: 'inline', marginRight: 6 }} />Clips & Capturas</> : <><Search size={13} style={{ display: 'inline', marginRight: 6 }} />Búsqueda IA</>}
            </button>
          ))}
        </div>

        {tab === 'search' && (
          <div className="card" style={{ padding: 20 }}>
            <SearchPane />
          </div>
        )}

        {tab === 'clips' && (
          <>
            {/* Filters */}
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 14, alignItems: 'center' }}>
              <select value={camId ?? ''} onChange={e => setCamId(e.target.value ? Number(e.target.value) : null)}
                style={{ background: 'var(--bg-input)', border: '1px solid var(--border)', borderRadius: 7, color: 'var(--text-primary)', padding: '6px 10px', fontSize: 13 }}>
                <option value="">Todas las cámaras</option>
                <option value="1">Cámara 1</option>
                <option value="2">Cámara 2</option>
              </select>
              <select value={analytic} onChange={e => setAnalytic(e.target.value)}
                style={{ background: 'var(--bg-input)', border: '1px solid var(--border)', borderRadius: 7, color: 'var(--text-primary)', padding: '6px 10px', fontSize: 13 }}>
                <option value="">Todas las analíticas</option>
                {Object.entries(ANALYTIC_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
              </select>
              <select value={mediaType} onChange={e => setMediaType(e.target.value)}
                style={{ background: 'var(--bg-input)', border: '1px solid var(--border)', borderRadius: 7, color: 'var(--text-primary)', padding: '6px 10px', fontSize: 13 }}>
                <option value="">Clips y capturas</option>
                <option value="clip">Solo clips</option>
                <option value="snapshot">Solo capturas</option>
              </select>
              {selected.size > 0 && (
                <button className="btn btn-ghost btn-sm" onClick={() => setSelected(new Set())} style={{ marginLeft: 'auto' }}>
                  <X size={12} /> Deseleccionar ({selected.size})
                </button>
              )}
              <span style={{ fontSize: 12, color: 'var(--text-muted)', marginLeft: 'auto' }}>
                {clips.length} archivos
              </span>
            </div>

            {loading && <div style={{ textAlign: 'center', padding: 60 }}><Loader size={28} style={{ opacity: .4, animation: 'spin 1s linear infinite' }} /></div>}

            {!loading && clips.length === 0 && (
              <div style={{ textAlign: 'center', padding: 60, color: 'var(--text-muted)' }}>
                <Film size={40} style={{ opacity: .15, marginBottom: 12 }} />
                <div style={{ fontWeight: 600 }}>Sin archivos grabados</div>
                <div style={{ fontSize: 13, marginTop: 4 }}>Los clips y capturas aparecerán aquí cuando se detecten eventos</div>
              </div>
            )}

            {!loading && clips.length > 0 && (
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill,minmax(200px,1fr))', gap: 12 }}>
                {clips.map(item => (
                  <ClipCard
                    key={item.path}
                    item={item}
                    selected={selected.has(item.path)}
                    onSelect={() => toggleSelect(item.path)}
                    onClick={() => setLight(item)}
                  />
                ))}
              </div>
            )}
          </>
        )}
      </div>
    </>
  );
}

/**
 * FaceLibrary — galería de rostros con crop, snapshot completo y clip de video.
 *
 * Inspirado en Hikvision FR pero mejorado:
 * - Crop del rostro (vista rápida en grid)
 * - Snapshot del frame completo con bbox (contexto de escena)
 * - Clip de video MP4 (3s pre + 5s post) con reproductor inline
 * - Identidad InsightFace mostrada cuando disponible
 * - Validar/Etiquetar/Descartar + Actualizar Gallery
 */
import { useState, useEffect, useCallback, useRef } from 'react';
import { apiGet, apiPost } from '../api';
import {
  User, Check, X, Trash2, RefreshCw,
  ChevronLeft, ChevronRight, Tag, Camera,
  Brain, Play, Pause, Image, Film, AlertCircle
} from 'lucide-react';

const STATUS_TABS = [
  { key: '',          label: 'Todos',      color: 'var(--text-muted)' },
  { key: 'pending',   label: 'Pendientes', color: '#f59e0b' },
  { key: 'validated', label: 'Validados',  color: '#22c55e' },
  { key: 'discarded', label: 'Descartados',color: '#ef4444' },
];

function ts(unix: number) {
  return new Date(unix * 1000).toLocaleString('es-MX', {
    month: 'short', day: 'numeric',
    hour: '2-digit', minute: '2-digit', second: '2-digit',
  });
}

interface Face {
  id: number;
  camera_id: number;
  timestamp: number;
  image_path: string;
  snapshot_path: string | null;
  clip_path: string | null;
  clip_ready: number;
  confidence: number;
  face_w: number;
  face_h: number;
  status: string;
  label: string | null;
  identity: string | null;
  similarity: number | null;
}

interface Props {
  onClose: () => void;
}

const STATUS_COLOR: Record<string, string> = {
  pending:   '#f59e0b',
  validated: '#22c55e',
  discarded: '#ef4444',
};
const STATUS_LABEL: Record<string, string> = {
  pending:   'Pendiente',
  validated: 'Validado',
  discarded: 'Descartado',
};

// ── Video player with retry logic ──────────────────────────────────────────────
function FaceClipPlayer({ faceId, clipReady }: { faceId: number; clipReady: number }) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const [status, setStatus] = useState<'loading'|'ready'|'recording'|'error'>(
    clipReady ? 'ready' : 'loading'
  );
  const [retries, setRetries] = useState(0);

  // Poll until clip is ready (max 30s / 6 retries at 5s interval)
  useEffect(() => {
    if (clipReady) { setStatus('ready'); return; }
    if (retries >= 6) { setStatus('recording'); return; }
    const timer = setTimeout(async () => {
      try {
        const res = await fetch(`/api/faces/${faceId}/clip`, { method: 'HEAD' });
        if (res.status === 200) {
          setStatus('ready');
        } else {
          setRetries(r => r + 1);
        }
      } catch {
        setRetries(r => r + 1);
      }
    }, 5000);
    return () => clearTimeout(timer);
  }, [faceId, clipReady, retries]);

  if (status === 'loading' || status === 'recording') {
    return (
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        gap: 8, padding: '12px 0', color: 'var(--text-muted)', fontSize: 12,
      }}>
        <div style={{
          width: 12, height: 12, borderRadius: '50%',
          border: '2px solid var(--border)', borderTopColor: '#f59e0b',
          animation: 'spin 0.8s linear infinite',
        }} />
        {status === 'loading' ? 'Grabando clip...' : 'Clip no disponible'}
      </div>
    );
  }

  return (
    <video
      ref={videoRef}
      src={`/api/faces/${faceId}/clip`}
      controls
      style={{
        width: '100%', borderRadius: 6,
        border: '1px solid var(--border)',
        background: '#000',
        maxHeight: 180,
      }}
      onError={() => setStatus('error')}
    />
  );
}

// ── Snapshot viewer (full frame) ───────────────────────────────────────────────
function SnapshotViewer({ faceId, hasSnapshot }: { faceId: number; hasSnapshot: boolean }) {
  const [expanded, setExpanded] = useState(false);
  if (!hasSnapshot) return null;
  return (
    <div>
      <button
        onClick={() => setExpanded(e => !e)}
        style={{
          display: 'flex', alignItems: 'center', gap: 6,
          fontSize: 11, color: 'var(--text-muted)',
          background: 'none', border: '1px solid var(--border)',
          borderRadius: 6, padding: '4px 10px', cursor: 'pointer',
          width: '100%', justifyContent: 'center',
          transition: 'all 0.15s',
        }}
      >
        <Image size={12} />
        {expanded ? 'Ocultar escena' : 'Ver escena completa'}
      </button>
      {expanded && (
        <img
          src={`/api/faces/${faceId}/snapshot`}
          alt="snapshot"
          style={{
            width: '100%', borderRadius: 6, marginTop: 6,
            border: '1px solid var(--border)',
          }}
        />
      )}
    </div>
  );
}

// ── Main component ─────────────────────────────────────────────────────────────
export default function FaceLibrary({ onClose }: Props) {
  const [faces,     setFaces]    = useState<Face[]>([]);
  const [total,     setTotal]    = useState(0);
  const [stats,     setStats]    = useState<Record<string, number>>({});
  const [status,    setStatus]   = useState('');
  const [page,      setPage]     = useState(1);
  const [loading,   setLoading]  = useState(false);
  const [selected,  setSelected] = useState<Face | null>(null);
  const [editLabel, setEditLabel]= useState('');
  const [saving,    setSaving]   = useState(false);
  const [galleryMsg,setGalleryMsg]= useState('');
  const [viewMode,  setViewMode] = useState<'crop'|'clip'>('crop');

  const LIMIT      = 40;
  const totalPages = Math.max(1, Math.ceil(total / LIMIT));

  const fetchStats = useCallback(() => {
    apiGet('/api/faces/stats').then(setStats).catch(() => {});
  }, []);

  const fetchFaces = useCallback(() => {
    setLoading(true);
    const q = new URLSearchParams({ page: String(page), limit: String(LIMIT) });
    if (status) q.set('status', status);
    apiGet(`/api/faces/?${q}`)
      .then(r => { setFaces(r.items); setTotal(r.total); })
      .finally(() => setLoading(false));
  }, [status, page]);

  useEffect(() => { fetchStats(); }, [fetchStats]);
  useEffect(() => { setPage(1); }, [status]);
  useEffect(() => { fetchFaces(); }, [fetchFaces]);

  const patchFace = async (id: number, s: string, label?: string) => {
    setSaving(true);
    try {
      await apiPost(`/api/faces/${id}`, { status: s, label: label ?? null }, 'PATCH');
      setFaces(prev => prev.map(f => f.id === id ? { ...f, status: s, label: label ?? null } : f));
      fetchStats();
      if (selected?.id === id) setSelected(prev => prev ? { ...prev, status: s, label: label ?? null } : null);
    } finally { setSaving(false); }
  };

  const deleteFace = async (id: number) => {
    await apiPost(`/api/faces/${id}`, {}, 'DELETE');
    setFaces(prev => prev.filter(f => f.id !== id));
    setTotal(t => t - 1);
    fetchStats();
    if (selected?.id === id) setSelected(null);
  };

  const refreshGallery = async () => {
    try {
      await apiPost('/api/faces/refresh-gallery', {});
      setGalleryMsg('Gallery actualizado');
      setTimeout(() => setGalleryMsg(''), 3000);
    } catch {
      setGalleryMsg('Error al actualizar');
      setTimeout(() => setGalleryMsg(''), 3000);
    }
  };

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div
        className="modal"
        style={{ maxWidth: 1060, width: '97vw', maxHeight: '94vh', display: 'flex', flexDirection: 'column' }}
        onClick={e => e.stopPropagation()}
      >
        {/* ── Header ────────────────────────────────────────────────────────── */}
        <div className="modal-header" style={{ flexShrink: 0 }}>
          <div>
            <div className="modal-title" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <User size={16} style={{ color: '#0ea5e9' }} />
              Biblioteca de Rostros
            </div>
            <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 2 }}>
              {stats.pending ?? 0} pendientes · {stats.validated ?? 0} validados · {stats.discarded ?? 0} descartados
            </div>
          </div>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            {galleryMsg && (
              <span style={{ fontSize: 11, color: '#22c55e', fontWeight: 600 }}>{galleryMsg}</span>
            )}
            <button
              className="btn btn-ghost btn-sm"
              onClick={refreshGallery}
              title="Reconstruir gallery de reconocimiento facial"
              style={{ display: 'flex', alignItems: 'center', gap: 5, fontSize: 11 }}
            >
              <Brain size={13} /> Actualizar Gallery
            </button>
            <button className="btn btn-ghost btn-icon" onClick={fetchFaces} title="Actualizar">
              <RefreshCw size={14} />
            </button>
            <button className="btn btn-ghost btn-icon" onClick={onClose}><X size={16} /></button>
          </div>
        </div>

        {/* ── Filter tabs ────────────────────────────────────────────────────── */}
        <div style={{ display: 'flex', gap: 4, padding: '8px 16px', borderBottom: '1px solid var(--border)', flexShrink: 0 }}>
          {STATUS_TABS.map(t => (
            <button
              key={t.key}
              onClick={() => setStatus(t.key)}
              style={{
                padding: '4px 14px', borderRadius: 6, fontSize: 12, fontWeight: 600,
                border: `1px solid ${status === t.key ? t.color : 'var(--border)'}`,
                background: status === t.key ? t.color + '22' : 'transparent',
                color: status === t.key ? t.color : 'var(--text-muted)',
                cursor: 'pointer', transition: 'all 0.15s',
              }}
            >
              {t.label}
              {t.key && stats[t.key] > 0 && (
                <span style={{
                  marginLeft: 6, background: t.color + '33',
                  color: t.color, padding: '0 5px', borderRadius: 8, fontSize: 11,
                }}>
                  {stats[t.key]}
                </span>
              )}
            </button>
          ))}
        </div>

        {/* ── Body ──────────────────────────────────────────────────────────── */}
        <div style={{ flex: 1, display: 'flex', minHeight: 0 }}>

          {/* Grid */}
          <div style={{ flex: 1, overflowY: 'auto', padding: 12 }}>
            {loading ? (
              <div style={{ display: 'flex', justifyContent: 'center', padding: 40 }}>
                <div style={{ width: 24, height: 24, borderRadius: '50%', border: '2px solid var(--border)', borderTopColor: '#0ea5e9', animation: 'spin 0.8s linear infinite' }} />
              </div>
            ) : faces.length === 0 ? (
              <div style={{ textAlign: 'center', padding: 60, color: 'var(--text-muted)' }}>
                <User size={36} style={{ opacity: 0.2, marginBottom: 8 }} />
                <div style={{ fontSize: 13 }}>No hay rostros en esta categoría</div>
                <div style={{ fontSize: 11, marginTop: 6, opacity: 0.6 }}>
                  Los rostros se capturan automáticamente cuando está activa la detección facial
                </div>
              </div>
            ) : (
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(120px, 1fr))', gap: 8 }}>
                {faces.map(f => (
                  <div
                    key={f.id}
                    onClick={() => { setSelected(f); setEditLabel(f.label ?? ''); setViewMode('crop'); }}
                    style={{
                      borderRadius: 8, overflow: 'hidden', cursor: 'pointer',
                      border: `2px solid ${selected?.id === f.id ? '#0ea5e9' : (STATUS_COLOR[f.status] + '55')}`,
                      background: 'var(--bg-card)', position: 'relative',
                      transition: 'border-color 0.15s, transform 0.12s, box-shadow 0.15s',
                      transform: selected?.id === f.id ? 'scale(1.04)' : 'scale(1)',
                      boxShadow: selected?.id === f.id ? '0 0 0 1px #0ea5e9' : 'none',
                    }}
                  >
                    <img
                      src={`/api/faces/${f.id}/image`}
                      alt="face"
                      style={{ width: '100%', aspectRatio: '1/1', objectFit: 'cover', display: 'block' }}
                      loading="lazy"
                    />

                    {/* Status dot */}
                    <div style={{
                      position: 'absolute', top: 4, right: 4,
                      width: 8, height: 8, borderRadius: '50%',
                      background: STATUS_COLOR[f.status] ?? '#666',
                      boxShadow: '0 0 4px rgba(0,0,0,0.6)',
                    }} />

                    {/* Clip available indicator */}
                    {f.clip_ready ? (
                      <div style={{
                        position: 'absolute', top: 4, left: 4,
                        background: 'rgba(0,180,255,0.85)', borderRadius: 3,
                        padding: '1px 4px',
                      }}>
                        <Film size={9} color="#fff" />
                      </div>
                    ) : null}

                    {/* Identity badge */}
                    {f.identity && (
                      <div style={{
                        position: 'absolute', bottom: 0, left: 0, right: 0,
                        background: 'rgba(34,197,94,0.85)',
                        fontSize: 9, color: '#fff', fontWeight: 700,
                        padding: '2px 4px', textAlign: 'center',
                        whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
                      }}>
                        {f.identity}
                      </div>
                    )}

                    {/* Label fallback */}
                    {!f.identity && f.label && (
                      <div style={{
                        position: 'absolute', bottom: 0, left: 0, right: 0,
                        background: 'rgba(0,0,0,0.75)',
                        fontSize: 9, color: '#fff',
                        padding: '2px 4px', textAlign: 'center',
                        whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
                      }}>
                        {f.label}
                      </div>
                    )}

                    {/* Cam badge */}
                    <div style={{
                      position: 'absolute', bottom: f.identity || f.label ? 16 : 4, left: 4,
                      background: 'rgba(0,0,0,0.55)', borderRadius: 3,
                      fontSize: 8, color: '#aaa', padding: '1px 3px',
                      display: 'flex', alignItems: 'center', gap: 2,
                    }}>
                      <Camera size={7} /> {f.camera_id}
                    </div>
                  </div>
                ))}
              </div>
            )}

            {/* Pagination */}
            {totalPages > 1 && (
              <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', gap: 12, marginTop: 16 }}>
                <button className="btn btn-ghost btn-sm" disabled={page === 1} onClick={() => setPage(p => p - 1)}>
                  <ChevronLeft size={14} />
                </button>
                <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>
                  {page} / {totalPages} — {total} rostros
                </span>
                <button className="btn btn-ghost btn-sm" disabled={page === totalPages} onClick={() => setPage(p => p + 1)}>
                  <ChevronRight size={14} />
                </button>
              </div>
            )}
          </div>

          {/* ── Detail panel ──────────────────────────────────────────────────── */}
          {selected && (
            <div style={{
              width: 268, flexShrink: 0,
              borderLeft: '1px solid var(--border)',
              overflowY: 'auto',
              display: 'flex', flexDirection: 'column', gap: 10,
              padding: 14,
            }}>
              {/* View mode toggle */}
              <div style={{ display: 'flex', gap: 4, marginBottom: 2 }}>
                {[
                  { key: 'crop', icon: <User size={11} />, label: 'Rostro' },
                  { key: 'clip', icon: <Film size={11} />, label: 'Clip' },
                ].map(m => (
                  <button
                    key={m.key}
                    onClick={() => setViewMode(m.key as any)}
                    style={{
                      flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center',
                      gap: 4, fontSize: 11, padding: '4px 0', borderRadius: 6, cursor: 'pointer',
                      border: `1px solid ${viewMode === m.key ? '#0ea5e9' : 'var(--border)'}`,
                      background: viewMode === m.key ? '#0ea5e922' : 'transparent',
                      color: viewMode === m.key ? '#0ea5e9' : 'var(--text-muted)',
                      transition: 'all 0.15s',
                    }}
                  >
                    {m.icon} {m.label}
                  </button>
                ))}
              </div>

              {/* Main media view */}
              {viewMode === 'crop' ? (
                <img
                  src={`/api/faces/${selected.id}/image`}
                  alt="face-detail"
                  style={{ width: '100%', borderRadius: 8, border: '1px solid var(--border)' }}
                />
              ) : (
                <FaceClipPlayer faceId={selected.id} clipReady={selected.clip_ready} />
              )}

              {/* Snapshot toggle */}
              <SnapshotViewer faceId={selected.id} hasSnapshot={!!selected.snapshot_path} />

              {/* Identity badge (if recognized) */}
              {selected.identity && (
                <div style={{
                  background: '#22c55e18', border: '1px solid #22c55e44',
                  borderRadius: 6, padding: '6px 10px', fontSize: 11,
                  color: '#22c55e',
                }}>
                  <div style={{ fontWeight: 700, marginBottom: 2 }}>Reconocido</div>
                  <div style={{ fontSize: 13, fontWeight: 800 }}>{selected.identity}</div>
                  <div style={{ opacity: 0.7 }}>Similitud: {((selected.similarity ?? 0) * 100).toFixed(0)}%</div>
                </div>
              )}

              {/* Meta */}
              <div style={{ fontSize: 11, color: 'var(--text-muted)', display: 'flex', flexDirection: 'column', gap: 3 }}>
                <div><span style={{ color: 'var(--text-secondary)' }}>Cámara:</span> {selected.camera_id}</div>
                <div><span style={{ color: 'var(--text-secondary)' }}>Fecha:</span> {ts(selected.timestamp)}</div>
                <div><span style={{ color: 'var(--text-secondary)' }}>Confianza:</span> {(selected.confidence * 100).toFixed(0)}%</div>
                <div><span style={{ color: 'var(--text-secondary)' }}>Tamaño:</span> {selected.face_w}×{selected.face_h}px</div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
                  <span style={{ color: 'var(--text-secondary)' }}>Estado:</span>
                  <span style={{ color: STATUS_COLOR[selected.status], fontWeight: 700 }}>
                    {STATUS_LABEL[selected.status] ?? selected.status}
                  </span>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
                  <span style={{ color: 'var(--text-secondary)' }}>Clip:</span>
                  <span style={{ color: selected.clip_ready ? '#22c55e' : '#f59e0b' }}>
                    {selected.clip_ready ? 'Listo' : 'Grabando...'}
                  </span>
                </div>
              </div>

              {/* Label input */}
              <div>
                <label style={{ fontSize: 11, color: 'var(--text-muted)', display: 'block', marginBottom: 4 }}>
                  Nombre / Etiqueta
                </label>
                <input
                  className="form-input"
                  style={{ fontSize: 12, padding: '5px 8px' }}
                  placeholder="Ej: Juan Pérez"
                  value={editLabel}
                  onChange={e => setEditLabel(e.target.value)}
                />
              </div>

              {/* Actions */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                <button
                  className="btn btn-sm"
                  disabled={saving}
                  style={{ background: '#22c55e22', border: '1px solid #22c55e44', color: '#22c55e', justifyContent: 'center' }}
                  onClick={() => patchFace(selected.id, 'validated', editLabel || undefined)}
                >
                  <Check size={13} /> Validar
                </button>
                <button
                  className="btn btn-sm"
                  disabled={saving}
                  style={{ background: '#f59e0b22', border: '1px solid #f59e0b44', color: '#f59e0b', justifyContent: 'center' }}
                  onClick={() => patchFace(selected.id, 'pending', editLabel || undefined)}
                >
                  <Tag size={13} /> Pendiente
                </button>
                <button
                  className="btn btn-sm"
                  disabled={saving}
                  style={{ background: '#ef444422', border: '1px solid #ef444444', color: '#ef4444', justifyContent: 'center' }}
                  onClick={() => patchFace(selected.id, 'discarded')}
                >
                  <X size={13} /> Descartar
                </button>
                <div style={{ borderTop: '1px solid var(--border)', paddingTop: 6 }}>
                  <button
                    className="btn btn-sm"
                    disabled={saving}
                    style={{ background: 'rgba(255,255,255,0.03)', border: '1px solid var(--border)', color: 'var(--text-muted)', justifyContent: 'center', width: '100%' }}
                    onClick={() => deleteFace(selected.id)}
                  >
                    <Trash2 size={13} /> Eliminar permanente
                  </button>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  );
}

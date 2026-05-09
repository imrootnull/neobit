import { useState, useEffect, useCallback, useRef } from 'react';
import { getSnapshotUrl } from '../api';
import { WifiOff, AlertTriangle, X, Maximize2 } from 'lucide-react';
import { ANALYTIC_ICONS } from './Icons';

// ─── Snapshot poller — replaces MJPEG persistent connection ──────────────────
// Polls /snapshot every INTERVAL ms via normal HTTP GET (no persistent stream).
// Visually identical to MJPEG but doesn't block uvicorn's event loop.

const POLL_INTERVAL = 150; // ms — ~6-7 fps display, ideal for CPU gateway

function SnapshotImg({
  cameraId,
  style,
  onError,
}: {
  cameraId: number;
  style?: React.CSSProperties;
  onError?: () => void;
}) {
  const [src, setSrc] = useState('');
  const timerRef = useRef<number | null>(null);
  const seqRef   = useRef(0);

  useEffect(() => {
    let active = true;

    const poll = () => {
      if (!active) return;
      const seq = ++seqRef.current;
      const url = `${getSnapshotUrl(cameraId)}?t=${Date.now()}`;
      const img = new Image();
      img.onload = () => {
        if (active && seq === seqRef.current) setSrc(url);
        timerRef.current = window.setTimeout(poll, POLL_INTERVAL);
      };
      img.onerror = () => {
        if (active) {
          onError?.();
          timerRef.current = window.setTimeout(poll, POLL_INTERVAL * 3);
        }
      };
      img.src = url;
    };

    poll();
    return () => {
      active = false;
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, [cameraId]);

  if (!src) return null;
  return <img src={src} alt={`cam-${cameraId}`} style={style} />;
}

// ─── Types ────────────────────────────────────────────────────────────────────

interface Camera {
  id: number;
  name: string;
  location?: string;
  rtsp_url?: string;
}

interface StreamInfo {
  camera_id: number;
  connected: boolean;
  fps: number;
  native_fps?: number;
}

interface AnalyticEvent {
  camera_id: number;
  analytic_type: string;
  severity: string;
  confidence: number;
  description?: string;
}

interface CameraGridProps {
  cameras: Camera[];
  streams: StreamInfo[];
  lastEvent: AnalyticEvent | null;
  onSelect?: (cam: Camera) => void;
}

// ─── Grid layout map ─────────────────────────────────────────────────────────

const GRID_CLASSES: Record<number, string> = {
  1: 'grid-1', 2: 'grid-2', 3: 'grid-2',
  4: 'grid-4', 5: 'grid-6', 6: 'grid-6',
  7: 'grid-8', 8: 'grid-8',
};

// ─── Main grid ────────────────────────────────────────────────────────────────

export default function CameraGrid({ cameras, streams, lastEvent, onSelect }: CameraGridProps) {
  const [expanded, setExpanded]         = useState<Camera | null>(null);
  const [cameraAlerts, setCameraAlerts] = useState<Record<number, AnalyticEvent>>({});

  useEffect(() => {
    if (!lastEvent) return;
    const cid = lastEvent.camera_id;
    setCameraAlerts(prev => ({ ...prev, [cid]: lastEvent }));
    const t = setTimeout(() => {
      setCameraAlerts(prev => { const n = { ...prev }; delete n[cid]; return n; });
    }, 5000);
    return () => clearTimeout(t);
  }, [lastEvent]);

  // Close on Escape
  useEffect(() => {
    const handle = (e: KeyboardEvent) => { if (e.key === 'Escape') setExpanded(null); };
    window.addEventListener('keydown', handle);
    return () => window.removeEventListener('keydown', handle);
  }, []);

  const gridClass = GRID_CLASSES[cameras.length] ?? 'grid-8';

  const handleSelect = useCallback((cam: Camera) => {
    setExpanded(cam);
    onSelect?.(cam);
  }, [onSelect]);

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

  const expandedStream = expanded
    ? streams.find(s => s.camera_id === expanded.id)
    : null;

  return (
    <>
      {/* ── Thumbnail grid ── */}
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
              selected={expanded?.id === cam.id}
              onClick={() => handleSelect(cam)}
            />
          );
        })}
      </div>

      {/* ── Expanded view modal ── */}
      {expanded && (
        <div
          style={{
            position: 'fixed',
            inset: 0,
            zIndex: 2000,
            background: 'rgba(0,0,0,0.88)',
            backdropFilter: 'blur(6px)',
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            padding: 24,
            animation: 'fadeIn 0.15s ease',
          }}
          onClick={() => setExpanded(null)}
        >
          <div
            style={{
              width: '100%',
              maxWidth: 1100,
              display: 'flex',
              flexDirection: 'column',
              gap: 10,
            }}
            onClick={e => e.stopPropagation()}
          >
            {/* Header */}
            <div style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
            }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                <span style={{
                  width: 8, height: 8, borderRadius: '50%',
                  background: expandedStream?.connected ? 'var(--accent-green)' : 'var(--accent-red)',
                  boxShadow: expandedStream?.connected ? '0 0 8px var(--accent-green)' : 'none',
                  flexShrink: 0,
                }} />
                <span style={{ fontSize: 18, fontWeight: 700, color: '#fff' }}>
                  {expanded.name}
                </span>
                {expanded.location && (
                  <span style={{ fontSize: 12, color: 'rgba(255,255,255,0.4)' }}>
                    · {expanded.location}
                  </span>
                )}
                {expandedStream?.connected && (
                  <span style={{
                    fontSize: 11, fontWeight: 700, letterSpacing: '0.08em',
                    background: 'rgba(239,68,68,0.85)', color: '#fff',
                    padding: '2px 7px', borderRadius: 4,
                  }}>
                    LIVE
                  </span>
                )}
                {expandedStream?.connected && (expandedStream.fps ?? 0) > 0 && (
                  <span style={{
                    fontSize: 11, color: 'rgba(255,255,255,0.5)',
                    fontFamily: 'monospace',
                  }}>
                    {(expandedStream.fps).toFixed(0)} fps
                  </span>
                )}
              </div>
              <button
                onClick={() => setExpanded(null)}
                style={{
                  background: 'rgba(255,255,255,0.1)',
                  border: '1px solid rgba(255,255,255,0.15)',
                  borderRadius: 8,
                  color: '#fff',
                  padding: '6px 10px',
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  gap: 6,
                  fontSize: 12,
                  fontWeight: 500,
                  transition: 'all 0.15s ease',
                }}
                title="Cerrar (Esc)"
              >
                <X size={14} /> Cerrar
              </button>
            </div>

            {/* Video */}
            <div style={{
              position: 'relative',
              width: '100%',
              aspectRatio: '16/9',
              background: '#000',
              borderRadius: 12,
              overflow: 'hidden',
              border: '1px solid rgba(255,255,255,0.1)',
              boxShadow: '0 32px 64px rgba(0,0,0,0.7)',
            }}>
              {expandedStream?.connected ? (
                <SnapshotImg
                  cameraId={expanded.id}
                  style={{ width: '100%', height: '100%', objectFit: 'contain', display: 'block' }}
                />
              ) : (
                <div style={{
                  display: 'flex', flexDirection: 'column',
                  alignItems: 'center', justifyContent: 'center',
                  height: '100%', gap: 12, color: 'rgba(255,255,255,0.3)',
                }}>
                  <WifiOff size={48} style={{ opacity: 0.3 }} />
                  <span style={{ fontSize: 14 }}>Sin señal — reconectando...</span>
                </div>
              )}
            </div>

            {/* Camera grid thumbnails — click to switch */}
            {cameras.length > 1 && (
              <div style={{ display: 'flex', gap: 8, overflowX: 'auto', paddingBottom: 2 }}>
                {cameras.map(cam => {
                  const info  = streams.find(s => s.camera_id === cam.id);
                  const isOk  = info?.connected ?? false;
                  const isAct = cam.id === expanded.id;
                  return (
                    <button
                      key={cam.id}
                      onClick={() => setExpanded(cam)}
                      style={{
                        flexShrink: 0,
                        width: 120,
                        aspectRatio: '16/9',
                        borderRadius: 6,
                        overflow: 'hidden',
                        border: `2px solid ${isAct ? 'var(--accent-cyan)' : 'rgba(255,255,255,0.12)'}`,
                        background: '#000',
                        cursor: 'pointer',
                        position: 'relative',
                        transition: 'border-color 0.15s ease',
                        padding: 0,
                      }}
                    >
                      {isOk ? (
                        <SnapshotImg
                          cameraId={cam.id}
                          style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                        />
                      ) : (
                        <div style={{
                          display: 'flex', alignItems: 'center', justifyContent: 'center',
                          height: '100%', background: '#111',
                        }}>
                          <WifiOff size={16} style={{ opacity: 0.3 }} />
                        </div>
                      )}
                      <div style={{
                        position: 'absolute', bottom: 0, left: 0, right: 0,
                        background: 'linear-gradient(to top, rgba(0,0,0,0.8), transparent)',
                        padding: '4px 6px',
                        fontSize: 10, fontWeight: 600, color: '#fff',
                        textAlign: 'left',
                      }}>
                        {cam.name}
                      </div>
                    </button>
                  );
                })}
              </div>
            )}
          </div>
        </div>
      )}
    </>
  );
}

// ─── Camera Cell (thumbnail) ─────────────────────────────────────────────────

interface CameraCellProps {
  camera: Camera;
  connected: boolean;
  fps: number;
  alert?: AnalyticEvent;
  selected: boolean;
  onClick: () => void;
}

function CameraCell({ camera, connected, fps, alert, selected, onClick }: CameraCellProps) {
  const [imgError, setImgError] = useState(false);

  useEffect(() => {
    if (connected) setImgError(false);
  }, [connected]);

  const AlertIcon = alert ? (ANALYTIC_ICONS[alert.analytic_type] ?? AlertTriangle) : null;

  return (
    <div
      className={`camera-cell ${selected ? 'selected' : ''}`}
      onClick={onClick}
      title={`${camera.name} — clic para expandir`}
      style={alert
        ? { borderColor: 'var(--accent-amber)', boxShadow: '0 0 16px rgba(245,158,11,0.25)', cursor: 'pointer' }
        : { cursor: 'pointer' }
      }
    >
      {connected && !imgError ? (
        <SnapshotImg
          cameraId={camera.id}
          style={{ width: '100%', height: '100%', objectFit: 'cover', display: 'block' }}
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

      {/* Expand hint on hover */}
      <div style={{
        position: 'absolute',
        top: 8, right: 8,
        background: 'rgba(0,0,0,0.6)',
        borderRadius: 6,
        padding: '4px 6px',
        opacity: 0,
        transition: 'opacity 0.15s ease',
        pointerEvents: 'none',
      }} className="camera-expand-hint">
        <Maximize2 size={12} color="#fff" />
      </div>

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

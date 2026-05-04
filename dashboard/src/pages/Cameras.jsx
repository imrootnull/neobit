import { useState, useEffect, useRef } from 'react';
import { apiGet, apiPost, apiDelete, apiPatch } from '../api';
import { useWS } from '../context/WSContext';
import AnalyticsConfigModal from '../components/AnalyticsConfigModal';
import {
  Camera, Plus, Trash2, Wifi, WifiOff, Pencil, X, Check,
  ScanLine, Search, Loader, ChevronDown, ChevronRight,
  Info, Radio, Fingerprint, SlidersHorizontal
} from 'lucide-react';
import { ANALYTIC_ICONS } from '../components/Icons';

const ANALYTICS_OPTIONS = [
  { key: 'person_detection',    label: 'Detección de personas'     },
  { key: 'vehicle_detection',   label: 'Detección de vehículos'    },
  { key: 'epp_detection',       label: 'EPP Industrial'            },
  { key: 'fall_detection',      label: 'Detección de caídas'       },
  { key: 'fire_detection',      label: 'Fuego'                     },
  { key: 'smoke_detection',     label: 'Humo'                      },
  { key: 'intrusion_detection', label: 'Intrusión'                 },
  { key: 'line_crossing',       label: 'Cruce de línea'            },
  { key: 'behavior_detection',  label: 'Comportamiento hostil'     },
  { key: 'theft_detection',     label: 'Robo'                      },
  { key: 'lpr_recognition',     label: 'Reconocimiento de placas'  },
  { key: 'crowd_detection',     label: 'Aglomeraciones'            },
  { key: 'face_detection',      label: 'Detección facial'          },
  { key: 'face_recognition',    label: 'Reconocimiento facial'     },
  { key: 'face_blacklist',      label: 'Lista negra facial'        },
];

export default function Cameras() {
  const [cameras, setCameras]     = useState([]);
  const [streams, setStreams]     = useState([]);
  const [showModal, setShowModal]       = useState(false);
  const [editCamera, setEditCamera]     = useState(null);
  const [initialData, setInitialData]   = useState(null);
  const [configCamera, setConfigCamera] = useState(null);
  const [deleteTarget, setDeleteTarget] = useState(null);  // camera pending delete
  const [deleting, setDeleting]         = useState(false);

  const refresh = async () => {
    const [cams, sts] = await Promise.all([
      apiGet('/api/cameras/'),
      apiGet('/api/stream/status'),
    ]);
    setCameras(cams);
    setStreams(sts);
  };

  useEffect(() => { refresh(); }, []);

  const handleDelete = async (cam) => {
    setDeleteTarget(cam);
  };

  const confirmDelete = async () => {
    if (!deleteTarget) return;
    setDeleting(true);
    try {
      await apiDelete(`/api/cameras/${deleteTarget.id}`);
      setDeleteTarget(null);
      await refresh();
    } catch (e) {
      alert(`Error al eliminar: ${e.message}`);
    } finally {
      setDeleting(false);
    }
  };

  const openAdd = (prefill = null) => {
    setEditCamera(null);
    setInitialData(prefill);
    setShowModal(true);
  };

  const openEdit = (cam) => {
    setEditCamera(cam);
    setInitialData(null);
    setShowModal(true);
  };

  const getStreamInfo = (id) => streams.find(s => s.camera_id === id);

  return (
    <>
      <div className="page-header">
        <div>
          <h1 className="page-title">Gestión de Cámaras</h1>
          <p className="page-subtitle">
            Hasta 8 cámaras RTSP — compatible con cualquier fabricante ONVIF
          </p>
        </div>
        <button
          id="add-camera-btn"
          className="btn btn-primary"
          onClick={() => openAdd()}
          disabled={cameras.length >= 8}
        >
          <Plus size={15} /> Agregar cámara
        </button>
      </div>

      <div className="page-content">
        {/* Discovery panel always visible */}
        <DiscoveryPanel onSelect={(data) => openAdd(data)} />

        {cameras.length === 0 ? (
          <div className="empty-state card" style={{ padding: 48, marginTop: 16 }}>
            <Camera size={40} style={{ opacity: 0.15 }} />
            <div className="empty-title">Sin cámaras configuradas</div>
            <div className="empty-desc">
              Usa el escáner de red para encontrar cámaras automáticamente,
              o agrégalas manualmente con su IP o URL RTSP.
            </div>
          </div>
        ) : (
          <div style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fill, minmax(340px, 1fr))',
            gap: 14,
            marginTop: 16,
          }}>
            {cameras.map(cam => {
              const info      = getStreamInfo(cam.id);
              const connected = info?.connected ?? false;
              return (
                <CameraCard
                  key={cam.id}
                  camera={cam}
                  connected={connected}
                  fps={info?.fps}
                  onEdit={() => openEdit(cam)}
                  onDelete={() => handleDelete(cam)}
                  onConfig={() => setConfigCamera(cam)}
                />
              );
            })}
          </div>
        )}
      </div>

      {showModal && (
        <CameraModal
          camera={editCamera}
          initialData={initialData}
          onClose={() => setShowModal(false)}
          onSave={() => { setShowModal(false); refresh(); }}
        />
      )}

      {configCamera && (
        <AnalyticsConfigModal
          camera={configCamera}
          onClose={() => setConfigCamera(null)}
        />
      )}

      {/* Delete confirmation modal */}
      {deleteTarget && (
        <div className="modal-backdrop" onClick={() => !deleting && setDeleteTarget(null)}>
          <div className="modal" style={{ maxWidth: 400 }} onClick={e => e.stopPropagation()}>
            <div className="modal-header">
              <span className="modal-title" style={{ color: 'var(--accent-red, #ef4444)' }}>
                <Trash2 size={16} style={{ verticalAlign: 'middle', marginRight: 6 }} />
                Eliminar camara
              </span>
            </div>
            <div className="modal-body" style={{ padding: '16px 20px', fontSize: 14 }}>
              <p style={{ marginBottom: 12 }}>
                Estas a punto de eliminar <strong>{deleteTarget.name}</strong>.
                Se detendra la transmision y se borrara toda la configuracion de analiticas.
              </p>
              <div style={{
                padding: '10px 14px', borderRadius: 8,
                background: 'rgba(239,68,68,0.08)',
                border: '1px solid rgba(239,68,68,0.2)',
                fontSize: 12, color: 'var(--text-muted)',
              }}>
                Las grabaciones en disco NO se eliminan automaticamente.
              </div>
            </div>
            <div className="modal-footer">
              <button className="btn btn-ghost" disabled={deleting}
                onClick={() => setDeleteTarget(null)}>Cancelar</button>
              <button
                style={{
                  background: 'var(--accent-red, #ef4444)',
                  color: 'white', border: 'none', borderRadius: 8,
                  padding: '7px 16px', fontWeight: 700, cursor: 'pointer',
                  opacity: deleting ? 0.6 : 1,
                }}
                disabled={deleting}
                onClick={confirmDelete}
              >
                {deleting ? 'Eliminando...' : 'Eliminar camara'}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}

// ─── Discovery Panel ──────────────────────────────────────────────────────────

function DiscoveryPanel({ onSelect }) {
  const [mode, setMode]           = useState('scan');   // 'scan' | 'manual'
  const [scanning, setScanning]   = useState(false);
  const [devices, setDevices]     = useState([]);
  const [probing, setProbing]     = useState(null);     // IP being probed
  const [manualIp, setManualIp]   = useState('');
  const [manualUser, setManualUser] = useState('admin');
  const [manualPass, setManualPass] = useState('');
  const [probeResult, setProbeResult] = useState(null);

  const scan = async () => {
    setScanning(true);
    setDevices([]);
    try {
      const data = await apiGet('/api/onvif/discover?timeout=4');
      setDevices(data.devices || []);
    } catch (e) {
      console.error('Discovery error:', e);
    } finally {
      setScanning(false);
    }
  };

  const probe = async (ip, user = 'admin', pass = '', xaddrs = []) => {
    setProbing(ip);
    setProbeResult(null);
    try {
      const result = await apiPost('/api/onvif/probe', { ip, user, password: pass, xaddrs });
      setProbeResult(result);
    } catch (e) {
      setProbeResult({ ip, onvif_ok: false, error: String(e), streams: [] });
    } finally {
      setProbing(null);
    }
  };

  const handleUseStream = (stream, deviceInfo = {}) => {
    onSelect({
      rtsp_url:     stream.rtsp_url,
      name:         deviceInfo.model
        ? `${deviceInfo.manufacturer} ${deviceInfo.model}`
        : `Cámara ${deviceInfo.ip || ''}`,
      location:     '',
      manufacturer: deviceInfo.manufacturer || '',
      model:        deviceInfo.model || '',
    });
  };

  return (
    <div className="card">
      <div className="card-header">
        <span className="card-title"><Radio size={14} /> Detección de cámaras IP</span>
        <div style={{ display: 'flex', gap: 6 }}>
          <button
            className={`btn btn-sm ${mode === 'scan' ? 'btn-primary' : 'btn-ghost'}`}
            onClick={() => setMode('scan')}
          >
            <ScanLine size={13} /> Escanear red
          </button>
          <button
            className={`btn btn-sm ${mode === 'manual' ? 'btn-primary' : 'btn-ghost'}`}
            onClick={() => setMode('manual')}
          >
            <Search size={13} /> IP manual
          </button>
        </div>
      </div>

      <div className="card-body">
        {mode === 'scan' && (
          <>
            <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 14 }}>
              <button className="btn btn-primary" onClick={scan} disabled={scanning}>
                {scanning
                  ? <><Loader size={13} style={{ animation: 'spin 0.8s linear infinite' }} /> Escaneando red...</>
                  : <><ScanLine size={13} /> Buscar cámaras ONVIF</>
                }
              </button>
              <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>
                Detecta automáticamente todas las cámaras ONVIF en tu red local
              </span>
            </div>

            {devices.length > 0 && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                {devices.map(dev => (
                  <DiscoveredDevice
                    key={dev.ip}
                    device={dev}
                    probing={probing === dev.ip}
                    onProbe={(user, pass) => probe(dev.ip, user, pass)}
                    onUse={handleUseStream}
                    probeResult={probeResult?.ip === dev.ip ? probeResult : null}
                  />
                ))}
              </div>
            )}

            {!scanning && devices.length === 0 && (
              <div style={{
                padding: '10px 14px', fontSize: 12, color: 'var(--text-muted)',
                background: 'rgba(59,130,246,0.06)', borderRadius: 8,
                border: '1px solid rgba(59,130,246,0.12)',
                display: 'flex', gap: 8, alignItems: 'flex-start',
              }}>
                <Info size={14} style={{ color: 'var(--accent-blue)', flexShrink: 0, marginTop: 1 }} />
                <span>
                  El escaneo usa WS-Discovery (protocolo ONVIF estándar). Compatible con Hikvision,
                  Dahua, Axis, Hanwha, Bosch, Uniview, Reolink y cualquier cámara ONVIF.
                  Asegúrate de estar en la misma red.
                </span>
              </div>
            )}
          </>
        )}

        {mode === 'manual' && (
          <ManualProbe
            onProbe={probe}
            probing={probing}
            probeResult={probeResult}
            onUse={handleUseStream}
          />
        )}
      </div>

      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  );
}

function DiscoveredDevice({ device, probing, onProbe, onUse, probeResult }) {
  const [expanded, setExpanded] = useState(false);
  const [creds, setCreds] = useState({ user: 'admin', pass: '' });

  return (
    <div style={{
      border: '1px solid var(--border)',
      borderRadius: 8,
      overflow: 'hidden',
      background: 'var(--bg-card)',
    }}>
      <div style={{
        display: 'flex', alignItems: 'center', gap: 10,
        padding: '10px 14px',
      }}>
        <div style={{
          width: 8, height: 8, borderRadius: '50%',
          background: 'var(--accent-green)',
          flexShrink: 0,
        }} />
        <div style={{ flex: 1 }}>
          <div style={{ fontWeight: 600, fontSize: 13 }}>{device.ip}</div>
          {device.xaddrs?.length > 0 && (
            <div style={{ fontSize: 11, color: 'var(--text-muted)', fontFamily: 'monospace' }}>
              {device.xaddrs[0]}
            </div>
          )}
        </div>
        <button
          className="btn btn-ghost btn-sm"
          onClick={() => setExpanded(e => !e)}
        >
          {expanded ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
          Conectar
        </button>
      </div>

      {expanded && (
        <div style={{ padding: '0 14px 14px', borderTop: '1px solid var(--border)' }}>
          <div style={{ display: 'flex', gap: 8, marginTop: 10 }}>
            <div className="form-group" style={{ flex: 1, marginBottom: 0 }}>
              <label className="form-label" style={{ fontSize: 11 }}>Usuario</label>
              <input className="form-input" style={{ padding: '6px 10px', fontSize: 12 }}
                value={creds.user}
                onChange={e => setCreds(p => ({ ...p, user: e.target.value }))} />
            </div>
            <div className="form-group" style={{ flex: 1, marginBottom: 0 }}>
              <label className="form-label" style={{ fontSize: 11 }}>Contraseña</label>
              <input className="form-input" type="password" style={{ padding: '6px 10px', fontSize: 12 }}
                value={creds.pass}
                onChange={e => setCreds(p => ({ ...p, pass: e.target.value }))}
                onKeyDown={e => e.key === 'Enter' && onProbe(creds.user, creds.pass)} />
            </div>
            <div style={{ alignSelf: 'flex-end' }}>
              <button className="btn btn-primary btn-sm" onClick={() => onProbe(creds.user, creds.pass)} disabled={probing}>
                {probing
                  ? <Loader size={12} style={{ animation: 'spin 0.8s linear infinite' }} />
                  : <Search size={12} />
                }
              </button>
            </div>
          </div>

          {probeResult && (
            <ProbeResults result={probeResult} onUse={(stream) => onUse(stream, probeResult)} />
          )}
        </div>
      )}
    </div>
  );
}

function ManualProbe({ onProbe, probing, probeResult, onUse }) {
  const [ip, setIp]     = useState('');
  const [user, setUser] = useState('admin');
  const [pass, setPass] = useState('');

  return (
    <div>
      <div style={{ display: 'flex', gap: 8, marginBottom: 12, flexWrap: 'wrap' }}>
        <div className="form-group" style={{ flex: '2 1 160px', marginBottom: 0 }}>
          <label className="form-label">Dirección IP</label>
          <input id="manual-ip-input" className="form-input"
            placeholder="192.168.1.100" value={ip}
            onChange={e => setIp(e.target.value)} />
        </div>
        <div className="form-group" style={{ flex: '1 1 100px', marginBottom: 0 }}>
          <label className="form-label">Usuario</label>
          <input className="form-input" value={user}
            onChange={e => setUser(e.target.value)} />
        </div>
        <div className="form-group" style={{ flex: '1 1 100px', marginBottom: 0 }}>
          <label className="form-label">Contraseña</label>
          <input className="form-input" type="password" value={pass}
            onChange={e => setPass(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && ip && onProbe(ip, user, pass)} />
        </div>
        <div style={{ alignSelf: 'flex-end' }}>
          <button className="btn btn-primary" onClick={() => onProbe(ip, user, pass)}
            disabled={!ip || !!probing}>
            {probing
              ? <><Loader size={13} style={{ animation: 'spin 0.8s linear infinite' }} /> Probando...</>
              : <><Search size={13} /> Conectar</>
            }
          </button>
        </div>
      </div>

      <div style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 12 }}>
        Detecta automáticamente el fabricante y obtiene las URLs RTSP disponibles vía ONVIF.
        Compatible con cualquier marca: Hikvision, Dahua, Axis, Hanwha, Bosch, Uniview, Reolink, etc.
      </div>

      {probeResult && (
        <ProbeResults result={probeResult} onUse={(stream) => onUse(stream, probeResult)} />
      )}
    </div>
  );
}

function ProbeResults({ result, onUse }) {
  if (!result.onvif_ok && result.streams.length === 0) {
    return (
      <div style={{
        marginTop: 10, padding: '10px 14px', fontSize: 12,
        color: 'var(--accent-red)', background: 'rgba(239,68,68,0.08)',
        borderRadius: 6, border: '1px solid rgba(239,68,68,0.15)',
      }}>
        No se pudo conectar vía ONVIF. Verifica la IP, usuario y contraseña.
        {result.error && <div style={{ marginTop: 4, opacity: 0.7 }}>{result.error}</div>}
      </div>
    );
  }

  return (
    <div style={{ marginTop: 10 }}>
      {/* Device info */}
      {result.onvif_ok && (
        <div style={{
          display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 10,
        }}>
          {result.manufacturer && result.manufacturer !== 'Unknown' && (
            <span className="badge badge-blue">{result.manufacturer}</span>
          )}
          {result.model && result.model !== 'Unknown' && (
            <span className="badge badge-gray">{result.model}</span>
          )}
          {result.firmware && (
            <span className="badge badge-gray">FW: {result.firmware}</span>
          )}
          <span className={`badge ${result.streams_source === 'onvif' ? 'badge-green' : 'badge-amber'}`}>
            {result.streams_source === 'onvif' ? 'ONVIF' : result.streams_source === 'brand_patterns' ? 'Patrón de marca' : 'Fallback genérico'}
          </span>
        </div>
      )}

      {/* Stream URLs */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        {result.streams.map((s, i) => (
          <div key={i} style={{
            display: 'flex', alignItems: 'center', gap: 8,
            padding: '8px 12px', borderRadius: 6,
            background: 'var(--bg-body)',
            border: '1px solid var(--border)',
            fontSize: 12,
          }}>
            <Camera size={12} style={{ flexShrink: 0, opacity: 0.6 }} />
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontWeight: 600, marginBottom: 2 }}>{s.label}</div>
              <div style={{
                fontFamily: 'monospace', fontSize: 11,
                color: 'var(--text-muted)',
                overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
              }}>
                {s.rtsp_url}
              </div>
            </div>
            <button
              className="btn btn-primary btn-sm"
              style={{ whiteSpace: 'nowrap', fontSize: 11 }}
              onClick={() => onUse(s)}
            >
              <Plus size={11} /> Usar
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}

// ─── Camera Card ──────────────────────────────────────────────────────────────

function CameraCard({ camera, connected, fps, onEdit, onDelete, onConfig }) {
  const enabledAnalytics = Object.entries(camera.analytics_config || {})
    .filter(([, v]) => v)
    .map(([k]) => k);

  return (
    <div className="card">
      <div className="card-header">
        <span className="card-title">
          {connected
            ? <Wifi size={14} style={{ color: 'var(--accent-green)' }} />
            : <WifiOff size={14} style={{ color: 'var(--accent-red)' }} />
          }
          {camera.name}
        </span>
        <div style={{ display: 'flex', gap: 6 }}>
          <button
            className="btn btn-ghost btn-sm"
            onClick={onConfig}
            title="Configurar analíticas"
            style={{ gap: 5 }}
          >
            <SlidersHorizontal size={12} />
            <span style={{ fontSize: 11 }}>Analíticas</span>
          </button>
          <button className="btn btn-ghost btn-sm btn-icon" onClick={onEdit}>
            <Pencil size={13} />
          </button>
          <button className="btn btn-danger btn-sm btn-icon" onClick={onDelete}>
            <Trash2 size={13} />
          </button>
        </div>
      </div>

      <div className="card-body">
        {/* RTSP URL */}
        <div style={{
          fontSize: 11, color: 'var(--text-muted)',
          marginBottom: 10, wordBreak: 'break-all',
          fontFamily: 'monospace',
          background: 'var(--bg-card)',
          padding: '6px 10px', borderRadius: 6,
          border: '1px solid var(--border)',
        }}>
          {camera.rtsp_url}
        </div>

        {/* Badges */}
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginBottom: 12 }}>
          <span className={`badge ${connected ? 'badge-green' : 'badge-red'}`}>
            {connected ? `${(fps || 0).toFixed(0)} FPS` : 'Desconectada'}
          </span>
          {camera.location && (
            <span className="badge badge-gray">{camera.location}</span>
          )}
          <span className="badge badge-gray">Skip {camera.frame_skip}</span>
        </div>

        {/* Active analytics icons */}
        {enabledAnalytics.length > 0 && (
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
            {enabledAnalytics.map(key => {
              const Icon = ANALYTIC_ICONS[key];
              const opt  = ANALYTICS_OPTIONS.find(o => o.key === key);
              if (!Icon) return null;
              return (
                <span key={key} title={opt?.label || key} style={{
                  display: 'flex', alignItems: 'center', gap: 4,
                  padding: '3px 8px', borderRadius: 6, fontSize: 11,
                  background: 'rgba(59,130,246,0.08)',
                  border: '1px solid rgba(59,130,246,0.15)',
                  color: 'var(--accent-blue)',
                }}>
                  <Icon size={11} />
                  {opt?.label || key}
                </span>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}

// ─── Camera Modal ─────────────────────────────────────────────────────────────

function CameraModal({ camera, initialData, onClose, onSave }) {
  const [form, setForm] = useState({
    name:             camera?.name             || initialData?.name     || '',
    rtsp_url:         camera?.rtsp_url         || initialData?.rtsp_url || '',
    location:         camera?.location         || initialData?.location || '',
    frame_skip:       camera?.frame_skip       ?? 3,
    resolution_w:     camera?.resolution_w     ?? 0,
    resolution_h:     camera?.resolution_h     ?? 0,
    fps:              camera?.fps              ?? 0,
    analytics_config: camera?.analytics_config || {},
  });
  const [saving, setSaving] = useState(false);

  const set = (k, v) => setForm(p => ({ ...p, [k]: v }));
  const toggleAnalytic = (key) => setForm(p => ({
    ...p,
    analytics_config: { ...p.analytics_config, [key]: !p.analytics_config[key] },
  }));

  const handleSave = async () => {
    setSaving(true);
    try {
      if (camera) {
        await apiPatch(`/api/cameras/${camera.id}`, form);
      } else {
        await apiPost('/api/cameras/', form);
      }
      onSave();
    } catch (e) {
      alert('Error: ' + e.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" style={{ maxHeight: '90vh', overflowY: 'auto' }} onClick={e => e.stopPropagation()}>
        <div className="modal-header">
          <span className="modal-title">
            {camera ? 'Editar cámara' : 'Nueva cámara'}
          </span>
          <button className="btn btn-ghost btn-icon" onClick={onClose}><X size={16} /></button>
        </div>

        <div className="modal-body">
          {initialData?.manufacturer && (
            <div style={{
              padding: '8px 12px', marginBottom: 12,
              background: 'rgba(16,185,129,0.08)',
              border: '1px solid rgba(16,185,129,0.15)',
              borderRadius: 6, fontSize: 12,
              display: 'flex', gap: 8, alignItems: 'center',
            }}>
              <Check size={13} style={{ color: 'var(--accent-green)' }} />
              Cámara detectada: {initialData.manufacturer} {initialData.model}
            </div>
          )}

          <div className="form-group">
            <label className="form-label">Nombre</label>
            <input id="cam-name" className="form-input"
              value={form.name}
              onChange={e => set('name', e.target.value)}
              placeholder="Entrada principal" />
          </div>

          <div className="form-group">
            <label className="form-label">URL RTSP</label>
            <input id="cam-rtsp" className="form-input"
              value={form.rtsp_url}
              onChange={e => set('rtsp_url', e.target.value)}
              placeholder="rtsp://usuario:pass@192.168.1.x:554/stream" />
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
            <div className="form-group">
              <label className="form-label">Ubicacion</label>
              <input className="form-input"
                value={form.location}
                onChange={e => set('location', e.target.value)}
                placeholder="Planta baja" />
            </div>
            <div className="form-group">
              <label className="form-label">FPS de procesamiento IA</label>
              <select className="form-select" value={form.frame_skip}
                onChange={e => set('frame_skip', +e.target.value)}>
                <option value={1}>Maximo (~25 FPS) — mayor CPU</option>
                <option value={2}>Alto (~12 FPS)</option>
                <option value={3}>Normal (~8 FPS) — recomendado</option>
                <option value={5}>Reducido (~5 FPS)</option>
                <option value={8}>Bajo (~3 FPS) — menor CPU</option>
                <option value={15}>Minimo (~2 FPS) — modo ahorro</option>
              </select>
              <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 4 }}>
                Controla cada cuantos frames del stream procesa la IA. Menor FPS = menos carga de CPU.
              </div>
            </div>
          </div>

          {/* Resolution + FPS cap */}
          <div style={{
            padding: '12px 14px', borderRadius: 10,
            border: '1px solid var(--border)',
            background: 'var(--bg-body)',
            marginBottom: 4,
          }}>
            <div style={{ fontWeight: 700, fontSize: 12, marginBottom: 10, color: 'var(--text-muted)' }}>
              Calidad del stream en este sistema
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
              <div className="form-group" style={{ marginBottom: 0 }}>
                <label className="form-label">Resolucion maxima</label>
                <select className="form-select"
                  value={`${form.resolution_w}x${form.resolution_h}`}
                  onChange={e => {
                    const [w, h] = e.target.value.split('x').map(Number);
                    set('resolution_w', w); set('resolution_h', h);
                  }}>
                  <option value="0x0">Original (sin limite)</option>
                  <option value="1920x1080">1080p — Full HD</option>
                  <option value="1280x720">720p — recomendado</option>
                  <option value="854x480">480p — bajo consumo</option>
                  <option value="640x360">360p — minimo</option>
                </select>
              </div>
              <div className="form-group" style={{ marginBottom: 0 }}>
                <label className="form-label">FPS maximo del stream</label>
                <select className="form-select" value={form.fps}
                  onChange={e => set('fps', +e.target.value)}>
                  <option value={0}>Sin limite (original)</option>
                  <option value={25}>25 FPS</option>
                  <option value={15}>15 FPS — recomendado</option>
                  <option value={10}>10 FPS</option>
                  <option value={5}>5 FPS — bajo consumo</option>
                </select>
              </div>
            </div>
            <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 8 }}>
              La camara seguira transmitiendo a su resolucion original — el sistema redimensiona y
              limita en software sin afectar la configuracion de la camara.
            </div>
          </div>

          <div>
            <label className="form-label" style={{ display: 'block', marginBottom: 8 }}>
              Analíticas IA
            </label>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 7 }}>
              {ANALYTICS_OPTIONS.map(opt => {
                const Icon = ANALYTIC_ICONS[opt.key] || Camera;
                return (
                  <label key={opt.key} className="toggle">
                    <input
                      type="checkbox"
                      checked={!!form.analytics_config[opt.key]}
                      onChange={() => toggleAnalytic(opt.key)}
                    />
                    <div className="toggle-track"><div className="toggle-thumb" /></div>
                    <Icon size={13} style={{ opacity: 0.7 }} />
                    <span style={{ fontSize: 13 }}>{opt.label}</span>
                  </label>
                );
              })}
            </div>
          </div>
        </div>

        <div className="modal-footer">
          <button className="btn btn-ghost" onClick={onClose}>Cancelar</button>
          <button
            id="save-camera-btn"
            className="btn btn-primary"
            onClick={handleSave}
            disabled={saving || !form.name || !form.rtsp_url}
          >
            {saving ? 'Guardando...' : <><Check size={14} /> Guardar</>}
          </button>
        </div>
      </div>
    </div>
  );
}

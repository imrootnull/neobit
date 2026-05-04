import { useState, useEffect } from 'react';
import { apiGet, apiPost } from '../api';
import { useWS } from '../context/WSContext';
import CameraGrid from '../components/CameraGrid';
import AlertFeed from '../components/AlertFeed';
import { ANALYTIC_ICONS, CATEGORY_ICONS, SEVERITY_COLORS, getSeverityIcon } from '../components/Icons';
import {
  ChevronDown, ChevronRight, Cpu, Upload, Plus, X, Check,
  AlertTriangle, Info
} from 'lucide-react';

const CATEGORY_META = {
  detection:   { label: 'Detección',                     color: 'var(--accent-blue)' },
  counting:    { label: 'Conteo',                         color: 'var(--accent-cyan)' },
  safety:      { label: 'Seguridad Industrial / EPP',    color: 'var(--accent-amber)' },
  security:    { label: 'Seguridad y Perímetro',         color: 'var(--accent-red)' },
  fire:        { label: 'Fuego, Humo y Riesgos',         color: '#f97316' },
  behavior:    { label: 'Comportamiento',                color: 'var(--accent-purple)' },
  traffic:     { label: 'Tráfico y Smart City',          color: '#14b8a6' },
  retail:      { label: 'Retail y Comercio',             color: '#ec4899' },
  health:      { label: 'Salud y Hospitales',            color: '#22c55e' },
  industrial:  { label: 'Industria Pesada / Oil & Gas',  color: '#ca8a04' },
  privacy:     { label: 'Privacidad y Cumplimiento',     color: '#64748b' },
  ai_advanced: { label: 'IA Avanzada',                   color: '#7c3aed' },
  facial_ai:   { label: 'IA Facial',                     color: '#db2777' },
  custom:      { label: 'IA Personalizada (Clientes)',   color: 'var(--accent-green)' },
};

const PHASE_LABELS = {
  1: { label: 'Disponible',   badge: 'badge-green'  },
  2: { label: 'Fase 2',      badge: 'badge-blue'   },
  3: { label: 'Fase 3',      badge: 'badge-amber'  },
  4: { label: 'Fase 4',      badge: 'badge-purple' },
  5: { label: 'Fase 5',      badge: 'badge-gray'   },
};

export default function Analytics() {
  const [catalog, setCatalog]           = useState({});
  const [customModels, setCustomModels] = useState([]);
  const [expanded, setExpanded]         = useState({});
  const [showUpload, setShowUpload]     = useState(false);

  useEffect(() => {
    apiGet('/api/models/catalog').then(setCatalog).catch(console.error);
    apiGet('/api/models/').then(setCustomModels).catch(console.error);
  }, []);

  const totalAnalytics = Object.values(catalog).flat().length;
  const toggle = (cat) => setExpanded(p => ({ ...p, [cat]: !p[cat] }));

  return (
    <>
      <div className="page-header">
        <div>
          <h1 className="page-title">Analíticas IA</h1>
          <p className="page-subtitle">
            {totalAnalytics > 0
              ? `${totalAnalytics} módulos analíticos disponibles en ${Object.keys(catalog).length} categorías`
              : 'Catálogo completo de módulos analíticos'}
          </p>
        </div>
        <button className="btn btn-primary" onClick={() => setShowUpload(true)}>
          <Upload size={14} /> Subir modelo custom
        </button>
      </div>

      <div className="page-content" style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>

        {Object.entries(CATEGORY_META).map(([catKey, catMeta]) => {
          const items  = catalog[catKey] || [];
          if (!items.length) return null;
          const CatIcon = CATEGORY_ICONS[catKey] || Info;
          const isOpen  = expanded[catKey] !== false;

          return (
            <div key={catKey} className="card">
              <div
                className="card-header"
                style={{ cursor: 'pointer', userSelect: 'none' }}
                onClick={() => toggle(catKey)}
              >
                <span className="card-title" style={{ fontSize: 14 }}>
                  <CatIcon size={16} style={{ color: catMeta.color }} />
                  {catMeta.label}
                  <span className="badge badge-gray" style={{ marginLeft: 6 }}>
                    {items.length}
                  </span>
                </span>
                {isOpen
                  ? <ChevronDown size={16} style={{ color: 'var(--text-muted)' }} />
                  : <ChevronRight size={16} style={{ color: 'var(--text-muted)' }} />
                }
              </div>

              {isOpen && (
                <div style={{
                  display: 'grid',
                  gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))',
                  gap: 10,
                  padding: '12px 16px',
                }}>
                  {items.map(analytic => (
                    <AnalyticCard
                      key={analytic.key}
                      analytic={analytic}
                      accentColor={catMeta.color}
                    />
                  ))}
                </div>
              )}
            </div>
          );
        })}

        {/* Custom models */}
        <div className="card">
          <div className="card-header">
            <span className="card-title">
              <Cpu size={14} />
              Modelos IA personalizados
            </span>
            <button className="btn btn-primary btn-sm" onClick={() => setShowUpload(true)}>
              <Plus size={13} /> Subir modelo
            </button>
          </div>
          <div className="card-body">
            {customModels.length === 0 ? (
              <div className="empty-state" style={{ padding: '24px 0' }}>
                <Cpu size={28} style={{ opacity: 0.2 }} />
                <div className="empty-title">Sin modelos personalizados</div>
                <div className="empty-desc">
                  Sube modelos YOLOv8 entrenados para uniformes, objetos
                  específicos o cualquier necesidad de un cliente.
                </div>
              </div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                {customModels.map(m => (
                  <CustomModelRow key={m.id} model={m} />
                ))}
              </div>
            )}
          </div>
        </div>

      </div>

      {showUpload && (
        <UploadModelModal
          onClose={() => setShowUpload(false)}
          onSave={() => {
            setShowUpload(false);
            apiGet('/api/models/').then(setCustomModels);
          }}
        />
      )}
    </>
  );
}

function AnalyticCard({ analytic, accentColor }) {
  const AnalIcon = ANALYTIC_ICONS[analytic.key] || Info;
  const phase    = PHASE_LABELS[analytic.phase]  || PHASE_LABELS[5];

  return (
    <div
      className="card"
      style={{ padding: '12px 14px', display: 'flex', flexDirection: 'column', gap: 6 }}
      onMouseEnter={e => e.currentTarget.style.borderColor = accentColor + '55'}
      onMouseLeave={e => e.currentTarget.style.borderColor = 'var(--border)'}
    >
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <div style={{
            width: 32, height: 32,
            borderRadius: 8,
            background: accentColor + '18',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            flexShrink: 0,
          }}>
            <AnalIcon size={16} style={{ color: accentColor }} />
          </div>
          <span style={{ fontWeight: 600, fontSize: 13, lineHeight: 1.2 }}>
            {analytic.label}
          </span>
        </div>
        <span className={`badge ${phase.badge}`} style={{ fontSize: 10, whiteSpace: 'nowrap' }}>
          {phase.label}
        </span>
      </div>
      <p style={{ fontSize: 12, color: 'var(--text-muted)', lineHeight: 1.5, margin: 0 }}>
        {analytic.description}
      </p>
    </div>
  );
}

function CustomModelRow({ model }) {
  const { Bot } = require('../components/Icons');
  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 12,
      padding: '10px 14px',
      borderRadius: 'var(--radius-sm)',
      background: 'var(--bg-card)',
      border: '1px solid var(--border)',
    }}>
      <div style={{
        width: 36, height: 36, borderRadius: 8,
        background: 'rgba(16,185,129,0.12)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        flexShrink: 0,
      }}>
        <Cpu size={16} style={{ color: 'var(--accent-green)' }} />
      </div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontWeight: 600, fontSize: 13 }}>{model.name}</div>
        <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 2 }}>
          Cliente: {model.client}
          {' · '}{model.framework?.toUpperCase()}
          {' · '}{model.size_mb} MB
          {model.classes?.length > 0 && ` · ${model.classes.join(', ')}`}
        </div>
      </div>
      <span className="badge badge-green" style={{ fontSize: 11 }}>
        {model.analytics_key}
      </span>
    </div>
  );
}

function UploadModelModal({ onClose, onSave }) {
  const [form, setForm] = useState({
    name: '', client: '', description: '',
    classes: '', analytics_key: 'custom_detection',
  });
  const [file, setFile]         = useState(null);
  const [uploading, setUploading] = useState(false);

  const set = (k, v) => setForm(p => ({ ...p, [k]: v }));

  const handleUpload = async () => {
    if (!file || !form.name || !form.client) return;
    setUploading(true);
    try {
      const fd = new FormData();
      Object.entries(form).forEach(([k, v]) => fd.append(k, v));
      fd.append('file', file);
      const res = await fetch('/api/models/upload', { method: 'POST', body: fd });
      if (!res.ok) throw new Error(await res.text());
      onSave();
    } catch (e) {
      alert('Error: ' + e.message);
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={e => e.stopPropagation()}>
        <div className="modal-header">
          <span className="modal-title">Subir modelo IA personalizado</span>
          <button className="btn btn-ghost btn-icon" onClick={onClose}><X size={16} /></button>
        </div>
        <div className="modal-body">
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
            <div className="form-group">
              <label className="form-label">Nombre del modelo</label>
              <input className="form-input" value={form.name}
                onChange={e => set('name', e.target.value)}
                placeholder="Uniforme ACME Corp" />
            </div>
            <div className="form-group">
              <label className="form-label">Cliente</label>
              <input className="form-input" value={form.client}
                onChange={e => set('client', e.target.value)}
                placeholder="ACME Corp" />
            </div>
          </div>
          <div className="form-group">
            <label className="form-label">Clases detectadas (separadas por coma)</label>
            <input className="form-input" value={form.classes}
              onChange={e => set('classes', e.target.value)}
              placeholder="uniforme_azul, uniforme_rojo, sin_uniforme" />
          </div>
          <div className="form-group">
            <label className="form-label">Descripción</label>
            <input className="form-input" value={form.description}
              onChange={e => set('description', e.target.value)}
              placeholder="Detección de uniforme corporativo..." />
          </div>
          <div className="form-group">
            <label className="form-label">Archivo del modelo (.pt, .tflite, .onnx)</label>
            <input type="file" accept=".pt,.tflite,.onnx"
              className="form-input"
              onChange={e => setFile(e.target.files[0])}
              style={{ padding: '7px 12px' }} />
          </div>
          <div style={{
            padding: '10px 14px',
            background: 'rgba(59,130,246,0.08)',
            borderRadius: 'var(--radius-sm)',
            border: '1px solid rgba(59,130,246,0.15)',
            fontSize: 12,
            color: 'var(--text-muted)',
            display: 'flex', gap: 8, alignItems: 'flex-start',
          }}>
            <Info size={14} style={{ color: 'var(--accent-blue)', flexShrink: 0, marginTop: 1 }} />
            <span>
              Soporta modelos YOLOv8 (.pt), TFLite (.tflite para Coral) y ONNX (.onnx).
              Entrena con tus datos y sube el modelo aquí para asignarlo a cualquier cámara.
            </span>
          </div>
        </div>
        <div className="modal-footer">
          <button className="btn btn-ghost" onClick={onClose}>Cancelar</button>
          <button className="btn btn-primary" onClick={handleUpload}
            disabled={uploading || !file || !form.name || !form.client}>
            {uploading ? 'Subiendo...' : <><Upload size={14} /> Subir modelo</>}
          </button>
        </div>
      </div>
    </div>
  );
}

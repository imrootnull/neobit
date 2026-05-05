/**
 * AnalyticsConfigModal
 * Per-camera analytics configuration with full parameter controls.
 * Supports: enable/disable, confidence threshold, zones, custom thresholds,
 * severity override, event rate limiting, and one-click test events.
 */
import { useState, useEffect } from 'react';
import { apiGet, apiPost } from '../api';
import {
  X, ChevronDown, ChevronRight, Check, Zap,
  SlidersHorizontal, AlertTriangle, Info
} from 'lucide-react';
import { ANALYTIC_ICONS, CATEGORY_ICONS } from './Icons';

const CATEGORY_LABELS = {
  detection:  'Detección',
  counting:   'Conteo',
  safety:     'Seguridad Industrial / EPP',
  security:   'Seguridad y Perímetro',
  fire:       'Fuego, Humo y Riesgos',
  behavior:   'Comportamiento',
  traffic:    'Tráfico y Smart City',
  retail:     'Retail y Comercio',
  health:     'Salud',
  industrial: 'Industria / Oil & Gas',
  privacy:    'Privacidad',
  ai_advanced:'IA Avanzada',
  facial_ai:  'IA Facial',
  custom:     'IA Personalizada',
};

const CATEGORY_COLORS = {
  detection:  '#3b82f6',
  counting:   '#06b6d4',
  safety:     '#f59e0b',
  security:   '#ef4444',
  fire:       '#f97316',
  behavior:   '#8b5cf6',
  traffic:    '#14b8a6',
  retail:     '#ec4899',
  health:     '#22c55e',
  industrial: '#ca8a04',
  privacy:    '#64748b',
  ai_advanced:'#7c3aed',
  facial_ai:  '#db2777',
  custom:     '#10b981',
};

const SEVERITY_OPTIONS = [
  { value: 'low',      label: 'Baja',     color: '#64748b' },
  { value: 'medium',   label: 'Media',    color: '#3b82f6' },
  { value: 'high',     label: 'Alta',     color: '#f59e0b' },
  { value: 'critical', label: 'Crítica',  color: '#ef4444' },
];

export default function AnalyticsConfigModal({ camera, onClose }) {
  const [analytics, setAnalytics] = useState([]);
  const [loading, setLoading]     = useState(true);
  const [saving, setSaving]       = useState(null);
  const [testing, setTesting]     = useState(null);
  const [expanded, setExpanded]   = useState({});

  useEffect(() => {
    apiGet(`/api/cameras/${camera.id}/analytics`)
      .then(data => {
        setAnalytics(data);
        // Auto-expand categories with enabled analytics
        const cats = {};
        data.filter(a => a.enabled).forEach(a => { cats[a.category] = true; });
        setExpanded(cats);
      })
      .finally(() => setLoading(false));
  }, [camera.id]);

  const grouped = analytics.reduce((acc, a) => {
    if (!acc[a.category]) acc[a.category] = [];
    acc[a.category].push(a);
    return acc;
  }, {});

  const toggleCategory = (cat) => setExpanded(p => ({ ...p, [cat]: !p[cat] }));

  const updateAnalytic = async (key, enabled, params) => {
    setSaving(key);
    try {
      await apiPost(
        `/api/cameras/${camera.id}/analytics/${key}`,
        { enabled, params },
        'PUT'
      );
      setAnalytics(prev => prev.map(a =>
        a.key === key ? { ...a, enabled, params: { ...a.params, ...params } } : a
      ));
    } catch (e) {
      alert('Error al guardar: ' + e.message);
    } finally {
      setSaving(null);
    }
  };

  const testEvent = async (key) => {
    setTesting(key);
    try {
      await apiPost(`/api/cameras/${camera.id}/analytics/${key}/test`, {});
    } catch (e) {
      console.error(e);
    } finally {
      setTimeout(() => setTesting(null), 1500);
    }
  };

  const enabledCount = analytics.filter(a => a.enabled).length;

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div
        className="modal"
        style={{ maxWidth: 740, maxHeight: '90vh', overflowY: 'auto' }}
        onClick={e => e.stopPropagation()}
      >
        <div className="modal-header">
          <div>
            <div className="modal-title">Analíticas — {camera.name}</div>
            <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 2 }}>
              {enabledCount} analítica{enabledCount !== 1 ? 's' : ''} activa{enabledCount !== 1 ? 's' : ''}
            </div>
          </div>
          <button className="btn btn-ghost btn-icon" onClick={onClose}>
            <X size={16} />
          </button>
        </div>

        <div className="modal-body" style={{ padding: '12px 16px' }}>
          {loading ? (
            <div className="empty-state" style={{ padding: 32 }}>
              <div style={{ width: 24, height: 24, borderRadius: '50%', border: '2px solid var(--border)', borderTopColor: 'var(--accent-blue)', animation: 'spin 0.8s linear infinite' }} />
            </div>
          ) : (
            Object.entries(CATEGORY_LABELS).map(([cat, catLabel]) => {
              const items = grouped[cat];
              if (!items?.length) return null;
              const CatIcon    = CATEGORY_ICONS[cat] || SlidersHorizontal;
              const catColor   = CATEGORY_COLORS[cat] || 'var(--text-muted)';
              const isOpen     = !!expanded[cat];
              const activeCount= items.filter(a => a.enabled).length;

              return (
                <div key={cat} style={{ marginBottom: 8 }}>
                  <div
                    style={{
                      display: 'flex', alignItems: 'center', gap: 8,
                      padding: '8px 12px', cursor: 'pointer',
                      borderRadius: 8,
                      background: isOpen ? 'rgba(255,255,255,0.03)' : 'transparent',
                      userSelect: 'none',
                    }}
                    onClick={() => toggleCategory(cat)}
                  >
                    <CatIcon size={15} style={{ color: catColor, flexShrink: 0 }} />
                    <span style={{ flex: 1, fontWeight: 600, fontSize: 13 }}>{catLabel}</span>
                    {activeCount > 0 && (
                      <span style={{
                        fontSize: 11, fontWeight: 700,
                        background: catColor + '22',
                        color: catColor,
                        padding: '1px 7px', borderRadius: 10,
                      }}>
                        {activeCount} activa{activeCount !== 1 ? 's' : ''}
                      </span>
                    )}
                    {isOpen
                      ? <ChevronDown size={14} style={{ color: 'var(--text-muted)' }} />
                      : <ChevronRight size={14} style={{ color: 'var(--text-muted)' }} />
                    }
                  </div>

                  {isOpen && (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 6, padding: '4px 0 8px 0' }}>
                      {items.map(analytic => (
                        <AnalyticRow
                          key={analytic.key}
                          analytic={analytic}
                          catColor={catColor}
                          saving={saving === analytic.key}
                          testing={testing === analytic.key}
                          onToggle={(enabled) => updateAnalytic(analytic.key, enabled, analytic.params)}
                          onParamChange={(params) => updateAnalytic(analytic.key, analytic.enabled, params)}
                          onTest={() => testEvent(analytic.key)}
                        />
                      ))}
                    </div>
                  )}
                </div>
              );
            })
          )}
        </div>

        <div className="modal-footer">
          <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>
            Los cambios se aplican en tiempo real sin reiniciar la cámara.
          </span>
          <button className="btn btn-primary" onClick={onClose}>
            <Check size={14} /> Listo
          </button>
        </div>
      </div>
      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  );
}

function AnalyticRow({ analytic, catColor, saving, testing, onToggle, onParamChange, onTest }) {
  const [expanded, setExpanded] = useState(false);
  const Icon = ANALYTIC_ICONS[analytic.key] || SlidersHorizontal;

  return (
    <div style={{
      borderRadius: 8,
      border: `1px solid ${analytic.enabled ? catColor + '33' : 'var(--border)'}`,
      background: analytic.enabled ? catColor + '08' : 'var(--bg-card)',
      overflow: 'hidden',
      transition: 'border-color 0.2s, background 0.2s',
    }}>
      {/* Row header */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: 10,
        padding: '9px 12px',
      }}>
        <div style={{
          width: 30, height: 30, borderRadius: 7, flexShrink: 0,
          background: analytic.enabled ? catColor + '20' : 'rgba(255,255,255,0.04)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
        }}>
          <Icon size={14} style={{ color: analytic.enabled ? catColor : 'var(--text-muted)' }} />
        </div>

        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{
            fontWeight: 600, fontSize: 12,
            color: analytic.enabled ? 'var(--text-primary)' : 'var(--text-muted)',
          }}>
            {analytic.label}
          </div>
        </div>

        {/* Test button — only when enabled */}
        {analytic.enabled && (
          <button
            className="btn btn-ghost btn-sm btn-icon"
            title="Disparar evento de prueba"
            onClick={(e) => { e.stopPropagation(); onTest(); }}
            disabled={testing}
            style={{ padding: '4px 8px', fontSize: 11, gap: 4 }}
          >
            {testing
              ? <div style={{ width: 10, height: 10, borderRadius: '50%', border: '2px solid var(--border)', borderTopColor: 'var(--accent-blue)', animation: 'spin 0.8s linear infinite' }} />
              : <Zap size={11} style={{ color: 'var(--accent-blue)' }} />
            }
          </button>
        )}

        {/* Config expand */}
        {analytic.enabled && (
          <button
            className="btn btn-ghost btn-sm btn-icon"
            title="Configurar parámetros"
            onClick={() => setExpanded(e => !e)}
            style={{ padding: '4px' }}
          >
            <SlidersHorizontal size={12} style={{ color: 'var(--text-muted)' }} />
          </button>
        )}

        {/* Enable/disable toggle */}
        <label className="toggle" style={{ margin: 0 }} onClick={e => e.stopPropagation()}>
          <input
            type="checkbox"
            checked={analytic.enabled}
            onChange={e => onToggle(e.target.checked)}
            disabled={saving}
          />
          <div className="toggle-track"><div className="toggle-thumb" /></div>
        </label>
      </div>

      {/* Params panel */}
      {analytic.enabled && expanded && (
        <ParamsPanel
          analytic={analytic}
          catColor={catColor}
          saving={saving}
          onSave={onParamChange}
        />
      )}
    </div>
  );
}

function ParamsPanel({ analytic, catColor, saving, onSave }) {
  const [local, setLocal] = useState({ ...analytic.params });

  const set = (k, v) => setLocal(p => ({ ...p, [k]: v }));
  const hasChanges = JSON.stringify(local) !== JSON.stringify(analytic.params);

  return (
    <div style={{
      borderTop: `1px solid ${catColor}22`,
      padding: '12px 14px',
      background: 'rgba(0,0,0,0.15)',
    }}>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10, marginBottom: 10 }}>

        {/* Confidence threshold */}
        {'confidence' in local && (
          <div className="form-group" style={{ flex: '1 1 160px', marginBottom: 0 }}>
            <label className="form-label" style={{ fontSize: 11 }}>
              Confianza mínima: <strong>{Math.round((local.confidence || 0.5) * 100)}%</strong>
            </label>
            <input
              type="range" min={0.3} max={0.99} step={0.01}
              value={local.confidence || 0.5}
              onChange={e => set('confidence', parseFloat(e.target.value))}
              style={{ width: '100%', accentColor: catColor }}
            />
          </div>
        )}

        {/* Severity override */}
        <div className="form-group" style={{ flex: '0 1 160px', marginBottom: 0 }}>
          <label className="form-label" style={{ fontSize: 11 }}>Severidad de alerta</label>
          <select
            className="form-select"
            value={local.severity_override || ''}
            onChange={e => set('severity_override', e.target.value || undefined)}
            style={{ fontSize: 12, padding: '5px 8px' }}
          >
            <option value="">Automática</option>
            {SEVERITY_OPTIONS.map(s => (
              <option key={s.value} value={s.value}>{s.label}</option>
            ))}
          </select>
        </div>

        {/* Alert cooldown */}
        <div className="form-group" style={{ flex: '0 1 140px', marginBottom: 0 }}>
          <label className="form-label" style={{ fontSize: 11 }}>
            Intervalo mínimo (s)
          </label>
          <input
            className="form-input"
            type="number" min={5} max={3600}
            style={{ padding: '5px 8px', fontSize: 12 }}
            value={local.min_event_interval_s || 20}
            onChange={e => set('min_event_interval_s', parseInt(e.target.value))}
          />
        </div>

        {/* EPP-specific */}
        {'required_ppe' in local && (() => {
          const EPP_ITEMS = [
            { key: 'helmet',   label: 'Casco',       zone: 'cabeza',  icon: '🪖' },
            { key: 'vest',     label: 'Chaleco',      zone: 'torso',   icon: '🦺' },
            { key: 'gloves',   label: 'Guantes',      zone: 'manos',   icon: '🧤' },
            { key: 'goggles',  label: 'Lentes',       zone: 'cara',    icon: '🥽' },
            { key: 'mask',     label: 'Mascarilla',   zone: 'cara',    icon: '😷' },
            { key: 'shoes',    label: 'Botas',        zone: 'pies',    icon: '👢' },
            { key: 'overalls', label: 'Overol',       zone: 'cuerpo',  icon: '👔' },
          ];
          return (
            <div className="form-group" style={{ flex: '1 1 100%', marginBottom: 0 }}>
              <label className="form-label" style={{ fontSize: 11 }}>
                EPP requerido — se valida colocación correcta en zona corporal
              </label>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                {EPP_ITEMS.map(({ key, label, zone, icon }) => {
                  const checked = (local.required_ppe || []).includes(key);
                  return (
                    <label key={key} style={{
                      display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer',
                      padding: '5px 11px', borderRadius: 8, fontSize: 12,
                      background: checked ? catColor + '22' : 'rgba(255,255,255,0.04)',
                      border: `1px solid ${checked ? catColor + '66' : 'var(--border)'}`,
                      color: checked ? catColor : 'var(--text-muted)',
                      transition: 'all 0.15s',
                      userSelect: 'none',
                    }}>
                      <input type="checkbox" style={{ display: 'none' }}
                        checked={checked}
                        onChange={() => {
                          const arr = local.required_ppe || [];
                          set('required_ppe', checked ? arr.filter(x => x !== key) : [...arr, key]);
                        }}
                      />
                      <span style={{ fontSize: 15 }}>{icon}</span>
                      <span style={{ fontWeight: 600 }}>{label}</span>
                      <span style={{
                        fontSize: 10, opacity: 0.7,
                        background: 'rgba(0,0,0,0.2)', borderRadius: 4,
                        padding: '1px 5px',
                      }}>{zone}</span>
                    </label>
                  );
                })}
              </div>
              {(local.required_ppe || []).length === 0 && (
                <div style={{ fontSize: 11, color: '#f59e0b', marginTop: 6 }}>
                  ⚠️ Selecciona al menos un EPP para activar la detección de incumplimiento
                </div>
              )}
            </div>
          );
        })()}

        {/* Crowd max density */}
        {'max_density' in local && (
          <div className="form-group" style={{ flex: '0 1 160px', marginBottom: 0 }}>
            <label className="form-label" style={{ fontSize: 11 }}>Densidad máxima (personas)</label>
            <input className="form-input" type="number" min={1} max={100}
              style={{ padding: '5px 8px', fontSize: 12 }}
              value={local.max_density || 5}
              onChange={e => set('max_density', parseInt(e.target.value))}
            />
          </div>
        )}

        {/* Loitering dwell time */}
        {'max_dwell_seconds' in local && (
          <div className="form-group" style={{ flex: '0 1 180px', marginBottom: 0 }}>
            <label className="form-label" style={{ fontSize: 11 }}>Tiempo máximo en zona (s)</label>
            <input className="form-input" type="number" min={5} max={600}
              style={{ padding: '5px 8px', fontSize: 12 }}
              value={local.max_dwell_seconds || 30}
              onChange={e => set('max_dwell_seconds', parseInt(e.target.value))}
            />
          </div>
        )}

        {/* Speed limit */}
        {'max_speed_kmh' in local && (
          <div className="form-group" style={{ flex: '0 1 180px', marginBottom: 0 }}>
            <label className="form-label" style={{ fontSize: 11 }}>Velocidad máxima (km/h)</label>
            <input className="form-input" type="number" min={5} max={200}
              style={{ padding: '5px 8px', fontSize: 12 }}
              value={local.max_speed_kmh || 20}
              onChange={e => set('max_speed_kmh', parseInt(e.target.value))}
            />
          </div>
        )}

        {/* Face recognition mode */}
        {'mode' in local && ['whitelist','blacklist','all'].includes(local.mode) && (
          <div className="form-group" style={{ flex: '0 1 200px', marginBottom: 0 }}>
            <label className="form-label" style={{ fontSize: 11 }}>Modo de reconocimiento</label>
            <select className="form-select"
              value={local.mode}
              onChange={e => set('mode', e.target.value)}
              style={{ fontSize: 12, padding: '5px 8px' }}
            >
              <option value="whitelist">Lista blanca (alertar desconocidos)</option>
              <option value="blacklist">Lista negra (alertar registrados)</option>
              <option value="all">Todos (registrar todas las identidades)</option>
            </select>
          </div>
        )}

      </div>

      {hasChanges && (
        <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
          <button
            className="btn btn-primary btn-sm"
            onClick={() => onSave(local)}
            disabled={saving}
          >
            {saving ? 'Guardando...' : <><Check size={12} /> Aplicar cambios</>}
          </button>
        </div>
      )}

      <div style={{
        marginTop: 10, padding: '6px 10px',
        background: 'rgba(59,130,246,0.06)',
        borderRadius: 6, border: '1px solid rgba(59,130,246,0.1)',
        fontSize: 11, color: 'var(--text-muted)',
        display: 'flex', gap: 6, alignItems: 'flex-start',
      }}>
        <Info size={12} style={{ color: 'var(--accent-blue)', flexShrink: 0, marginTop: 1 }} />
        <span>
          {analytic.description}
        </span>
      </div>
    </div>
  );
}

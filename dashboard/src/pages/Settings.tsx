import { useState, useEffect } from 'react';
import { apiGet, apiPost } from '../api';
import { Cpu, Cloud, Link, Check, Info, Webhook, Settings } from 'lucide-react';

export default function SettingsPage() {
  const [system, setSystem]         = useState(null);
  const [cloudForm, setCloudForm]   = useState({ url: '', api_key: '', gateway_id: 'gateway-01' });
  const [webhookUrl, setWebhookUrl] = useState('');
  const [webhooks, setWebhooks]     = useState([]);
  const [saved, setSaved]           = useState(false);

  useEffect(() => {
    apiGet('/api/system').then(setSystem).catch(console.error);
    apiGet('/api/events/integrations/webhooks').then(setWebhooks).catch(console.error);
  }, []);

  const saveCloud = async () => {
    await apiPost('/api/events/integrations/cloud', cloudForm);
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  };

  const addWebhook = async () => {
    if (!webhookUrl.trim()) return;
    await apiPost('/api/events/integrations/webhooks', { url: webhookUrl });
    setWebhooks(prev => [...prev, { url: webhookUrl }]);
    setWebhookUrl('');
  };

  const hw = system?.hardware || {};

  return (
    <>
      <div className="page-header">
        <div>
          <h1 className="page-title">Ajustes del Sistema</h1>
          <p className="page-subtitle">
            Hardware, conexión cloud y compatibilidad con VMS externos
          </p>
        </div>
      </div>

      <div className="page-content" style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>

        {/* Hardware */}
        <div className="card">
          <div className="card-header">
            <span className="card-title"><Cpu size={14} /> Hardware detectado</span>
          </div>
          <div className="card-body">
            <div style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))',
              gap: 12,
            }}>
              <HwItem label="Procesador"       value={hw.processor || '—'} />
              <HwItem label="RAM Total"         value={hw.ram_total_gb ? `${hw.ram_total_gb} GB` : '—'} />
              <HwItem label="RAM Disponible"    value={hw.ram_available_gb ? `${hw.ram_available_gb} GB` : '—'} />
              <HwItem label="Núcleos CPU"       value={hw.cpu_cores ? `${hw.cpu_cores}c / ${hw.cpu_threads}t` : '—'} />
              <HwItem label="Google Coral USB"  value={hw.coral ? 'Detectado' : 'No detectado'} positive={hw.coral} />
              <HwItem label="CUDA / GPU"        value={hw.cuda ? 'Disponible' : 'No disponible'} positive={hw.cuda} />
              <HwItem label="TensorRT (Jetson)" value={hw.tensorrt ? 'Disponible' : 'No disponible (futuro)'} positive={hw.tensorrt} />
              <HwItem label="Backend activo"    value={system?.inference_backend || '—'} />
            </div>
          </div>
        </div>

        {/* Cloud Platform */}
        <div className="card">
          <div className="card-header">
            <span className="card-title"><Cloud size={14} /> Plataforma Cloud (VPS)</span>
          </div>
          <div className="card-body">
            <p style={{ fontSize: 13, color: 'var(--text-muted)', marginBottom: 16 }}>
              Conecta este gateway a tu plataforma NeoBit en el VPS para control remoto
              y recepción centralizada de eventos desde múltiples instalaciones.
            </p>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 12 }}>
              <div className="form-group">
                <label className="form-label">URL del servidor VPS</label>
                <input
                  id="cloud-url"
                  className="form-input"
                  placeholder="https://neobit.tudominio.com"
                  value={cloudForm.url}
                  onChange={e => setCloudForm(p => ({ ...p, url: e.target.value }))}
                />
              </div>
              <div className="form-group">
                <label className="form-label">Gateway ID</label>
                <input
                  className="form-input"
                  placeholder="gateway-01"
                  value={cloudForm.gateway_id}
                  onChange={e => setCloudForm(p => ({ ...p, gateway_id: e.target.value }))}
                />
              </div>
            </div>
            <div className="form-group" style={{ marginBottom: 16 }}>
              <label className="form-label">API Key</label>
              <input
                id="cloud-apikey"
                className="form-input"
                type="password"
                placeholder="••••••••••••••••"
                value={cloudForm.api_key}
                onChange={e => setCloudForm(p => ({ ...p, api_key: e.target.value }))}
              />
            </div>
            <button
              id="save-cloud-btn"
              className="btn btn-primary"
              onClick={saveCloud}
              disabled={!cloudForm.url || !cloudForm.api_key}
            >
              {saved
                ? <><Check size={14} /> Guardado</>
                : <><Cloud size={14} /> Conectar al VPS</>
              }
            </button>
          </div>
        </div>

        {/* VMS Webhooks */}
        <div className="card">
          <div className="card-header">
            <span className="card-title"><Link size={14} /> Integración con VMS externos</span>
          </div>
          <div className="card-body">
            <p style={{ fontSize: 13, color: 'var(--text-muted)', marginBottom: 16 }}>
              Envía eventos de analíticas en tiempo real a cualquier VMS o sistema externo vía HTTP POST.
              Compatible con Milestone, Genetec, Hanwha, Dahua VMS, o cualquier endpoint REST.
            </p>

            <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
              <input
                id="webhook-url-input"
                className="form-input"
                placeholder="https://tu-vms.com/api/events"
                value={webhookUrl}
                onChange={e => setWebhookUrl(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && addWebhook()}
              />
              <button
                className="btn btn-primary"
                onClick={addWebhook}
                style={{ whiteSpace: 'nowrap' }}
              >
                <Link size={14} /> Agregar
              </button>
            </div>

            {webhooks.length > 0 ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginBottom: 16 }}>
                {webhooks.map(w => (
                  <div key={w.url} style={{
                    display: 'flex', alignItems: 'center', gap: 10,
                    padding: '8px 12px',
                    borderRadius: 'var(--radius-sm)',
                    background: 'var(--bg-card)',
                    border: '1px solid var(--border)',
                    fontSize: 12,
                    fontFamily: 'monospace',
                  }}>
                    <Check size={12} style={{ color: 'var(--accent-green)', flexShrink: 0 }} />
                    <span style={{ flex: 1, wordBreak: 'break-all' }}>{w.url}</span>
                  </div>
                ))}
              </div>
            ) : (
              <div style={{
                fontSize: 12, color: 'var(--text-muted)',
                textAlign: 'center', padding: '12px 0', marginBottom: 16,
              }}>
                Sin webhooks configurados
              </div>
            )}

            {/* Event format reference */}
            <div style={{
              padding: '12px 14px',
              background: 'rgba(59,130,246,0.06)',
              borderRadius: 'var(--radius-sm)',
              border: '1px solid rgba(59,130,246,0.12)',
            }}>
              <div style={{
                fontSize: 12, fontWeight: 600,
                color: 'var(--accent-blue)',
                marginBottom: 8,
                display: 'flex', alignItems: 'center', gap: 6,
              }}>
                <Info size={13} />
                Formato de evento enviado (JSON estándar)
              </div>
              <pre style={{
                fontSize: 11, color: 'var(--text-muted)',
                lineHeight: 1.6, margin: 0, overflow: 'auto',
              }}>
{`{
  "source": "neobit",
  "version": "1.0",
  "event": {
    "gateway_id": "gateway-01",
    "camera_id": 1,
    "analytic_type": "fall_detection",
    "severity": "critical",
    "confidence": 0.94,
    "timestamp": 1714000000
  }
}`}
              </pre>
            </div>
          </div>
        </div>

      </div>
    </>
  );
}

function HwItem({ label, value, positive }) {
  return (
    <div style={{
      padding: '10px 14px',
      background: 'var(--bg-card)',
      borderRadius: 'var(--radius-sm)',
      border: `1px solid ${positive ? 'rgba(16,185,129,0.2)' : 'var(--border)'}`,
    }}>
      <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 3 }}>{label}</div>
      <div style={{
        fontSize: 13, fontWeight: 600,
        color: positive ? 'var(--accent-green)' : 'var(--text-primary)',
      }}>
        {positive !== undefined && (
          <span style={{ marginRight: 5 }}>
            {positive
              ? <Check size={12} style={{ display: 'inline', verticalAlign: 'middle' }} />
              : null
            }
          </span>
        )}
        {value}
      </div>
    </div>
  );
}

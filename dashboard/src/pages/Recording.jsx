import { useState, useEffect } from 'react';
import { apiGet } from '../api';
import { HardDrive, Check, Save, RefreshCw, Play, Pause,
         Film, AlertTriangle, Info, Cpu, Zap, Folder } from 'lucide-react';

const API = 'http://localhost:8000';
const put = (p, b) => fetch(`${API}${p}`, {
  method: 'PUT', headers: {'Content-Type':'application/json'}, body: JSON.stringify(b)
}).then(r => { if (!r.ok) throw new Error(r.statusText); return r.json(); });

function fmtGB(gb) {
  if (!gb && gb !== 0) return '—';
  return gb < 1 ? `${(gb*1024).toFixed(0)} MB` : `${gb.toFixed(1)} GB`;
}

function Bar({ pct }) {
  const p = Math.min(pct||0, 100);
  return (
    <div style={{ height:5, borderRadius:3, background:'rgba(255,255,255,0.07)', overflow:'hidden' }}>
      <div style={{
        height:'100%', width:`${p}%`, borderRadius:3, transition:'width 0.4s',
        background: p>85 ? 'linear-gradient(90deg,#f59e0b,#ef4444)'
                         : 'linear-gradient(90deg,#3b82f6,#8b5cf6)',
      }}/>
    </div>
  );
}

export default function Recording() {
  const [status,  setStatus]  = useState(null);
  const [disks,   setDisks]   = useState([]);
  const [files,   setFiles]   = useState([]);
  const [tab,     setTab]     = useState('config');
  const [saving,  setSaving]  = useState(false);
  const [saved,   setSaved]   = useState(false);
  const [loading, setLoading] = useState(true);

  const [form, setForm] = useState({
    enabled: false, mode: 'motion',
    storage_path: './recordings', max_disk_gb: 50,
    segment_minutes: 5, pre_buffer_s: 10, post_buffer_s: 20,
    retain_days: 30, video_quality: 'medium', video_codec: 'h264',
  });

  const load = async () => {
    setLoading(true);
    try {
      const [st, dk] = await Promise.all([
        apiGet('/api/recording/status'),
        apiGet('/api/recording/disks'),
      ]);
      setStatus(st);
      setDisks(dk);
      setForm(f => ({...f,
        enabled: st.enabled, mode: st.mode,
        storage_path: st.storage_path, max_disk_gb: st.max_disk_gb,
        segment_minutes: st.segment_minutes, pre_buffer_s: st.pre_buffer_s,
        post_buffer_s: st.post_buffer_s, retain_days: st.retain_days,
      }));
    } finally { setLoading(false); }
  };

  useEffect(() => { load(); }, []);
  useEffect(() => { if (tab==='files') apiGet('/api/recording/files?limit=50').then(setFiles); }, [tab]);

  const set = (k,v) => setForm(p=>({...p,[k]:v}));

  // One-click disk selection
  const selectDisk = async (disk) => {
    const newPath = disk.suggested_path;
    const newQuota = Math.floor(disk.free_gb * 0.80);
    const newForm = {...form, storage_path: newPath, max_disk_gb: newQuota};
    setForm(newForm);
    setSaving(true);
    try {
      await put('/api/recording/config', newForm);
      setSaved(true);
      setTimeout(() => setSaved(false), 2500);
      await load();
    } catch(e) { alert('Error: '+e.message); }
    finally { setSaving(false); }
  };

  const save = async () => {
    setSaving(true);
    try {
      await put('/api/recording/config', form);
      setSaved(true);
      setTimeout(()=>setSaved(false), 2500);
      await load();
    } catch(e) { alert('Error: '+e.message); }
    finally { setSaving(false); }
  };

  const activeDisk = disks.find(d => form.storage_path.startsWith(d.mount));

  return (
    <>
      <div className="page-header">
        <div>
          <h1 className="page-title">Grabacion y Almacenamiento</h1>
          <p className="page-subtitle">Sistema NVR — elige un disco y graba automaticamente</p>
        </div>
        <div style={{display:'flex',gap:8}}>
          <button className="btn btn-ghost" onClick={load}>
            <RefreshCw size={14} style={loading?{animation:'spin 0.8s linear infinite'}:{}}/>
          </button>
          <button className="btn btn-primary" onClick={save} disabled={saving}>
            {saved ? <><Check size={14}/> Guardado</> : saving ? 'Guardando...' : <><Save size={14}/> Guardar</>}
          </button>
        </div>
      </div>

      <div className="page-content">

        {/* ── DISK SELECTOR ─────────────────────────────── */}
        <div className="card" style={{marginBottom:14}}>
          <div className="card-header">
            <span className="card-title"><HardDrive size={14}/> Disco de grabacion</span>
            <span style={{fontSize:11,color:'var(--text-muted)'}}>
              Haz clic en un disco para seleccionarlo. Todos los videos, clips y capturas se guardan ahí.
            </span>
          </div>
          <div className="card-body" style={{display:'flex',flexDirection:'column',gap:10}}>

            {loading ? (
              <div style={{textAlign:'center',padding:24,color:'var(--text-muted)',fontSize:13}}>
                Detectando discos...
              </div>
            ) : disks.length === 0 ? (
              <div style={{textAlign:'center',padding:32,color:'var(--text-muted)',fontSize:13}}>
                <HardDrive size={32} style={{opacity:0.1,display:'block',margin:'0 auto 10px'}}/>
                Conecta un disco externo o memoria USB para verlo aquí.
              </div>
            ) : (
              <div style={{display:'grid',gridTemplateColumns:'repeat(auto-fill,minmax(260px,1fr))',gap:10}}>
                {disks.map((d,i) => {
                  const sel = form.storage_path.startsWith(d.mount);
                  const low = d.free_gb < 2;
                  return (
                    <button key={i} onClick={() => !low && selectDisk(d)} style={{
                      all:'unset', cursor: low ? 'not-allowed':'pointer',
                      display:'block', borderRadius:12, padding:'14px 16px',
                      border:`2px solid ${sel ? 'var(--accent-blue)' : 'var(--border)'}`,
                      background: sel ? 'rgba(59,130,246,0.09)' : 'var(--bg-body)',
                      transition:'all 0.2s', opacity: low ? 0.5 : 1,
                    }}>
                      <div style={{display:'flex',alignItems:'center',gap:10,marginBottom:10}}>
                        <div style={{
                          width:38,height:38,borderRadius:9,flexShrink:0,
                          display:'flex',alignItems:'center',justifyContent:'center',
                          background: sel ? 'rgba(59,130,246,0.18)':'rgba(255,255,255,0.05)',
                        }}>
                          <HardDrive size={18} style={{color: sel?'var(--accent-blue)':'var(--text-muted)'}}/>
                        </div>
                        <div style={{flex:1,minWidth:0}}>
                          <div style={{display:'flex',alignItems:'center',gap:6,flexWrap:'wrap'}}>
                            <span style={{fontWeight:700,fontSize:13}}>
                              {d.mount==='/'?'Disco principal':'Disco externo'}
                            </span>
                            {sel && <span className="badge badge-green" style={{fontSize:10}}><Check size={9}/> En uso</span>}
                            {d.device.includes('sd') && d.mount!=='/' &&
                              <span className="badge badge-blue" style={{fontSize:10}}>USB</span>}
                          </div>
                          <div style={{fontSize:11,color:'var(--text-muted)',fontFamily:'monospace',marginTop:2}}>
                            {d.mount} · {d.device}
                          </div>
                        </div>
                        <div style={{textAlign:'right',flexShrink:0}}>
                          <div style={{fontWeight:800,fontSize:16,color: low?'var(--accent-amber)':'var(--accent-green)'}}>
                            {fmtGB(d.free_gb)}
                          </div>
                          <div style={{fontSize:10,color:'var(--text-muted)'}}>libre de {fmtGB(d.total_gb)}</div>
                        </div>
                      </div>
                      <Bar pct={d.used_pct}/>
                      <div style={{display:'flex',justifyContent:'space-between',marginTop:5,fontSize:10,color:'var(--text-muted)'}}>
                        <span>{d.used_pct}% usado · {d.fstype}</span>
                        {low && <span style={{color:'var(--accent-amber)',display:'flex',gap:4,alignItems:'center'}}><AlertTriangle size={10}/> Espacio insuficiente</span>}
                      </div>
                      {sel && (
                        <div style={{
                          marginTop:8,padding:'6px 10px',borderRadius:7,fontSize:11,
                          background:'rgba(59,130,246,0.07)',
                          border:'1px solid rgba(59,130,246,0.15)',
                          color:'var(--accent-blue)',fontFamily:'monospace',
                          wordBreak:'break-all',
                        }}>
                          📁 {d.suggested_path}
                        </div>
                      )}
                    </button>
                  );
                })}
              </div>
            )}

            {/* Ruta manual como respaldo */}
            <div style={{display:'flex',gap:8,alignItems:'center',paddingTop:4}}>
              <Folder size={13} style={{color:'var(--text-muted)',flexShrink:0}}/>
              <input className="form-input" style={{flex:1,fontFamily:'monospace',fontSize:12}}
                value={form.storage_path}
                onChange={e=>set('storage_path',e.target.value)}
                placeholder="/media/usb/NeoBit_Recordings"/>
              <span style={{fontSize:11,color:'var(--text-muted)',whiteSpace:'nowrap'}}>o escribe la ruta</span>
            </div>
          </div>
        </div>

        {/* ── STATUS BAR ────────────────────────────────── */}
        {status && (
          <div className="card" style={{marginBottom:14}}>
            <div style={{display:'grid',gridTemplateColumns:'repeat(auto-fit,minmax(150px,1fr))'}}>
              {[
                { label:'Usado', value: fmtGB(status.used_gb), sub:`de ${fmtGB(status.max_disk_gb)} cuota`, color:'var(--accent-blue)' },
                { label:'Libre en disco', value: fmtGB(status.free_gb), sub: activeDisk?.device||'—', color:'var(--accent-green)' },
                { label:'Camaras', value: status.active_cameras?.length??0, sub: status.mode==='continuous'?'modo continuo':'modo evento', color:'var(--accent-purple)' },
                { label:'Estado', value: status.enabled?'Grabando':'Pausado', sub: status.enabled?`anillo circular activo`:'activa para grabar', color: status.enabled?'var(--accent-green)':'var(--text-muted)' },
                { label:'Codec', value: status.codec||'mp4v', sub: status.ffmpeg_available?'ffmpeg ok':'OpenCV fallback', color:'var(--accent-amber)' },
              ].map(s=>(
                <div key={s.label} style={{padding:'14px 18px',borderRight:'1px solid var(--border)'}}>
                  <div style={{fontSize:11,color:'var(--text-muted)',marginBottom:4}}>{s.label}</div>
                  <div style={{fontWeight:800,fontSize:20,color:s.color}}>{s.value}</div>
                  <div style={{fontSize:10,color:'var(--text-muted)',marginTop:2}}>{s.sub}</div>
                </div>
              ))}
            </div>
            {status.quota_used_pct > 0 && (
              <div style={{padding:'6px 18px 12px'}}>
                <Bar pct={status.quota_used_pct}/>
                <div style={{fontSize:11,color:'var(--text-muted)',marginTop:4}}>
                  {status.quota_used_pct}% de cuota — los archivos mas antiguos se sobrescriben al llegar al limite
                </div>
              </div>
            )}
          </div>
        )}

        {/* ── TABS ──────────────────────────────────────── */}
        <div style={{display:'flex',gap:4,marginBottom:14}}>
          {['config','files'].map(t=>(
            <button key={t} className={`btn btn-sm ${tab===t?'btn-primary':'btn-ghost'}`} onClick={()=>setTab(t)}>
              {t==='config'?'Configuracion':'Grabaciones'}
            </button>
          ))}
        </div>

        {tab==='config' && (
          <div style={{display:'grid',gridTemplateColumns:'1fr 1fr',gap:14}}>

            {/* Modo + toggle */}
            <div style={{display:'flex',flexDirection:'column',gap:14}}>
              <div className="card">
                <div className="card-body">
                  <label className="toggle" style={{gap:12}}>
                    <input type="checkbox" checked={form.enabled} onChange={e=>set('enabled',e.target.checked)}/>
                    <div className="toggle-track"><div className="toggle-thumb"/></div>
                    <div>
                      <div style={{fontWeight:700,fontSize:14}}>{form.enabled?'Grabacion activa':'Grabacion desactivada'}</div>
                      <div style={{fontSize:12,color:'var(--text-muted)',marginTop:2}}>
                        {form.enabled ? 'Grabando en anillo — los archivos mas antiguos se sobrescriben' : 'Activa para comenzar a grabar'}
                      </div>
                    </div>
                  </label>
                </div>
              </div>

              <div className="card">
                <div className="card-header"><span className="card-title">Modo de grabacion</span></div>
                <div className="card-body" style={{display:'flex',flexDirection:'column',gap:10}}>
                  <div style={{display:'flex',gap:8}}>
                    {[
                      {id:'motion',label:'Por evento',desc:'Solo graba cuando la IA detecta algo. Ahorra espacio.',icon:<Cpu size={15}/>},
                      {id:'continuous',label:'Continua 24/7',desc:'Graba siempre en segmentos. Igual que un NVR fisico.',icon:<Film size={15}/>},
                    ].map(m=>(
                      <label key={m.id} onClick={()=>set('mode',m.id)} style={{
                        flex:1,padding:'12px 14px',borderRadius:10,cursor:'pointer',
                        border:`2px solid ${form.mode===m.id?'var(--accent-blue)':'var(--border)'}`,
                        background: form.mode===m.id?'rgba(59,130,246,0.08)':'transparent',
                        transition:'all 0.2s',
                      }}>
                        <div style={{color:form.mode===m.id?'var(--accent-blue)':'var(--text-muted)',marginBottom:6}}>{m.icon}</div>
                        <div style={{fontWeight:700,fontSize:13,marginBottom:4}}>{m.label}</div>
                        <div style={{fontSize:11,color:'var(--text-muted)',lineHeight:1.4}}>{m.desc}</div>
                      </label>
                    ))}
                  </div>

                  {form.mode==='continuous' && (
                    <div className="form-group" style={{marginBottom:0}}>
                      <label className="form-label">Duracion del segmento (min)</label>
                      <input className="form-input" type="number" min={1} max={60} value={form.segment_minutes} onChange={e=>set('segment_minutes',+e.target.value)}/>
                    </div>
                  )}
                  {form.mode==='motion' && (
                    <div style={{display:'grid',gridTemplateColumns:'1fr 1fr',gap:10}}>
                      <div className="form-group" style={{marginBottom:0}}>
                        <label className="form-label">Pre-buffer (seg antes)</label>
                        <input className="form-input" type="number" min={0} max={60} value={form.pre_buffer_s} onChange={e=>set('pre_buffer_s',+e.target.value)}/>
                      </div>
                      <div className="form-group" style={{marginBottom:0}}>
                        <label className="form-label">Post-buffer (seg despues)</label>
                        <input className="form-input" type="number" min={5} max={300} value={form.post_buffer_s} onChange={e=>set('post_buffer_s',+e.target.value)}/>
                      </div>
                    </div>
                  )}
                </div>
              </div>
            </div>

            {/* Cuota + calidad */}
            <div style={{display:'flex',flexDirection:'column',gap:14}}>
              <div className="card">
                <div className="card-header"><span className="card-title">Espacio y retencion</span></div>
                <div className="card-body" style={{display:'grid',gridTemplateColumns:'1fr 1fr',gap:10}}>
                  <div className="form-group" style={{marginBottom:0}}>
                    <label className="form-label">Cuota maxima (GB)</label>
                    <input className="form-input" type="number" min={1} value={form.max_disk_gb} onChange={e=>set('max_disk_gb',+e.target.value)}/>
                  </div>
                  <div className="form-group" style={{marginBottom:0}}>
                    <label className="form-label">Retener (dias)</label>
                    <input className="form-input" type="number" min={1} max={365} value={form.retain_days} onChange={e=>set('retain_days',+e.target.value)}/>
                  </div>
                </div>
              </div>

              <div className="card">
                <div className="card-header"><span className="card-title"><Zap size={13}/> Compresion de video</span></div>
                <div className="card-body" style={{display:'flex',flexDirection:'column',gap:10}}>
                  <div className="form-group" style={{marginBottom:0}}>
                    <label className="form-label">Calidad</label>
                    <select className="form-select" value={form.video_quality} onChange={e=>set('video_quality',e.target.value)}>
                      <option value="low">Baja — CRF 35, maximo espacio</option>
                      <option value="medium">Media — CRF 26, estandar NVR</option>
                      <option value="high">Alta — CRF 18, maxima calidad</option>
                    </select>
                  </div>
                  <div className="form-group" style={{marginBottom:0}}>
                    <label className="form-label">Codec</label>
                    <select className="form-select" value={form.video_codec} onChange={e=>set('video_codec',e.target.value)}>
                      <option value="h264">H.264 — compatible universal (recomendado)</option>
                      <option value="h265">H.265 — 2x mas compacto, requiere ffmpeg</option>
                    </select>
                  </div>
                  {status && (
                    <div style={{fontSize:11,color: status.ffmpeg_available?'var(--accent-green)':'var(--accent-amber)',display:'flex',gap:5,alignItems:'center'}}>
                      {status.ffmpeg_available ? <Check size={11}/> : <AlertTriangle size={11}/>}
                      {status.codec || 'mp4v'}
                      {!status.ffmpeg_available && ' — instala ffmpeg para mejor compresion'}
                    </div>
                  )}
                  <div style={{fontSize:11,color:'var(--text-muted)',padding:'7px 10px',borderRadius:7,background:'rgba(139,92,246,0.07)',border:'1px solid rgba(139,92,246,0.15)',display:'flex',gap:7}}>
                    <Info size={12} style={{color:'var(--accent-purple)',flexShrink:0,marginTop:1}}/>
                    Anillo circular: al llegar a la cuota, los segmentos mas antiguos se sobrescriben automaticamente.
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}

        {tab==='files' && (
          <div style={{display:'flex',flexDirection:'column',gap:8}}>
            <div style={{display:'flex',justifyContent:'space-between',alignItems:'center',marginBottom:4}}>
              <span style={{fontSize:12,color:'var(--text-muted)'}}>{files.length} archivo(s)</span>
              <button className="btn btn-ghost btn-sm" onClick={()=>apiGet('/api/recording/files?limit=50').then(setFiles)}>
                <RefreshCw size={12}/> Actualizar
              </button>
            </div>
            {files.length===0 ? (
              <div className="empty-state card" style={{padding:48}}>
                <Film size={36} style={{opacity:0.12}}/>
                <div className="empty-title">Sin grabaciones</div>
                <div className="empty-desc">Selecciona un disco y habilita la grabacion</div>
              </div>
            ) : files.map((f,i)=>(
              <div key={i} className="card" style={{padding:0}}>
                <div style={{display:'flex',alignItems:'center',gap:12,padding:'10px 16px'}}>
                  <Film size={15} style={{color:'var(--accent-blue)',flexShrink:0}}/>
                  <div style={{flex:1,minWidth:0}}>
                    <div style={{fontWeight:600,fontSize:13,whiteSpace:'nowrap',overflow:'hidden',textOverflow:'ellipsis'}}>{f.filename}</div>
                    <div style={{fontSize:11,color:'var(--text-muted)',marginTop:2}}>
                      Cam {f.camera_id??'?'} · {f.size_mb} MB · {new Date(f.created*1000).toLocaleString('es-MX')}
                    </div>
                  </div>
                  <a href={`http://localhost:8000${f.url}`} target="_blank" rel="noreferrer">
                    <button className="btn btn-ghost btn-sm"><Play size={12}/> Ver</button>
                  </a>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
      <style>{`@keyframes spin{to{transform:rotate(360deg);}}`}</style>
    </>
  );
}

import { useState } from 'react';
import { apiPost } from '../api';
import { Search, Loader, Clock, Camera } from 'lucide-react';

const EXAMPLE_QUERIES = [
  'persona con casco amarillo',
  'persona sin chaleco de seguridad',
  'persona en el suelo',
  'vehículo de color blanco',
  'dos personas juntas',
  'persona con camisa roja',
];

export default function SemanticSearch() {
  const [query, setQuery]     = useState('');
  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(false);
  const [searched, setSearched] = useState(false);
  const [topK, setTopK]       = useState(12);

  const doSearch = async (q = query) => {
    if (!q.trim()) return;
    setLoading(true);
    setSearched(true);
    try {
      const data = await apiPost('/api/search/semantic', { query: q, top_k: topK });
      setResults(data.results || []);
    } catch (err) {
      console.error(err);
      setResults([]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      <div className="page-header">
        <div>
          <h1 className="page-title">Búsqueda Semántica</h1>
          <p className="page-subtitle">
            Busca en el historial de video usando lenguaje natural — impulsado por CLIP
          </p>
        </div>
      </div>

      <div className="page-content">
        {/* Search box */}
        <div className="card" style={{ padding: '20px 24px', marginBottom: 16 }}>
          <div className="search-container">
            <Search size={18} className="search-icon" />
            <input
              id="semantic-search-input"
              className="search-input"
              placeholder='Describe lo que buscas, ej: "persona con camisa roja y lentes"'
              value={query}
              onChange={e => setQuery(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && doSearch()}
            />
            <button
              id="semantic-search-btn"
              className="btn btn-primary search-btn"
              onClick={() => doSearch()}
              disabled={loading || !query.trim()}
            >
              {loading
                ? <><Loader size={14} style={{ animation: 'spin 1s linear infinite' }} /> Buscando...</>
                : <><Search size={14} /> Buscar</>
              }
            </button>
          </div>

          {/* Quick examples */}
          <div style={{ marginTop: 14, display: 'flex', flexWrap: 'wrap', gap: 6, alignItems: 'center' }}>
            <span style={{ fontSize: 11, color: 'var(--text-muted)', fontWeight: 500 }}>
              Ejemplos:
            </span>
            {EXAMPLE_QUERIES.map(q => (
              <button
                key={q}
                className="btn btn-ghost btn-sm"
                onClick={() => { setQuery(q); doSearch(q); }}
                style={{ fontSize: 11 }}
              >
                {q}
              </button>
            ))}
          </div>
        </div>

        {/* Loading */}
        {loading && (
          <div className="empty-state">
            <Loader size={32} style={{ opacity: 0.4, animation: 'spin 1s linear infinite' }} />
            <div className="empty-title">Buscando en el índice de video...</div>
            <div className="empty-desc">
              CLIP está comparando tu consulta con los frames indexados
            </div>
          </div>
        )}

        {/* No results */}
        {!loading && searched && results.length === 0 && (
          <div className="empty-state">
            <Search size={32} style={{ opacity: 0.2 }} />
            <div className="empty-title">Sin resultados</div>
            <div className="empty-desc">
              No se encontraron frames que coincidan. Intenta con términos más generales.
            </div>
          </div>
        )}

        {/* Results grid */}
        {!loading && results.length > 0 && (
          <>
            <div style={{ marginBottom: 12, fontSize: 13, color: 'var(--text-muted)' }}>
              <strong style={{ color: 'var(--text-primary)' }}>{results.length}</strong>
              {' '}resultados para "{query}"
            </div>
            <div className="search-results">
              {results.map((r, i) => (
                <SearchResultCard key={i} result={r} />
              ))}
            </div>
          </>
        )}

        {/* Initial state */}
        {!searched && (
          <div className="empty-state" style={{ marginTop: 32 }}>
            <Search size={48} style={{ opacity: 0.1 }} />
            <div className="empty-title">Búsqueda semántica de video</div>
            <div className="empty-desc">
              Describe lo que buscas en lenguaje natural. El sistema busca en el historial
              de todas las cámaras usando inteligencia artificial visual.
            </div>
          </div>
        )}
      </div>

      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </>
  );
}

function SearchResultCard({ result }) {
  const score   = Math.round((result.score || 0) * 100);
  const date    = new Date((result.timestamp || 0) * 1000);
  const timeStr = date.toLocaleString('es-MX', {
    month: 'short', day: 'numeric',
    hour: '2-digit', minute: '2-digit', second: '2-digit',
  });

  const scoreColor = score > 70
    ? 'var(--accent-green)'
    : score > 50
    ? 'var(--accent-amber)'
    : 'var(--text-muted)';

  return (
    <div className="search-result-card">
      <div style={{ position: 'relative' }}>
        {result.frame_path ? (
          <img
            src={`/api/search/frame/${encodeURIComponent(result.frame_path)}`}
            alt={`Frame ${result.timestamp}`}
            style={{
              width: '100%', aspectRatio: '16/9',
              objectFit: 'cover', display: 'block', background: '#000',
            }}
          />
        ) : (
          <div style={{
            width: '100%', aspectRatio: '16/9',
            background: 'var(--bg-card)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}>
            <Camera size={24} style={{ opacity: 0.2 }} />
          </div>
        )}

        {/* Score badge */}
        <div style={{
          position: 'absolute', top: 6, right: 6,
          background: 'rgba(0,0,0,0.7)',
          color: scoreColor,
          fontSize: 11, fontWeight: 700,
          padding: '2px 7px', borderRadius: 6,
          backdropFilter: 'blur(4px)',
        }}>
          {score}%
        </div>
      </div>

      <div className="search-result-meta">
        <div style={{ fontSize: 12, fontWeight: 600, color: scoreColor }}>
          {score > 70 ? 'Alta coincidencia' : score > 50 ? 'Coincidencia media' : 'Coincidencia baja'}
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 4, marginTop: 4, fontSize: 11, color: 'var(--text-muted)' }}>
          <Camera size={11} />
          <span>Cámara {result.camera_id}</span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 4, marginTop: 2, fontSize: 11, color: 'var(--text-muted)' }}>
          <Clock size={11} />
          <span>{timeStr}</span>
        </div>
      </div>
    </div>
  );
}

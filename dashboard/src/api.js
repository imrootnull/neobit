// Global API base URL — reads from env or defaults to relative (works local AND cloud)
export const API_BASE = import.meta.env.VITE_API_URL || '';

// ─── REST helpers ────────────────────────────────────────────────────────────

export async function apiGet(path) {
  const res = await fetch(`${API_BASE}${path}`);
  if (!res.ok) throw new Error(`GET ${path} → ${res.status}`);
  return res.json();
}

export async function apiPost(path, body, method = 'POST') {
  const res = await fetch(`${API_BASE}${path}`, {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`${method} ${path} → ${res.status}`);
  return res.json();
}

export async function apiPut(path, body) {
  return apiPost(path, body, 'PUT');
}

export async function apiPatch(path, body) {
  const res = await fetch(`${API_BASE}${path}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`PATCH ${path} → ${res.status}`);
  return res.json();
}

export async function apiDelete(path) {
  const res = await fetch(`${API_BASE}${path}`, { method: 'DELETE' });
  if (!res.ok) throw new Error(`DELETE ${path} → ${res.status}`);
  return res.status === 204 ? null : res.json();
}

// ─── WebSocket ────────────────────────────────────────────────────────────────

export function createWebSocket(onMessage, onConnect, onDisconnect) {
  const wsBase = API_BASE.replace(/^http/, 'ws') || `ws://${window.location.host}`;
  const ws = new WebSocket(`${wsBase}/ws`);

  ws.onopen = () => onConnect?.();
  ws.onclose = () => onDisconnect?.();
  ws.onerror = () => onDisconnect?.();
  ws.onmessage = (e) => {
    try { onMessage(JSON.parse(e.data)); }
    catch {}
  };

  return ws;
}

// ─── Stream URL helpers ───────────────────────────────────────────────────────

export function getMjpegUrl(cameraId) {
  return `${API_BASE}/api/stream/${cameraId}/mjpeg`;
}

export function getSnapshotUrl(cameraId) {
  return `${API_BASE}/api/stream/${cameraId}/snapshot?t=${Date.now()}`;
}

// Global API base URL — reads from env or defaults to relative (works local AND cloud)
export const API_BASE: string = import.meta.env.VITE_API_URL || '';
export const POLL_INTERVAL = 200; // ms — ~5fps display, safe for single uvicorn worker

// ─── Domain Types ─────────────────────────────────────────────────────────────

export type Severity = 'low' | 'medium' | 'high' | 'critical';
export type RecordingMode = 'motion' | 'continuous';
export type VideoCodec = 'h264' | 'h265' | 'mp4v';
export type VideoQuality = 'low' | 'medium' | 'high';
export type CameraStatus = 'active' | 'inactive' | 'error';

export interface Camera {
  id: number;
  name: string;
  rtsp_url: string;
  location?: string;
  status: CameraStatus;
  enabled: boolean;
  frame_skip: number;
  resolution_w: number;
  resolution_h: number;
  fps: number;
  analytics_config: Record<string, boolean | AnalyticConfig>;
  zones: Zone[];
  created_at: string;
  updated_at: string;
}

export interface AnalyticConfig {
  enabled: boolean;
  confidence?: number;
  min_event_interval_s?: number;
  [key: string]: unknown;
}

export interface Zone {
  name: string;
  points: [number, number][];
}

export interface CameraCreate {
  name: string;
  rtsp_url: string;
  location?: string;
  frame_skip?: number;
  resolution_w?: number;
  resolution_h?: number;
  fps?: number;
  analytics_config?: Record<string, boolean | AnalyticConfig>;
  zones?: Zone[];
}

export interface CameraUpdate extends Partial<CameraCreate> {}

export interface StreamStatus {
  camera_id: number;
  connected: boolean;
  fps: number;
  frame_count: number;
  error_count: number;
  last_frame_time: number | null;
}

export interface AnalyticEvent {
  id: number;
  camera_id: number;
  analytic_type: string;
  severity: Severity;
  description?: string;
  confidence?: number;
  snapshot_path?: string;
  recording_path?: string;
  timestamp: number;
  event_meta: Record<string, unknown>;
  acknowledged: boolean;
}

export interface EventStats {
  [analytic_type: string]: {
    [severity: string]: number;
  };
}

export interface RecordingStatus {
  enabled: boolean;
  mode: RecordingMode;
  storage_path: string;
  max_disk_gb: number;
  used_gb: number;
  free_gb: number;
  quota_used_pct: number;
  segment_minutes: number;
  pre_buffer_s: number;
  post_buffer_s: number;
  retain_days: number;
  video_quality: VideoQuality;
  video_codec: VideoCodec;
  codec: string;
  ffmpeg_available: boolean;
  active_cameras: number[];
}

export interface DiskInfo {
  device: string;
  mount: string;
  fstype: string;
  total_gb: number;
  used_gb: number;
  free_gb: number;
  used_pct: number;
  suggested_path: string;
}

export interface RecordingFile {
  filename: string;
  camera_id?: number;
  size_mb: number;
  created: number;
  url: string;
}

export interface RecordingConfig {
  enabled?: boolean;
  mode?: RecordingMode;
  storage_path?: string;
  max_disk_gb?: number;
  segment_minutes?: number;
  pre_buffer_s?: number;
  post_buffer_s?: number;
  retain_days?: number;
  video_quality?: VideoQuality;
  video_codec?: VideoCodec;
}

export interface SystemInfo {
  cpu_pct: number;
  ram_pct: number;
  ram_used_gb: number;
  ram_total_gb: number;
  platform: string;
  uptime_s: number;
  coral: boolean;
  cuda: boolean;
}

export interface WSMessage {
  type: string;
  event?: AnalyticEvent;
  [key: string]: unknown;
}

// ─── REST helpers ─────────────────────────────────────────────────────────────

export async function apiGet<T = unknown>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`);
  if (!res.ok) throw new Error(`GET ${path} → ${res.status}`);
  return res.json() as Promise<T>;
}

export async function apiPost<T = unknown>(
  path: string,
  body: unknown,
  method = 'POST',
): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`${method} ${path} → ${res.status}`);
  return res.json() as Promise<T>;
}

export async function apiPut<T = unknown>(path: string, body: unknown): Promise<T> {
  return apiPost<T>(path, body, 'PUT');
}

export async function apiPatch<T = unknown>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`PATCH ${path} → ${res.status}`);
  return res.json() as Promise<T>;
}

export async function apiDelete(path: string): Promise<null> {
  const res = await fetch(`${API_BASE}${path}`, { method: 'DELETE' });
  if (!res.ok) throw new Error(`DELETE ${path} → ${res.status}`);
  return null;
}

// ─── WebSocket ────────────────────────────────────────────────────────────────

export function createWebSocket(
  onMessage: (msg: WSMessage) => void,
  onConnect?: () => void,
  onDisconnect?: () => void,
): WebSocket {
  const wsBase = API_BASE.replace(/^http/, 'ws') || `ws://${window.location.host}`;
  const ws = new WebSocket(`${wsBase}/ws`);

  ws.onopen    = () => onConnect?.();
  ws.onclose   = () => onDisconnect?.();
  ws.onerror   = () => onDisconnect?.();
  ws.onmessage = (e: MessageEvent<string>) => {
    try { onMessage(JSON.parse(e.data) as WSMessage); }
    catch { /* ignore malformed frames */ }
  };

  return ws;
}

// ─── Stream URL helpers ───────────────────────────────────────────────────────

export function getMjpegUrl(cameraId: number): string {
  return `${API_BASE}/api/stream/${cameraId}/mjpeg`;
}

export function getSnapshotUrl(cameraId: number): string {
  return `${API_BASE}/api/stream/${cameraId}/snapshot`;
}

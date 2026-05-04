"""
Recording Manager — handles continuous and motion-triggered recording.

Features:
- Two recording modes: continuous (24/7 rotating files) or motion (event-triggered)
- Configurable storage path — supports external drives, NAS, network paths
- Disk quota enforcement — auto-deletes oldest files when limit reached
- Pre-buffer: for motion mode, keeps last N seconds before the trigger
- Post-buffer: continues recording N seconds after the last detection
- Per-camera recording workers
"""
import os
import cv2
import time
import threading
import shutil
from datetime import datetime
from collections import deque
from dataclasses import dataclass, field
from typing import Optional, Literal
from loguru import logger
from backend.core.video_writer import open_writer, codec_name


# ─── Recording configuration ──────────────────────────────────────────────────

@dataclass
class RecordingConfig:
    """Per-system recording configuration (applied to all cameras)."""
    enabled:          bool    = False
    mode:             str     = "motion"      # "continuous" | "motion"
    storage_path:     str     = "./recordings" # Can be /mnt/external, /media/usb, etc.
    max_disk_gb:      float   = 50.0          # Maximum disk usage in GB
    segment_minutes:  int     = 5             # Length of each video segment
    pre_buffer_s:     int     = 10            # Seconds before event to include
    post_buffer_s:    int     = 20            # Seconds after last event to keep recording
    video_fps:        float   = 10.0          # FPS of saved recordings
    video_quality:    str     = "medium"      # "low" | "medium" | "high"
    retain_days:      int     = 30            # Delete recordings older than N days

    @property
    def max_disk_bytes(self) -> int:
        return int(self.max_disk_gb * 1024 ** 3)

    @property
    def segment_seconds(self) -> int:
        return self.segment_minutes * 60

    @property
    def codec_params(self) -> dict:
        q = {"low": 20, "medium": 35, "high": 50}
        return {"quality": q.get(self.video_quality, 35)}


# ─── Disk utilities ───────────────────────────────────────────────────────────

def get_disk_usage_bytes(path: str) -> int:
    """Total bytes used in a directory tree."""
    total = 0
    for root, dirs, files in os.walk(path):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(root, f))
            except OSError:
                pass
    return total


def get_disk_free_bytes(path: str) -> int:
    """Free disk space on the volume containing path."""
    try:
        stat = shutil.disk_usage(path)
        return stat.free
    except Exception:
        return 0


def purge_oldest_recordings(base_path: str, max_bytes: int):
    """
    Delete oldest .mp4 files until usage is well below max_bytes.
    Called every time a segment is closed (ring-buffer behaviour).
    """
    files = []
    for root, dirs, fnames in os.walk(base_path):
        for f in fnames:
            if f.endswith('.mp4'):
                fp = os.path.join(root, f)
                try:
                    files.append((os.path.getmtime(fp), fp))
                except OSError:
                    pass
    files.sort()  # oldest first

    current = get_disk_usage_bytes(base_path)
    target  = max_bytes * 0.80   # keep usage at 80% max
    removed = 0
    for _, fp in files:
        if current <= target:
            break
        try:
            size = os.path.getsize(fp)
            os.remove(fp)
            current -= size
            removed += 1
        except OSError:
            pass

    if removed:
        logger.info(f'Ring-buffer: removed {removed} old segment(s) to stay under quota')
    return removed


def purge_old_days(base_path: str, retain_days: int):
    """Delete recording files older than retain_days."""
    cutoff = time.time() - retain_days * 86400
    for root, dirs, fnames in os.walk(base_path):
        for f in fnames:
            if f.endswith('.mp4') or f.endswith('.jpg'):
                fp = os.path.join(root, f)
                try:
                    if os.path.getmtime(fp) < cutoff:
                        os.remove(fp)
                except OSError:
                    pass


def purge_oldest_snapshots(base_dir: str, keep_last: int = 200):
    """
    Keep only the `keep_last` most recent snapshot JPEGs in a directory.
    Called after every event snapshot is saved — ring-buffer for event images.
    """
    try:
        files = sorted(
            [f for f in os.listdir(base_dir) if f.endswith('_snap.jpg')],
        )
        excess = len(files) - keep_last
        for f in files[:excess]:
            try:
                os.remove(os.path.join(base_dir, f))
            except OSError:
                pass
    except Exception:
        pass


# ─── Camera Recording Worker ──────────────────────────────────────────────────

class CameraRecorder:
    """
    Records video for a single camera.

    CONTINUOUS mode:
        Always writes rotating segments (e.g., every 5 minutes a new file).

    MOTION mode:
        Keeps a rolling pre-buffer.
        When triggered (by any analytic event), starts writing:
          pre_buffer + live frames until post_buffer_s after last trigger.
    """

    def __init__(self, camera_id: int, config: RecordingConfig,
                 get_frame_fn):
        self.camera_id    = camera_id
        self.config       = config
        self.get_frame    = get_frame_fn   # callable → frame | None

        self._thread:   Optional[threading.Thread] = None
        self._running   = False
        self._writer:   Optional[cv2.VideoWriter]  = None
        self._writer_path: str = ""
        self._seg_start: float = 0.0

        # Motion mode state
        self._pre_buffer: deque = deque()   # sized in _run
        self._last_trigger: float = 0.0
        self._recording_motion: bool = False

    def start(self):
        self._running = True
        self._thread  = threading.Thread(
            target=self._run,
            name=f"recorder-cam{self.camera_id}",
            daemon=True,
        )
        self._thread.start()
        logger.info(f"Recorder started: cam{self.camera_id} | mode={self.config.mode} | "
                    f"path={self.config.storage_path}")

    def stop(self):
        self._running = False
        if self._writer:
            self._writer.release()
            self._writer = None
        if self._thread:
            self._thread.join(timeout=5)

    def trigger(self):
        """Call this when a detection event fires (for motion mode)."""
        self._last_trigger = time.time()

    def _cam_dir(self) -> str:
        d = os.path.join(self.config.storage_path, f"cam{self.camera_id}")
        os.makedirs(d, exist_ok=True)
        return d

    def _new_filename(self, prefix: str = "") -> str:
        ts  = datetime.now().strftime("%Y%m%d_%H%M%S")
        tag = f"{prefix}_" if prefix else ""
        return os.path.join(self._cam_dir(), f"{tag}{ts}.mp4")

    def _open_writer(self, frame, path: str):
        h, w = frame.shape[:2]
        os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
        writer = open_writer(
            path, self.config.video_fps, w, h,
            quality=self.config.video_quality,
        )
        logger.debug(f'Recording started [{codec_name()}]: {path}')
        return writer

    def _close_writer(self):
        if self._writer:
            self._writer.release()
            self._writer   = None
            self._seg_start = 0.0
            logger.debug(f'Segment saved: {self._writer_path}')
            # Enforce ring-buffer quota immediately after every segment
            self._enforce_quota()

    def _enforce_quota(self):
        """Delete oldest recordings if over quota — called after every segment."""
        usage = get_disk_usage_bytes(self.config.storage_path)
        if usage > self.config.max_disk_bytes * 0.85:   # start purging at 85%
            purge_oldest_recordings(self.config.storage_path, self.config.max_disk_bytes)

    def _run(self):
        # Size pre-buffer: pre_buffer_s * fps frames
        max_pre = int(self.config.pre_buffer_s * self.config.video_fps)
        self._pre_buffer = deque(maxlen=max(max_pre, 10))

        frame_interval = 1.0 / self.config.video_fps
        quota_check_counter = 0

        while self._running:
            t0    = time.time()
            frame = self.get_frame()

            if frame is None:
                time.sleep(0.1)
                continue

            if self.config.mode == 'continuous':
                self._write_continuous(frame)
            else:
                self._write_motion(frame)

            # Quota + age check every 30s (ring-buffer top-up)
            quota_check_counter += 1
            if quota_check_counter >= int(30 * self.config.video_fps):
                quota_check_counter = 0
                self._enforce_quota()
                purge_old_days(self.config.storage_path, self.config.retain_days)

            elapsed = time.time() - t0
            sleep   = max(0, frame_interval - elapsed)
            time.sleep(sleep)

        self._close_writer()

    def _write_continuous(self, frame):
        """Write frame to current segment, rotate when segment_seconds elapsed."""
        now = time.time()
        if self._writer is None:
            path             = self._new_filename("cont")
            self._writer     = self._open_writer(frame, path)
            self._writer_path= path
            self._seg_start  = now

        self._writer.write(frame)

        if now - self._seg_start >= self.config.segment_seconds:
            self._close_writer()

    def _write_motion(self, frame):
        """Write frame only when motion/event was recently triggered."""
        now        = time.time()
        since_trig = now - self._last_trigger

        self._pre_buffer.append(frame)

        if since_trig <= self.config.post_buffer_s:
            # We are in the recording window
            if not self._recording_motion:
                # Start new clip — flush pre-buffer first
                self._recording_motion = True
                path             = self._new_filename("event")
                self._writer     = self._open_writer(frame, path)
                self._writer_path= path
                self._seg_start  = now
                for pre_frame in self._pre_buffer:
                    self._writer.write(pre_frame)
            else:
                self._writer.write(frame)
        else:
            # Outside recording window
            if self._recording_motion:
                self._recording_motion = False
                self._close_writer()


# ─── Recording Manager ────────────────────────────────────────────────────────

class RecordingManager:
    """
    Manages one CameraRecorder per active camera.
    Configuration is shared across all cameras.
    """

    def __init__(self):
        self._recorders: dict[int, CameraRecorder] = {}
        self._config: RecordingConfig = RecordingConfig()

    @property
    def config(self) -> RecordingConfig:
        return self._config

    def configure(self, **kwargs):
        """Update recording config and restart all recorders."""
        for k, v in kwargs.items():
            if hasattr(self._config, k):
                setattr(self._config, k, v)
        logger.info(f"Recording config updated: {kwargs}")

        # Restart all active recorders with new config
        for cam_id, rec in list(self._recorders.items()):
            get_fn = rec.get_frame
            rec.stop()
            self._start_recorder(cam_id, get_fn)

    def add_camera(self, camera_id: int, get_frame_fn):
        """Register a camera and start recording if enabled."""
        if camera_id in self._recorders:
            return
        if self._config.enabled:
            self._start_recorder(camera_id, get_frame_fn)
        else:
            # Store get_frame so we can start later without a camera ref
            self._recorders[camera_id] = _PendingRecorder(camera_id, get_frame_fn)

    def remove_camera(self, camera_id: int):
        rec = self._recorders.pop(camera_id, None)
        if rec and hasattr(rec, "stop"):
            rec.stop()

    def trigger(self, camera_id: int):
        """Notify a detection event — relevant for motion mode."""
        rec = self._recorders.get(camera_id)
        if isinstance(rec, CameraRecorder):
            rec.trigger()

    def enable(self):
        """Enable recording for all registered cameras."""
        self._config.enabled = True
        for cam_id, rec in list(self._recorders.items()):
            if isinstance(rec, _PendingRecorder):
                self._start_recorder(cam_id, rec.get_frame)

    def disable(self):
        """Stop all recordings."""
        self._config.enabled = False
        for rec in self._recorders.values():
            if isinstance(rec, CameraRecorder):
                rec.stop()
        self._recorders.clear()

    def get_status(self) -> dict:
        """Return storage stats + per-camera status."""
        path    = self._config.storage_path
        os.makedirs(path, exist_ok=True)
        used_b  = get_disk_usage_bytes(path)
        free_b  = get_disk_free_bytes(path)
        max_b   = self._config.max_disk_bytes
        return {
            "enabled":        self._config.enabled,
            "mode":           self._config.mode,
            "storage_path":   path,
            "max_disk_gb":    self._config.max_disk_gb,
            "used_gb":        round(used_b / 1024**3, 3),
            "free_gb":        round(free_b / 1024**3, 1),
            "quota_used_pct": round(used_b / max_b * 100, 1) if max_b else 0,
            "segment_minutes":   self._config.segment_minutes,
            "video_fps":         self._config.video_fps,
            "pre_buffer_s":      self._config.pre_buffer_s,
            "post_buffer_s":     self._config.post_buffer_s,
            "retain_days":       self._config.retain_days,
            "active_cameras":    [c for c, r in self._recorders.items()
                                   if isinstance(r, CameraRecorder)],
        }

    def _start_recorder(self, camera_id: int, get_frame_fn):
        os.makedirs(self._config.storage_path, exist_ok=True)
        rec = CameraRecorder(camera_id, self._config, get_frame_fn)
        rec.start()
        self._recorders[camera_id] = rec


class _PendingRecorder:
    """Placeholder when recording is disabled but camera is registered."""
    def __init__(self, camera_id, get_frame):
        self.camera_id = camera_id
        self.get_frame = get_frame
    def stop(self): pass


# Global singleton
recording_manager = RecordingManager()

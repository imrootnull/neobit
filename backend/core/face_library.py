"""
Face Library — captura, almacena y gestiona rostros detectados en cámara.

Flujo (similar a Hikvision FR):
1. Pipeline detecta cara → llama FaceLibrary.capture(frame, bbox, cam_id, conf)
2. Se guarda:
   - face_crop.jpg  — recuadro del rostro con margen (lo que ve Hikvision)
   - snapshot.jpg   — frame completo en el momento de captura
   - clip.mp4       — video 3s pre + 5s post (grabado en background)
3. Se inserta registro en SQLite con status='pending'
4. API sirve imágenes y clip, permite: validar, etiquetar, descartar
"""
from __future__ import annotations
import os
import time
import sqlite3
import threading
from pathlib import Path
import cv2
import numpy as np
from loguru import logger

# ─── Storage paths ────────────────────────────────────────────────────────────

LIBRARY_DIR  = Path("data/face_library")
CLIPS_DIR    = Path("data/face_library/clips")
DB_PATH      = Path("data/neobit.db")

LIBRARY_DIR.mkdir(parents=True, exist_ok=True)
CLIPS_DIR.mkdir(parents=True, exist_ok=True)

# ─── Per-camera rate limit: capture at most 1 face every N seconds ────────────
CAPTURE_INTERVAL_S = 10   # avoids flooding; 10s feels like Hikvision behavior

# ─── Min face size to bother saving ──────────────────────────────────────────
MIN_FACE_PX = 48   # pixels — faces smaller than this are too blurry

# ─── Margin around face crop ─────────────────────────────────────────────────
CROP_MARGIN = 0.35   # 35% extra → includes forehead, chin, shoulders

# ─── Clip parameters ─────────────────────────────────────────────────────────
CLIP_PRE_S  = 3.0    # seconds of pre-buffer before detection
CLIP_POST_S = 5.0    # seconds of post-buffer after detection
CLIP_FPS    = 10.0   # output FPS for clips


class FaceLibrary:
    """Thread-safe singleton for face capture and storage."""

    _instance: "FaceLibrary | None" = None
    _lock = threading.Lock()

    def __init__(self):
        self._last_capture: dict[int, float] = {}   # camera_id → last timestamp
        self._init_db()

    @classmethod
    def get(cls) -> "FaceLibrary":
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    # ── DB ────────────────────────────────────────────────────────────────────

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._conn() as c:
            c.execute("""
                CREATE TABLE IF NOT EXISTS face_captures (
                    id            INTEGER PRIMARY KEY AUTOINCREMENT,
                    camera_id     INTEGER NOT NULL,
                    timestamp     REAL    NOT NULL,
                    image_path    TEXT    NOT NULL,
                    snapshot_path TEXT,
                    clip_path     TEXT,
                    clip_ready    INTEGER NOT NULL DEFAULT 0,
                    confidence    REAL,
                    face_w        INTEGER,
                    face_h        INTEGER,
                    status        TEXT    NOT NULL DEFAULT 'pending',
                    label         TEXT,
                    identity      TEXT,
                    similarity    REAL,
                    created_at    REAL    NOT NULL
                )
            """)
            # Migrate existing DBs: add new columns if absent
            existing = {row[1] for row in c.execute("PRAGMA table_info(face_captures)")}
            for col, defn in [
                ("snapshot_path", "TEXT"),
                ("clip_path",     "TEXT"),
                ("clip_ready",    "INTEGER NOT NULL DEFAULT 0"),
                ("identity",      "TEXT"),
                ("similarity",    "REAL"),
            ]:
                if col not in existing:
                    try:
                        c.execute(f"ALTER TABLE face_captures ADD COLUMN {col} {defn}")
                        logger.debug(f"DB migrated: added column face_captures.{col}")
                    except Exception:
                        pass

            c.execute("CREATE INDEX IF NOT EXISTS idx_fc_status    ON face_captures(status)")
            c.execute("CREATE INDEX IF NOT EXISTS idx_fc_camera    ON face_captures(camera_id)")
            c.execute("CREATE INDEX IF NOT EXISTS idx_fc_timestamp ON face_captures(timestamp)")

    # ── Capture ───────────────────────────────────────────────────────────────

    def capture(
        self,
        frame: np.ndarray,
        bbox: tuple[int, int, int, int],
        camera_id: int,
        confidence: float,
        pre_frames: list | None = None,   # frames from ring buffer for clip pre-roll
        identity:   str | None = None,    # matched identity label (if recognized)
        similarity: float      = 0.0,
    ) -> int | None:
        """
        Crop and save a detected face.

        Saves:
          - Cropped face JPEG (with margin)
          - Full-frame JPEG snapshot
          - MP4 clip (3s pre + 5s post) in background thread

        Returns the new record id, or None if rate-limited / face too small.
        """
        now = time.time()

        # Rate limit per camera
        last = self._last_capture.get(camera_id, 0)
        if now - last < CAPTURE_INTERVAL_S:
            return None

        x1, y1, x2, y2 = bbox
        fw, fh = x2 - x1, y2 - y1

        if fw < MIN_FACE_PX or fh < MIN_FACE_PX:
            return None

        ts_ms  = int(now * 1000)
        base   = f"cam{camera_id}_{ts_ms}"

        # ── Face crop ─────────────────────────────────────────────────────────
        h_frame, w_frame = frame.shape[:2]
        mx  = int(fw * CROP_MARGIN)
        my  = int(fh * CROP_MARGIN)
        cx1 = max(x1 - mx, 0)
        cy1 = max(y1 - my, 0)
        cx2 = min(x2 + mx, w_frame)
        cy2 = min(y2 + my, h_frame)

        crop = frame[cy1:cy2, cx1:cx2]
        if crop.size == 0:
            return None

        face_path = str(LIBRARY_DIR / f"{base}_face.jpg")
        cv2.imwrite(face_path, crop, [cv2.IMWRITE_JPEG_QUALITY, 92])

        # ── Full-frame snapshot ────────────────────────────────────────────────
        # Draw bbox on snapshot copy so it's clear which face triggered it
        snap_frame = frame.copy()
        cv2.rectangle(snap_frame, (x1, y1), (x2, y2), (0, 220, 120), 2)
        snap_path = str(LIBRARY_DIR / f"{base}_snap.jpg")
        cv2.imwrite(snap_path, snap_frame, [cv2.IMWRITE_JPEG_QUALITY, 85])

        # ── Clip path (written later by background thread) ────────────────────
        clip_path = str(CLIPS_DIR / f"{base}_clip.mp4")

        # ── Insert record ──────────────────────────────────────────────────────
        with self._conn() as c:
            cur = c.execute("""
                INSERT INTO face_captures
                    (camera_id, timestamp, image_path, snapshot_path, clip_path,
                     clip_ready, confidence, face_w, face_h, identity, similarity, created_at)
                VALUES (?, ?, ?, ?, ?, 0, ?, ?, ?, ?, ?, ?)
            """, (
                camera_id, now, face_path, snap_path, clip_path,
                round(confidence, 3), fw, fh,
                identity, round(similarity, 3) if similarity else None,
                now,
            ))
            new_id = cur.lastrowid

        self._last_capture[camera_id] = now
        logger.info(
            f"Face captured: cam{camera_id} id={new_id} size={fw}x{fh} "
            f"conf={confidence:.0%}"
            + (f" identity={identity} sim={similarity:.0%}" if identity else "")
        )

        # ── Record clip in background ──────────────────────────────────────────
        threading.Thread(
            target=self._record_clip,
            args=(camera_id, new_id, clip_path, pre_frames or []),
            daemon=True,
            name=f"face-clip-{new_id}",
        ).start()

        return new_id

    def _record_clip(
        self,
        camera_id: int,
        face_id:   int,
        clip_path: str,
        pre_frames: list,
    ):
        """
        Record a clip: pre_frames + POST_SECS of live frames from the ring buffer.
        Runs in a daemon thread to avoid blocking the inference pipeline.
        """
        import time as _time
        from backend.core.stream_manager import stream_manager
        from backend.core.video_writer import open_writer

        post_frames: list = []
        deadline = _time.time() + CLIP_POST_S
        interval = 1.0 / CLIP_FPS

        while _time.time() < deadline:
            t0 = _time.time()
            s  = stream_manager.streams.get(camera_id)
            if s and s.clip_buffer:
                _, latest = s.clip_buffer[-1]
                post_frames.append(latest.copy())
            elapsed = _time.time() - t0
            sleep   = interval - elapsed
            if sleep > 0:
                _time.sleep(sleep)

        all_frames = pre_frames + post_frames
        if not all_frames:
            logger.warning(f"Face clip {face_id}: no frames available")
            return

        h, w = all_frames[0].shape[:2]
        writer = open_writer(clip_path, fps=CLIP_FPS, width=w, height=h)
        for f in all_frames:
            writer.write(f)
        writer.release()

        # Mark clip as ready in DB
        with self._conn() as c:
            c.execute(
                "UPDATE face_captures SET clip_ready = 1 WHERE id = ?",
                (face_id,)
            )
        logger.info(
            f"Face clip ready: id={face_id} "
            f"frames={len(pre_frames)}pre+{len(post_frames)}post → {clip_path}"
        )


    def update_clip_identity(self, face_id: int, identity: str, similarity: float):
        """Update identity info after gallery matching (if recognized later)."""
        with self._conn() as c:
            c.execute(
                "UPDATE face_captures SET identity=?, similarity=? WHERE id=?",
                (identity, round(similarity, 3), face_id),
            )

    # ── Query ─────────────────────────────────────────────────────────────────

    def list_faces(
        self,
        status:    str | None = None,
        camera_id: int | None = None,
        page:      int = 1,
        limit:     int = 50,
    ) -> tuple[list[dict], int]:
        """Returns (rows, total_count) for the given filters."""
        where, params = [], []
        if status:
            where.append("status = ?")
            params.append(status)
        if camera_id is not None:
            where.append("camera_id = ?")
            params.append(camera_id)

        clause = ("WHERE " + " AND ".join(where)) if where else ""
        offset = (page - 1) * limit

        with self._conn() as c:
            total = c.execute(
                f"SELECT COUNT(*) FROM face_captures {clause}", params
            ).fetchone()[0]
            rows = c.execute(
                f"SELECT * FROM face_captures {clause} ORDER BY timestamp DESC LIMIT ? OFFSET ?",
                params + [limit, offset],
            ).fetchall()

        return [dict(r) for r in rows], total

    def get_face(self, face_id: int) -> dict | None:
        with self._conn() as c:
            row = c.execute(
                "SELECT * FROM face_captures WHERE id = ?", (face_id,)
            ).fetchone()
        return dict(row) if row else None

    def update_face(self, face_id: int, status: str, label: str | None = None) -> bool:
        with self._conn() as c:
            c.execute(
                "UPDATE face_captures SET status = ?, label = ? WHERE id = ?",
                (status, label, face_id),
            )
            return c.total_changes > 0

    def delete_face(self, face_id: int) -> bool:
        row = self.get_face(face_id)
        if not row:
            return False
        for col in ("image_path", "snapshot_path", "clip_path"):
            p = row.get(col)
            if p:
                try:
                    Path(p).unlink(missing_ok=True)
                except Exception:
                    pass
        with self._conn() as c:
            c.execute("DELETE FROM face_captures WHERE id = ?", (face_id,))
        return True

    def stats(self) -> dict:
        with self._conn() as c:
            rows = c.execute(
                "SELECT status, COUNT(*) as cnt FROM face_captures GROUP BY status"
            ).fetchall()
        return {r["status"]: r["cnt"] for r in rows}

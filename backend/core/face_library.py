"""
Face Library — captura, almacena y gestiona rostros detectados en cámara.

Flujo:
1. Pipeline detecta cara → llama FaceLibrary.capture(frame, bbox, cam_id, conf)
2. Se recorta el rostro con margen, se guarda como JPEG
3. Se inserta registro en SQLite con status='pending'
4. API sirve las imágenes y permite: validar, etiquetar, descartar
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

LIBRARY_DIR = Path("data/face_library")
DB_PATH     = Path("data/neobit.db")

LIBRARY_DIR.mkdir(parents=True, exist_ok=True)

# ─── Per-camera rate limit: capture at most 1 face every N seconds ────────────
CAPTURE_INTERVAL_S = 15   # avoids flooding the library with duplicate frames

# ─── Min face size to bother saving ──────────────────────────────────────────
MIN_FACE_PX = 48   # pixels — faces smaller than this are too blurry to be useful

# ─── Margin around face crop ─────────────────────────────────────────────────
CROP_MARGIN = 0.30   # 30% extra on each side so the crop includes forehead/chin


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
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    camera_id   INTEGER NOT NULL,
                    timestamp   REAL    NOT NULL,
                    image_path  TEXT    NOT NULL,
                    confidence  REAL,
                    face_w      INTEGER,
                    face_h      INTEGER,
                    status      TEXT    NOT NULL DEFAULT 'pending',
                    label       TEXT,
                    created_at  REAL    NOT NULL
                )
            """)
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
    ) -> int | None:
        """
        Crop and save a face from `frame`.
        Returns the new record id, or None if rate-limited / too small.
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

        # Add margin
        h_frame, w_frame = frame.shape[:2]
        mx = int(fw * CROP_MARGIN)
        my = int(fh * CROP_MARGIN)
        cx1 = max(x1 - mx, 0)
        cy1 = max(y1 - my, 0)
        cx2 = min(x2 + mx, w_frame)
        cy2 = min(y2 + my, h_frame)

        crop = frame[cy1:cy2, cx1:cx2]
        if crop.size == 0:
            return None

        # Save image
        fname = f"cam{camera_id}_{int(now * 1000)}.jpg"
        fpath = LIBRARY_DIR / fname
        cv2.imwrite(str(fpath), crop, [cv2.IMWRITE_JPEG_QUALITY, 90])

        # Insert record
        with self._conn() as c:
            cur = c.execute("""
                INSERT INTO face_captures
                    (camera_id, timestamp, image_path, confidence, face_w, face_h, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (camera_id, now, str(fpath), round(confidence, 3), fw, fh, now))
            new_id = cur.lastrowid

        self._last_capture[camera_id] = now
        logger.debug(f"Face captured: cam{camera_id} id={new_id} size={fw}x{fh} conf={confidence:.0%}")
        return new_id

    # ── Query ─────────────────────────────────────────────────────────────────

    def list_faces(
        self,
        status: str | None = None,
        camera_id: int | None = None,
        page: int = 1,
        limit: int = 50,
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
        # Delete image file
        try:
            Path(row["image_path"]).unlink(missing_ok=True)
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

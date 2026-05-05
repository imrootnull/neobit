"""
Face Recognizer — InsightFace buffalo_s (CPU-optimized).

Architecture:
  Detection:   RetinaFace (det_s model — lightweight for CPU)
  Embedding:   ArcFace R50 (512-d face embeddings)
  Matching:    Cosine similarity against validated faces in FaceLibrary

Flow per frame:
  1. Detect all faces via RetinaFace
  2. For each face crop → compute 512-d embedding
  3. Compare embedding against known identities (validated faces with labels)
  4. If similarity > threshold → identity match → emit recognition event
  5. Always save new captures to FaceLibrary (pending, for operator review)
"""
from __future__ import annotations

import threading
import numpy as np
from loguru import logger
from typing import Optional

# ─── Config ──────────────────────────────────────────────────────────────────

MODEL_PACK      = "buffalo_s"   # buffalo_s = det_500m + w600k_r50 — CPU friendly
                                # buffalo_l = larger, more accurate but ~3x slower
DET_THRESH      = 0.45          # face detection min score
RECOG_THRESH    = 0.45          # cosine similarity threshold for identity match
                                # >0.45 = same person (empirically validated)
MIN_FACE_PX     = 48            # ignore tiny faces

# ─── Singleton model holder ──────────────────────────────────────────────────

_app_cache: dict = {}
_app_lock  = threading.Lock()


def _load_app():
    """Load InsightFace app (downloads model on first run ~50MB)."""
    with _app_lock:
        if "app" in _app_cache:
            return _app_cache["app"]
        try:
            import insightface
            from insightface.app import FaceAnalysis

            app = FaceAnalysis(
                name=MODEL_PACK,
                providers=["CPUExecutionProvider"],   # CPU only — no CUDA
            )
            # det_size controls RetinaFace input — 320 is fast, 640 is more accurate
            app.prepare(ctx_id=0, det_size=(320, 320), det_thresh=DET_THRESH)
            _app_cache["app"] = app
            logger.success(f"InsightFace '{MODEL_PACK}' loaded OK")
            return app
        except Exception as e:
            logger.error(f"InsightFace load failed: {e}")
            _app_cache["app"] = None
            return None


def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    """Cosine similarity in [-1, 1]. Higher = more similar."""
    na = np.linalg.norm(a)
    nb = np.linalg.norm(b)
    if na == 0 or nb == 0:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


# ─── Main recognizer class ───────────────────────────────────────────────────

class FaceRecognizer:
    """
    Thread-safe InsightFace wrapper.

    Maintains an in-memory identity gallery built from validated
    FaceLibrary entries. Call `refresh_gallery()` to rebuild after
    new validations.
    """

    def __init__(self):
        self._app:     object  = None
        self._ready:   bool    = False
        self._gallery: list[dict] = []   # [{label, embedding, face_id}]
        self._gallery_lock = threading.Lock()
        threading.Thread(target=self._init, daemon=True, name="insightface-load").start()

    def _init(self):
        self._app   = _load_app()
        self._ready = self._app is not None
        if self._ready:
            self.refresh_gallery()

    # ── Gallery ───────────────────────────────────────────────────────────────

    def refresh_gallery(self):
        """
        Rebuild embedding gallery from validated FaceLibrary entries.
        Call this after validating/labeling new faces in the UI.
        """
        if not self._ready:
            return
        try:
            from backend.core.face_library import FaceLibrary, LIBRARY_DIR
            import cv2, os

            lib = FaceLibrary.get()
            rows, _ = lib.list_faces(status="validated", limit=500)
            labeled = [r for r in rows if r.get("label")]

            gallery = []
            for row in labeled:
                path = row["image_path"]
                if not os.path.exists(path):
                    continue
                img = cv2.imread(path)
                if img is None:
                    continue
                faces = self._app.get(img)
                if not faces:
                    continue
                # Take the largest face in the stored crop
                face = max(faces, key=lambda f: (f.bbox[2]-f.bbox[0]) * (f.bbox[3]-f.bbox[1]))
                gallery.append({
                    "label":    row["label"],
                    "face_id":  row["id"],
                    "embedding": face.normed_embedding,
                })

            with self._gallery_lock:
                self._gallery = gallery

            logger.info(f"Face gallery rebuilt: {len(gallery)} identity(ies)")
        except Exception as e:
            logger.warning(f"Gallery refresh failed: {e}")

    # ── Inference ─────────────────────────────────────────────────────────────

    def process(
        self,
        frame: np.ndarray,
        camera_id: int,
        config: dict,
        person_detections: list | None = None,
        draw: bool = True,
    ) -> list[dict]:
        """
        Detect and optionally identify all faces in `frame`.

        Returns list of:
          {
            'bbox':       [x1,y1,x2,y2],
            'confidence': float,   # RetinaFace score
            'identity':   str | None,  # matched label or None
            'sim':        float,   # cosine similarity (0 if no match)
            'face_id':    int | None,  # gallery entry
          }
        """
        if not self._ready or self._app is None:
            return []

        import cv2 as _cv2

        try:
            insight_faces = self._app.get(frame)
        except Exception as e:
            logger.warning(f"InsightFace inference error: {e}")
            return []

        if not insight_faces:
            return []

        with self._gallery_lock:
            gallery = list(self._gallery)

        results = []
        for face in insight_faces:
            x1, y1, x2, y2 = face.bbox.astype(int)
            x1, y1 = max(x1, 0), max(y1, 0)
            x2, y2 = min(x2, frame.shape[1]), min(y2, frame.shape[0])
            fw, fh = x2 - x1, y2 - y1

            if fw < MIN_FACE_PX or fh < MIN_FACE_PX:
                continue

            score = float(face.det_score)

            # Cross-validate against YOLO person bbox (top 40% = head region)
            if person_detections:
                fcx = (x1 + x2) / 2
                fcy = (y1 + y2) / 2
                in_person = False
                for p in person_detections:
                    px1, py1, px2, py2 = p["bbox"]
                    head_y2 = py1 + int((py2 - py1) * 0.45)
                    if px1 <= fcx <= px2 and py1 <= fcy <= head_y2:
                        in_person = True
                        break
                if not in_person:
                    continue   # false positive not inside any person bbox

            # Identity matching
            identity   = None
            best_sim   = 0.0
            best_fid   = None
            emb        = face.normed_embedding
            if emb is not None and gallery:
                for entry in gallery:
                    sim = _cosine(emb, entry["embedding"])
                    if sim > best_sim:
                        best_sim = sim
                        if sim >= RECOG_THRESH:
                            identity = entry["label"]
                            best_fid = entry["face_id"]

            rec = {
                "bbox":       [x1, y1, x2, y2],
                "confidence": round(score, 3),
                "identity":   identity,
                "sim":        round(best_sim, 3),
                "face_id":    best_fid,
            }
            results.append(rec)

            if draw:
                self._draw_face(frame, rec)

        return results

    @staticmethod
    def _draw_face(frame: np.ndarray, rec: dict):
        import cv2 as _cv2
        x1, y1, x2, y2 = rec["bbox"]
        identity = rec["identity"]
        score    = rec["confidence"]
        sim      = rec["sim"]

        # Color: teal for unknown, green for identified
        color = (0, 220, 120) if identity else (0, 200, 220)

        # Corner brackets
        L = max(min(x2 - x1, y2 - y1) // 5, 8)
        brackets = [
            [(x1, y1 + L), (x1, y1), (x1 + L, y1)],
            [(x2 - L, y1), (x2, y1), (x2, y1 + L)],
            [(x1, y2 - L), (x1, y2), (x1 + L, y2)],
            [(x2 - L, y2), (x2, y2), (x2, y2 - L)],
        ]
        for seg in brackets:
            for i in range(len(seg) - 1):
                _cv2.line(frame, seg[i], seg[i + 1], color, 2, _cv2.LINE_AA)

        # Label
        if identity:
            label = f"{identity}  {sim:.0%}"
        else:
            label = f"Rostro  {score:.0%}"

        font = _cv2.FONT_HERSHEY_DUPLEX
        fs   = 0.40
        (tw, th), _ = _cv2.getTextSize(label, font, fs, 1)
        pad = 4
        _cv2.rectangle(frame, (x1, y1 - th - pad * 2), (x1 + tw + pad * 2, y1), color, -1)
        _cv2.putText(frame, label, (x1 + pad, y1 - pad),
                     font, fs, (10, 10, 10), 1, _cv2.LINE_AA)

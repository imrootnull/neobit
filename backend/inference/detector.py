"""
Real-time Object Detector using YOLOv8.

Runs inference on camera frames and draws bounding boxes directly on the image.
The annotated frame is stored back in the StreamManager's annotated buffer
so the MJPEG endpoint can serve it to the dashboard.

Supported analytics driven by this detector:
  - person_detection
  - vehicle_detection
  - person_counting
  - vehicle_counting
  - crowd_detection
  - intrusion_detection   (zone-based — future)
  - line_crossing         (line-based — future)
"""
import cv2
import numpy as np
import threading
import time
from typing import Optional
from loguru import logger

# ─── Visual style constants ───────────────────────────────────────────────────

# BGR colors per class category
CLASS_COLORS = {
    # People
    "person":       (0,   200, 255),   # cyan-orange
    # Vehicles
    "car":          (255, 100,  50),   # blue
    "truck":        (255, 150,  50),   # blue-lighter
    "bus":          (255, 120,  80),
    "motorcycle":   (200, 100, 255),
    "bicycle":      (150, 255, 100),
    # Fire/smoke
    "fire":         ( 20,  60, 255),   # red
    "smoke":        (180, 180, 180),
    # Default
    "__default__":  ( 50, 200, 100),
}

FONT            = cv2.FONT_HERSHEY_DUPLEX
FONT_SCALE      = 0.50
FONT_THICKNESS  = 1
BOX_THICKNESS   = 2
LABEL_PAD       = 4


def _color_for(class_name: str) -> tuple:
    return CLASS_COLORS.get(class_name.lower(), CLASS_COLORS["__default__"])


def _draw_detection(frame, x1, y1, x2, y2, label: str, confidence: float,
                    color: tuple, track_id: int | None = None):
    """Draw a Dahua SMD-style corner-bracket bounding box with label."""
    w, h = x2 - x1, y2 - y1
    L = max(min(w, h) // 5, 10)   # bracket length
    T = 2                          # line thickness

    # Corner brackets (4 corners, 2 lines each)
    corners = [
        [(x1, y1 + L), (x1, y1), (x1 + L, y1)],           # top-left
        [(x2 - L, y1), (x2, y1), (x2, y1 + L)],           # top-right
        [(x1, y2 - L), (x1, y2), (x1 + L, y2)],           # bottom-left
        [(x2 - L, y2), (x2, y2), (x2, y2 - L)],           # bottom-right
    ]
    for pts in corners:
        for i in range(len(pts) - 1):
            cv2.line(frame, pts[i], pts[i + 1], color, T, cv2.LINE_AA)

    # Thin full border (semi-transparent)
    overlay = frame.copy()
    cv2.rectangle(overlay, (x1, y1), (x2, y2), color, 1)
    cv2.addWeighted(overlay, 0.25, frame, 0.75, 0, frame)

    # Label (top-left of box)
    id_str = f"#{track_id} " if track_id is not None else ""
    text   = f"{id_str}{label} {confidence:.0%}"
    (tw, th), _ = cv2.getTextSize(text, FONT, FONT_SCALE, FONT_THICKNESS)
    ly1 = max(y1 - th - LABEL_PAD * 2, 0)
    ly2 = y1

    # Label bg
    bg = frame.copy()
    cv2.rectangle(bg, (x1, ly1), (x1 + tw + LABEL_PAD * 2, ly2), (15, 15, 20), -1)
    cv2.addWeighted(bg, 0.72, frame, 0.28, 0, frame)

    cv2.putText(
        frame, text,
        (x1 + LABEL_PAD, ly2 - LABEL_PAD),
        FONT, FONT_SCALE, color, FONT_THICKNESS, cv2.LINE_AA,
    )


def _draw_overlay_stats(frame, detections: list, enabled_analytics: list):
    """Bottom stats bar + top-right corner panel showing live counts."""
    h, w = frame.shape[:2]

    # ── Bottom bar ──────────────────────────────────────────────────────
    bar_h = 24
    overlay = frame.copy()
    cv2.rectangle(overlay, (0, h - bar_h), (w, h), (12, 12, 18), -1)
    cv2.addWeighted(overlay, 0.70, frame, 0.30, 0, frame)

    counts: dict[str, int] = {}
    for d in detections:
        counts[d["class"]] = counts.get(d["class"], 0) + 1

    stats_parts = []
    for cls, cnt in counts.items():
        label = {
            "person": "Personas", "car": "Autos", "truck": "Camiones",
            "bus": "Autobuses", "motorcycle": "Motos", "bicycle": "Bicicletas",
        }.get(cls, cls.capitalize())
        stats_parts.append(f"{label}: {cnt}")
    stats_text = "  |  ".join(stats_parts) if stats_parts else "Sin detecciones"

    cv2.putText(frame, stats_text, (8, h - 7),
                FONT, 0.40, (160, 220, 255), 1, cv2.LINE_AA)

    # ── Top-right counter panel (like Dahua) ──────────────────────────
    persons  = counts.get("person", 0)
    vehicles = sum(counts.get(c, 0) for c in ("car","truck","bus","motorcycle","bicycle"))

    panel_w, panel_h = 130, 48
    px1 = w - panel_w - 6
    py1 = 4
    bg2 = frame.copy()
    cv2.rectangle(bg2, (px1, py1), (px1 + panel_w, py1 + panel_h), (12, 12, 18), -1)
    cv2.addWeighted(bg2, 0.72, frame, 0.28, 0, frame)
    cv2.rectangle(frame, (px1, py1), (px1 + panel_w, py1 + panel_h),
                  (60, 80, 100), 1)

    cv2.putText(frame, f"Personas: {persons}",
                (px1 + 6, py1 + 17), FONT, 0.40, (0, 200, 255), 1, cv2.LINE_AA)
    cv2.putText(frame, f"Vehiculos: {vehicles}",
                (px1 + 6, py1 + 36), FONT, 0.40, (255, 150, 80), 1, cv2.LINE_AA)

    # IA badge (top-right corner below panel)
    if enabled_analytics:
        badge = f"IA: {len(enabled_analytics)} activas"
        (bw, _), _ = cv2.getTextSize(badge, FONT, 0.36, 1)
        cv2.putText(frame, badge, (w - bw - 8, py1 + panel_h + 16),
                    FONT, 0.36, (100, 255, 180), 1, cv2.LINE_AA)


# ─── Model loader (lazy, singleton per model path) ───────────────────────────

_model_cache: dict[str, object] = {}
_model_lock  = threading.Lock()


def _load_model(model_path: str = "yolov8n.pt"):
    """Load and cache a YOLO model. Downloads on first use (~6 MB for nano)."""
    with _model_lock:
        if model_path not in _model_cache:
            try:
                from ultralytics import YOLO
                logger.info(f"Loading YOLO model: {model_path}")
                _model_cache[model_path] = YOLO(model_path)
                logger.success(f"YOLO model loaded: {model_path}")
            except Exception as e:
                logger.error(f"Failed to load YOLO model {model_path}: {e}")
                _model_cache[model_path] = None
        return _model_cache[model_path]


# ─── YOLO class → analytic mapping ───────────────────────────────────────────

# Which YOLO class IDs are relevant to each analytic
ANALYTIC_CLASSES: dict[str, set[str]] = {
    "person_detection":    {"person"},
    "vehicle_detection":   {"car", "truck", "bus", "motorcycle", "bicycle"},
    "person_counting":     {"person"},
    "vehicle_counting":    {"car", "truck", "bus", "motorcycle", "bicycle"},
    "crowd_detection":     {"person"},
    "intrusion_detection": {"person"},
    "line_crossing":       {"person", "car", "truck"},
    "theft_detection":     {"person"},
    "loitering_detection": {"person"},
    "tailgating":          {"person"},
    "forklift_safety":     {"person"},
}

# Analytics that need the YOLO general model
YOLO_ANALYTICS = set(ANALYTIC_CLASSES.keys())


# ─── Detector class ───────────────────────────────────────────────────────────

class YOLODetector:
    """
    Wraps a YOLO model for a specific camera.
    Runs inference, filters by enabled analytics, draws bounding boxes.
    Returns annotated frame + structured detections.
    """

    def __init__(self, model_path: str = "yolov8n.pt",
                 device: str = "cpu",
                 conf_threshold: float = 0.45):
        self.model_path     = model_path
        self.device         = device
        self.conf_threshold = conf_threshold
        self._model         = None

    def ensure_loaded(self) -> bool:
        if self._model is not None:
            return True
        self._model = _load_model(self.model_path)
        return self._model is not None

    def detect(self,
               frame: np.ndarray,
               enabled_analytics: dict[str, dict],
               draw: bool = True) -> tuple[np.ndarray, list[dict]]:
        """
        Run tracking+detection on a frame.
        Uses model.track() for persistent object IDs across frames.
        Falls back to model() if tracking fails.

        Returns:
            (annotated_frame, detections)
            detections: [{"class", "confidence", "bbox", "track_id"}]
        """
        if not self.ensure_loaded():
            return frame, []

        target_classes: set[str] = set()
        for key in enabled_analytics:
            if key in ANALYTIC_CLASSES:
                target_classes.update(ANALYTIC_CLASSES[key])

        if not target_classes:
            return frame, []

        min_conf = min(
            (cfg.get("confidence", self.conf_threshold)
             for cfg in enabled_analytics.values()),
            default=self.conf_threshold,
        )

        try:
            # Use track() for persistent IDs (ByteTrack built into ultralytics)
            results = self._model.track(
                frame,
                conf=min_conf,
                device=self.device,
                verbose=False,
                stream=False,
                persist=True,     # maintain tracker state across calls
                tracker="bytetrack.yaml",
            )
        except Exception:
            # Fallback to plain detection if tracking unavailable
            try:
                results = self._model(
                    frame, conf=min_conf, device=self.device,
                    verbose=False, stream=False,
                )
            except Exception as e:
                logger.warning(f"YOLO inference error: {e}")
                return frame, []

        annotated  = frame.copy() if draw else frame
        detections: list[dict] = []

        LABELS = {
            "person":     "Persona",
            "car":        "Auto",
            "truck":      "Camión",
            "bus":        "Autobús",
            "motorcycle": "Moto",
            "bicycle":    "Bicicleta",
        }

        for result in results:
            boxes = result.boxes
            if boxes is None:
                continue
            for box in boxes:
                cls_id   = int(box.cls[0])
                cls_name = result.names.get(cls_id, str(cls_id)).lower()
                conf     = float(box.conf[0])

                if cls_name not in target_classes:
                    continue

                xyxy = box.xyxy[0].cpu().numpy().astype(int)
                x1, y1, x2, y2 = xyxy

                # Extract track ID if available
                track_id = None
                if box.id is not None:
                    track_id = int(box.id[0])

                detections.append({
                    "class":      cls_name,
                    "confidence": conf,
                    "bbox":       [int(x1), int(y1), int(x2), int(y2)],
                    "track_id":   track_id,
                })

                if draw:
                    color = _color_for(cls_name)
                    label = LABELS.get(cls_name, cls_name.capitalize())
                    _draw_detection(annotated, x1, y1, x2, y2, label, conf,
                                    color, track_id)

        if draw:
            _draw_overlay_stats(annotated, detections,
                                list(enabled_analytics.keys()))

        return annotated, detections

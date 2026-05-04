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


def _draw_detection(frame, x1, y1, x2, y2, label: str, confidence: float, color: tuple):
    """Draw a single bounding box with label on the frame (in-place)."""
    # Box
    cv2.rectangle(frame, (x1, y1), (x2, y2), color, BOX_THICKNESS)

    # Label background
    text     = f"{label} {confidence:.0%}"
    (tw, th), _ = cv2.getTextSize(text, FONT, FONT_SCALE, FONT_THICKNESS)
    ly1 = max(y1 - th - LABEL_PAD * 2, 0)
    ly2 = y1
    cv2.rectangle(frame, (x1, ly1), (x1 + tw + LABEL_PAD * 2, ly2), color, -1)

    # Label text (dark on colored bg)
    cv2.putText(
        frame, text,
        (x1 + LABEL_PAD, ly2 - LABEL_PAD),
        FONT, FONT_SCALE, (10, 10, 10), FONT_THICKNESS, cv2.LINE_AA,
    )


def _draw_overlay_stats(frame, detections: list, enabled_analytics: list):
    """Draw a translucent stats bar at the bottom of the frame."""
    h, w = frame.shape[:2]
    bar_h = 28

    # Semi-transparent bar
    overlay = frame.copy()
    cv2.rectangle(overlay, (0, h - bar_h), (w, h), (15, 15, 20), -1)
    cv2.addWeighted(overlay, 0.65, frame, 0.35, 0, frame)

    # Count by class
    counts: dict[str, int] = {}
    for d in detections:
        cls = d["class"]
        counts[cls] = counts.get(cls, 0) + 1

    stats_parts = [f"{cls}: {cnt}" for cls, cnt in counts.items()]
    stats_text  = "  |  ".join(stats_parts) if stats_parts else "Sin detecciones"

    cv2.putText(
        frame, stats_text,
        (8, h - 9),
        FONT, 0.42, (180, 220, 255), 1, cv2.LINE_AA,
    )

    # Active analytics indicator (top-right corner)
    if enabled_analytics:
        badge = f"IA: {len(enabled_analytics)} activas"
        (bw, _), _ = cv2.getTextSize(badge, FONT, 0.38, 1)
        cv2.putText(
            frame, badge,
            (w - bw - 8, 18),
            FONT, 0.38, (100, 255, 180), 1, cv2.LINE_AA,
        )


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
        Run detection on a frame.

        Args:
            frame:            OpenCV BGR frame
            enabled_analytics: {key: config_dict} for all active analytics
            draw:             Whether to draw bboxes on the frame

        Returns:
            (annotated_frame, detections)
            detections: [{"class": str, "confidence": float, "bbox": [x1,y1,x2,y2]}]
        """
        if not self.ensure_loaded():
            return frame, []

        # Determine which classes to show based on enabled analytics
        target_classes: set[str] = set()
        for key in enabled_analytics:
            if key in ANALYTIC_CLASSES:
                target_classes.update(ANALYTIC_CLASSES[key])

        if not target_classes:
            return frame, []

        # Get minimum confidence (use lowest configured across active analytics)
        min_conf = min(
            (cfg.get("confidence", self.conf_threshold)
             for cfg in enabled_analytics.values()),
            default=self.conf_threshold,
        )

        try:
            results = self._model(
                frame,
                conf=min_conf,
                device=self.device,
                verbose=False,
                stream=False,
            )
        except Exception as e:
            logger.warning(f"YOLO inference error: {e}")
            return frame, []

        annotated = frame.copy() if draw else frame
        detections: list[dict] = []

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

                detections.append({
                    "class":      cls_name,
                    "confidence": conf,
                    "bbox":       [int(x1), int(y1), int(x2), int(y2)],
                })

                if draw:
                    color = _color_for(cls_name)
                    label = {
                        "person":     "Persona",
                        "car":        "Vehículo",
                        "truck":      "Camión",
                        "bus":        "Autobús",
                        "motorcycle": "Moto",
                        "bicycle":    "Bicicleta",
                    }.get(cls_name, cls_name.capitalize())
                    _draw_detection(annotated, x1, y1, x2, y2, label, conf, color)

        if draw:
            _draw_overlay_stats(annotated, detections,
                                list(enabled_analytics.keys()))

        return annotated, detections

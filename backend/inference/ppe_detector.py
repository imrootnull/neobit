"""
PPE Detector — model-based Personal Protective Equipment detection.

Uses a pre-trained YOLOv8 model (keremberke/yolov8n-safety-equipment-detection)
downloaded from HuggingFace Hub on first use (~6 MB).

Detected classes:
  Positive (PPE present): Hardhat, Safety Vest, Mask, Safety Cone
  Negative (PPE missing): NO-Hardhat, NO-Safety Vest, NO-Mask

This approach is color/brand agnostic — works for any client's PPE equipment.
"""
from __future__ import annotations

import os
import threading
import cv2
import numpy as np
from typing import Optional
from loguru import logger

# ─── Model source ─────────────────────────────────────────────────────────────

HF_REPO     = "keremberke/yolov8n-protective-equipment-detection"
HF_FILENAME = "best.pt"

# ─── Class maps ──────────────────────────────────────────────────────────────

# Map model class names (lowercase) → our EPP item key
# Model classes: helmet, no_helmet, glove, no_glove, goggles, no_goggles,
#                mask, no_mask, shoes, no_shoes
PPE_PRESENT = {
    "helmet":   "helmet",
    "glove":    "gloves",
    "goggles":  "goggles",
    "mask":     "mask",
    "shoes":    "shoes",
}
PPE_ABSENT = {
    "no_helmet":  "helmet",
    "no_glove":   "gloves",
    "no_goggles": "goggles",
    "no_mask":    "mask",
    "no_shoes":   "shoes",
}

# Colors for drawing (BGR)
COLOR_OK      = (0,   210,  80)   # green
COLOR_MISSING = (0,    60, 230)   # red
COLOR_INFO    = (200, 180,  50)   # amber (neutral info)

FONT       = cv2.FONT_HERSHEY_DUPLEX
FONT_SCALE = 0.42
THICKNESS  = 1


# ─── Singleton model loader ───────────────────────────────────────────────────

_model_cache: dict[str, object] = {}
_model_lock  = threading.Lock()


def _load_ppe_model() -> Optional[object]:
    """Download and cache the PPE YOLO model. Returns None if unavailable."""
    with _model_lock:
        if HF_REPO in _model_cache:
            return _model_cache[HF_REPO]

        try:
            from huggingface_hub import hf_hub_download
            logger.info(f"Downloading PPE model from HuggingFace: {HF_REPO}")
            model_path = hf_hub_download(repo_id=HF_REPO, filename=HF_FILENAME)
            from ultralytics import YOLO
            model = YOLO(model_path)
            _model_cache[HF_REPO] = model
            logger.success(f"PPE model loaded: {HF_REPO}")
            return model
        except ImportError:
            logger.warning("huggingface_hub not installed — PPE model unavailable")
        except Exception as e:
            logger.warning(f"PPE model download failed: {e}")

        _model_cache[HF_REPO] = None
        return None


# ─── PPE Detector class ───────────────────────────────────────────────────────

class PPEDetector:
    """
    Detects PPE items (helmet, vest, mask…) using a dedicated YOLO model.
    Works regardless of PPE color, brand, or style.
    Falls back to a banner overlay when the model is not available.
    """

    def __init__(self, device: str = "cpu", conf_threshold: float = 0.25):
        self.device         = device
        self.conf_threshold = conf_threshold
        self._model         = None
        self._model_ready   = False
        # Start model loading in background so it doesn't block startup
        threading.Thread(target=self._init_model, daemon=True).start()

    def _init_model(self):
        self._model       = _load_ppe_model()
        self._model_ready = True

    def detect(
        self,
        frame: np.ndarray,
        config: dict,
        draw: bool = True,
    ) -> tuple[np.ndarray, list[dict]]:
        """
        Run PPE detection on a frame.

        Returns:
            (annotated_frame, results)
            results: list of {
                'class': str,       # 'Hardhat', 'NO-Hardhat', 'Safety Vest', etc.
                'ppe_key': str,     # 'helmet', 'vest', 'mask'
                'present': bool,    # True if PPE detected, False if missing
                'confidence': float,
                'bbox': [x1,y1,x2,y2]
            }
        """
        if not self._model_ready or self._model is None:
            # Model still loading or unavailable — return frame unchanged
            return frame, []

        conf = config.get("confidence", self.conf_threshold)

        try:
            results = self._model(
                frame,
                conf=conf,
                device=self.device,
                verbose=False,
                stream=False,
            )
        except Exception as e:
            logger.warning(f"PPE inference error: {e}")
            return frame, []

        annotated = frame.copy() if draw else frame
        detections: list[dict] = []

        for result in results:
            boxes = result.boxes
            if boxes is None:
                continue
            for box in boxes:
                cls_id   = int(box.cls[0])
                cls_name = result.names.get(cls_id, "").lower().strip()
                conf_val = float(box.conf[0])
                xyxy     = box.xyxy[0].cpu().numpy().astype(int)
                x1, y1, x2, y2 = xyxy

                # Skip 'person', 'vehicle', 'machinery', 'safety cone' (non-PPE status)
                if cls_name in ("person", "machinery", "vehicle", "safety cone"):
                    continue

                present = cls_name in PPE_PRESENT
                absent  = cls_name in PPE_ABSENT
                if not present and not absent:
                    continue

                ppe_key = PPE_PRESENT.get(cls_name) or PPE_ABSENT.get(cls_name)

                detections.append({
                    "class":      cls_name,
                    "ppe_key":    ppe_key,
                    "present":    present,
                    "confidence": conf_val,
                    "bbox":       [int(x1), int(y1), int(x2), int(y2)],
                })

                if draw:
                    color = COLOR_OK if present else COLOR_MISSING
                    label_map = {
                        "helmet":     "Casco ✓",
                        "no_helmet":  "Sin casco",
                        "glove":      "Guantes ✓",
                        "no_glove":   "Sin guantes",
                        "goggles":    "Gafas ✓",
                        "no_goggles": "Sin gafas",
                        "mask":       "Mascarilla ✓",
                        "no_mask":    "Sin mascarilla",
                        "shoes":      "Calzado ✓",
                        "no_shoes":   "Sin calzado",
                    }
                    label = label_map.get(cls_name, cls_name.title())
                    self._draw_ppe_box(annotated, x1, y1, x2, y2, label, conf_val, color)

        return annotated, detections

    @staticmethod
    def _draw_ppe_box(frame, x1, y1, x2, y2, label: str, conf: float, color: tuple):
        """Draw a bounding box with label for a PPE detection."""
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)

        text = f"{label} {conf:.0%}"
        (tw, th), _ = cv2.getTextSize(text, FONT, FONT_SCALE, THICKNESS)
        ly1 = max(y1 - th - 6, 0)
        ly2 = y1

        # Label background
        cv2.rectangle(frame, (x1, ly1), (x1 + tw + 6, ly2), color, -1)
        # Label text
        cv2.putText(
            frame, text,
            (x1 + 3, ly2 - 3),
            FONT, FONT_SCALE, (10, 10, 10), THICKNESS, cv2.LINE_AA,
        )

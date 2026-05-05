"""
PPE Detector — High-precision Personal Protective Equipment detection.

Uses TWO complementary models:
  PRIMARY:   Tanishjain9/yolov8n-ppe-detection-6classes
             Classes: Gloves, Vest, goggles, helmet, mask, safety_shoe
             Fine-tuned on Construction Site Safety dataset (Roboflow)

  SECONDARY: keremberke/yolov8m-protective-equipment-detection
             Classes: glove, goggles, helmet, mask, no_glove, no_goggles,
                      no_helmet, no_mask, no_shoes, shoes
             Used for 'no_xxx' absence signals (helmet/glove/goggles/mask)

Both models run on every frame; results are merged.
"""
from __future__ import annotations

import os
import threading
import cv2
import numpy as np
from typing import Optional
from loguru import logger

# ─── Model repos ──────────────────────────────────────────────────────────────
# Primary model — has Vest/Gloves/goggles/helmet/mask/safety_shoe
HF_PRIMARY_REPO = "Tanishjain9/yolov8n-ppe-detection-6classes"
HF_PRIMARY_FILE = "best.pt"

# Secondary model — has no_xxx absence classes (glove,goggles,helmet,mask,shoes)
HF_SECONDARY_REPO = "keremberke/yolov8m-protective-equipment-detection"
HF_SECONDARY_FILE = "best.pt"

# ─── Class maps ───────────────────────────────────────────────────────────────
# Map model class names (lowercase, normalized) → canonical EPP key
# The medium model may have slightly different class names — handle both
PPE_PRESENT: dict[str, str] = {
    # Helmets / hard hats
    "helmet":          "helmet",
    "hardhat":         "helmet",
    "hard hat":        "helmet",
    "hard_hat":        "helmet",
    # Safety vest
    "vest":            "vest",
    "safety vest":     "vest",
    "safety_vest":     "vest",
    "jacket":          "vest",
    # Gloves
    "glove":           "gloves",
    "gloves":          "gloves",
    # Goggles / safety glasses
    "goggles":         "goggles",
    "glasses":         "goggles",
    "safety glasses":  "goggles",
    "safety_glasses":  "goggles",
    # Mask
    "mask":            "mask",
    "face mask":       "mask",
    "face_mask":       "mask",
    # Footwear
    "shoes":           "shoes",
    "boots":           "shoes",
    "safety shoes":    "shoes",
    "safety_shoes":    "shoes",
    # Overalls
    "overalls":        "overalls",
    "coverall":        "overalls",
    "coveralls":       "overalls",
    "ppe-suit":        "overalls",
    "ppe_suit":        "overalls",
    # Safety harness
    "harness":         "harness",
    "safety-harness":  "harness",
    "safety_harness":  "harness",
    # Ear protection
    "ear-protector":   "ear_protector",
    "ear_protector":   "ear_protector",
    "earmuff":         "ear_protector",
    "earplugs":        "ear_protector",
}

PPE_ABSENT: dict[str, str] = {
    "no_helmet":        "helmet",
    "no-helmet":        "helmet",
    "no_hardhat":       "helmet",
    "no-hardhat":       "helmet",
    "no_vest":          "vest",
    "no-vest":          "vest",
    "no_safety_vest":   "vest",
    "no-safety-vest":   "vest",
    "no_glove":         "gloves",
    "no-glove":         "gloves",
    "no_gloves":        "gloves",
    "no-gloves":        "gloves",
    "no_goggles":       "goggles",
    "no-goggles":       "goggles",
    "no_mask":          "mask",
    "no-mask":          "mask",
    "no_shoes":         "shoes",
    "no-shoes":         "shoes",
    "no_overalls":      "overalls",
    "no-overalls":      "overalls",
    "no_harness":       "harness",
    "no-harness":       "harness",
    "no_ear_protector": "ear_protector",
    "no-ear-protector": "ear_protector",
}

# Human-readable Spanish labels for each EPP key
EPP_LABELS_ES: dict[str, str] = {
    "helmet":        "Casco",
    "vest":          "Chaleco",
    "gloves":        "Guantes",
    "goggles":       "Lentes",
    "mask":          "Mascarilla",
    "shoes":         "Botas",
    "overalls":      "Overol",
    "harness":       "Arnés",
    "ear_protector": "Protector auditivo",
}

# Body zone: (top_frac, bottom_frac) of person bounding box height where item MUST appear
# 0.0 = top of person bbox, 1.0 = bottom
BODY_ZONES: dict[str, tuple[float, float]] = {
    "helmet":        (0.00, 0.25),   # head: top 25%
    "goggles":       (0.02, 0.28),   # face/eyes: top 28%
    "mask":          (0.05, 0.30),   # lower face: 5–30%
    "ear_protector": (0.00, 0.25),   # ears: head zone
    "vest":          (0.15, 0.75),   # torso: 15–75%
    "harness":       (0.05, 0.85),   # full torso+shoulders: 5–85%
    "gloves":        (0.40, 1.00),   # hands/forearms: lower 60%
    "shoes":         (0.70, 1.00),   # feet: bottom 30%
    "overalls":      (0.05, 1.00),   # full body: 5–100%
}

ZONE_NAMES_ES: dict[str, str] = {
    "helmet":        "cabeza",
    "goggles":       "cara",
    "mask":          "cara",
    "ear_protector": "orejas",
    "vest":          "torso",
    "harness":       "cuerpo",
    "gloves":        "manos",
    "shoes":         "pies",
    "overalls":      "cuerpo",
}

# Colors (BGR)
COLOR_OK      = (0,   210,  80)   # green
COLOR_MISSING = (0,    50, 220)   # red
COLOR_MISUSE  = (0,   140, 230)   # amber
COLOR_TEXT    = (255, 255, 255)

FONT       = cv2.FONT_HERSHEY_DUPLEX
FONT_SCALE = 0.42
THICKNESS  = 1


# ─── Singleton model loader ──────────────────────────────────────────────────

_model_cache: dict[str, object] = {}
_model_lock  = threading.Lock()


def _try_load(repo: str, filename: str):
    try:
        from huggingface_hub import hf_hub_download
        from ultralytics import YOLO
        logger.info(f"Downloading PPE model: {repo}")
        path = hf_hub_download(repo_id=repo, filename=filename)
        model = YOLO(path)
        logger.success(f"PPE model loaded: {repo}")
        return model
    except Exception as e:
        logger.warning(f"PPE model {repo} failed: {e}")
        return None


def _load_ppe_models() -> tuple:
    """Load primary (6-class) and secondary (absence) models."""
    with _model_lock:
        if "ppe_primary" in _model_cache:
            return _model_cache["ppe_primary"], _model_cache.get("ppe_secondary")

        primary = _try_load(HF_PRIMARY_REPO, HF_PRIMARY_FILE)
        if primary is None:
            # Final fallback: keremberke nano
            primary = _try_load("keremberke/yolov8n-protective-equipment-detection", "best.pt")
        _model_cache["ppe_primary"] = primary

        secondary = _try_load(HF_SECONDARY_REPO, HF_SECONDARY_FILE)
        _model_cache["ppe_secondary"] = secondary

        logger.info(f"PPE models ready — primary: {'OK' if primary else 'FAIL'}, secondary: {'OK' if secondary else 'FAIL'}")
        return primary, secondary


# ─── PPE Detector ────────────────────────────────────────────────────────────

class PPEDetector:
    """
    Dual-model PPE detector:
      PRIMARY:   Tanishjain9/yolov8n-ppe-detection-6classes
                 Detects Gloves, Vest, goggles, helmet, mask, safety_shoe
      SECONDARY: keremberke/yolov8m-protective-equipment-detection
                 Provides no_xxx absence signals for helmet, gloves, goggles, mask
    Results from both models are merged before spatial zone analysis.
    """

    def __init__(self, device: str = "cpu", conf_threshold: float = 0.25):
        self.device          = device
        self.conf_threshold  = conf_threshold
        self._primary        = None
        self._secondary      = None
        self._model_ready    = False
        threading.Thread(target=self._init_model, daemon=True,
                         name="ppe-model-load").start()

    def _init_model(self):
        self._primary, self._secondary = _load_ppe_models()
        self._model_ready = True

    def detect(
        self,
        frame: np.ndarray,
        config: dict,
        draw: bool = True,
    ) -> tuple[np.ndarray, list[dict]]:
        """
        Run PPE detection using both models and return merged detections.

        Returns:
            (frame, detections)
            detections: [{
                'class':      str,   # raw model class name
                'ppe_key':    str,   # canonical key: helmet/vest/gloves/…
                'present':    bool,  # True=PPE present, False=absent signal
                'confidence': float,
                'bbox':       [x1,y1,x2,y2]
            }]
        """
        if not self._model_ready or self._primary is None:
            return frame, []

        conf = config.get("confidence", self.conf_threshold)
        detections: list[dict] = []

        # ── Run each loaded model ─────────────────────────────────────────────
        models_to_run = [m for m in (self._primary, self._secondary) if m is not None]
        for model in models_to_run:
            try:
                results = model(
                    frame, conf=conf, device=self.device,
                    verbose=False, stream=False,
                )
            except Exception as e:
                logger.warning(f"PPE inference error: {e}")
                continue

            for result in results:
                boxes = result.boxes
                if boxes is None:
                    continue
                names = result.names or {}
                for box in boxes:
                    cls_id   = int(box.cls[0])
                    raw_name = names.get(cls_id, "").lower().strip()
                    conf_val = float(box.conf[0])
                    xyxy     = box.xyxy[0].cpu().numpy().astype(int)
                    x1, y1, x2, y2 = xyxy

                    # Skip non-EPP classes
                    if raw_name in ("person", "machinery", "vehicle",
                                    "safety cone", "cone", "worker"):
                        continue

                    present = raw_name in PPE_PRESENT
                    absent  = raw_name in PPE_ABSENT

                    if not present and not absent:
                        # Try partial / substring match
                        matched_key = None
                        for k, v in PPE_PRESENT.items():
                            if k in raw_name or raw_name in k:
                                matched_key = v
                                present = True
                                break
                        if not matched_key:
                            for k, v in PPE_ABSENT.items():
                                if k in raw_name or raw_name in k:
                                    matched_key = v
                                    absent = True
                                    break
                        if not matched_key:
                            logger.trace(f"PPE unknown class: '{raw_name}'")
                            continue
                        ppe_key = matched_key
                    else:
                        ppe_key = PPE_PRESENT.get(raw_name) or PPE_ABSENT.get(raw_name)

                    detections.append({
                        "class":      raw_name,
                        "ppe_key":    ppe_key,
                        "present":    present,
                        "confidence": conf_val,
                        "bbox":       [int(x1), int(y1), int(x2), int(y2)],
                    })

        return frame, detections

    @staticmethod
    def draw_ppe_overlay(
        frame: np.ndarray,
        x1: int, y1: int, x2: int, y2: int,
        label: str,
        conf: float,
        status: str,   # 'correct' | 'missing' | 'misuse'
    ):
        """
        Draw a rich semi-transparent overlay on an EPP detection.
          correct  → green fill + green border + checkmark label
          misuse   → amber fill + amber border + warning label
          missing  → red fill  + red border  + X label
        """
        import cv2 as _cv2

        COLOR_MAP = {
            "correct": (0,   210,  70),    # green
            "misuse":  (0,   160, 230),    # amber
            "missing": (40,   40, 220),    # red
        }
        STATUS_ICON = {
            "correct": "✓",
            "misuse":  "!",
            "missing": "✗",
        }

        color = COLOR_MAP.get(status, (120, 120, 120))
        icon  = STATUS_ICON.get(status, "?")

        # Semi-transparent fill
        overlay = frame.copy()
        alpha   = 0.18 if status == "correct" else 0.28
        _cv2.rectangle(overlay, (x1, y1), (x2, y2), color, -1)
        _cv2.addWeighted(overlay, alpha, frame, 1 - alpha, 0, frame)

        # Border — thicker for violations
        border_t = 2 if status == "correct" else 3
        _cv2.rectangle(frame, (x1, y1), (x2, y2), color, border_t)

        # Corner brackets for professional NVR look
        L = max(min((x2 - x1), (y2 - y1)) // 5, 8)
        pts = [
            [(x1, y1 + L), (x1, y1), (x1 + L, y1)],
            [(x2 - L, y1), (x2, y1), (x2, y1 + L)],
            [(x1, y2 - L), (x1, y2), (x1 + L, y2)],
            [(x2 - L, y2), (x2, y2), (x2, y2 - L)],
        ]
        for seg in pts:
            for i in range(len(seg) - 1):
                _cv2.line(frame, seg[i], seg[i + 1], color, 2, _cv2.LINE_AA)

        # Label background + text
        text = f"{icon} {label}  {conf:.0%}"
        font       = _cv2.FONT_HERSHEY_DUPLEX
        font_scale = 0.40
        thickness  = 1
        (tw, th), _ = _cv2.getTextSize(text, font, font_scale, thickness)
        pad  = 4
        lx1  = x1
        ly1  = max(y1 - th - pad * 2, 0)
        ly2  = y1
        _cv2.rectangle(frame, (lx1, ly1), (lx1 + tw + pad * 2, ly2), color, -1)
        _cv2.putText(
            frame, text,
            (lx1 + pad, ly2 - pad),
            font, font_scale, (10, 10, 10), thickness, _cv2.LINE_AA,
        )


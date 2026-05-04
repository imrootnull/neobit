"""
Inference Pipeline — per-camera analytics engine.

Architecture:
  StreamManager → frame buffer → InferencePipeline → EventBus

Each camera runs one analytics worker thread that:
1. Reads frames from the camera's ring buffer
2. Runs only the analytics enabled in that camera's config
3. Respects each analytic's parameters (confidence, zones, etc.)
4. Publishes events to EventBus when detections fire

In development mode (no RTSP + no model files), a built-in simulator
generates realistic events so the full event pipeline can be tested.
"""
import asyncio
import threading
import time
import random
from typing import Optional
from dataclasses import dataclass, field
from loguru import logger

from backend.core.event_bus import EventBus, AnalyticEvent
from backend.core.stream_manager import stream_manager
from backend.analytics.registry import ANALYTICS_BY_KEY
from backend.inference.detector     import YOLODetector, YOLO_ANALYTICS
from backend.inference.fall_detector import FallDetector
from backend.inference.ppe_detector  import PPEDetector
from backend.core.recording_manager import purge_oldest_snapshots


# ─── Per-analytic severity rules ──────────────────────────────────────────────

SEVERITY_RULES: dict[str, str] = {
    "epp_detection":      "high",
    "fall_detection":     "critical",
    "fire_detection":     "critical",
    "smoke_detection":    "high",
    "weapon_detection":   "critical",
    "behavior_detection": "high",
    "medical_emergency":  "critical",
    "face_blacklist":     "critical",
    "intrusion_detection":"high",
    "lpr_recognition":    "low",
    "person_detection":   "low",
    "vehicle_detection":  "low",
    "person_counting":    "low",
    "vehicle_counting":   "low",
    "crowd_detection":    "medium",
    "theft_detection":    "high",
    "loitering_detection":"medium",
    "line_crossing":      "medium",
    "tailgating":         "high",
    "vandalism_detection":"high",
    "forklift_safety":    "critical",
    "working_at_heights": "high",
    "confined_space":     "medium",
    "driver_fatigue":     "critical",
    "atm_security":       "high",
    "drone_detection":    "high",
    "face_recognition":   "low",
    "face_detection":     "low",
    "liveness_detection": "medium",
    "emotion_detection":  "low",
}

EVENT_DESCRIPTIONS: dict[str, list[str]] = {
    "epp_detection":       ["Persona sin casco detectada", "Persona sin chaleco de seguridad", "Persona sin botas de seguridad", "Múltiples EPP faltantes"],
    "fall_detection":      ["Caída de persona detectada", "Persona en el suelo sin movimiento"],
    "fire_detection":      ["Llamas detectadas en la escena", "Fuego activo detectado"],
    "smoke_detection":     ["Humo detectado en la escena", "Presencia de humo antes de llamas"],
    "behavior_detection":  ["Comportamiento agresivo detectado", "Posible altercado físico", "Conducta hostil detectada"],
    "theft_detection":     ["Comportamiento de robo detectado", "Sustracción de objeto sospechosa"],
    "intrusion_detection": ["Persona en zona restringida", "Intrusión detectada en perímetro"],
    "line_crossing":       ["Cruce de línea virtual detectado", "Objeto cruzó la línea definida"],
    "crowd_detection":     ["Aglomeración de personas detectada", "Densidad de personas supera el límite"],
    "loitering_detection": ["Persona merodeando en zona controlada", "Permanencia prolongada detectada"],
    "weapon_detection":    ["Posible arma detectada", "Objeto peligroso identificado en escena"],
    "face_blacklist":      ["Persona en lista negra detectada", "Identidad restringida en cámara"],
    "forklift_safety":     ["Persona en zona de operación de montacargas", "Riesgo de colisión detectado"],
    "medical_emergency":   ["Persona inconsciente en el suelo", "Posible emergencia médica"],
    "driver_fatigue":      ["Signos de somnolencia en conductor", "Fatiga detectada al volante"],
    "atm_security":        ["Comportamiento sospechoso en ATM", "Merodeo prolongado en cajero"],
    "person_detection":    ["Persona detectada en escena"],
    "vehicle_detection":   ["Vehículo detectado en escena"],
    "lpr_recognition":     ["Placa vehicular reconocida"],
    "crowd_detection":     ["Concentración de personas detectada"],
    "face_recognition":    ["Persona identificada en base de datos"],
    "tailgating":          ["Acceso no autorizado detectado", "Más de una persona cruzó el acceso"],
    "vandalism_detection": ["Acto de vandalismo detectado"],
    "drone_detection":     ["Dron detectado sobre la zona"],
    "smoke_detection":     ["Humo detectado — posible incendio"],
    "working_at_heights":  ["Trabajo en altura sin arnés detectado"],
}


def _get_description(analytic_type: str, config: dict) -> str:
    descs = EVENT_DESCRIPTIONS.get(analytic_type, [f"Evento de {analytic_type}"])
    base = random.choice(descs)
    # Enrich with config context
    if analytic_type == "epp_detection":
        req = config.get("required_ppe", [])
        if req:
            base += f" (requerido: {', '.join(req)})"
    elif analytic_type == "crowd_detection":
        limit = config.get("max_density", 5)
        base += f" (límite: {limit} personas)"
    elif analytic_type == "lpr_recognition":
        base += f" — placa: {_random_plate()}"
    return base


def _random_plate() -> str:
    letters = "ABCDEFGHJKLMNPQRSTUVWXYZ"
    digits  = "0123456789"
    return f"{''.join(random.choices(letters, k=3))}-{''.join(random.choices(digits, k=3))}"


# ─── Camera Analytics Worker ───────────────────────────────────────────────────

@dataclass
class AnalyticsWorker:
    camera_id:        int
    analytics_config: dict
    event_bus:        EventBus
    loop:             asyncio.AbstractEventLoop

    thread:           Optional[threading.Thread] = field(default=None, repr=False)
    running:          bool = False
    _last_event:      dict = field(default_factory=dict, repr=False)
    _detector:        Optional[YOLODetector] = field(default=None, repr=False)
    _fall_detector:   Optional[FallDetector] = field(default=None, repr=False)
    _ppe_detector:    Optional[PPEDetector]  = field(default=None, repr=False)
    _face_net:        object = field(default=None, repr=False)   # cv2.dnn face net

    def start(self):
        self.running = True
        self.thread = threading.Thread(
            target=self._worker_loop,
            name=f"analytics-cam{self.camera_id}",
            daemon=True,
        )
        self.thread.start()
        logger.info(f"Analytics worker started for camera {self.camera_id} "
                    f"({len(self._enabled_analytics())} analytics active)")

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=3)

    def update_config(self, analytics_config: dict):
        self.analytics_config = analytics_config
        logger.info(f"Analytics config updated for camera {self.camera_id}")

    def _enabled_analytics(self) -> dict[str, dict]:
        """Returns {key: config_dict} for all enabled analytics."""
        result = {}
        for key, val in self.analytics_config.items():
            if val is True:
                # Simple boolean toggle — use analytic defaults
                defn = ANALYTICS_BY_KEY.get(key)
                result[key] = defn.default_config.copy() if defn else {}
            elif isinstance(val, dict) and val.get("enabled", False):
                result[key] = val
        return result

    def _rate_limit_ok(self, analytic_key: str, config: dict) -> bool:
        """Ensure we don't spam events. Min interval from config or default."""
        min_interval = config.get("min_event_interval_s", _default_interval(analytic_key))
        last = self._last_event.get(analytic_key, 0)
        return (time.time() - last) >= min_interval

    def _record_event(self, analytic_key: str):
        self._last_event[analytic_key] = time.time()

    def _worker_loop(self):
        """
        Main analytics loop.

        DEVELOPMENT MODE: When no frames are available (no RTSP camera),
        the worker uses a probabilistic simulator to generate realistic events,
        allowing full testing of the event pipeline without hardware.

        PRODUCTION MODE: Processes real frames from the stream manager buffer,
        running the appropriate inference model for each enabled analytic.
        """
        logger.info(f"Analytics worker loop running — camera {self.camera_id}")

        while self.running:
            enabled = self._enabled_analytics()
            if not enabled:
                time.sleep(2)
                continue

            # Try to get a real frame
            frame = stream_manager.get_latest_frame(self.camera_id)

            if frame is not None:
                # PRODUCTION: process real frame
                self._process_frame(frame, enabled)
                time.sleep(0.1)
            else:
                # DEVELOPMENT SIMULATOR: no camera connected
                self._simulate_events(enabled)
                time.sleep(2.0)  # check every 2s

    def _process_frame(self, frame, enabled: dict[str, dict]):
        """Run YOLO + Fall + Face + EPP detection on a real frame."""
        working_frame = frame.copy()
        person_detections: list[dict] = []
        h_frame, w_frame = frame.shape[:2]

        # ── General YOLO (persons, vehicles, etc.) ────────────────────────────
        yolo_analytics = {k: v for k, v in enabled.items() if k in YOLO_ANALYTICS}
        need_persons   = "epp_detection" in enabled or "face_detection" in enabled
        if yolo_analytics or need_persons:
            run_analytics = yolo_analytics.copy()
            if need_persons and "person_detection" not in run_analytics:
                run_analytics["person_detection"] = enabled.get("person_detection", {})
            if self._detector is None:
                self._detector = YOLODetector("yolov8n.pt", "cpu", 0.55)
            working_frame, detections = self._detector.detect(working_frame, run_analytics, draw=True)
            raw_persons = [d for d in detections if d["class"] == "person"]
            # Plausibility filter: real persons have h > w and occupy >2% frame area
            person_detections = [
                d for d in raw_persons
                if self._is_plausible_person(d, h_frame, w_frame)
            ]
            self._evaluate_detections(detections, yolo_analytics)

        # ── EPP detection (model-based + body-zone spatial analysis) ──────────
        if "epp_detection" in enabled:
            if self._ppe_detector is None:
                self._ppe_detector = PPEDetector(device="cpu",
                                                 conf_threshold=enabled["epp_detection"].get("confidence", 0.40))
            self._run_epp_detection(working_frame, enabled["epp_detection"], person_detections)

        # ── Fall detection ─────────────────────────────────────────────────
        if "fall_detection" in enabled:
            if self._fall_detector is None:
                self._fall_detector = FallDetector("yolov8n-pose.pt", "cpu", 0.50)
            fall_cfg = enabled["fall_detection"]
            working_frame, falls = self._fall_detector.detect(working_frame, fall_cfg, draw=False)
            self._evaluate_falls(falls, fall_cfg)

        # ── Face detection (only if YOLO confirmed plausible person) ───────────
        if "face_detection" in enabled and person_detections:
            self._run_face_detection(working_frame, enabled["face_detection"], person_detections)

        # Commit
        stream_manager.set_annotated_frame(self.camera_id, working_frame)
        stream = stream_manager.streams.get(self.camera_id)
        if stream is not None:
            stream.clip_buffer.append(working_frame)
        logger.debug(f"cam{self.camera_id} | persons={len(person_detections)} | "
                     f"analytics={list(enabled.keys())}")

    @staticmethod
    def _is_plausible_person(det: dict, frame_h: int, frame_w: int) -> bool:
        """Reject clear YOLO false positives (tiny objects, horizontal blobs)."""
        x1, y1, x2, y2 = det["bbox"]
        w, h = max(x2 - x1, 1), max(y2 - y1, 1)
        aspect = h / w                           # person: h > w
        area_r = (w * h) / (frame_h * frame_w)  # fraction of frame
        # Relaxed for fisheye/wide-angle cameras: 0.5% area, aspect > 0.5
        return aspect > 0.50 and area_r > 0.005


    # ── EPP detection (model-based) ───────────────────────────────────


    def _run_epp_detection(self, frame, config: dict, person_detections: list | None = None):
        """
        Model-based EPP detection with body-zone spatial analysis.
        Per item determines:
          - MISSING: model detected NO_xxx class
          - MAL PORTADO: item detected but NOT in the correct body region (e.g., helmet in hand)
          - CORRECTO: item detected in the expected body region
        """
        if self._ppe_detector is None:
            return

        working_frame, detections = self._ppe_detector.detect(frame, config, draw=True)
        frame[:] = working_frame

        # ── Body zone definitions (fraction of person bbox height) ─────────────
        CORRECT_ZONE: dict[str, tuple[float, float]] = {
            "helmet":  (0.00, 0.28),   # head: top 28%
            "goggles": (0.02, 0.30),   # eyes/face: top 30%
            "mask":    (0.05, 0.35),   # face: 5–35%
            "gloves":  (0.25, 0.95),   # hands: anywhere below shoulders
            "shoes":   (0.65, 1.00),   # feet: bottom 35%
        }
        ZONE_NAMES: dict[str, str] = {
            "helmet":  "cabeza",
            "goggles": "ojos",
            "mask":    "rostro",
            "gloves":  "manos",
            "shoes":   "pies",
        }
        KEY_ES: dict[str, str] = {
            "helmet":  "casco",
            "gloves":  "guantes",
            "goggles": "gafas",
            "mask":    "mascarilla",
            "shoes":   "calzado",
        }
        required = config.get("required_ppe", ["helmet"])

        violations_missing: set[str]              = set()   # no_xxx detected
        violations_misuse:  set[tuple[str, str]]  = set()   # item present but wrong zone
        correctly_worn:     set[str]              = set()   # item in correct zone

        for det in detections:
            ppe_key = det["ppe_key"]
            if ppe_key not in required:
                continue

            if not det["present"]:
                violations_missing.add(ppe_key)
                continue

            # PPE detected — check spatial position relative to nearest person
            if not person_detections:
                correctly_worn.add(ppe_key)   # can't determine; assume ok
                continue

            ex1, ey1, ex2, ey2 = det["bbox"]
            epy_center = (ey1 + ey2) / 2
            epx_center = (ex1 + ex2) / 2

            # Find the person whose bbox horizontally overlaps or is nearest
            best_person = None
            best_score  = float('inf')
            for p in person_detections:
                px1, py1, px2, py2 = p["bbox"]
                pcx = (px1 + px2) / 2
                pcy = (py1 + py2) / 2
                dist = abs(epx_center - pcx) + abs(epy_center - pcy)
                # Bonus if EPP center is within person bbox horizontally
                if px1 <= epx_center <= px2:
                    dist *= 0.4
                if dist < best_score:
                    best_score  = dist
                    best_person = p

            if best_person is None:
                correctly_worn.add(ppe_key)
                continue

            bx1, by1, bx2, by2 = best_person["bbox"]
            ph    = max(by2 - by1, 1)
            rel_y = (epy_center - by1) / ph   # 0 = top of person, 1 = bottom

            zone = CORRECT_ZONE.get(ppe_key, (0.0, 1.0))
            if zone[0] <= rel_y <= zone[1]:
                correctly_worn.add(ppe_key)
                # Draw green tick on the live frame to confirm correct wear
                import cv2 as _cv2
                ex1i, ey1i, ex2i, ey2i = [int(v) for v in det["bbox"]]
                _cv2.putText(frame, f"{KEY_ES.get(ppe_key, ppe_key)} OK ✓",
                             (ex1i, ey1i - 4), _cv2.FONT_HERSHEY_DUPLEX,
                             0.38, (0, 200, 60), 1, _cv2.LINE_AA)
            else:
                zone_name = ZONE_NAMES.get(ppe_key, "posición correcta")
                violations_misuse.add((ppe_key, zone_name))
                # Draw amber warning for misuse
                import cv2 as _cv2
                ex1i, ey1i, ex2i, ey2i = [int(v) for v in det["bbox"]]
                _cv2.rectangle(frame, (ex1i, ey1i), (ex2i, ey2i), (0, 140, 230), 2)
                _cv2.putText(frame, f"Mal portado: {KEY_ES.get(ppe_key, ppe_key)}",
                             (ex1i, ey1i - 4), _cv2.FONT_HERSHEY_DUPLEX,
                             0.38, (0, 140, 230), 1, _cv2.LINE_AA)

        # Status bar under each person bbox
        import cv2 as _cv2
        h_frame = frame.shape[0]
        if person_detections:
            misuse_keys = {k for k, _ in violations_misuse}
            for p in person_detections:
                bx1, by1, bx2, by2 = p["bbox"]
                label_y = min(by2 + 16, h_frame - 4)
                all_ok  = not violations_misuse and not violations_missing
                color   = (0, 200, 60) if all_ok else (0, 60, 220)
                parts   = []
                for k in sorted(violations_missing):
                    parts.append(f"sin {KEY_ES.get(k, k)}")
                for k, zn in sorted(violations_misuse):
                    parts.append(f"{KEY_ES.get(k, k)} no en {zn}")
                label = "EPP correcto" if all_ok else "EPP: " + ", ".join(parts[:2])
                _cv2.putText(frame, label, (bx1 + 2, label_y),
                             _cv2.FONT_HERSHEY_DUPLEX, 0.40, color, 1, _cv2.LINE_AA)

        # Fire events
        if (violations_missing or violations_misuse) and self._rate_limit_ok("epp_detection", config):
            min_conf   = config.get("confidence", 0.70)
            n_viol     = len(violations_missing) + len(violations_misuse)
            confidence = round(min(0.96, 0.72 + n_viol * 0.05), 2)
            if confidence >= min_conf:
                parts = []
                for k in sorted(violations_missing):
                    parts.append(f"{KEY_ES.get(k, k)} faltante")
                for k, zn in sorted(violations_misuse):
                    parts.append(f"{KEY_ES.get(k, k)} mal portado (no en {zn})")
                self._emit_event("epp_detection", confidence, "; ".join(parts), config)



    def _run_face_detection(self, frame, config: dict, person_detections: list | None = None):
        """
        Detect faces using OpenCV DNN (ResNet-SSD) face detector.
        Far more accurate than Haar cascade: handles varying angles, lighting,
        and strongly rejects non-face patterns (objects, body parts, clutter).

        Model: res10_300x300_ssd_iter_140000.caffemodel (~10 MB, local)
        Cross-validates with YOLO person bboxes to further eliminate FPs.
        """
        import cv2 as _cv2
        import os
        if not self._rate_limit_ok("face_detection", config):
            return

        if person_detections is not None and len(person_detections) == 0:
            return

        # Lazy init of DNN face detector
        if self._face_net is None:
            models_dir = os.path.join(os.path.dirname(__file__), "..", "..", "models")
            proto  = os.path.abspath(os.path.join(models_dir, "deploy.prototxt"))
            model  = os.path.abspath(os.path.join(models_dir, "res10_300x300_ssd_iter_140000.caffemodel"))
            if os.path.exists(proto) and os.path.exists(model):
                self._face_net = _cv2.dnn.readNetFromCaffe(proto, model)
                logger.info("DNN face detector loaded")
            else:
                logger.warning("DNN face model files not found — face detection disabled")
                self._face_net = False   # sentinel: don't retry
                return

        if self._face_net is False:
            return

        h_frame, w_frame = frame.shape[:2]
        min_conf_dnn = 0.65   # DNN internal confidence threshold
        min_conf_evt = config.get("confidence", 0.70)

        # Prepare input blob
        blob = _cv2.dnn.blobFromImage(
            _cv2.resize(frame, (300, 300)), 1.0,
            (300, 300), (104.0, 177.0, 123.0),
        )
        self._face_net.setInput(blob)
        detections = self._face_net.forward()

        faces = []  # list of (x1, y1, x2, y2, conf)
        for i in range(detections.shape[2]):
            dnn_conf = float(detections[0, 0, i, 2])
            if dnn_conf < min_conf_dnn:
                continue
            box = detections[0, 0, i, 3:7] * [w_frame, h_frame, w_frame, h_frame]
            x1, y1, x2, y2 = box.astype(int)
            # Clamp to frame
            x1, y1 = max(x1, 0), max(y1, 0)
            x2, y2 = min(x2, w_frame), min(y2, h_frame)
            fw, fh = x2 - x1, y2 - y1
            if fw < 40 or fh < 40:    # ignore tiny detections
                continue
            faces.append((x1, y1, x2, y2, dnn_conf))

        if not faces:
            return

        # Cross-validate: face center must be in head region of a YOLO person bbox
        if person_detections:
            confirmed = []
            for (fx1, fy1, fx2, fy2, fc) in faces:
                fcx = (fx1 + fx2) / 2
                fcy = (fy1 + fy2) / 2
                for p in person_detections:
                    px1, py1, px2, py2 = p["bbox"]
                    ph = py2 - py1
                    head_y2 = py1 + int(ph * 0.40)   # top 40% = head region
                    if px1 <= fcx <= px2 and py1 <= fcy <= head_y2:
                        confirmed.append((fx1, fy1, fx2, fy2, fc))
                        break
            faces = confirmed

        if not faces:
            return

        # Best confidence from DNN detections
        best_conf = max(fc for *_, fc in faces)
        if best_conf < min_conf_evt:
            return

        # Draw confirmed faces
        for (x1, y1, x2, y2, fc) in faces:
            _cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 220, 180), 2)
            label = f"Rostro {fc:.0%}"
            (tw, th), _ = _cv2.getTextSize(label, _cv2.FONT_HERSHEY_DUPLEX, 0.42, 1)
            _cv2.rectangle(frame, (x1, y1 - th - 6), (x1 + tw + 6, y1), (0, 220, 180), -1)
            _cv2.putText(frame, label, (x1 + 3, y1 - 4),
                         _cv2.FONT_HERSHEY_DUPLEX, 0.42, (10, 10, 10), 1, _cv2.LINE_AA)

        desc = f"{len(faces)} rostro(s) detectado(s)" if len(faces) > 1 else "Rostro detectado"
        self._emit_event("face_detection", round(best_conf, 2), desc, config)


    def _evaluate_detections(self, detections: list, enabled: dict[str, dict]):
        """Turn YOLO detections into analytic events."""
        # Count detections by class
        class_counts: dict[str, int] = {}
        for d in detections:
            cls = d["class"]
            class_counts[cls] = class_counts.get(cls, 0) + 1

        person_count  = class_counts.get("person", 0)
        vehicle_count = sum(class_counts.get(c, 0) for c in ["car","truck","bus","motorcycle","bicycle"])

        # person_detection — fire if any person detected
        if "person_detection" in enabled and person_count > 0:
            if self._rate_limit_ok("person_detection", enabled["person_detection"]):
                best = max((d for d in detections if d["class"]=="person"), key=lambda d: d["confidence"], default=None)
                if best:
                    self._emit_event("person_detection", best["confidence"],
                                     f"{person_count} persona(s) detectada(s)",
                                     enabled["person_detection"])

        # vehicle_detection
        if "vehicle_detection" in enabled and vehicle_count > 0:
            if self._rate_limit_ok("vehicle_detection", enabled["vehicle_detection"]):
                best = max((d for d in detections if d["class"] in ["car","truck","bus","motorcycle","bicycle"]),
                           key=lambda d: d["confidence"], default=None)
                if best:
                    self._emit_event("vehicle_detection", best["confidence"],
                                     f"{vehicle_count} vehículo(s) detectado(s)",
                                     enabled["vehicle_detection"])

        # crowd_detection — fire if count exceeds threshold
        if "crowd_detection" in enabled:
            cfg       = enabled["crowd_detection"]
            max_dens  = cfg.get("max_density", 5)
            if person_count >= max_dens and self._rate_limit_ok("crowd_detection", cfg):
                self._emit_event("crowd_detection", 0.90,
                                 f"Aglomeración: {person_count} personas (límite: {max_dens})",
                                 cfg)

        # intrusion_detection — any person in any frame (zone logic TBD)
        if "intrusion_detection" in enabled and person_count > 0:
            cfg = enabled["intrusion_detection"]
            if self._rate_limit_ok("intrusion_detection", cfg):
                self._emit_event("intrusion_detection", 0.85,
                                 f"Persona en zona restringida detectada", cfg)

    def _evaluate_falls(self, falls: list, config: dict):
        """Fire events for detected falls."""
        if not self._rate_limit_ok("fall_detection", config):
            return
        for fall in falls:
            if fall["fallen"] and fall["confidence"] >= config.get("confidence", 0.50):
                self._emit_event(
                    "fall_detection",
                    fall["confidence"],
                    f"Caida detectada — {fall['reason']}",
                    config,
                )
                break   # one event per frame is enough

    def _simulate_events(self, enabled: dict[str, dict]):
        """
        Development simulator — probabilistic event generation.
        Fires events based on configured probability per analytic.
        NOTE: face_detection and epp_detection are excluded here — they run
        real inference (Haar cascade / HSV color analysis) in _process_frame.
        """
        # Analytics with real frame implementations — never simulate on offline cameras
        # All of these require an actual camera frame to produce meaningful results
        REAL_ANALYTICS = {
            "face_detection",     # Haar cascade — needs real frame
            "epp_detection",      # PPE model — needs real frame
            "fall_detection",     # Pose estimation — needs real frame
            "person_detection",   # YOLO — needs real frame
            "vehicle_detection",  # YOLO — needs real frame
        }

        for analytic_key, config in enabled.items():
            if analytic_key in REAL_ANALYTICS:
                continue
            if not self._rate_limit_ok(analytic_key, config):
                continue

            prob = config.get("sim_probability", _default_sim_prob(analytic_key))
            if random.random() < prob:
                confidence = _sim_confidence(analytic_key, config)
                min_conf   = config.get("confidence", 0.5)

                if confidence >= min_conf:
                    self._emit_event(analytic_key, confidence, None, config)


    def _emit_event(self, analytic_key: str, confidence: float,
                    description: Optional[str], config: dict):
        """Publish event to EventBus and save snapshot + clip."""
        import os, time as _time
        self._record_event(analytic_key)
        severity    = config.get('severity_override',
                                  SEVERITY_RULES.get(analytic_key, 'medium'))
        description = description or _get_description(analytic_key, config)

        # Save snapshot and clip — use the configured storage_path so
        # all media goes to the selected disk (USB, NAS, etc.)
        import os as _os, time as _time
        from backend.core.recording_manager import recording_manager as _rm
        ts           = _time.time()
        ts_str       = _time.strftime('%Y%m%d_%H%M%S', _time.localtime(ts))
        storage_root = _os.path.abspath(_rm._config.storage_path)
        base_dir     = _os.path.join(storage_root, 'events',
                                     f'cam{self.camera_id}', analytic_key)
        _os.makedirs(base_dir, exist_ok=True)
        snap_path    = _os.path.join(base_dir, f'{ts_str}_snap.jpg')
        clip_path    = _os.path.join(base_dir, f'{ts_str}_clip.mp4')

        snap_saved = stream_manager.save_snapshot(self.camera_id, snap_path)
        if snap_saved:
            # Ring-buffer: keep only the last 200 snapshots per camera/analytic
            purge_oldest_snapshots(base_dir, keep_last=200)
        clip_saved = stream_manager.save_clip(self.camera_id, clip_path)

        event = AnalyticEvent(
            camera_id     = self.camera_id,
            analytic_type = analytic_key,
            severity      = severity,
            description   = description,
            confidence    = confidence,
            timestamp     = ts,
            snapshot_path = snap_path  if snap_saved else None,
            recording_path= clip_path  if clip_saved else None,
            metadata      = {'config_snapshot': {
                k: v for k, v in config.items()
                if k not in ('sim_probability',)
            }},
        )

        asyncio.run_coroutine_threadsafe(
            self.event_bus.publish(event),
            self.loop,
        )
        logger.debug(f'Event: cam{self.camera_id} | {analytic_key} | '
                     f'{severity} | {confidence:.0%} | snap={snap_saved}')


# ─── Simulator helpers ────────────────────────────────────────────────────────

def _default_sim_prob(key: str) -> float:
    """Base probability per poll cycle (every 2s) of a simulated event firing."""
    return {
        "fire_detection":     0.01,   # rare but critical
        "fall_detection":     0.02,
        "weapon_detection":   0.005,
        "face_blacklist":     0.01,
        "medical_emergency":  0.01,
        "forklift_safety":    0.03,
        "epp_detection":      0.08,   # common in industrial
        "behavior_detection": 0.04,
        "theft_detection":    0.03,
        "intrusion_detection":0.06,
        "crowd_detection":    0.05,
        "loitering_detection":0.04,
        "line_crossing":      0.10,
        "person_detection":   0.20,
        "vehicle_detection":  0.15,
        "lpr_recognition":    0.12,
        "tailgating":         0.03,
        "driver_fatigue":     0.02,
        "atm_security":       0.02,
    }.get(key, 0.05)


def _default_interval(key: str) -> float:
    """Minimum seconds between events for the same analytic (rate limit)."""
    return {
        # High-priority — still need reasonable cooldown
        "fire_detection":         15,
        "smoke_detection":        15,
        "weapon_detection":       10,
        "fall_detection":         20,
        "medical_emergency":      20,
        "face_blacklist":         15,
        # Medium-priority — longer cooldown prevents spam
        "behavior_detection":     30,
        "intrusion_detection":    20,
        "line_crossing":          20,
        # Low-priority — long cooldown, expected continuous presence
        "person_detection":       60,
        "face_detection":         60,
        "face_recognition":       45,
        "epp_detection":          45,
        "vehicle_detection":      45,
        "lpr_recognition":        30,
        "crowd_detection":        60,
        "loitering_detection":    30,
        "theft_detection":        20,
    }.get(key, 30)


def _sim_confidence(key: str, config: dict) -> float:
    """Generate a realistic confidence value for simulation."""
    base = config.get("confidence", 0.55)
    # Vary ±15% around the configured threshold (weighted toward just above)
    lo = max(0.0, base - 0.10)
    hi = min(1.0, base + 0.25)
    return round(random.uniform(lo, hi), 2)


# ─── Pipeline Manager ─────────────────────────────────────────────────────────

class InferencePipeline:
    """
    Manages one AnalyticsWorker per active camera.
    Workers are started/stopped as cameras are added or removed.
    """

    def __init__(self):
        self._workers: dict[int, AnalyticsWorker] = {}
        self._event_bus: Optional[EventBus] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    def init(self, event_bus: EventBus, loop: asyncio.AbstractEventLoop):
        self._event_bus = event_bus
        self._loop      = loop
        logger.info("Inference pipeline initialized")

    def add_camera(self, camera_id: int, analytics_config: dict):
        """Start analytics worker for a camera."""
        if camera_id in self._workers:
            self._workers[camera_id].update_config(analytics_config)
            return

        if not self._event_bus or not self._loop:
            logger.warning("Pipeline not initialized — call init() first")
            return

        worker = AnalyticsWorker(
            camera_id       = camera_id,
            analytics_config= analytics_config,
            event_bus       = self._event_bus,
            loop            = self._loop,
        )
        worker.start()
        self._workers[camera_id] = worker

    def remove_camera(self, camera_id: int):
        worker = self._workers.pop(camera_id, None)
        if worker:
            worker.stop()
            logger.info(f"Analytics worker stopped for camera {camera_id}")

    def update_camera_config(self, camera_id: int, analytics_config: dict):
        """Hot-reload analytics config for a running camera."""
        worker = self._workers.get(camera_id)
        if worker:
            worker.update_config(analytics_config)
        else:
            self.add_camera(camera_id, analytics_config)

    def get_status(self) -> list[dict]:
        return [
            {
                "camera_id": cid,
                "active_analytics": list(w._enabled_analytics().keys()),
                "running": w.running,
            }
            for cid, w in self._workers.items()
        ]

    def stop_all(self):
        for worker in self._workers.values():
            worker.stop()
        self._workers.clear()


# Global singleton
inference_pipeline = InferencePipeline()

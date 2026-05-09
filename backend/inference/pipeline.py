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
from backend.inference.detector        import YOLODetector, YOLO_ANALYTICS
from backend.inference.fall_detector   import FallDetector
from backend.inference.ppe_detector    import PPEDetector
from backend.inference.face_recognizer import FaceRecognizer
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
    _detector:        Optional[YOLODetector]  = field(default=None, repr=False)
    _fall_detector:   Optional[FallDetector]  = field(default=None, repr=False)
    _ppe_detector:    Optional[PPEDetector]   = field(default=None, repr=False)
    _face_recognizer: Optional[FaceRecognizer] = field(default=None, repr=False)
    # PPE async: run inference in background thread, cache overlay annotations
    _ppe_frame_skip:  int    = field(default=5,    repr=False)   # run PPE every N frames
    _ppe_frame_ctr:   int    = field(default=0,    repr=False)
    _ppe_busy:        bool   = field(default=False, repr=False)  # background job running
    _ppe_overlay:     object = field(default=None, repr=False)   # last annotated frame crop
    _ppe_lock:        object = field(default=None, repr=False)   # threading.Lock
    _camera_id:       int    = field(default=0,    repr=False)   # alias for camera_id
    _fall_frame_ctr:  int    = field(default=0,    repr=False)   # run fall every N frames
    _fall_frame_skip: int    = field(default=3,    repr=False)

    def start(self):
        self.running   = True
        self._ppe_lock = threading.Lock()
        self._camera_id = self.camera_id
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
                # Track time so we know our actual inference rate
                t0 = time.monotonic()
                self._process_frame(frame, enabled)
                elapsed = time.monotonic() - t0

                # Yield CPU if inference was very fast (< 20ms).
                # This prevents burning 100% CPU when the reader thread
                # is faster than inference. Natural rate: ~15-30 fps on CPU.
                if elapsed < 0.020:
                    time.sleep(0.020 - elapsed)
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
                # Force low-confidence person detection for cross-validation
                run_analytics["person_detection"] = {"confidence": 0.25}
            # yolov8n (nano) at imgsz=416: ~18ms vs yolov8m at 640: ~160ms
            # Precision tradeoff is acceptable for person detection at typical
            # surveillance distances. EPP uses its own dedicated models.
            if self._detector is None:
                from backend.utils.hardware import get_device
                self._detector = YOLODetector("yolov8n.pt", get_device(), 0.25)
            working_frame, detections = self._detector.detect(
                working_frame, run_analytics, draw=True, imgsz=416
            )
            raw_persons = [d for d in detections if d["class"] == "person"]
            person_detections = [
                d for d in raw_persons
                if self._is_plausible_person(d, h_frame, w_frame)
            ]
            logger.debug(f"cam{self.camera_id} | YOLO raw_persons={len(raw_persons)} "
                         f"plausible={len(person_detections)}")
            self._evaluate_detections(detections, yolo_analytics)

        # ── EPP detection — async background, cached overlays ─────────────────
        # PPE models are heavy (2x YOLO on CPU). We run them in a background
        # thread every _ppe_frame_skip frames and overlay the last cached result
        # on every intermediate frame to keep the stream latency low.
        if "epp_detection" in enabled and person_detections:
            if self._ppe_detector is None:
                from backend.utils.hardware import get_device
                self._ppe_detector = PPEDetector(
                    device=get_device(),
                    conf_threshold=enabled["epp_detection"].get("confidence", 0.30),
                )
            self._ppe_frame_ctr += 1
            if self._ppe_frame_ctr >= self._ppe_frame_skip and not self._ppe_busy:
                # Snapshot inputs for the background thread (thread-safe copies)
                _frame_snap   = working_frame.copy()
                _persons_snap = list(person_detections)
                _config_snap  = dict(enabled["epp_detection"])

                def _ppe_job():
                    self._ppe_busy = True
                    try:
                        self._run_epp_detection(_frame_snap, _config_snap, _persons_snap)
                        with self._ppe_lock:
                            self._ppe_overlay = _frame_snap   # store annotated snapshot
                    finally:
                        self._ppe_busy = False

                self._ppe_frame_ctr = 0
                threading.Thread(target=_ppe_job, daemon=True, name="ppe-infer").start()

            # Paint cached PPE overlay onto the current working frame
            if self._ppe_lock is not None:
                with self._ppe_lock:
                    if self._ppe_overlay is not None:
                        oh, ow = self._ppe_overlay.shape[:2]
                        fh, fw = working_frame.shape[:2]
                        if oh == fh and ow == fw:
                            # Simple: blit entire cached overlay
                            # It already contains YOLO person boxes + PPE overlays
                            import numpy as _np
                            working_frame[:] = self._ppe_overlay

        # ── Fall detection — pose model ~50ms, skip when no persons or every 3 frames
        if "fall_detection" in enabled and person_detections:
            self._fall_frame_ctr += 1
            if self._fall_frame_ctr >= self._fall_frame_skip:
                self._fall_frame_ctr = 0
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
            stream.clip_buffer.append((time.time(), working_frame))
        logger.debug(f"cam{self.camera_id} | persons={len(person_detections)} | "
                     f"analytics={list(enabled.keys())}")

    @staticmethod
    def _is_plausible_person(det: dict, frame_h: int, frame_w: int) -> bool:
        """Reject clear YOLO false positives (tiny blobs, extreme horizontals)."""
        x1, y1, x2, y2 = det["bbox"]
        w, h = max(x2 - x1, 1), max(y2 - y1, 1)
        aspect = h / w                           # person: h > w
        area_r = (w * h) / (frame_h * frame_w)  # fraction of frame
        # Very relaxed for fisheye: 0.3% area, aspect > 0.35
        return aspect > 0.35 and area_r > 0.003


    # ── EPP detection (model-based) ───────────────────────────────────


    def _run_epp_detection(self, frame, config: dict, person_detections: list | None = None):
        """
        High-precision EPP detection with body-zone spatial validation.
        Draws color-coded overlays on each detected EPP item:
          green  — item detected AND in correct body zone
          amber  — item detected but in wrong body zone (mal portado)
          red    — item absent (no_xxx class) or required but not seen

        REQUIRES at least one YOLO-confirmed person in the frame.
        Without a person there is nobody to enforce EPP on, and the model
        generates false positives against background objects (walls, shelves).
        """
        if self._ppe_detector is None:
            return
        # Hard guard: never run without a confirmed person
        if not person_detections:
            return

        from backend.inference.ppe_detector import (
            BODY_ZONES, ZONE_NAMES_ES, EPP_LABELS_ES, PPEDetector
        )
        import cv2 as _cv2

        # detect() returns raw detections without any drawing
        _, detections = self._ppe_detector.detect(frame, config, draw=False)

        required: list[str] = config.get("required_ppe", ["helmet"])

        # Per-item tracking
        status:      dict[str, str] = {k: "not_seen" for k in required}
        det_by_key:  dict[str, dict] = {}   # best detection per ppe_key
        misuse_zone: dict[str, str]  = {}

        for det in detections:
            ppe_key = det["ppe_key"]
            if ppe_key not in required:
                continue

            if not det["present"]:
                status[ppe_key] = "missing"
                det_by_key[ppe_key] = det
                continue

            # Spatial check against nearest person bbox
            if not person_detections:
                if status[ppe_key] != "missing":
                    status[ppe_key] = "correct"
                    det_by_key[ppe_key] = det
                continue

            ex1, ey1, ex2, ey2 = det["bbox"]
            ecy = (ey1 + ey2) / 2
            ecx = (ex1 + ex2) / 2

            best_person, best_score = None, float("inf")
            for p in person_detections:
                px1, py1, px2, py2 = p["bbox"]
                dist = abs(ecx - (px1+px2)/2) + abs(ecy - (py1+py2)/2)
                if px1 <= ecx <= px2:
                    dist *= 0.3
                if dist < best_score:
                    best_score  = dist
                    best_person = p

            if best_person is None:
                if status[ppe_key] != "missing":
                    status[ppe_key] = "correct"
                    det_by_key[ppe_key] = det
                continue

            bx1, by1, bx2, by2 = best_person["bbox"]
            ph    = max(by2 - by1, 1)
            rel_y = (ecy - by1) / ph
            zone  = BODY_ZONES.get(ppe_key, (0.0, 1.0))

            logger.debug(
                f"PPE zone | {ppe_key}: rel_y={rel_y:.2f} zone={zone} "
                f"person_h={ph}px ({'IN' if zone[0] <= rel_y <= zone[1] else 'OUT'})"
            )

            if zone[0] <= rel_y <= zone[1]:
                if status[ppe_key] != "missing":
                    status[ppe_key] = "correct"
                    det_by_key[ppe_key] = det
            else:
                if status[ppe_key] != "missing":
                    status[ppe_key] = "misuse"
                    misuse_zone[ppe_key] = ZONE_NAMES_ES.get(ppe_key, "posición correcta")
                    det_by_key[ppe_key] = det

        # Items never seen → mark as missing
        for k in required:
            if status[k] == "not_seen":
                status[k] = "missing"

        # ── Draw overlays on each detected item ──────────────────────────────
        for ppe_key, det in det_by_key.items():
            x1, y1, x2, y2 = det["bbox"]
            es    = EPP_LABELS_ES.get(ppe_key, ppe_key)
            conf  = det["confidence"]
            s     = status[ppe_key]
            if s == "correct":
                label = es
            elif s == "misuse":
                zone_es = misuse_zone.get(ppe_key, ZONE_NAMES_ES.get(ppe_key, ""))
                label = f"{es}: debe ir en {zone_es}"
            else:
                label = f"Sin {es}"
            PPEDetector.draw_ppe_overlay(frame, x1, y1, x2, y2, label, conf, s)

        # ── Status bar per person: missing items shown at person level ────────
        if person_detections:
            for p in person_detections:
                bx1, by1, bx2, by2 = p["bbox"]
                all_ok = all(v == "correct" for v in status.values())

                if all_ok:
                    # Green checkmark bar at bottom of person bbox
                    bar_text = "EPP correcto \u2713"
                    bar_color = (0, 200, 60)
                else:
                    missing_parts = []
                    for k, s in status.items():
                        es = EPP_LABELS_ES.get(k, k)
                        if s == "missing":
                            missing_parts.append(f"\u2717{es}")
                        elif s == "misuse":
                            missing_parts.append(f"!{es}")
                    bar_text  = "EPP: " + "  ".join(missing_parts[:4])
                    bar_color = (40, 40, 220)

                # Draw bar below person bbox
                font = _cv2.FONT_HERSHEY_DUPLEX
                fs   = 0.38
                (tw, th), _ = _cv2.getTextSize(bar_text, font, fs, 1)
                bar_y1 = min(by2 + 2, frame.shape[0] - th - 6)
                bar_y2 = bar_y1 + th + 6
                bar_x2 = min(bx1 + tw + 10, frame.shape[1])
                _cv2.rectangle(frame, (bx1, bar_y1), (bar_x2, bar_y2), bar_color, -1)
                _cv2.putText(frame, bar_text, (bx1 + 4, bar_y2 - 4),
                             font, fs, (255, 255, 255), 1, _cv2.LINE_AA)

        # ── Fire event on violation ───────────────────────────────────────────
        violations = {k: v for k, v in status.items() if v in ("missing", "misuse")}
        if violations and self._rate_limit_ok("epp_detection", config):
            n     = len(violations)
            conf  = round(min(0.97, 0.75 + n * 0.06), 2)
            parts = []
            for k, s in violations.items():
                es = EPP_LABELS_ES.get(k, k)
                if s == "missing":
                    parts.append(f"{es} faltante")
                else:
                    zone = misuse_zone.get(k, ZONE_NAMES_ES.get(k, ""))
                    parts.append(f"{es} mal portado (debe ir en {zone})")
            self._emit_event("epp_detection", conf, "; ".join(parts), config)


    def _run_face_detection(self, frame, config: dict, person_detections: list | None = None):
        """
        Detect and identify faces using InsightFace buffalo_s.

        - RetinaFace detects faces at 320x320 input (~30ms CPU)
        - ArcFace R50 generates 512-d embeddings for identity matching
        - Cross-validates against YOLO person bboxes (top 45% = head zone)
        - Saves crop + full snapshot + video clip to FaceLibrary
        - Emits face_detection events; recognized faces include identity info
        """
        if person_detections is not None and len(person_detections) == 0:
            return

        # Lazy-init InsightFace recognizer (downloads model once ~50MB)
        if self._face_recognizer is None:
            self._face_recognizer = FaceRecognizer()

        results = self._face_recognizer.process(
            frame,
            camera_id         = self._camera_id,
            config            = config,
            person_detections = person_detections,
            draw              = True,
        )

        if not results:
            return

        # ── Save to FaceLibrary: crop + snapshot + clip ────────────────────────
        try:
            from backend.core.face_library import FaceLibrary, CLIP_PRE_S
            best = max(results, key=lambda r: r["confidence"])
            x1, y1, x2, y2 = best["bbox"]

            # Pull pre-buffer frames from ring buffer (last CLIP_PRE_S seconds)
            pre_frames: list = []
            stream = stream_manager.streams.get(self._camera_id)
            if stream:
                cutoff     = time.time() - CLIP_PRE_S
                pre_frames = [f for t, f in stream.clip_buffer if t >= cutoff]

            FaceLibrary.get().capture(
                frame,
                bbox       = (x1, y1, x2, y2),
                camera_id  = self._camera_id,
                confidence = best["confidence"],
                pre_frames = pre_frames,
                identity   = best.get("identity"),
                similarity = best.get("sim", 0.0),
            )
        except Exception as _e:
            logger.trace(f"Face library capture error: {_e}")

        # ── Rate-limited event emission ────────────────────────────────────────
        if not self._rate_limit_ok("face_detection", config):
            return

        identified = [r for r in results if r["identity"]]
        if identified:
            names     = ", ".join(r["identity"] for r in identified)
            desc      = f"Persona identificada: {names}"
            best_conf = max(r["sim"] for r in identified)
        else:
            n         = len(results)
            desc      = f"{n} rostro(s) detectado(s) — sin identificar"
            best_conf = max(r["confidence"] for r in results)

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
        """Publish event to EventBus and save snapshot + clip (5s pre + 5s post)."""
        import os as _os, time as _time, threading as _threading
        self._record_event(analytic_key)
        severity    = config.get('severity_override',
                                  SEVERITY_RULES.get(analytic_key, 'medium'))
        description = description or _get_description(analytic_key, config)

        from backend.core.recording_manager import recording_manager as _rm
        ts           = _time.time()
        ts_str       = _time.strftime('%Y%m%d_%H%M%S', _time.localtime(ts))
        storage_root = _os.path.abspath(_rm._config.storage_path)
        base_dir     = _os.path.join(storage_root, 'events',
                                     f'cam{self.camera_id}', analytic_key)
        _os.makedirs(base_dir, exist_ok=True)
        snap_path = _os.path.join(base_dir, f'{ts_str}_snap.jpg')
        clip_path = _os.path.join(base_dir, f'{ts_str}_clip.mp4')

        # ── Snapshot ──────────────────────────────────────────────────────────
        snap_saved = stream_manager.save_snapshot(self.camera_id, snap_path)
        if snap_saved:
            purge_oldest_snapshots(base_dir, keep_last=200)

        # ── Pre-buffer: extract frames from last 5 seconds ───────────────────
        PRE_SECS  = 5.0
        POST_SECS = 5.0
        CLIP_FPS  = 10.0

        stream = stream_manager.streams.get(self.camera_id)
        pre_frames = []
        if stream:
            cutoff = ts - PRE_SECS
            pre_frames = [f for t, f in stream.clip_buffer if t >= cutoff]

        # ── Post-buffer: collect frames for POST_SECS in background ──────────
        camera_id_capture = self.camera_id

        def _record_post_and_save():
            post_frames = []
            deadline = _time.time() + POST_SECS
            interval = 1.0 / CLIP_FPS
            while _time.time() < deadline:
                t0 = _time.time()
                s = stream_manager.streams.get(camera_id_capture)
                if s and s.clip_buffer:
                    _, latest = s.clip_buffer[-1]
                    post_frames.append(latest.copy())
                sleep = interval - (_time.time() - t0)
                if sleep > 0:
                    _time.sleep(sleep)

            all_frames = pre_frames + post_frames
            if all_frames:
                stream_manager.save_clip(
                    camera_id_capture, clip_path,
                    fps=CLIP_FPS, frames=all_frames,
                )
                logger.debug(f"Clip saved: {len(pre_frames)} pre + "
                             f"{len(post_frames)} post frames → {clip_path}")
            else:
                logger.warning(f"No frames for clip cam{camera_id_capture}")

        clip_thread = _threading.Thread(target=_record_post_and_save, daemon=True,
                                        name=f"clip-cam{self.camera_id}")
        clip_thread.start()

        # Publish event immediately — clip will be updated on disk once thread finishes
        event = AnalyticEvent(
            camera_id     = self.camera_id,
            analytic_type = analytic_key,
            severity      = severity,
            description   = description,
            confidence    = confidence,
            timestamp     = ts,
            snapshot_path = snap_path  if snap_saved else None,
            recording_path= clip_path,   # path is known; file written by thread
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
                     f'{severity} | {confidence:.0%} | snap={snap_saved} | '
                     f'pre={len(pre_frames)}f post-recording=5s')


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

    def get_camera_state(self, camera_id: int) -> dict | None:
        """
        Return latest detection state for a camera — used by CLIP indexer
        to enrich frame metadata with what was detected.
        """
        worker = self._workers.get(camera_id)
        if not worker:
            return None
        return getattr(worker, "_last_detection_state", None)


    def refresh_face_gallery(self):
        """Rebuild InsightFace embedding gallery in all running workers."""
        refreshed = 0
        for worker in self._workers.values():
            rec = getattr(worker, "_face_recognizer", None)
            if rec is not None:
                rec.refresh_gallery()
                refreshed += 1
        logger.info(f"Face gallery refresh requested — {refreshed} worker(s) updated")
        return refreshed

    def stop_all(self):
        for worker in self._workers.values():
            worker.stop()
        self._workers.clear()


# Global singleton
inference_pipeline = InferencePipeline()

# Expose workers dict so the faces API can access recognizer instances
_worker_registry = inference_pipeline._workers

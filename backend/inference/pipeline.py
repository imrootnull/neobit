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
from backend.inference.detector import YOLODetector, YOLO_ANALYTICS
from backend.inference.fall_detector import FallDetector
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
    camera_id: int
    analytics_config: dict
    event_bus: EventBus
    loop: asyncio.AbstractEventLoop

    thread: Optional[threading.Thread] = field(default=None, repr=False)
    running: bool = False
    _last_event: dict = field(default_factory=dict, repr=False)
    _detector: Optional[YOLODetector] = field(default=None, repr=False)
    _fall_detector: Optional[FallDetector] = field(default=None, repr=False)

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
        """Run YOLO + Fall detection on a real frame, draw bboxes, write annotated frame, fire events."""
        working_frame = frame.copy()

        # ── General YOLO (persons, vehicles, etc.) ────────────────────────────
        yolo_analytics = {k: v for k, v in enabled.items() if k in YOLO_ANALYTICS}
        if yolo_analytics:
            if self._detector is None:
                self._detector = YOLODetector("yolov8n.pt", "cpu", 0.45)
            working_frame, detections = self._detector.detect(working_frame, yolo_analytics, draw=True)
            self._evaluate_detections(detections, yolo_analytics)

        # ── Fall detection (pose estimation) ──────────────────────────────────
        if "fall_detection" in enabled:
            if self._fall_detector is None:
                self._fall_detector = FallDetector("yolov8n-pose.pt", "cpu", 0.35)
            fall_cfg = enabled["fall_detection"]
            working_frame, falls = self._fall_detector.detect(working_frame, fall_cfg, draw=True)
            self._evaluate_falls(falls, fall_cfg)

        # Write final annotated frame to stream buffer
        stream_manager.set_annotated_frame(self.camera_id, working_frame)
        stream = stream_manager.streams.get(self.camera_id)
        if stream is not None:
            stream.clip_buffer.append(working_frame)

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
        """
        for analytic_key, config in enabled.items():
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
        "fire_detection":     5,
        "fall_detection":     10,
        "weapon_detection":   5,
        "face_blacklist":     8,
        "medical_emergency":  10,
        "person_detection":   30,
        "vehicle_detection":  20,
        "lpr_recognition":    15,
        "crowd_detection":    30,
        "line_crossing":      10,
    }.get(key, 20)


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

"""
Stream Manager — manages up to 8 concurrent RTSP camera streams.
Each camera runs in its own thread with a ring frame buffer.
"""
import cv2
import threading
import time
import numpy as np
import os
from collections import deque
from dataclasses import dataclass, field
from typing import Optional
from loguru import logger
from backend.core.video_writer import open_writer


@dataclass
class CameraStream:
    camera_id:    int
    rtsp_url:     str
    name:         str
    frame_skip:   int   = 3
    max_width:    int   = 0       # 0 = no downscale; else resize to this width
    target_fps:   float = 0.0     # 0 = no throttle; else limit to this FPS
    max_buffer:   int   = 30      # Ring buffer size

    # Runtime state
    cap:          Optional[cv2.VideoCapture] = field(default=None, repr=False)
    thread:       Optional[threading.Thread] = field(default=None, repr=False)
    buffer:       deque = field(default_factory=lambda: deque(maxlen=30), repr=False)
    # Pre-event ring buffer: (timestamp, annotated_frame) tuples
    # maxlen sized for 10s at ~15fps = 150 frames — enough for any pre-buffer window
    clip_buffer:  deque = field(default_factory=lambda: deque(maxlen=150), repr=False)
    annotated_frame: Optional[np.ndarray] = field(default=None, repr=False)
    running:      bool  = False
    connected:    bool  = False
    fps:          float = 0.0        # effective processed FPS (after throttle+skip)
    native_fps:   float = 0.0        # raw camera stream FPS
    frame_count:  int   = 0
    error_count:  int   = 0
    last_frame_time: float = 0.0

    def __post_init__(self):
        self.buffer = deque(maxlen=self.max_buffer)


class StreamManager:
    """
    Manages multiple RTSP camera streams concurrently.
    Thread-safe frame buffer per camera.
    """

    MAX_CAMERAS = 8
    RECONNECT_DELAY = 5  # seconds

    def __init__(self):
        self.streams: dict[int, CameraStream] = {}
        self._lock = threading.Lock()

    def add_camera(self, camera_id: int, rtsp_url: str, name: str = "",
                   frame_skip: int = 3,
                   max_width: int = 0,
                   target_fps: float = 0.0) -> bool:
        """Add and start a camera stream."""
        with self._lock:
            if len(self.streams) >= self.MAX_CAMERAS:
                logger.warning(f"Max cameras ({self.MAX_CAMERAS}) reached")
                return False
            if camera_id in self.streams:
                logger.warning(f"Camera {camera_id} already registered")
                return False

            stream = CameraStream(
                camera_id=camera_id,
                rtsp_url=rtsp_url,
                name=name,
                frame_skip=frame_skip,
                max_width=max_width,
                target_fps=target_fps,
            )
            self.streams[camera_id] = stream
            self._start_stream(stream)
            logger.info(f"📹 Camera {camera_id} '{name}' registered "
                        f"(skip={frame_skip} max_w={max_width} fps_cap={target_fps})")
            return True

    def remove_camera(self, camera_id: int):
        """Stop and remove a camera stream."""
        with self._lock:
            stream = self.streams.pop(camera_id, None)
            if stream:
                stream.running = False
                if stream.thread:
                    stream.thread.join(timeout=5)
                if stream.cap:
                    stream.cap.release()
                logger.info(f"📹 Camera {camera_id} removed")

    def get_latest_frame(self, camera_id: int):
        """Get the most recent raw frame for a camera."""
        stream = self.streams.get(camera_id)
        if stream and stream.buffer:
            return stream.buffer[-1]
        return None

    def get_annotated_frame(self, camera_id: int):
        """Get the latest annotated (bbox-drawn) frame, or raw frame if no annotation yet."""
        stream = self.streams.get(camera_id)
        if not stream:
            return None
        if stream.annotated_frame is not None:
            return stream.annotated_frame
        if stream.buffer:
            return stream.buffer[-1]
        return None

    def set_annotated_frame(self, camera_id: int, frame):
        """Store the latest annotated frame produced by the inference pipeline."""
        stream = self.streams.get(camera_id)
        if stream:
            stream.annotated_frame = frame

    def save_snapshot(self, camera_id: int, path: str) -> bool:
        """Save the latest annotated frame as a JPEG snapshot."""
        frame = self.get_annotated_frame(camera_id)
        if frame is None:
            return False
        os.makedirs(os.path.dirname(path), exist_ok=True)
        ret, _ = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 90])
        if ret:
            _, buf = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 90])
            with open(path, 'wb') as f:
                f.write(buf.tobytes())
            return True
        return False

    def save_clip(self, camera_id: int, path: str, fps: float = 10.0,
                  quality: str = 'medium', frames: list | None = None) -> bool:
        """
        Save frames to an mp4 clip.
        If `frames` is provided use those; otherwise fall back to clip_buffer.
        """
        stream = self.streams.get(camera_id)
        if frames is None:
            if not stream or len(stream.clip_buffer) < 3:
                return False
            # clip_buffer stores (timestamp, frame) tuples
            frames = [f for _, f in stream.clip_buffer]
        if not frames:
            return False
        h, w = frames[0].shape[:2]
        os.makedirs(os.path.dirname(path), exist_ok=True)
        writer = open_writer(path, fps, w, h, quality=quality)
        for f in frames:
            writer.write(f)
        writer.release()
        return True

    def get_status(self, camera_id: int) -> dict:
        """Get camera stream status."""
        stream = self.streams.get(camera_id)
        if not stream:
            return {"connected": False, "fps": 0, "frame_count": 0}
        return {
            "camera_id": camera_id,
            "name": stream.name,
            "connected": stream.connected,
            "fps": round(stream.fps, 1),
            "frame_count": stream.frame_count,
            "error_count": stream.error_count,
            "last_frame_time": stream.last_frame_time,
        }

    def get_all_status(self) -> list[dict]:
        return [self.get_status(cid) for cid in self.streams]

    def _start_stream(self, stream: CameraStream):
        stream.running = True
        stream.thread = threading.Thread(
            target=self._capture_loop,
            args=(stream,),
            name=f"stream-cam{stream.camera_id}",
            daemon=True,
        )
        stream.thread.start()

    def _grab_loop(self, stream: CameraStream):
        """
        Fast grab-only loop — runs in its own thread.
        Continuously drains the RTSP buffer by calling cap.grab() without
        decoding. This prevents frame queue buildup which causes stream lag.
        The main capture loop calls cap.retrieve() to get the latest frame.
        """
        while stream.running and stream.cap and stream.cap.isOpened():
            stream.cap.grab()
        logger.debug(f"Grab loop ended for camera {stream.camera_id}")

    def _capture_loop(self, stream: CameraStream):
        """Main capture loop — always reads the freshest frame via grab+retrieve."""
        logger.info(f"Starting capture loop for camera {stream.camera_id}: {stream.rtsp_url}")

        while stream.running:
            try:
                cap = cv2.VideoCapture(stream.rtsp_url)
                # BUFFERSIZE=1: keep only the latest frame in the OS buffer
                # The grab loop drains everything above that continuously
                cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                if not cap.isOpened():
                    raise ConnectionError(f"Cannot open: {stream.rtsp_url}")

                stream.cap       = cap
                stream.connected = True
                stream.error_count = 0
                logger.success(f"Camera {stream.camera_id} connected")

                # Start the fast grab-drain thread
                grab_thread = threading.Thread(
                    target=self._grab_loop,
                    args=(stream,),
                    name=f"grab-cam{stream.camera_id}",
                    daemon=True,
                )
                grab_thread.start()

                skip_counter   = 0
                fps_start      = time.time()
                native_frames  = 0
                proc_frames    = 0
                throttle_start = time.time()

                while stream.running:
                    # retrieve() decodes only the latest grabbed frame
                    ret, frame = cap.retrieve()
                    if not ret:
                        # grab loop may still be running; give it a moment
                        time.sleep(0.005)
                        # Double-check with a fresh grab
                        if not cap.grab():
                            raise RuntimeError("Frame grab failed — stream lost")
                        ret, frame = cap.retrieve()
                        if not ret:
                            raise RuntimeError("Frame retrieve failed")

                    stream.last_frame_time = time.time()
                    stream.frame_count    += 1
                    native_frames         += 1

                    # FPS accounting
                    elapsed = time.time() - fps_start
                    if elapsed >= 1.0:
                        stream.native_fps = native_frames / elapsed
                        stream.fps        = proc_frames   / elapsed
                        native_frames     = 0
                        proc_frames       = 0
                        fps_start         = time.time()

                    # ── Target FPS throttle ──────────────────────────────────
                    if stream.target_fps > 0:
                        min_interval = 1.0 / stream.target_fps
                        since_last   = time.time() - throttle_start
                        if since_last < min_interval:
                            # Sleep remainder so grab loop stays active
                            time.sleep(min_interval - since_last)
                            continue
                        throttle_start = time.time()

                    # ── Frame skip (analytics cadence) ───────────────────────
                    skip_counter += 1
                    if skip_counter < stream.frame_skip:
                        continue
                    skip_counter = 0

                    # ── Downscale to max_width ───────────────────────────────
                    if stream.max_width > 0:
                        h, w = frame.shape[:2]
                        if w > stream.max_width:
                            scale = stream.max_width / w
                            frame = cv2.resize(
                                frame,
                                (stream.max_width, int(h * scale)),
                                interpolation=cv2.INTER_AREA,
                            )

                    proc_frames += 1
                    stream.buffer.append(frame)

            except Exception as e:
                stream.connected  = False
                stream.error_count += 1
                logger.error(f"Camera {stream.camera_id} error: {e}")
                if stream.cap:
                    stream.cap.release()
                    stream.cap = None

                if stream.running:
                    logger.info(f"Camera {stream.camera_id} reconnecting in {self.RECONNECT_DELAY}s...")
                    time.sleep(self.RECONNECT_DELAY)

        logger.info(f"Capture loop ended for camera {stream.camera_id}")

    def stop_all(self):
        """Stop all running streams."""
        for camera_id in list(self.streams.keys()):
            self.remove_camera(camera_id)
        logger.info("🛑 All streams stopped")


# Global singleton
stream_manager = StreamManager()

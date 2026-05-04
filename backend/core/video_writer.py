"""
NVR-grade video writer with H.264/H.265 compression.

Strategy (auto-detected at runtime):
  1. ffmpeg subprocess pipe  — best compression, any codec, sub-process H.264/H.265
  2. OpenCV + FFMPEG backend — cv2.VideoWriter with avc1/x264 (OpenCV built with FFMPEG=YES)
  3. OpenCV mp4v fallback    — MPEG-4 Part 2, larger files but always works

NVR-typical CRF values (Constant Rate Factor):
  quality='low'    → CRF 35  (~70% smaller than uncompressed MJPEG)
  quality='medium' → CRF 26  (~85% smaller, NVR default)
  quality='high'   → CRF 18  (~90% smaller, surveillance HD quality)

H.264 gives ~4–6x better compression than mp4v (MPEG-4 Part 2).
H.265 gives ~8–10x but requires libx265 (more CPU).
"""
import cv2
import subprocess
import numpy as np
import os
import shutil
from typing import Optional
from loguru import logger


# ─── Codec detection ──────────────────────────────────────────────────────────

def _ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


def _opencv_h264_available() -> bool:
    """Test if OpenCV can open a H.264 VideoWriter (silent)."""
    try:
        import sys, io
        tmp    = "/tmp/_neobit_h264_test.mp4"
        fourcc = cv2.VideoWriter_fourcc(*"avc1")
        # Suppress OpenCV/FFMPEG error output during the test
        old_err = sys.stderr
        sys.stderr = io.StringIO()
        try:
            w  = cv2.VideoWriter(tmp, fourcc, 10, (64, 64))
            ok = w.isOpened()
            w.release()
        finally:
            sys.stderr = old_err
        if os.path.exists(tmp):
            os.remove(tmp)
        return ok
    except Exception:
        return False


# Cache codec capability at import time
_HAS_FFMPEG    = _ffmpeg_available()
_HAS_CV2_H264 = _opencv_h264_available()

logger.info(
    f"Video codec: ffmpeg={_HAS_FFMPEG} cv2_h264={_HAS_CV2_H264} "
    f"(fallback=mp4v)"
)


# ─── Quality → codec params ───────────────────────────────────────────────────

# CRF: lower = better quality, larger file. Range 0–51.
QUALITY_CRF = {
    "low":    35,   # ~70% smaller than mp4v
    "medium": 26,   # ~85% smaller — NVR default
    "high":   18,   # ~90% smaller — HD surveillance
}

QUALITY_PRESET = {
    "low":    "veryfast",  # fastest encoding
    "medium": "fast",
    "high":   "medium",
}


# ─── Writer implementations ───────────────────────────────────────────────────

class FfmpegPipeWriter:
    """
    Writes frames via pipe to an ffmpeg subprocess.
    Produces true H.264 MP4 with CRF compression.
    Best quality/size ratio — identical to professional NVR output.
    """

    def __init__(self, path: str, fps: float, width: int, height: int,
                 quality: str = "medium", codec: str = "h264"):
        self.path  = path
        crf        = QUALITY_CRF.get(quality, 26)
        preset     = QUALITY_PRESET.get(quality, "fast")
        vcodec     = "libx265" if codec == "h265" else "libx264"

        cmd = [
            "ffmpeg", "-y",
            "-f", "rawvideo",
            "-vcodec", "rawvideo",
            "-pix_fmt", "bgr24",
            "-s", f"{width}x{height}",
            "-r", str(fps),
            "-i", "pipe:0",
            "-vcodec", vcodec,
            "-crf", str(crf),
            "-preset", preset,
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",   # web-compatible, plays before full download
            path,
        ]
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self._proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        self._ok = True
        logger.debug(f"ffmpeg H.264 writer: {path} crf={crf} preset={preset}")

    def write(self, frame: np.ndarray):
        if not self._ok:
            return
        try:
            self._proc.stdin.write(frame.tobytes())
        except BrokenPipeError:
            self._ok = False

    def release(self):
        if self._proc and self._ok:
            try:
                self._proc.stdin.close()
                self._proc.wait(timeout=30)
            except Exception:
                self._proc.kill()
        self._ok = False

    def isOpened(self) -> bool:
        return self._ok


class Cv2H264Writer:
    """OpenCV VideoWriter with avc1 (H.264) — works when OpenCV built with FFMPEG."""

    def __init__(self, path: str, fps: float, width: int, height: int,
                 quality: str = "medium"):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        fourcc     = cv2.VideoWriter_fourcc(*"avc1")
        self._w    = cv2.VideoWriter(path, fourcc, fps, (width, height))
        logger.debug(f"cv2 H.264 writer: {path}")

    def write(self, frame):     self._w.write(frame)
    def release(self):          self._w.release()
    def isOpened(self) -> bool: return self._w.isOpened()


class Cv2Mp4vWriter:
    """OpenCV MPEG-4 Part 2 fallback. Larger files but universally compatible."""

    def __init__(self, path: str, fps: float, width: int, height: int,
                 quality: str = "medium"):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        fourcc  = cv2.VideoWriter_fourcc(*"mp4v")
        self._w = cv2.VideoWriter(path, fourcc, fps, (width, height))
        logger.debug(f"cv2 mp4v writer: {path}")

    def write(self, frame):     self._w.write(frame)
    def release(self):          self._w.release()
    def isOpened(self) -> bool: return self._w.isOpened()


# ─── Factory ──────────────────────────────────────────────────────────────────

def open_writer(path: str, fps: float, width: int, height: int,
                quality: str = "medium",
                codec: str = "h264") -> object:
    """
    Open the best available video writer for the platform.

    Priority:
      1. ffmpeg subprocess (H.264 or H.265)
      2. OpenCV + avc1 (H.264, needs FFMPEG-enabled OpenCV)
      3. OpenCV mp4v  (always works, larger files)
    """
    if _HAS_FFMPEG:
        try:
            w = FfmpegPipeWriter(path, fps, width, height, quality, codec)
            if w.isOpened():
                return w
        except Exception as e:
            logger.warning(f"ffmpeg writer failed, falling back: {e}")

    if _HAS_CV2_H264:
        w = Cv2H264Writer(path, fps, width, height, quality)
        if w.isOpened():
            return w

    return Cv2Mp4vWriter(path, fps, width, height, quality)


def codec_name() -> str:
    """Return the active codec name for display in the UI."""
    if _HAS_FFMPEG:
        return "H.264 (ffmpeg)"
    if _HAS_CV2_H264:
        return "H.264 (OpenCV)"
    return "MPEG-4 (mp4v)"

"""
MJPEG Stream — serves AI-annotated frames at inference rate.

Design:
  - mjpeg_generator() yields ONLY annotated frames (with bbox overlays).
  - Rate is naturally governed by how fast the inference pipeline
    produces annotated frames — typically 10-15 fps on CPU.
  - No fixed sleep: uses change-detection on the frame object id so
    the browser always gets the very latest annotated frame without
    waiting a fixed interval.
  - If no new annotated frame is ready within MAX_WAIT, a low-quality
    placeholder is sent to keep the connection alive.
"""
import cv2
import asyncio
import time
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse, Response
from backend.core.stream_manager import stream_manager
from loguru import logger

router = APIRouter(prefix="/api/stream", tags=["Streams"])

# Maximum time to wait for a new annotated frame before re-sending last one
_MAX_WAIT    = 0.5    # seconds — keeps connection alive even if pipeline stalls
_POLL_SLEEP  = 0.008  # 8ms polling loop — CPU-light, sub-frame latency

# JPEG quality: lower = smaller packets = lower latency on LAN
_JPEG_QUALITY = 70


def _encode(frame, quality: int = _JPEG_QUALITY) -> bytes:
    ret, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, quality])
    if not ret:
        raise RuntimeError("JPEG encode failed")
    return buf.tobytes()


async def mjpeg_generator(camera_id: int, quality: int = _JPEG_QUALITY):
    """
    Yield MJPEG frames at inference rate.

    Waits for a new annotated frame (produced by the AI pipeline).
    Sends immediately when ready → zero artificial delay.
    Falls back to last frame if pipeline stalls.
    """
    boundary = b"--frame"
    last_id  = None
    last_sent = 0.0
    last_jpeg: bytes | None = None

    while True:
        frame = stream_manager.get_annotated_frame(camera_id)

        if frame is None:
            await asyncio.sleep(0.05)
            continue

        frame_id = id(frame)
        now = time.monotonic()

        if frame_id != last_id:
            # New annotated frame ready — encode and send immediately
            try:
                last_jpeg = _encode(frame, quality)
                last_id   = frame_id
                last_sent = now
            except Exception as e:
                logger.warning(f"Encode error cam {camera_id}: {e}")
                await asyncio.sleep(0.05)
                continue

        elif now - last_sent < _MAX_WAIT:
            # Same frame, still within wait window — poll again
            await asyncio.sleep(_POLL_SLEEP)
            continue

        # else: same frame but timeout reached → re-send to keep connection alive

        if last_jpeg is None:
            await asyncio.sleep(_POLL_SLEEP)
            continue

        yield (
            boundary + b"\r\n"
            b"Content-Type: image/jpeg\r\n"
            b"Content-Length: " + str(len(last_jpeg)).encode() + b"\r\n"
            b"\r\n" + last_jpeg + b"\r\n"
        )
        last_sent = now
        await asyncio.sleep(_POLL_SLEEP)


@router.get("/{camera_id}/mjpeg")
async def stream_mjpeg(camera_id: int, quality: int = _JPEG_QUALITY):
    """
    MJPEG live stream — annotated at AI inference rate (no artificial lag).
    Usage: <img src="/api/stream/{id}/mjpeg" />
    """
    status = stream_manager.get_status(camera_id)
    if not status.get("connected", False):
        raise HTTPException(status_code=503, detail=f"Camera {camera_id} not connected")

    return StreamingResponse(
        mjpeg_generator(camera_id, quality),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={
            "Cache-Control":     "no-cache, no-store",
            "X-Camera-Id":       str(camera_id),
            "X-Accel-Buffering": "no",   # disable Nginx buffering if behind proxy
        },
    )


@router.get("/{camera_id}/snapshot")
async def get_snapshot(camera_id: int, quality: int = 85):
    """Single JPEG snapshot (latest annotated frame)."""
    frame = stream_manager.get_annotated_frame(camera_id)
    if frame is None:
        raise HTTPException(status_code=503, detail=f"No frame for camera {camera_id}")
    try:
        jpeg = _encode(frame, quality)
        return Response(
            content=jpeg, media_type="image/jpeg",
            headers={"Cache-Control": "no-cache", "X-Camera-Id": str(camera_id)},
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status")
async def all_stream_status():
    return stream_manager.get_all_status()

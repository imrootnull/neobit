"""
MJPEG Stream — serves AI-annotated frames at inference rate.

Design:
  - Checks for new annotated frame every 33ms (max 30 fps visual cap)
  - JPEG encode runs in thread pool via run_in_executor to avoid
    blocking the asyncio event loop
  - Falls back to re-sending last frame every 500ms to keep connection alive
"""
import cv2
import asyncio
import time
from concurrent.futures import ThreadPoolExecutor
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse, Response
from backend.core.stream_manager import stream_manager
from loguru import logger

router = APIRouter(prefix="/api/stream", tags=["Streams"])

# Shared thread pool for JPEG encoding (CPU-bound but very fast ~1ms)
_encode_pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="mjpeg-enc")


_JPEG_QUALITY = 70
_POLL_MS      = 0.033
_KEEPALIVE_S  = 0.5

# Cache of SharedFrame slots keyed by camera_id.
# Populated lazily; retries every 5s if worker.py hasn't created the slot yet.
_shm_cache: dict[int, object] = {}
_shm_last_try: dict[int, float] = {}

def _get_shm(camera_id: int):
    """Return cached SharedFrame for camera, or None if not available.
    Retries opening every 5s so uvicorn picks up overlays once worker starts.
    """
    import time as _time
    slot = _shm_cache.get(camera_id, "unset")
    if slot != "unset" and slot is not None:
        return slot
    # Retry if None or never tried, but throttle to every 5s
    last = _shm_last_try.get(camera_id, 0)
    if _time.monotonic() - last < 5.0 and slot is None:
        return None
    _shm_last_try[camera_id] = _time.monotonic()
    try:
        from backend.core.frame_bridge import SharedFrame
        new_slot = SharedFrame(f"nb_ann_{camera_id}", create=False)
        _shm_cache[camera_id] = new_slot
        return new_slot
    except Exception:
        _shm_cache[camera_id] = None
        return None


def _encode_sync(frame, quality: int) -> bytes:
    """Encode frame to JPEG synchronously (runs in thread pool)."""
    ret, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, quality])
    if not ret:
        raise RuntimeError("JPEG encode failed")
    return buf.tobytes()


async def mjpeg_generator(camera_id: int, quality: int = _JPEG_QUALITY):
    """
    Yield MJPEG frames.
    - Polls for new annotated frame every 33ms
    - Encodes in thread pool (non-blocking)
    - Re-sends last frame every 500ms to keep connection alive
    """
    boundary  = b"--frame\r\nContent-Type: image/jpeg\r\n"
    last_id   = None
    last_jpeg: bytes | None = None
    last_sent = 0.0
    loop = asyncio.get_event_loop()

    while True:
        await asyncio.sleep(_POLL_MS)

        frame = stream_manager.get_annotated_frame(camera_id)
        if frame is None:
            continue

        now      = time.monotonic()
        frame_id = id(frame)
        is_new   = (frame_id != last_id)
        timeout  = (now - last_sent) >= _KEEPALIVE_S

        if not is_new and not timeout:
            continue

        # Encode in thread pool so we don't block the event loop
        try:
            jpeg = await loop.run_in_executor(_encode_pool, _encode_sync, frame, quality)
        except Exception as e:
            logger.warning(f"Encode error cam {camera_id}: {e}")
            continue

        last_id   = frame_id
        last_jpeg = jpeg
        last_sent = now

        yield (
            boundary
            + b"Content-Length: " + str(len(jpeg)).encode() + b"\r\n\r\n"
            + jpeg + b"\r\n"
        )


@router.get("/{camera_id}/mjpeg")
async def stream_mjpeg(camera_id: int, quality: int = _JPEG_QUALITY):
    """
    MJPEG live stream — annotated at AI inference rate.
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
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/{camera_id}/snapshot")
async def get_snapshot(camera_id: int, quality: int = 85):
    """
    Single JPEG snapshot — reads annotated frame from shared memory
    (written by worker.py with YOLO overlays). Falls back to local
    stream_manager frame if shared memory not yet populated.
    """
    frame = None

    # Try shared memory first (annotated frame with YOLO overlays from worker)
    frame = None
    slot = _get_shm(camera_id)
    if slot is not None:
        frame, fid = slot.read()
        if fid == 0:
            frame = None

    # Fallback: raw frame from local stream_manager
    if frame is None:
        frame = stream_manager.get_annotated_frame(camera_id)


    if frame is None:
        raise HTTPException(status_code=503, detail=f"No frame for camera {camera_id}")

    loop = asyncio.get_event_loop()
    try:
        jpeg = await loop.run_in_executor(_encode_pool, _encode_sync, frame, quality)
        return Response(content=jpeg, media_type="image/jpeg",
                        headers={"Cache-Control": "no-cache"})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))



@router.get("/status")
async def all_stream_status():
    return stream_manager.get_all_status()

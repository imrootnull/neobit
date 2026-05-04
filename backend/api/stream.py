"""
MJPEG Stream proxy endpoint — serves live camera frames as MJPEG
for browser-compatible video display without WebRTC complexity.

Also serves individual snapshots per camera.
"""
import cv2
import asyncio
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse, Response
from backend.core.stream_manager import stream_manager
from loguru import logger

router = APIRouter(prefix="/api/stream", tags=["Streams"])


def encode_frame_jpeg(frame, quality: int = 75) -> bytes:
    """Encode OpenCV frame to JPEG bytes."""
    ret, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, quality])
    if not ret:
        raise RuntimeError("Frame encoding failed")
    return buf.tobytes()


async def mjpeg_generator(camera_id: int):
    """Async generator yielding MJPEG frames — annotated (bbox) when inference is active."""
    boundary  = b"--frame"
    last_hash = None

    while True:
        frame = stream_manager.get_annotated_frame(camera_id)

        if frame is None:
            await asyncio.sleep(0.05)
            continue

        # Simple identity check (avoid sending same frame twice)
        frame_id = id(frame)
        if frame_id == last_hash:
            await asyncio.sleep(0.033)
            continue
        last_hash = frame_id

        try:
            jpeg = encode_frame_jpeg(frame)
            yield (
                boundary + b"\r\n"
                b"Content-Type: image/jpeg\r\n"
                b"Content-Length: " + str(len(jpeg)).encode() + b"\r\n"
                b"\r\n" + jpeg + b"\r\n"
            )
        except Exception as e:
            logger.warning(f"Frame encode error cam {camera_id}: {e}")

        await asyncio.sleep(0.033)  # ~30 fps target


@router.get("/{camera_id}/mjpeg")
async def stream_mjpeg(camera_id: int, quality: int = 75):
    """
    MJPEG live stream for a camera.
    Compatible with any browser <img> tag or VMS that supports MJPEG.
    Usage: <img src="/api/stream/{id}/mjpeg" />
    """
    status = stream_manager.get_status(camera_id)
    if not status.get("connected", False):
        raise HTTPException(status_code=503, detail=f"Camera {camera_id} not connected")

    return StreamingResponse(
        mjpeg_generator(camera_id),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={
            "Cache-Control": "no-cache",
            "X-Camera-Id": str(camera_id),
        },
    )


@router.get("/{camera_id}/snapshot")
async def get_snapshot(camera_id: int, quality: int = 85):
    """
    Get a single JPEG snapshot from a camera.
    Useful for thumbnails, event snapshots, and VMS integration.
    """
    frame = stream_manager.get_latest_frame(camera_id)
    if frame is None:
        raise HTTPException(status_code=503, detail=f"No frame available for camera {camera_id}")

    try:
        jpeg = encode_frame_jpeg(frame, quality=quality)
        return Response(
            content=jpeg,
            media_type="image/jpeg",
            headers={
                "Cache-Control": "no-cache",
                "X-Camera-Id": str(camera_id),
            },
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status")
async def all_stream_status():
    """Get connection status for all registered streams."""
    return stream_manager.get_all_status()

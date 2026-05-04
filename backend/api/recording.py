"""
Recording API — configure and monitor the recording system.
"""
import os
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional, Literal
from backend.storage.database import get_db, Camera
from backend.core.recording_manager import recording_manager
from backend.core.video_writer import codec_name, _HAS_FFMPEG, _HAS_CV2_H264
from loguru import logger

router = APIRouter(prefix="/api/recording", tags=["Recording"])


class RecordingConfigUpdate(BaseModel):
    enabled:         Optional[bool]  = None
    mode:            Optional[str]   = None
    storage_path:    Optional[str]   = None
    max_disk_gb:     Optional[float] = None
    segment_minutes: Optional[int]   = None
    pre_buffer_s:    Optional[int]   = None
    post_buffer_s:   Optional[int]   = None
    retain_days:     Optional[int]   = None
    video_quality:   Optional[str]   = None
    video_codec:     Optional[str]   = None
    video_fps:       Optional[float] = None   # Recording FPS (1-30)


@router.get("/status")
async def recording_status():
    """Get recording system status, storage metrics, and active codec."""
    status = recording_manager.get_status()
    status['codec']         = codec_name()
    status['ffmpeg_available'] = _HAS_FFMPEG
    status['h265_available']   = _HAS_FFMPEG   # H.265 requires ffmpeg
    return status


@router.put("/config")
async def update_recording_config(data: RecordingConfigUpdate):
    """
    Update recording configuration.
    Changes take effect immediately — active recordings are restarted.

    storage_path examples:
      Linux:   /mnt/usb, /media/rootnull/SSD2, /mnt/nas
      Windows: /mnt/d (if WSL), D:/recordings
    """
    updates = data.model_dump(exclude_none=True)

    if not updates:
        raise HTTPException(400, "No hay cambios para aplicar")

    # Validate storage_path if provided
    if "storage_path" in updates:
        path = updates["storage_path"]
        try:
            os.makedirs(path, exist_ok=True)
        except Exception as e:
            raise HTTPException(400, f"No se puede acceder a la ruta: {e}")
        free_gb = _free_gb(path)
        if free_gb < 1:
            raise HTTPException(400, f"Disco lleno o sin permisos en: {path}")
        updates["_free_gb"] = free_gb

    recording_manager.configure(**{k: v for k, v in updates.items() if not k.startswith("_")})

    # Handle enable/disable
    if updates.get("enabled") is True:
        recording_manager.enable()
    elif updates.get("enabled") is False:
        recording_manager.disable()

    status = recording_manager.get_status()
    if "storage_path" in updates:
        status["free_gb_on_new_path"] = updates.get("_free_gb")
    return status


@router.get("/disks")
async def list_available_disks():
    """
    Detect available storage devices (mounted drives).
    Helps the user pick a disk/path for recordings.
    """
    import subprocess, re
    disks = []

    # Linux: parse /proc/mounts
    try:
        with open("/proc/mounts") as f:
            for line in f:
                parts = line.split()
                if len(parts) < 3:
                    continue
                device, mount, fstype = parts[0], parts[1], parts[2]
                # Skip system mounts
                if any(m in mount for m in ["/proc", "/sys", "/dev", "/run", "/snap"]):
                    continue
                if fstype in ("tmpfs", "devtmpfs", "sysfs", "proc", "cgroup", "overlay"):
                    continue
                try:
                    stat = os.statvfs(mount)
                    total_gb = stat.f_blocks * stat.f_frsize / 1024**3
                    free_gb  = stat.f_bavail * stat.f_frsize / 1024**3
                    if total_gb < 0.1:
                        continue
                    disks.append({
                        "device":    device,
                        "mount":     mount,
                        "fstype":    fstype,
                        "total_gb":  round(total_gb, 1),
                        "free_gb":   round(free_gb, 1),
                        "used_pct":  round((1 - free_gb / total_gb) * 100, 1),
                        "suggested_path": os.path.join(mount, "NeoBit_Recordings"),
                    })
                except Exception:
                    pass
    except Exception as e:
        logger.warning(f"Disk listing error: {e}")

    return sorted(disks, key=lambda d: d["free_gb"], reverse=True)


@router.get("/files")
async def list_recordings(camera_id: Optional[int] = None, limit: int = 50):
    """List saved recording files, optionally filtered by camera."""
    base = recording_manager.config.storage_path
    files = []
    for root, dirs, fnames in os.walk(base):
        for f in fnames:
            if not f.endswith(".mp4"):
                continue
            fp = os.path.join(root, f)
            # Extract camera ID from path
            rel    = os.path.relpath(fp, base)
            parts  = rel.split(os.sep)
            cam_id = None
            if parts[0].startswith("cam"):
                try:
                    cam_id = int(parts[0][3:])
                except ValueError:
                    pass
            if camera_id is not None and cam_id != camera_id:
                continue
            try:
                stat = os.stat(fp)
                files.append({
                    "path":      fp,
                    "filename":  f,
                    "camera_id": cam_id,
                    "size_mb":   round(stat.st_size / 1024**2, 2),
                    "created":   stat.st_mtime,
                    "url":       f"/api/recording/play?path={fp}",
                })
            except OSError:
                pass

    files.sort(key=lambda x: x["created"], reverse=True)
    return files[:limit]


@router.get("/play")
async def play_recording(path: str):
    """Stream a recording file."""
    if not os.path.exists(path):
        raise HTTPException(404, "Archivo no encontrado")
    # Basic path traversal guard
    real = os.path.realpath(path)
    base = os.path.realpath(recording_manager.config.storage_path)
    if not real.startswith(base):
        raise HTTPException(403, "Acceso denegado")
    return FileResponse(path, media_type="video/mp4")


def _free_gb(path: str) -> float:
    try:
        stat = os.statvfs(path)
        return stat.f_bavail * stat.f_frsize / 1024**3
    except Exception:
        return 0.0

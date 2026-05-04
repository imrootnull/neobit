"""
NVR Playback API — timeline queries, clip listing, export, and smart search.
"""
import os
import io
import zipfile
import subprocess
import shutil
from datetime import datetime, timedelta
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, func, and_
from pydantic import BaseModel
from backend.storage.database import get_db, Event
from backend.core.recording_manager import recording_manager
from loguru import logger

router = APIRouter(prefix="/api/playback", tags=["Playback"])

# ─── helpers ─────────────────────────────────────────────────────────────────

def _parse_ts(ts: str) -> datetime:
    """Parse ISO datetime string → UTC datetime."""
    return datetime.fromisoformat(ts.replace("Z", "+00:00")).replace(tzinfo=None)


def _scan_clips(camera_id: Optional[int] = None) -> list[dict]:
    """Walk the recordings directory and return all .mp4 / .jpg files."""
    base = recording_manager.config.storage_path
    items = []
    for root, dirs, files in os.walk(base):
        for f in files:
            if not (f.endswith(".mp4") or f.endswith(".jpg")):
                continue
            fp = os.path.join(root, f)
            rel = os.path.relpath(fp, base)
            parts = rel.replace("\\", "/").split("/")

            # path pattern: events/cam2/face_detection/20260504_090645_clip.mp4
            cam_id = None
            analytic = None
            file_ts = None
            media_type = "clip" if f.endswith(".mp4") else "snapshot"

            for i, p in enumerate(parts):
                if p.startswith("cam"):
                    try:
                        cam_id = int(p[3:])
                    except ValueError:
                        pass
                elif p in ("face_detection", "person_detection", "epp_detection",
                           "fall_detection", "vehicle_detection", "intrusion_detection",
                           "line_crossing", "theft_detection", "crowd_detection"):
                    analytic = p

            # Timestamp from filename: 20260504_090645
            stem = f.split("_clip")[0].split("_snap")[0]
            try:
                file_ts = datetime.strptime(stem, "%Y%m%d_%H%M%S")
            except ValueError:
                try:
                    stat = os.stat(fp)
                    file_ts = datetime.fromtimestamp(stat.st_mtime)
                except Exception:
                    file_ts = datetime.now()

            if camera_id is not None and cam_id != camera_id:
                continue

            try:
                size = os.path.getsize(fp)
            except Exception:
                size = 0

            items.append({
                "path":       fp,
                "filename":   f,
                "camera_id":  cam_id,
                "analytic":   analytic,
                "timestamp":  file_ts.isoformat(),
                "media_type": media_type,
                "size_bytes": size,
                "url":        f"/api/playback/file?path={fp}",
            })

    items.sort(key=lambda x: x["timestamp"], reverse=True)
    return items


# ─── endpoints ───────────────────────────────────────────────────────────────

@router.get("/timeline")
async def get_timeline(
    camera_id: Optional[int] = None,
    date: Optional[str] = None,         # YYYY-MM-DD
    db: AsyncSession = Depends(get_db),
):
    """
    Return events + clips grouped by hour for NVR timeline view.
    """
    # Parse date filter
    if date:
        try:
            day = datetime.strptime(date, "%Y-%m-%d")
        except ValueError:
            raise HTTPException(400, "date must be YYYY-MM-DD")
    else:
        day = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

    day_end = day + timedelta(days=1)

    # Query events for the day
    q = select(Event).where(
        and_(Event.timestamp >= day, Event.timestamp < day_end)
    ).order_by(Event.timestamp)
    if camera_id:
        q = q.where(Event.camera_id == camera_id)

    result = await db.execute(q)
    events = result.scalars().all()

    # Group by hour
    buckets: dict[int, list] = {h: [] for h in range(24)}
    for ev in events:
        buckets[ev.timestamp.hour].append({
            "id":        ev.id,
            "analytic":  ev.analytic_key,
            "severity":  ev.severity,
            "confidence": ev.confidence,
            "description": ev.description,
            "timestamp": ev.timestamp.isoformat(),
            "has_snapshot": bool(ev.snapshot_path and os.path.exists(ev.snapshot_path)),
            "has_clip":     bool(ev.recording_path and os.path.exists(ev.recording_path)),
            "snapshot_url": f"/api/events/{ev.id}/snapshot" if ev.snapshot_path else None,
            "clip_url":     f"/api/events/{ev.id}/clip"     if ev.recording_path else None,
        })

    # Also scan disk clips for this day (files saved independently)
    all_clips = _scan_clips(camera_id)
    day_str = day.strftime("%Y%m%d")
    disk_clips = [c for c in all_clips if day_str in c["filename"]]

    return {
        "date":       day.strftime("%Y-%m-%d"),
        "timeline":   [{"hour": h, "events": buckets[h]} for h in range(24)],
        "total_events": len(events),
        "disk_clips": disk_clips[:200],
    }


@router.get("/clips")
async def list_clips(
    camera_id: Optional[int] = None,
    analytic:  Optional[str] = None,
    media_type: Optional[str] = None,   # "clip" | "snapshot"
    limit: int = 100,
    offset: int = 0,
):
    """List all stored clips and snapshots, filterable."""
    items = _scan_clips(camera_id)
    if analytic:
        items = [i for i in items if i["analytic"] == analytic]
    if media_type:
        items = [i for i in items if i["media_type"] == media_type]
    return {
        "total":  len(items),
        "items":  items[offset: offset + limit],
    }


@router.get("/file")
async def serve_file(path: str):
    """Serve a recording file (mp4 or jpg) with security check."""
    if not os.path.exists(path):
        raise HTTPException(404, "Archivo no encontrado")
    real = os.path.realpath(path)
    base = os.path.realpath(recording_manager.config.storage_path)
    if not real.startswith(base):
        raise HTTPException(403, "Acceso denegado")
    mt = "video/mp4" if path.endswith(".mp4") else "image/jpeg"
    return FileResponse(path, media_type=mt,
                        headers={"Cache-Control": "max-age=86400"})


@router.get("/export")
async def export_clips(paths: str = Query(..., description="Comma-separated file paths")):
    """
    Export one or multiple clips/snapshots as a ZIP.
    Usage: GET /api/playback/export?paths=/path/a.mp4,/path/b.jpg
    """
    path_list = [p.strip() for p in paths.split(",") if p.strip()]
    base = os.path.realpath(recording_manager.config.storage_path)

    valid = []
    for p in path_list:
        real = os.path.realpath(p)
        if real.startswith(base) and os.path.exists(p):
            valid.append(p)

    if not valid:
        raise HTTPException(404, "Ningún archivo válido seleccionado")

    if len(valid) == 1 and valid[0].endswith(".mp4"):
        # Single video — stream directly (possibly transcode)
        path = valid[0]
        has_ffmpeg = shutil.which("ffmpeg") is not None
        if has_ffmpeg:
            cmd = ["ffmpeg", "-i", path, "-c:v", "libx264", "-preset", "fast",
                   "-crf", "23", "-movflags", "frag_keyframe+empty_moov",
                   "-f", "mp4", "pipe:1"]
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            return StreamingResponse(proc.stdout, media_type="video/mp4",
                                     headers={"Content-Disposition": f"attachment; filename={os.path.basename(path)}"})
        return FileResponse(path, media_type="video/mp4",
                            headers={"Content-Disposition": f"attachment; filename={os.path.basename(path)}"})

    # Multiple files → ZIP
    def zip_generator():
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for p in valid:
                zf.write(p, os.path.basename(p))
        buf.seek(0)
        yield buf.read()

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return StreamingResponse(
        zip_generator(),
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename=neobit_export_{ts}.zip"},
    )


@router.get("/stats")
async def playback_stats(db: AsyncSession = Depends(get_db)):
    """Storage and event statistics for the NVR page header."""
    base = recording_manager.config.storage_path
    total_clips = 0
    total_snaps = 0
    total_size  = 0

    for root, dirs, files in os.walk(base):
        for f in files:
            fp = os.path.join(root, f)
            try:
                sz = os.path.getsize(fp)
            except Exception:
                sz = 0
            total_size += sz
            if f.endswith(".mp4"):
                total_clips += 1
            elif f.endswith(".jpg"):
                total_snaps += 1

    # Event count from DB
    res = await db.execute(select(func.count()).select_from(Event))
    total_events = res.scalar()

    # Disk usage
    try:
        stat = os.statvfs(base)
        free_gb  = stat.f_bavail * stat.f_frsize / 1024**3
        total_gb = stat.f_blocks * stat.f_frsize / 1024**3
    except Exception:
        free_gb = total_gb = 0

    return {
        "total_clips":    total_clips,
        "total_snapshots": total_snaps,
        "total_events":   total_events,
        "used_gb":        round(total_size / 1024**3, 2),
        "free_gb":        round(free_gb, 1),
        "total_gb":       round(total_gb, 1),
        "storage_path":   base,
    }

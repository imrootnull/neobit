"""
Events API — query analytics events, acknowledge alerts,
manage cloud/VMS integration settings, and serve event media (snapshot/clip).
"""
import os
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from backend.storage.database import get_db, Event, EventSeverity
from backend.core.event_bus import event_bus
from loguru import logger

router = APIRouter(prefix="/api/events", tags=["Events"])


@router.get("/{event_id}/snapshot")
async def get_event_snapshot(event_id: int, db: AsyncSession = Depends(get_db)):
    """Serve the snapshot image saved when this event fired."""
    ev = await db.get(Event, event_id)
    if not ev:
        raise HTTPException(404, "Evento no encontrado")
    if not ev.snapshot_path or not os.path.exists(ev.snapshot_path):
        raise HTTPException(404, "Snapshot no disponible para este evento")
    return FileResponse(ev.snapshot_path, media_type="image/jpeg",
                        headers={"Cache-Control": "max-age=3600"})


@router.get("/{event_id}/clip")
async def get_event_clip(event_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    """Serve the video clip with HTTP Range support for browser video playback."""
    ev = await db.get(Event, event_id)
    if not ev:
        raise HTTPException(404, "Evento no encontrado")
    path = ev.recording_path
    if not path or not os.path.exists(path):
        raise HTTPException(404, "Clip no disponible para este evento")

    file_size = os.path.getsize(path)
    range_header = request.headers.get("range")

    if range_header:
        # Parse "bytes=start-end"
        try:
            start_str, end_str = range_header.replace("bytes=", "").split("-")
            start = int(start_str)
            end   = int(end_str) if end_str else file_size - 1
        except Exception:
            start, end = 0, file_size - 1

        end   = min(end, file_size - 1)
        chunk = end - start + 1

        def iter_file():
            with open(path, "rb") as f:
                f.seek(start)
                remaining = chunk
                while remaining > 0:
                    data = f.read(min(65536, remaining))
                    if not data:
                        break
                    remaining -= len(data)
                    yield data

        return StreamingResponse(
            iter_file(),
            status_code=206,
            media_type="video/mp4",
            headers={
                "Content-Range":  f"bytes {start}-{end}/{file_size}",
                "Accept-Ranges":  "bytes",
                "Content-Length": str(chunk),
                "Cache-Control":  "max-age=3600",
            },
        )

    # No Range header — stream entire file
    def iter_full():
        with open(path, "rb") as f:
            while True:
                data = f.read(65536)
                if not data:
                    break
                yield data

    return StreamingResponse(
        iter_full(),
        media_type="video/mp4",
        headers={
            "Accept-Ranges":  "bytes",
            "Content-Length": str(file_size),
            "Cache-Control":  "max-age=3600",
        },
    )



class EventResponse(BaseModel):
    id: int
    camera_id: int
    analytic_type: str
    severity: str
    description: Optional[str]
    confidence: Optional[float]
    snapshot_path: Optional[str]
    recording_path: Optional[str]
    timestamp: float
    event_meta: dict = {}
    acknowledged: bool

    class Config:
        from_attributes = True


class WebhookConfig(BaseModel):
    url: str
    description: Optional[str] = None


class CloudConfig(BaseModel):
    url: str
    api_key: str
    gateway_id: str


@router.get("/", response_model=list[EventResponse])
async def list_events(
    camera_id: Optional[int] = None,
    analytic_type: Optional[str] = None,
    severity: Optional[str] = None,
    acknowledged: Optional[bool] = None,
    limit: int = Query(default=50, le=500),
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
):
    """Query events with filters. Supports pagination."""
    stmt = select(Event).order_by(desc(Event.created_at))

    if camera_id is not None:
        stmt = stmt.where(Event.camera_id == camera_id)
    if analytic_type:
        stmt = stmt.where(Event.analytic_type == analytic_type)
    if severity:
        stmt = stmt.where(Event.severity == severity)
    if acknowledged is not None:
        stmt = stmt.where(Event.acknowledged == acknowledged)

    stmt = stmt.limit(limit).offset(offset)
    result = await db.execute(stmt)
    return result.scalars().all()


@router.post("/{event_id}/acknowledge")
async def acknowledge_event(event_id: int, db: AsyncSession = Depends(get_db)):
    """Mark an event as acknowledged."""
    ev = await db.get(Event, event_id)
    if not ev:
        raise HTTPException(status_code=404, detail="Event not found")
    ev.acknowledged = True
    await db.commit()
    return {"status": "acknowledged", "event_id": event_id}


@router.post("/acknowledge-all")
async def acknowledge_all(camera_id: Optional[int] = None, db: AsyncSession = Depends(get_db)):
    """Acknowledge all unread events, optionally for a specific camera."""
    stmt = select(Event).where(Event.acknowledged == False)
    if camera_id:
        stmt = stmt.where(Event.camera_id == camera_id)
    result = await db.execute(stmt)
    events = result.scalars().all()
    for ev in events:
        ev.acknowledged = True
    await db.commit()
    return {"acknowledged": len(events)}


@router.get("/stats")
async def event_stats(db: AsyncSession = Depends(get_db)):
    """Summary stats for the events dashboard widget."""
    from sqlalchemy import func
    result = await db.execute(
        select(Event.analytic_type, Event.severity, func.count(Event.id))
        .group_by(Event.analytic_type, Event.severity)
    )
    rows = result.all()
    stats = {}
    for analytic_type, severity, count in rows:
        if analytic_type not in stats:
            stats[analytic_type] = {}
        stats[analytic_type][severity] = count
    return stats


# ─── Cloud + VMS Integration ─────────────────────────────────────────────────

_webhooks: dict[str, str] = {}  # url -> description


@router.post("/integrations/cloud")
async def configure_cloud(config: CloudConfig):
    """Configure the NeoBit Cloud Platform connection."""
    event_bus.configure_cloud(config.url, config.api_key, config.gateway_id)
    return {"status": "configured", "url": config.url, "gateway_id": config.gateway_id}


@router.post("/integrations/webhooks")
async def add_webhook(config: WebhookConfig):
    """Add an external VMS/system webhook endpoint."""
    event_bus.add_webhook(config.url)
    _webhooks[config.url] = config.description or ""
    return {"status": "added", "url": config.url}


@router.delete("/integrations/webhooks")
async def remove_webhook(url: str):
    """Remove a webhook."""
    event_bus.remove_webhook(url)
    _webhooks.pop(url, None)
    return {"status": "removed", "url": url}


@router.get("/integrations/webhooks")
async def list_webhooks():
    """List all configured webhooks."""
    return [{"url": url, "description": desc} for url, desc in _webhooks.items()]

"""
API routers — Cameras CRUD + Analytics configuration per camera
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional, Any
from backend.storage.database import get_db, Camera, CameraStatus
from backend.core.stream_manager import stream_manager
from backend.analytics.registry import ANALYTICS_BY_KEY, get_catalog_by_category
from loguru import logger

router = APIRouter(prefix="/api/cameras", tags=["Cameras"])


class CameraCreate(BaseModel):
    name: str
    rtsp_url: str
    location: Optional[str] = None
    frame_skip: int = 3
    analytics_config: dict = {}
    zones: list = []


class CameraUpdate(BaseModel):
    name: Optional[str] = None
    rtsp_url: Optional[str] = None
    location: Optional[str] = None
    frame_skip: Optional[int] = None
    enabled: Optional[bool] = None
    analytics_config: Optional[dict] = None
    zones: Optional[list] = None


class AnalyticConfigUpdate(BaseModel):
    """Update the full config for a single analytic on a camera."""
    enabled: bool = True
    params: dict = {}   # confidence, zones, thresholds, alert_on, etc.


class CameraResponse(BaseModel):
    id: int
    name: str
    rtsp_url: str
    location: Optional[str]
    status: str
    enabled: bool
    frame_skip: int
    analytics_config: dict
    zones: list

    class Config:
        from_attributes = True


def _start_pipeline(cam: Camera):
    """Start analytics worker for a camera if it has any enabled analytics."""
    from backend.inference.pipeline import inference_pipeline
    cfg = cam.analytics_config or {}
    if any(cfg.values()):
        inference_pipeline.add_camera(cam.id, cfg)


def _stop_pipeline(camera_id: int):
    from backend.inference.pipeline import inference_pipeline
    inference_pipeline.remove_camera(camera_id)


@router.get("/", response_model=list[CameraResponse])
async def list_cameras(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Camera))
    return result.scalars().all()


@router.post("/", response_model=CameraResponse, status_code=201)
async def create_camera(data: CameraCreate, db: AsyncSession = Depends(get_db)):
    from backend.config.settings import settings
    result = await db.execute(select(Camera))
    count  = len(result.scalars().all())
    if count >= settings.max_cameras:
        raise HTTPException(400, f"Máximo {settings.max_cameras} cámaras permitidas")

    cam = Camera(
        name             = data.name,
        rtsp_url         = data.rtsp_url,
        location         = data.location,
        frame_skip       = data.frame_skip,
        analytics_config = data.analytics_config,
        zones            = data.zones,
    )
    db.add(cam)
    await db.commit()
    await db.refresh(cam)

    # Start RTSP stream with resolution/fps constraints
    stream_manager.add_camera(
        cam.id, cam.rtsp_url, cam.name, cam.frame_skip,
        max_width=cam.resolution_w or 0,
        target_fps=cam.fps or 0.0,
    )
    cam.status = CameraStatus.active
    await db.commit()

    # Start analytics pipeline
    _start_pipeline(cam)

    logger.info(f"Camera created: {cam.name} (id={cam.id})")
    return cam


@router.get("/{camera_id}", response_model=CameraResponse)
async def get_camera(camera_id: int, db: AsyncSession = Depends(get_db)):
    cam = await db.get(Camera, camera_id)
    if not cam:
        raise HTTPException(404, "Cámara no encontrada")
    return cam


@router.patch("/{camera_id}", response_model=CameraResponse)
async def update_camera(camera_id: int, data: CameraUpdate, db: AsyncSession = Depends(get_db)):
    cam = await db.get(Camera, camera_id)
    if not cam:
        raise HTTPException(404, "Cámara no encontrada")

    update_data = data.model_dump(exclude_unset=True)
    for key, val in update_data.items():
        setattr(cam, key, val)

    # Restart stream if connectivity or quality settings changed
    if any(k in update_data for k in ("rtsp_url", "frame_skip", "resolution_w", "resolution_h", "fps")):
        stream_manager.remove_camera(camera_id)
        if cam.enabled:
            stream_manager.add_camera(
                cam.id, cam.rtsp_url, cam.name, cam.frame_skip,
                max_width=cam.resolution_w or 0,
                target_fps=cam.fps or 0.0,
            )

    # Hot-reload analytics pipeline if config changed
    if "analytics_config" in update_data:
        from backend.inference.pipeline import inference_pipeline
        inference_pipeline.update_camera_config(camera_id, cam.analytics_config or {})

    await db.commit()
    await db.refresh(cam)
    return cam


@router.delete("/{camera_id}", status_code=204)
async def delete_camera(camera_id: int, db: AsyncSession = Depends(get_db)):
    cam = await db.get(Camera, camera_id)
    if not cam:
        raise HTTPException(404, "Cámara no encontrada")

    # Stop live services first
    stream_manager.remove_camera(camera_id)
    _stop_pipeline(camera_id)
    try:
        from backend.core.recording_manager import recording_manager
        recording_manager.remove_camera(camera_id)
    except Exception:
        pass

    # Expunge from ORM identity map so the relationship doesn't
    # try to NULL-ify events (which violates NOT NULL constraint).
    # Then delete everything via raw SQL in a single transaction.
    from sqlalchemy import text
    db.expunge(cam)
    await db.execute(text("DELETE FROM events WHERE camera_id = :cid"), {"cid": camera_id})
    await db.execute(text("DELETE FROM cameras WHERE id = :cid"), {"cid": camera_id})
    await db.commit()


@router.get("/{camera_id}/status")
async def camera_stream_status(camera_id: int):
    return stream_manager.get_status(camera_id)


# ─── Per-camera analytics configuration ──────────────────────────────────────

@router.get("/{camera_id}/analytics")
async def get_camera_analytics(camera_id: int, db: AsyncSession = Depends(get_db)):
    """
    Return the full analytics configuration for a camera,
    merged with the catalog defaults for each analytic.
    """
    cam = await db.get(Camera, camera_id)
    if not cam:
        raise HTTPException(404, "Cámara no encontrada")

    current_cfg = cam.analytics_config or {}
    result      = []

    for key, defn in ANALYTICS_BY_KEY.items():
        raw = current_cfg.get(key, False)
        if raw is True:
            # Simple toggle — expand with defaults
            params  = defn.default_config.copy()
            enabled = True
        elif isinstance(raw, dict):
            params  = {**defn.default_config, **raw}
            enabled = raw.get("enabled", True)
        else:
            params  = defn.default_config.copy()
            enabled = False

        result.append({
            "key":         key,
            "label":       defn.label,
            "description": defn.description,
            "category":    defn.category.value,
            "icon":        defn.icon,
            "phase":       defn.phase,
            "enabled":     enabled,
            "params":      params,
        })

    return result


@router.put("/{camera_id}/analytics/{analytic_key}")
async def update_analytic_config(
    camera_id: int,
    analytic_key: str,
    data: AnalyticConfigUpdate,
    db: AsyncSession = Depends(get_db),
):
    """
    Enable/disable and configure a specific analytic for a camera.
    Supports hot-reload — no restart needed.
    """
    cam = await db.get(Camera, camera_id)
    if not cam:
        raise HTTPException(404, "Cámara no encontrada")
    if analytic_key not in ANALYTICS_BY_KEY:
        raise HTTPException(400, f"Analítica desconocida: {analytic_key}")

    # Build updated config dict
    cfg = dict(cam.analytics_config or {})
    if data.enabled:
        defn = ANALYTICS_BY_KEY[analytic_key]
        merged = {**defn.default_config, **data.params, "enabled": True}
        cfg[analytic_key] = merged
    else:
        cfg[analytic_key] = False

    cam.analytics_config = cfg
    await db.commit()
    await db.refresh(cam)

    # Hot-reload inference pipeline
    from backend.inference.pipeline import inference_pipeline
    inference_pipeline.update_camera_config(camera_id, cfg)

    logger.info(f"Analytics config updated: cam{camera_id} | {analytic_key} | enabled={data.enabled}")
    return {
        "camera_id":    camera_id,
        "analytic_key": analytic_key,
        "enabled":      data.enabled,
        "params":       data.params,
    }


@router.post("/{camera_id}/analytics/{analytic_key}/test")
async def test_analytic_event(camera_id: int, analytic_key: str, db: AsyncSession = Depends(get_db)):
    """
    Manually trigger a simulated event for a specific analytic.
    Useful for testing the event pipeline (WebSocket, webhooks, cloud).
    """
    cam = await db.get(Camera, camera_id)
    if not cam:
        raise HTTPException(404, "Cámara no encontrada")

    from backend.core.event_bus import event_bus, AnalyticEvent
    from backend.inference.pipeline import SEVERITY_RULES, _get_description
    import random, time

    cfg = (cam.analytics_config or {}).get(analytic_key, {})
    if isinstance(cfg, bool):
        cfg = {}

    event = AnalyticEvent(
        camera_id     = camera_id,
        analytic_type = analytic_key,
        severity      = SEVERITY_RULES.get(analytic_key, "medium"),
        description   = f"[TEST] {_get_description(analytic_key, cfg)}",
        confidence    = round(random.uniform(0.75, 0.98), 2),
        timestamp     = time.time(),
        metadata      = {"source": "manual_test"},
    )
    await event_bus.publish(event)
    return {"status": "sent", "event": event.to_dict()}

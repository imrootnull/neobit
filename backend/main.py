"""
NeoBit Gateway — FastAPI main application.
Starts the stream manager, event bus, and all API routers.
"""
import asyncio
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from loguru import logger

from backend.config.settings import settings
from backend.storage.database import init_db, get_db, Camera
from backend.core.stream_manager import stream_manager
from backend.core.event_bus import event_bus
from backend.utils.hardware import get_system_info

from backend.api.cameras import router as cameras_router
from backend.api.stream import router as stream_router
from backend.api.events import router as events_router
from backend.api.websocket import router as ws_router
from backend.api.search import router as search_router
from backend.api.models import router as models_router
from backend.api.onvif import router as onvif_router
from backend.api.recording import router as recording_router
from backend.api.playback import router as playback_router
from backend.api.faces import router as faces_router
from backend.inference.pipeline import inference_pipeline
from backend.core.recording_manager import recording_manager


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown lifecycle."""
    logger.info("🚀 NeoBit Gateway starting...")
    os.makedirs("logs", exist_ok=True)
    os.makedirs(settings.recordings_dir, exist_ok=True)
    os.makedirs(settings.chroma_persist_dir, exist_ok=True)

    # Initialize DB (fast — must be done before serving)
    await init_db()
    logger.info("✅ Database initialized")

    # Register event DB writer
    async def _write_event_to_db(event):
        from backend.storage.database import AsyncSessionLocal, Event
        try:
            async with AsyncSessionLocal() as db:
                ev = Event(
                    camera_id     = event.camera_id,
                    analytic_type = event.analytic_type,
                    severity      = event.severity,
                    description   = event.description,
                    confidence    = event.confidence,
                    timestamp     = event.timestamp,
                    snapshot_path = event.snapshot_path,
                    recording_path= event.recording_path,
                    event_meta    = event.metadata or {},
                )
                db.add(ev)
                await db.commit()
                recording_manager.trigger(event.camera_id)
        except Exception as e:
            logger.error(f"DB event write error: {e}")

    event_bus.subscribe(_write_event_to_db)
    bus_task = asyncio.create_task(event_bus.start())

    # ── Defer heavy startup to background task ────────────────────────────────
    # Uvicorn starts serving requests immediately after `yield`.
    # Camera/YOLO/CLIP init happens in the background so the dashboard
    # loads instantly — cameras appear within a few seconds.
    async def _delayed_startup():
        await asyncio.sleep(1)   # let uvicorn fully bind and serve first
        try:
            from sqlalchemy import select
            from backend.storage.database import AsyncSessionLocal
            loop = asyncio.get_event_loop()

            # Hardware info (may do I/O)
            hw = get_system_info()
            logger.info(f"🖥️  {hw.get('processor','?')} | RAM {hw.get('ram_total_gb','?')}GB")

            inference_pipeline.init(event_bus, loop)

            async with AsyncSessionLocal() as db:
                result = await db.execute(select(Camera).where(Camera.enabled == True))
                cameras = result.scalars().all()
                for cam in cameras:
                    stream_manager.add_camera(
                        cam.id, cam.rtsp_url, cam.name, cam.frame_skip,
                        max_width=cam.resolution_w or 0,
                        target_fps=cam.fps or 0.0,
                    )
                    cfg = cam.analytics_config or {}
                    if cfg:
                        inference_pipeline.add_camera(cam.id, cfg)
                    recording_manager.add_camera(
                        cam.id,
                        lambda cid=cam.id: stream_manager.get_annotated_frame(cid)
                    )
                logger.info(f"✅ Restored {len(cameras)} cameras")
        except Exception as e:
            logger.error(f"Startup error: {e}")

    startup_task = asyncio.create_task(_delayed_startup())

    # Start CLIP indexer (already has 20s internal delay)
    from backend.semantic.search_engine import clip_indexer
    clip_task = asyncio.create_task(clip_indexer.start())

    logger.info(f"✅ NeoBit Gateway ready — http://{settings.api_host}:{settings.api_port}")

    yield

    # ── Shutdown ─────────────────────────────────────────────────────────────
    logger.info("🛑 NeoBit Gateway shutting down...")
    event_bus.stop()
    clip_indexer.stop()
    inference_pipeline.stop_all()
    stream_manager.stop_all()
    startup_task.cancel()
    bus_task.cancel()
    clip_task.cancel()
    logger.info("Goodbye")



# ─── App ──────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="NeoBit Gateway API",
    description="AI Analytics Gateway for Surveillance Cameras",
    version=settings.app_version,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    lifespan=lifespan,
)

# CORS — allow local dashboard + cloud platform
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # Tighten in production with specific VPS domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Routers ─────────────────────────────────────────────────────────────────

app.include_router(cameras_router)
app.include_router(stream_router)
app.include_router(events_router)
app.include_router(ws_router)
app.include_router(search_router)
app.include_router(models_router)
app.include_router(onvif_router)
app.include_router(recording_router)
app.include_router(playback_router)
app.include_router(faces_router)


# ─── System Info ─────────────────────────────────────────────────────────────

@app.get("/api/system", tags=["System"])
async def system_info():
    """Gateway system info — hardware, version, stream count."""
    return {
        "app": settings.app_name,
        "version": settings.app_version,
        "hardware": get_system_info(),
        "streams": stream_manager.get_all_status(),
        "inference_backend": settings.inference_backend,
    }


@app.get("/api/health", tags=["System"])
async def health():
    return {"status": "ok", "service": "neobit-gateway"}


# ─── Serve React Dashboard (local access) ────────────────────────────────────

# Project root is one level above backend/
PROJECT_ROOT   = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DASHBOARD_DIST = os.path.join(PROJECT_ROOT, "dashboard", "dist")

if os.path.exists(DASHBOARD_DIST):
    app.mount("/assets", StaticFiles(directory=f"{DASHBOARD_DIST}/assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_dashboard(full_path: str):
        index = os.path.join(DASHBOARD_DIST, "index.html")
        return FileResponse(index)

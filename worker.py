#!/usr/bin/env python3
"""
NeoBit Analytics Worker — runs YOLO/InsightFace/PPE in an isolated process.

Separated from uvicorn so inference never holds the HTTP server's GIL.
Reads frames from stream_manager (shares RTSP connections with main process
via the same SQLite-backed camera registry).

Usage: python3 worker.py   (run alongside python3 run.py)
"""
import os, asyncio, time

# ROCm: gfx1200 (RDNA 4 / RX 9060 XT) requires this override so ROCm
# uses the correct kernel ISA. Without it torch.cuda.is_available() = False.
os.environ["HSA_OVERRIDE_GFX_VERSION"] = "12.0.0"
os.environ["OMP_NUM_THREADS"]          = "4"
os.environ["MKL_NUM_THREADS"]          = "4"
os.environ["OPENBLAS_NUM_THREADS"]     = "4"
os.environ["NUMEXPR_NUM_THREADS"]      = "4"
os.environ["TOKENIZERS_PARALLELISM"]   = "false"

import torch, cv2
torch.set_num_threads(4)
cv2.setNumThreads(2)

# Confirm GPU
if torch.cuda.is_available():
    print(f"[worker] GPU: {torch.cuda.get_device_name(0)} ✅")
else:
    print("[worker] GPU not available — running on CPU")

from loguru import logger


async def main():
    from backend.storage.database import init_db, Camera, AsyncSessionLocal, Event as EvModel
    from backend.core.stream_manager import stream_manager
    from backend.core.event_bus import event_bus
    from backend.inference.pipeline import inference_pipeline
    from backend.core.recording_manager import recording_manager
    from sqlalchemy import select

    await init_db()
    loop = asyncio.get_event_loop()
    inference_pipeline.init(event_bus, loop)

    # Write events to DB
    async def _write_event(ev):
        try:
            async with AsyncSessionLocal() as db:
                from backend.storage.database import Event
                row = Event(
                    camera_id=ev.camera_id,
                    analytic_type=ev.analytic_type,
                    severity=ev.severity,
                    description=ev.description,
                    confidence=ev.confidence,
                    timestamp=ev.timestamp,
                    snapshot_path=ev.snapshot_path,
                    recording_path=ev.recording_path,
                    event_meta=ev.metadata or {},
                )
                db.add(row); await db.commit()
                recording_manager.trigger(ev.camera_id)
        except Exception as e:
            logger.error(f"Event write error: {e}")

    event_bus.subscribe(_write_event)
    asyncio.create_task(event_bus.start())

    # Restore cameras
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
            cam.id, lambda cid=cam.id: stream_manager.get_annotated_frame(cid)
        )

    logger.info(f"✅ Analytics worker running — {len(cameras)} cameras")

    # Run CLIP indexer here (uvicorn skips it in HTTP-only mode)
    from backend.semantic.search_engine import clip_indexer
    asyncio.create_task(clip_indexer.start())

    # Keep alive
    while True:
        await asyncio.sleep(10)


if __name__ == "__main__":
    asyncio.run(main())

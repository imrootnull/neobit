#!/usr/bin/env python3
"""
NeoBit Analytics Worker — YOLO/InsightFace/PPE en proceso separado (GPU).

Comparte frames anotados con uvicorn via shared memory (frame_bridge).
El snapshot endpoint de uvicorn lee los frames anotados desde shared memory,
mostrando los overlays de detección en tiempo real.
"""
import os, asyncio, time

os.environ["HSA_OVERRIDE_GFX_VERSION"] = "12.0.0"  # RDNA 4 gfx1200
os.environ["ROCR_VISIBLE_DEVICES"]     = "0"        # ROCm: use GPU 0
os.environ["OMP_NUM_THREADS"]          = "4"
os.environ["MKL_NUM_THREADS"]          = "4"
os.environ["OPENBLAS_NUM_THREADS"]     = "4"
os.environ["NUMEXPR_NUM_THREADS"]      = "4"
os.environ["TOKENIZERS_PARALLELISM"]   = "false"
# CUDA_VISIBLE_DEVICES was set by CUDA toolkit install and confuses ROCm torch
os.environ.pop("CUDA_VISIBLE_DEVICES", None)

import torch, cv2
torch.set_num_threads(4)
cv2.setNumThreads(2)

if torch.cuda.is_available():
    print(f"[worker] GPU: {torch.cuda.get_device_name(0)} ✅")
else:
    print("[worker] GPU not available — running on CPU")

from loguru import logger


async def main():
    from backend.storage.database import init_db, Camera, AsyncSessionLocal, Event
    from backend.core.stream_manager import stream_manager
    from backend.core.event_bus import event_bus
    from backend.inference.pipeline import inference_pipeline
    from backend.core.recording_manager import recording_manager
    from backend.core.frame_bridge import SharedFrame
    from sqlalchemy import select

    await init_db()
    loop = asyncio.get_event_loop()
    inference_pipeline.init(event_bus, loop)

    # Write events to DB
    async def _write_event(ev):
        try:
            async with AsyncSessionLocal() as db:
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

    # Patch set_annotated_frame to write JPEG to /dev/shm for uvicorn to read
    # Uses RAM disk (/dev/shm) — same speed as shared memory, zero IPC risk
    import cv2 as _cv2
    _orig_set = stream_manager.__class__.set_annotated_frame

    def _patched_set(self, camera_id: int, frame):
        _orig_set(self, camera_id, frame)
        if frame is not None:
            try:
                path = f"/dev/shm/neobit_ann_{camera_id}.jpg"
                ret, buf = _cv2.imencode(".jpg", frame, [_cv2.IMWRITE_JPEG_QUALITY, 80])
                if ret:
                    tmp = path + ".tmp"
                    with open(tmp, "wb") as f:
                        f.write(buf.tobytes())
                    import os as _os
                    _os.replace(tmp, path)  # atomic rename — no torn reads
            except Exception:
                pass

    stream_manager.__class__.set_annotated_frame = _patched_set
    logger.info("🔗 Annotated frame bridge: worker → uvicorn via /dev/shm JPEG")

    # Register cameras with stream_manager and inference pipeline
    for cam in cameras:
        stream_manager.add_camera(
            cam.id, cam.rtsp_url, cam.name, cam.frame_skip,
            max_width=cam.resolution_w or 0,
            target_fps=cam.fps or 10.0,
        )
        cfg = cam.analytics_config or {}
        if cfg:
            inference_pipeline.add_camera(cam.id, cfg)
        recording_manager.add_camera(
            cam.id, lambda cid=cam.id: stream_manager.get_annotated_frame(cid)
        )

    logger.info(f"✅ Analytics worker running — {len(cameras)} cameras")


    # CLIP indexer (uvicorn skips it in HTTP-only mode)
    from backend.semantic.search_engine import clip_indexer
    asyncio.create_task(clip_indexer.start())

    # Keep alive
    while True:
        await asyncio.sleep(10)


if __name__ == "__main__":
    asyncio.run(main())

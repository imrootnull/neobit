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

    # Shared memory slots — one per camera for annotated frames
    # uvicorn reads from these to serve /snapshot with overlays
    shm_slots: dict[int, SharedFrame] = {}

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
        # Create shared memory slot for this camera
        try:
            shm_slots[cam.id] = SharedFrame(f"nb_ann_{cam.id}", create=True)
            logger.info(f"📡 Shared memory slot created for camera {cam.id}")
        except Exception as e:
            logger.warning(f"Shared memory error cam {cam.id}: {e}")

    # Patch set_annotated_frame to also write to shared memory
    # This runs every time pipeline produces an annotated frame
    _orig_set = stream_manager.__class__.set_annotated_frame

    def _patched_set(self, camera_id: int, frame):
        _orig_set(self, camera_id, frame)
        slot = shm_slots.get(camera_id)
        if slot is not None and frame is not None:
            try:
                slot.write(frame)
            except Exception:
                pass

    stream_manager.__class__.set_annotated_frame = _patched_set
    logger.info("🔗 Annotated frame bridge: worker → uvicorn via shared memory")

    logger.info(f"✅ Analytics worker running — {len(cameras)} cameras")

    # CLIP indexer (uvicorn skips it in HTTP-only mode)
    from backend.semantic.search_engine import clip_indexer
    asyncio.create_task(clip_indexer.start())

    # Keep alive
    while True:
        await asyncio.sleep(10)


if __name__ == "__main__":
    asyncio.run(main())

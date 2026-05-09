"""
Inference subprocess entry point.

Runs YOLO / InsightFace / PPE analytics completely isolated from uvicorn.
Shares frames with the HTTP server via FrameBridge (shared memory).
Events are sent back via a multiprocessing.Queue.
"""
import os, time, asyncio
import numpy as np

os.environ["OMP_NUM_THREADS"]      = "4"
os.environ["MKL_NUM_THREADS"]      = "4"
os.environ["OPENBLAS_NUM_THREADS"] = "4"


def run(camera_configs: list[dict], event_queue, shm_names: dict):
    """
    camera_configs: list of {id, rtsp_url, name, frame_skip, fps, analytics_config}
    event_queue:    multiprocessing.Queue to push events to uvicorn process
    shm_names:      dict {camera_id: {"raw": name, "ann": name}} for shared mem
    """
    import torch, cv2
    torch.set_num_threads(4)
    cv2.setNumThreads(2)

    from backend.core.frame_bridge import SharedFrame
    from backend.core.stream_manager import stream_manager
    from backend.core.event_bus import event_bus
    from backend.inference.pipeline import inference_pipeline

    # Open shared memory (created by main process)
    raw_frames = {cfg["id"]: SharedFrame(shm_names[cfg["id"]]["raw"], create=False)
                  for cfg in camera_configs}
    ann_frames = {cfg["id"]: SharedFrame(shm_names[cfg["id"]]["ann"], create=False)
                  for cfg in camera_configs}

    # Wire event bus to push events to queue
    async def _on_event(ev):
        try:
            event_queue.put_nowait({
                "camera_id":     ev.camera_id,
                "analytic_type": ev.analytic_type,
                "severity":      ev.severity,
                "description":   ev.description,
                "confidence":    ev.confidence,
                "timestamp":     ev.timestamp.isoformat() if ev.timestamp else None,
                "snapshot_path": ev.snapshot_path,
                "recording_path":ev.recording_path,
                "metadata":      ev.metadata or {},
            })
        except Exception:
            pass

    async def _start():
        loop = asyncio.get_event_loop()
        inference_pipeline.init(event_bus, loop)
        event_bus.subscribe(_on_event)
        asyncio.create_task(event_bus.start())

        # Register cameras in pipeline (analytics only — no RTSP here)
        for cfg in camera_configs:
            cid = cfg["id"]
            if cfg.get("analytics_config"):
                inference_pipeline.add_camera(cid, cfg["analytics_config"])

        TARGET = 0.10  # 10fps inference

        while True:
            for cid in list(raw_frames.keys()):
                t0 = time.monotonic()
                frame, fid = raw_frames[cid].read()
                if frame is None:
                    continue

                # Run inference (has its own GIL — won't block uvicorn)
                from backend.core.stream_manager import stream_manager as sm
                # Inject frame so pipeline can process it
                sm._inject_frame(cid, frame)
                # Retrieve annotated result
                ann = sm.get_annotated_frame(cid)
                if ann is not None:
                    ann_frames[cid].write(ann)

                elapsed = time.monotonic() - t0
                await asyncio.sleep(max(TARGET - elapsed, 0.005))

    asyncio.run(_start())

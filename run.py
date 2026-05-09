#!/usr/bin/env python3
"""
NeoBit Gateway — Entry point

Architecture: Two separate OS processes to avoid GIL contention.

  Process 1 (main): uvicorn HTTP server + stream reader threads
  Process 2 (inference): YOLO/InsightFace/CLIP in isolated process

The inference process communicates back via shared memory (mmap)
for annotated frames and a multiprocessing Queue for events.

SIMPLIFIED VERSION: runs uvicorn with --workers 1, but moves all
blocking torch/YOLO calls to ProcessPoolExecutor so they never
hold the GIL in the uvicorn process.
"""
import os
import sys
import multiprocessing as mp

# ── Critical: set torch thread limits BEFORE any torch import ────────────────
os.environ["OMP_NUM_THREADS"] = "2"
os.environ["MKL_NUM_THREADS"] = "2"
os.environ["OPENBLAS_NUM_THREADS"] = "2"
os.environ["NUMEXPR_NUM_THREADS"] = "2"

import torch
torch.set_num_threads(2)
torch.set_num_interop_threads(1)

import cv2
cv2.setNumThreads(2)


def run_server():
    """Run uvicorn HTTP server in the main process."""
    import uvicorn
    from backend.config.settings import settings
    uvicorn.run(
        "backend.main:app",
        host      = settings.api_host,
        port      = settings.api_port,
        reload    = False,
        log_level = settings.log_level.lower(),
        loop      = "uvloop",
        http      = "h11",
        timeout_keep_alive = 5,
        workers   = 1,
    )


if __name__ == "__main__":
    mp.set_start_method("fork", force=True)
    print(f"[NeoBit] Starting — torch threads: {torch.get_num_threads()} "
          f"cv2 threads: {cv2.getNumThreads()}")
    run_server()

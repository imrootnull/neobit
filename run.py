#!/usr/bin/env python3
"""
NeoBit Gateway — Entry point
"""
import os, sys

os.environ["OMP_NUM_THREADS"]        = "1"
os.environ["MKL_NUM_THREADS"]        = "1"
os.environ["OPENBLAS_NUM_THREADS"]   = "1"
os.environ["NUMEXPR_NUM_THREADS"]    = "1"
os.environ["TOKENIZERS_PARALLELISM"] = "false"

try:
    import torch
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
except ImportError:
    pass

try:
    import cv2
    cv2.setNumThreads(1)
except ImportError:
    pass

import uvicorn
from backend.config.settings import settings

if __name__ == "__main__":
    # workers=1: the inference thread holds the GIL which starves uvicorn.
    # Solution: run the inference pipeline in a separate process (neobit-worker)
    # and keep uvicorn single-worker but preloaded.
    # 
    # The start.sh script launches:
    #   python3 run.py          ← uvicorn (HTTP only, no analytics)
    #   python3 worker.py       ← analytics worker (YOLO, no HTTP)
    # For now: single worker with OMP=1 and 2fps inference gives acceptable UX.
    uvicorn.run(
        "backend.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=False,
        log_level=settings.log_level.lower(),
        loop="uvloop",
        http="h11",
        timeout_keep_alive=5,
    )

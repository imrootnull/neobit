#!/usr/bin/env python3
"""
NeoBit Gateway — Entry point

Uses uvicorn with uvloop. Inference runs in background daemon threads.
Thread limits are set aggressively to prevent GIL starvation of uvicorn.
"""
import os
import sys

# Must be set BEFORE any C extension import (torch, cv2, numpy)
os.environ["OMP_NUM_THREADS"]      = "1"
os.environ["MKL_NUM_THREADS"]      = "1"
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["NUMEXPR_NUM_THREADS"]  = "1"
os.environ["VECLIB_MAXIMUM_THREADS"] = "1"
os.environ["TOKENIZERS_PARALLELISM"] = "false"

# Also tell torch directly — belt and suspenders
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
    print(f"[NeoBit] HTTP server starting on {settings.api_host}:{settings.api_port}")
    uvicorn.run(
        "backend.main:app",
        host      = settings.api_host,
        port      = settings.api_port,
        reload    = False,
        log_level = settings.log_level.lower(),
        loop      = "uvloop",
        http      = "h11",
        timeout_keep_alive = 5,
    )

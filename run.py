#!/usr/bin/env python3
"""
NeoBit Gateway — HTTP server entry point (no inference).
Analytics run in worker.py (separate process, separate GIL).
"""
import os

os.environ["OMP_NUM_THREADS"]        = "1"
os.environ["MKL_NUM_THREADS"]        = "1"
os.environ["OPENBLAS_NUM_THREADS"]   = "1"
os.environ["NUMEXPR_NUM_THREADS"]    = "1"
os.environ["TOKENIZERS_PARALLELISM"] = "false"
os.environ["NEOBIT_NO_INFERENCE"]    = "1"   # always set here

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
    uvicorn.run(
        "backend.main:app",
        host             = settings.api_host,
        port             = settings.api_port,
        reload           = False,
        log_level        = settings.log_level.lower(),
        loop             = "uvloop",
        http             = "h11",
        timeout_keep_alive = 5,
    )

#!/usr/bin/env python3
"""
NeoBit Gateway — Entry point
Run: python run.py
"""
import uvicorn
from backend.config.settings import settings

if __name__ == "__main__":
    uvicorn.run(
        "backend.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.debug,
        log_level=settings.log_level.lower(),
    )

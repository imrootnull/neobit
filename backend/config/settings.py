from pydantic_settings import BaseSettings
from typing import Literal


class Settings(BaseSettings):
    # App
    app_name: str = "NeoBit"
    app_version: str = "1.0.0"
    debug: bool = True

    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    # Database
    database_url: str = "sqlite+aiosqlite:///./data/neobit.db"

    # Storage
    recordings_dir: str = "./recordings"
    models_dir: str = "./models"

    # Stream
    max_cameras: int = 8
    frame_skip_default: int = 3
    clip_sample_interval: float = 2.0

    # Inference
    inference_backend: Literal["auto", "coral", "cpu", "tensorrt"] = "auto"

    # ChromaDB
    chroma_persist_dir: str = "./data/chroma"

    # CLIP
    clip_model: str = "ViT-B/32"

    # Logging
    log_level: str = "INFO"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()

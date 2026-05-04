"""
Database models and async engine setup.
"""
from datetime import datetime
from typing import Optional
from sqlalchemy import (
    Column, Integer, String, Float, Boolean,
    DateTime, JSON, ForeignKey, Text, Enum as SAEnum
)
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import DeclarativeBase, relationship, sessionmaker
from backend.config.settings import settings
import enum


# ─── Engine ──────────────────────────────────────────────────────────────────

engine = create_async_engine(
    settings.database_url,
    echo=settings.debug,
    connect_args={"check_same_thread": False},
)

AsyncSessionLocal = sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


# ─── Base ─────────────────────────────────────────────────────────────────────

class Base(DeclarativeBase):
    pass


# ─── Enums ────────────────────────────────────────────────────────────────────

class CameraStatus(str, enum.Enum):
    active = "active"
    inactive = "inactive"
    error = "error"


class EventSeverity(str, enum.Enum):
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


# AnalyticType is open-ended — stored as plain String to support all 50+ analytics
# class AnalyticType(str, enum.Enum): ... (removed — use String column instead)


# ─── Models ───────────────────────────────────────────────────────────────────

class Camera(Base):
    __tablename__ = "cameras"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    rtsp_url = Column(String(500), nullable=False)
    location = Column(String(200), nullable=True)
    status = Column(SAEnum(CameraStatus), default=CameraStatus.inactive)
    enabled = Column(Boolean, default=True)
    frame_skip = Column(Integer, default=3)
    resolution_w = Column(Integer, default=1280)
    resolution_h = Column(Integer, default=720)
    fps = Column(Float, default=25.0)
    zones = Column(JSON, default=list)           # List of polygon zones
    analytics_config = Column(JSON, default=dict) # Per-camera analytic toggles
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    events = relationship("Event", back_populates="camera", lazy="dynamic")


class Event(Base):
    __tablename__ = "events"

    id = Column(Integer, primary_key=True, index=True)
    camera_id = Column(Integer, ForeignKey("cameras.id"), nullable=False)
    analytic_type = Column(String(100), nullable=False)  # open-ended: any analytic key
    severity = Column(SAEnum(EventSeverity), default=EventSeverity.medium)
    description = Column(Text, nullable=True)
    confidence = Column(Float, nullable=True)
    snapshot_path = Column(String(500), nullable=True)  # Path to saved frame
    recording_path = Column(String(500), nullable=True) # Path to video clip
    timestamp = Column(Float, nullable=False)           # Unix timestamp
    event_meta = Column(JSON, default=dict)               # Extra event data
    acknowledged = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    camera = relationship("Camera", back_populates="events")


class SemanticIndex(Base):
    __tablename__ = "semantic_index"

    id = Column(Integer, primary_key=True, index=True)
    camera_id = Column(Integer, ForeignKey("cameras.id"), nullable=False)
    timestamp = Column(Float, nullable=False)
    frame_path = Column(String(500), nullable=True)
    chroma_id  = Column(String(100), nullable=True)      # ChromaDB doc ID
    created_at = Column(DateTime, default=datetime.utcnow)


async def init_db():
    """Create all tables."""
    import os
    os.makedirs("data", exist_ok=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

"""
Semantic Search API — CLIP-based video search endpoints.
"""
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional
import os

router = APIRouter(prefix="/api/search", tags=["Semantic Search"])


class SearchRequest(BaseModel):
    query: str
    top_k: int = 12
    camera_id: Optional[int] = None
    timestamp_from: Optional[float] = None
    timestamp_to: Optional[float] = None


class SearchResult(BaseModel):
    camera_id: int
    timestamp: float
    score: float
    frame_path: Optional[str] = None
    chroma_id: Optional[str] = None


@router.post("/semantic")
async def semantic_search(req: SearchRequest):
    """
    Search video frames by natural language description using CLIP embeddings.
    Returns top-K matching frames with similarity scores.
    """
    try:
        from backend.semantic.search_engine import search_engine
        results = await search_engine.search(
            query=req.query,
            top_k=req.top_k,
            camera_id=req.camera_id,
            timestamp_from=req.timestamp_from,
            timestamp_to=req.timestamp_to,
        )
        return {"query": req.query, "results": results}
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Search engine unavailable: {str(e)}")


@router.get("/frame/{frame_path:path}")
async def serve_frame(frame_path: str):
    """Serve a stored frame thumbnail for search results."""
    full_path = os.path.join(".", frame_path)
    if not os.path.exists(full_path):
        raise HTTPException(status_code=404, detail="Frame not found")
    return FileResponse(full_path, media_type="image/jpeg")


@router.get("/stats")
async def index_stats():
    """Return semantic index statistics."""
    try:
        from backend.semantic.search_engine import search_engine
        return search_engine.get_stats()
    except Exception as e:
        return {"error": str(e), "indexed_frames": 0}

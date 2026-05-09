"""
Semantic Search API — CLIP + event fusion endpoints.

POST /api/search/semantic     — search by natural language
GET  /api/search/stats        — index statistics
GET  /api/search/frame/{path} — serve frame thumbnail
GET  /api/search/events       — search by analytic event type + time range
"""
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional
import os

router = APIRouter(prefix="/api/search", tags=["Semantic Search"])


class SearchRequest(BaseModel):
    query:          str
    top_k:          int   = 20
    camera_id:      Optional[int]   = None
    timestamp_from: Optional[float] = None
    timestamp_to:   Optional[float] = None
    min_score:      float = 0.15
    use_events:     bool  = True


@router.post("/semantic")
async def semantic_search(req: SearchRequest):
    """
    Search video frames by natural language (auto-translated ES→EN for CLIP).
    Fuses CLIP visual similarity with analytic event proximity for better ranking.
    """
    try:
        from backend.semantic.search_engine import search_engine
        results = await search_engine.search(
            query          = req.query,
            top_k          = req.top_k,
            camera_id      = req.camera_id,
            timestamp_from = req.timestamp_from,
            timestamp_to   = req.timestamp_to,
            min_score      = req.min_score,
            use_events     = req.use_events,
        )
        # Include translated query in response for UI transparency
        from backend.semantic.search_engine import _translate_to_english
        translated = _translate_to_english(req.query)
        return {
            "query":      req.query,
            "translated": translated if translated != req.query else None,
            "results":    results,
            "total":      len(results),
        }
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


@router.get("/events")
async def search_by_events(
    analytic_type:  Optional[str]   = Query(None, description="epp_detection, fall_detection, etc."),
    camera_id:      Optional[int]   = Query(None),
    timestamp_from: Optional[float] = Query(None),
    timestamp_to:   Optional[float] = Query(None),
    limit:          int             = Query(20, ge=1, le=100),
):
    """
    Search analytic events directly (non-CLIP).
    Useful for: 'show all PPE violations in the last hour'.
    Returns events with associated frame thumbnails when available.
    """
    try:
        import sqlite3, time
        DB_PATH = "data/neobit.db"
        conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        conn.row_factory = sqlite3.Row

        where, params = [], []
        if analytic_type:
            where.append("analytic_type = ?")
            params.append(analytic_type)
        if camera_id is not None:
            where.append("camera_id = ?")
            params.append(camera_id)
        if timestamp_from:
            where.append("timestamp >= ?")
            params.append(timestamp_from)
        if timestamp_to:
            where.append("timestamp <= ?")
            params.append(timestamp_to)

        clause = ("WHERE " + " AND ".join(where)) if where else ""
        rows = conn.execute(
            f"SELECT * FROM events {clause} ORDER BY timestamp DESC LIMIT ?",
            params + [limit],
        ).fetchall()
        conn.close()

        return {"results": [dict(r) for r in rows], "total": len(rows)}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

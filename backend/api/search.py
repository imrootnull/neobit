"""
Semantic Search API — CLIP + event fusion + clip playback.

POST /api/search/semantic        — search by natural language (CLIP + events)
GET  /api/search/stats           — index statistics
GET  /api/search/frame/{path}    — serve frame thumbnail
GET  /api/search/events          — filter analytic events by type/camera/date
GET  /api/search/clip-at         — find nearest event clip for a timestamp
"""
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse, StreamingResponse, JSONResponse
from pydantic import BaseModel
from typing import Optional
import os, sqlite3

router = APIRouter(prefix="/api/search", tags=["Semantic Search"])


class SearchRequest(BaseModel):
    query:          str
    top_k:          int   = 20
    camera_id:      Optional[int]   = None
    timestamp_from: Optional[float] = None
    timestamp_to:   Optional[float] = None
    min_score:      float = 0.0
    use_events:     bool  = True


@router.post("/semantic")
async def semantic_search(req: SearchRequest):
    """
    Search video frames by natural language.
    Auto-translates ES→EN, normalizes scores, fuses analytic events.
    Results include event_clip path for direct playback.
    """
    try:
        from backend.semantic.search_engine import search_engine, _translate_to_english
        results = await search_engine.search(
            query          = req.query,
            top_k          = req.top_k,
            camera_id      = req.camera_id,
            timestamp_from = req.timestamp_from,
            timestamp_to   = req.timestamp_to,
            min_score      = req.min_score,
            use_events     = req.use_events,
        )
        translated = _translate_to_english(req.query)
        return {
            "query":      req.query,
            "translated": translated if translated.lower() != req.query.lower() else None,
            "results":    results,
            "total":      len(results),
        }
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Search engine unavailable: {str(e)}")


@router.get("/frame/{frame_path:path}")
async def serve_frame(frame_path: str):
    """Serve a stored frame thumbnail."""
    full_path = os.path.join(".", frame_path)
    if not os.path.exists(full_path):
        raise HTTPException(status_code=404, detail="Frame not found")
    return FileResponse(full_path, media_type="image/jpeg")


@router.get("/clip-at")
async def clip_at(
    camera_id: int   = Query(..., description="Camera ID"),
    timestamp: float = Query(..., description="Unix timestamp of the frame"),
    window:    float = Query(120.0, description="Search window in seconds"),
):
    """
    Find the nearest event clip for a given camera + timestamp.
    Returns the recording_path, snapshot_path and event info.
    Used by the UI to open a video player when clicking a search result.
    """
    DB_PATH = "data/neobit.db"
    if not os.path.exists(DB_PATH):
        raise HTTPException(404, "No event database found")

    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        """SELECT id, analytic_type, description, timestamp,
                  recording_path, snapshot_path
           FROM events
           WHERE camera_id = ?
             AND timestamp BETWEEN ? AND ?
           ORDER BY ABS(timestamp - ?) LIMIT 1""",
        [camera_id, timestamp - window, timestamp + window, timestamp],
    ).fetchone()
    conn.close()

    if not row:
        raise HTTPException(404, "No event found near this timestamp")

    clip_path = row["recording_path"]
    snap_path = row["snapshot_path"]

    if not clip_path or not os.path.exists(clip_path):
        return JSONResponse({"event_id": row["id"], "clip_available": False,
                             "description": row["description"],
                             "analytic_type": row["analytic_type"]})

    return {
        "event_id":     row["id"],
        "analytic_type": row["analytic_type"],
        "description":  row["description"],
        "timestamp":    row["timestamp"],
        "clip_path":    clip_path,
        "snap_path":    snap_path,
        "clip_available": True,
    }


@router.get("/clip-stream")
async def stream_clip(path: str = Query(...)):
    """Stream an event clip MP4 with proper range headers."""
    if not os.path.exists(path):
        raise HTTPException(404, "Clip not found")

    file_size = os.path.getsize(path)

    def iter_file():
        with open(path, "rb") as f:
            while chunk := f.read(1024 * 64):
                yield chunk

    return StreamingResponse(
        iter_file(),
        media_type="video/mp4",
        headers={
            "Content-Length": str(file_size),
            "Accept-Ranges":  "bytes",
            "Cache-Control":  "no-cache",
        },
    )


@router.get("/stats")
async def index_stats():
    try:
        from backend.semantic.search_engine import search_engine
        return search_engine.get_stats()
    except Exception as e:
        return {"error": str(e), "indexed_frames": 0}


@router.get("/events")
async def search_by_events(
    analytic_type:  Optional[str]   = Query(None),
    camera_id:      Optional[int]   = Query(None),
    timestamp_from: Optional[float] = Query(None),
    timestamp_to:   Optional[float] = Query(None),
    limit:          int             = Query(30, ge=1, le=200),
):
    """Search analytic events directly (no CLIP). Returns events with clips."""
    try:
        conn = sqlite3.connect("data/neobit.db", check_same_thread=False)
        conn.row_factory = sqlite3.Row
        where, params = [], []
        if analytic_type:
            where.append("analytic_type = ?"); params.append(analytic_type)
        if camera_id is not None:
            where.append("camera_id = ?"); params.append(camera_id)
        if timestamp_from:
            where.append("timestamp >= ?"); params.append(timestamp_from)
        if timestamp_to:
            where.append("timestamp <= ?"); params.append(timestamp_to)
        clause = ("WHERE " + " AND ".join(where)) if where else ""
        rows = conn.execute(
            f"SELECT * FROM events {clause} ORDER BY timestamp DESC LIMIT ?",
            params + [limit],
        ).fetchall()
        conn.close()
        results = []
        for r in rows:
            d = dict(r)
            d["clip_available"] = bool(d.get("recording_path") and os.path.exists(d["recording_path"] or ""))
            results.append(d)
        return {"results": results, "total": len(results)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

"""
API — Face Library endpoints.

GET    /api/faces/              — list faces (filterable by status, camera_id, page)
GET    /api/faces/stats         — counts per status
GET    /api/faces/{id}/image    — face crop JPEG
GET    /api/faces/{id}/snapshot — full-frame JPEG at capture moment
GET    /api/faces/{id}/clip     — MP4 clip (3s pre + 5s post)
PATCH  /api/faces/{id}          — update status and/or label
DELETE /api/faces/{id}          — delete record + all files
POST   /api/faces/refresh-gallery — rebuild InsightFace embedding gallery
"""
import os
from fastapi import APIRouter, HTTPException, Query, BackgroundTasks
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from backend.core.face_library import FaceLibrary

router = APIRouter(prefix="/api/faces", tags=["faces"])

VALID_STATUSES = {"pending", "validated", "discarded"}


class FacePatch(BaseModel):
    status: str | None = None
    label:  str | None = None


# ── Stats ─────────────────────────────────────────────────────────────────────

@router.get("/stats")
async def face_stats():
    return FaceLibrary.get().stats()


# ── List ──────────────────────────────────────────────────────────────────────

@router.get("/")
async def list_faces(
    status:    str | None = Query(None, description="pending | validated | discarded"),
    camera_id: int | None = Query(None),
    page:      int        = Query(1, ge=1),
    limit:     int        = Query(50, ge=1, le=200),
):
    if status and status not in VALID_STATUSES:
        raise HTTPException(400, f"status must be one of {VALID_STATUSES}")
    rows, total = FaceLibrary.get().list_faces(status, camera_id, page, limit)
    return {"items": rows, "total": total, "page": page, "limit": limit}


# ── Media ─────────────────────────────────────────────────────────────────────

@router.get("/{face_id}/image")
async def face_image(face_id: int):
    """Serve the cropped face JPEG."""
    face = FaceLibrary.get().get_face(face_id)
    if not face:
        raise HTTPException(404, "Face not found")
    path = face["image_path"]
    if not path or not os.path.exists(path):
        raise HTTPException(404, "Face image not found")
    return FileResponse(path, media_type="image/jpeg")


@router.get("/{face_id}/snapshot")
async def face_snapshot(face_id: int):
    """Serve the full-frame JPEG at the moment of capture (with bbox overlay)."""
    face = FaceLibrary.get().get_face(face_id)
    if not face:
        raise HTTPException(404, "Face not found")
    path = face.get("snapshot_path")
    if not path or not os.path.exists(path):
        raise HTTPException(404, "Snapshot not available")
    return FileResponse(path, media_type="image/jpeg")


@router.get("/{face_id}/clip")
async def face_clip(face_id: int):
    """
    Serve the MP4 clip associated with this face capture.
    Returns 202 Accepted if the clip is still being recorded.
    """
    face = FaceLibrary.get().get_face(face_id)
    if not face:
        raise HTTPException(404, "Face not found")
    clip_path  = face.get("clip_path")
    clip_ready = face.get("clip_ready", 0)

    if not clip_path:
        raise HTTPException(404, "No clip associated with this capture")

    if not clip_ready or not os.path.exists(clip_path):
        return JSONResponse(
            status_code=202,
            content={"status": "recording", "message": "Clip still being recorded, retry in a few seconds"},
        )

    return FileResponse(
        clip_path,
        media_type="video/mp4",
        filename=os.path.basename(clip_path),
    )


# ── CRUD ──────────────────────────────────────────────────────────────────────

@router.patch("/{face_id}")
async def update_face(face_id: int, body: FacePatch):
    if body.status and body.status not in VALID_STATUSES:
        raise HTTPException(400, f"status must be one of {VALID_STATUSES}")
    ok = FaceLibrary.get().update_face(face_id, body.status or "pending", body.label)
    if not ok:
        raise HTTPException(404, "Face not found")
    return {"ok": True}


@router.delete("/{face_id}")
async def delete_face(face_id: int):
    ok = FaceLibrary.get().delete_face(face_id)
    if not ok:
        raise HTTPException(404, "Face not found")
    return {"ok": True}


# ── Gallery ───────────────────────────────────────────────────────────────────

@router.post("/refresh-gallery")
async def refresh_gallery(background_tasks: BackgroundTasks):
    """
    Rebuild the InsightFace embedding gallery from all validated+labeled faces.
    Runs in background (1-5s). Call after validating/labeling faces in the UI.
    """
    def _do_refresh():
        try:
            from backend.inference.pipeline import inference_pipeline
            inference_pipeline.refresh_face_gallery()
        except Exception as e:
            import logging
            logging.warning(f"Gallery refresh error: {e}")

    background_tasks.add_task(_do_refresh)
    return {"ok": True, "message": "Gallery refresh scheduled"}

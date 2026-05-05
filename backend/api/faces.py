"""
API — Face Library endpoints.

GET    /api/faces/           — list faces (filterable by status, camera_id, page)
GET    /api/faces/stats      — counts per status
GET    /api/faces/{id}/image — serve face image (JPEG)
PATCH  /api/faces/{id}       — update status and/or label
DELETE /api/faces/{id}       — delete record + image file
POST   /api/faces/refresh-gallery — rebuild InsightFace embedding gallery
"""
import os
from fastapi import APIRouter, HTTPException, Query, BackgroundTasks
from fastapi.responses import FileResponse
from pydantic import BaseModel
from backend.core.face_library import FaceLibrary

router = APIRouter(prefix="/api/faces", tags=["faces"])

VALID_STATUSES = {"pending", "validated", "discarded"}


class FacePatch(BaseModel):
    status: str | None = None
    label:  str | None = None


@router.get("/stats")
async def face_stats():
    return FaceLibrary.get().stats()


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


@router.get("/{face_id}/image")
async def face_image(face_id: int):
    face = FaceLibrary.get().get_face(face_id)
    if not face:
        raise HTTPException(404, "Face not found")
    path = face["image_path"]
    if not os.path.exists(path):
        raise HTTPException(404, "Image file not found")
    return FileResponse(path, media_type="image/jpeg")


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


@router.post("/refresh-gallery")
async def refresh_gallery(background_tasks: BackgroundTasks):
    """
    Rebuild the InsightFace embedding gallery from all validated+labeled faces.
    Runs in background (1-5s depending on gallery size).
    Call this after validating/labeling faces in the UI.
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



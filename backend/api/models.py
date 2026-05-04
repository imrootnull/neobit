"""
Custom Model Registry — manages per-client trained models.
Clients can upload YOLOv8 custom models for any detection need
(uniforms, specific objects, custom behaviors, etc.)
"""
import os
import json
import shutil
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Optional
from loguru import logger
from fastapi import APIRouter, UploadFile, File, HTTPException, Form
from fastapi.responses import JSONResponse
from pydantic import BaseModel

MODELS_DIR = Path("models")
CUSTOM_DIR = MODELS_DIR / "custom"
REGISTRY_FILE = CUSTOM_DIR / "registry.json"

router = APIRouter(prefix="/api/models", tags=["Custom Models"])


@dataclass
class CustomModel:
    id: str
    name: str
    client: str
    description: str
    classes: list[str]
    file_path: str
    framework: str          # yolov8 | tflite | onnx
    analytics_key: str      # Which analytic type uses this
    created_at: str
    size_mb: float


def _load_registry() -> dict[str, dict]:
    if REGISTRY_FILE.exists():
        return json.loads(REGISTRY_FILE.read_text())
    return {}


def _save_registry(reg: dict):
    CUSTOM_DIR.mkdir(parents=True, exist_ok=True)
    REGISTRY_FILE.write_text(json.dumps(reg, indent=2))


@router.get("/")
async def list_models():
    """List all registered custom models."""
    return list(_load_registry().values())


@router.get("/catalog")
async def analytics_catalog():
    """Return the full analytics catalog grouped by category."""
    from backend.analytics.registry import get_catalog_by_category
    return get_catalog_by_category()


@router.post("/upload")
async def upload_model(
    name: str = Form(...),
    client: str = Form(...),
    description: str = Form(""),
    classes: str = Form(""),       # comma-separated class names
    analytics_key: str = Form("custom_detection"),
    file: UploadFile = File(...),
):
    """
    Upload a custom trained model (YOLOv8 .pt, TFLite .tflite, or ONNX .onnx).
    Each client can have multiple models for different use cases.
    """
    CUSTOM_DIR.mkdir(parents=True, exist_ok=True)

    # Validate file extension
    suffix = Path(file.filename).suffix.lower()
    framework_map = {".pt": "yolov8", ".tflite": "tflite", ".onnx": "onnx"}
    if suffix not in framework_map:
        raise HTTPException(status_code=400, detail=f"Unsupported model format: {suffix}. Use .pt, .tflite, or .onnx")

    import time
    model_id = f"{client.lower().replace(' ', '_')}_{int(time.time())}"
    dest_path = CUSTOM_DIR / f"{model_id}{suffix}"

    # Save file
    with open(dest_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    size_mb = round(dest_path.stat().st_size / 1e6, 2)
    class_list = [c.strip() for c in classes.split(",") if c.strip()] if classes else []

    model = CustomModel(
        id=model_id,
        name=name,
        client=client,
        description=description,
        classes=class_list,
        file_path=str(dest_path),
        framework=framework_map[suffix],
        analytics_key=analytics_key,
        created_at=time.strftime("%Y-%m-%d %H:%M:%S"),
        size_mb=size_mb,
    )

    reg = _load_registry()
    reg[model_id] = asdict(model)
    _save_registry(reg)

    logger.info(f"✅ Custom model registered: {name} (client: {client}, {size_mb}MB)")
    return {"status": "registered", "model": asdict(model)}


@router.get("/{model_id}")
async def get_model(model_id: str):
    reg = _load_registry()
    if model_id not in reg:
        raise HTTPException(status_code=404, detail="Model not found")
    return reg[model_id]


@router.delete("/{model_id}")
async def delete_model(model_id: str):
    reg = _load_registry()
    if model_id not in reg:
        raise HTTPException(status_code=404, detail="Model not found")
    model = reg.pop(model_id)
    # Delete file
    fpath = Path(model["file_path"])
    if fpath.exists():
        fpath.unlink()
    _save_registry(reg)
    logger.info(f"🗑️  Custom model deleted: {model_id}")
    return {"status": "deleted", "model_id": model_id}


@router.post("/{model_id}/test")
async def test_model(model_id: str, camera_id: int):
    """
    Run a quick inference test of a custom model on a specific camera's current frame.
    Returns detected objects and confidence scores.
    """
    reg = _load_registry()
    if model_id not in reg:
        raise HTTPException(status_code=404, detail="Model not found")

    from backend.core.stream_manager import stream_manager
    frame = stream_manager.get_latest_frame(camera_id)
    if frame is None:
        raise HTTPException(status_code=503, detail=f"Camera {camera_id} has no frame")

    model_info = reg[model_id]
    results = []

    try:
        if model_info["framework"] == "yolov8":
            from ultralytics import YOLO
            import tempfile, cv2
            model = YOLO(model_info["file_path"])
            preds = model(frame, verbose=False)
            for pred in preds:
                for box in pred.boxes:
                    cls_id = int(box.cls[0])
                    label = pred.names.get(cls_id, str(cls_id))
                    conf = float(box.conf[0])
                    results.append({"class": label, "confidence": round(conf, 3)})
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Inference failed: {str(e)}")

    return {"model_id": model_id, "camera_id": camera_id, "detections": results}

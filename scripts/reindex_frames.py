#!/usr/bin/env python3
"""
Re-index existing CLIP frames with YOLO detection metadata.

Runs YOLO on every frame thumbnail in data/frames/ and updates
the ChromaDB metadata WITHOUT re-computing CLIP embeddings (fast).

After this, the semantic search will be able to boost frames
that contain the objects mentioned in the query.

Usage: python3 scripts/reindex_frames.py
"""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cv2
import chromadb
import numpy as np
from pathlib import Path
from loguru import logger

# ── Config ────────────────────────────────────────────────────────────────────
FRAMES_DIR    = Path("data/frames")
CHROMA_PATH   = "data/chroma"
COLLECTION    = "neobit_frames"
YOLO_MODEL    = "yolov8n.pt"
CONF          = 0.25
BATCH_SIZE    = 50     # update ChromaDB in batches

# YOLO class → semantic tag mapping
CLASS_TAGS = {
    "person":         "person",
    "helmet":         "helmet",
    "safety helmet":  "helmet",
    "hard hat":       "helmet",
    "vest":           "vest",
    "safety vest":    "vest",
    "hi-vis":         "vest",
    "boot":           "boot",
    "safety boot":    "boot",
    "glove":          "glove",
    "glasses":        "glasses",
    "car":            "vehicle",
    "truck":          "vehicle",
    "bus":            "vehicle",
    "motorcycle":     "vehicle",
    "bicycle":        "vehicle",
    "forklift":       "vehicle",
    "fire":           "fire",
    "smoke":          "fire",
    "dog":            "animal",
    "cat":            "animal",
}

PPE_ITEMS  = {"helmet", "vest", "boot", "glove", "glasses"}
REQUIRED   = {"helmet", "vest", "boot"}   # items whose absence flags ppe_violation


def run_yolo(model, frame_path: str) -> tuple[list[str], list[str], int]:
    """Run YOLO on a frame. Returns (detections, ppe_tags, person_count)."""
    img = cv2.imread(frame_path)
    if img is None:
        return [], [], 0

    results = model(img, imgsz=320, verbose=False, conf=CONF)
    names   = model.names

    found_classes: set[str] = set()
    person_count = 0

    for box in results[0].boxes:
        cls_name = names[int(box.cls)].lower()
        found_classes.add(cls_name)
        if cls_name == "person":
            person_count += 1

    detections: list[str] = []
    for cls in found_classes:
        tag = CLASS_TAGS.get(cls)
        if tag:
            detections.append(tag)

    # PPE missing tags (only meaningful if a person is present)
    ppe_tags: list[str] = []
    if person_count > 0:
        found_ppe = {t for t in detections if t in PPE_ITEMS}
        for item in REQUIRED:
            if item not in found_ppe:
                ppe_tags.append(f"no_{item}")
        if ppe_tags:
            ppe_tags.append("ppe_violation")

    return list(set(detections)), ppe_tags, person_count


def main():
    logger.info("Re-index script starting...")

    # ── Load YOLO ─────────────────────────────────────────────────────────────
    from ultralytics import YOLO
    from backend.utils.hardware import get_device
    device = get_device()
    logger.info(f"Loading YOLO ({YOLO_MODEL}) on {device}...")
    model = YOLO(YOLO_MODEL)
    model.to(device)
    # warmup
    model(np.zeros((320, 320, 3), dtype=np.uint8), imgsz=320, verbose=False)
    logger.info("YOLO ready")

    # ── Connect ChromaDB ──────────────────────────────────────────────────────
    client     = chromadb.PersistentClient(path=CHROMA_PATH)
    collection = client.get_or_create_collection(
        name     = COLLECTION,
        metadata = {"hnsw:space": "cosine"},
    )
    total = collection.count()
    logger.info(f"ChromaDB: {total} frames to process")

    if total == 0:
        logger.warning("No frames in ChromaDB, nothing to do.")
        return

    # ── Process in batches ────────────────────────────────────────────────────
    offset    = 0
    processed = 0
    skipped   = 0
    updated   = 0
    t_start   = time.time()

    while offset < total:
        # Fetch batch of existing docs (no embeddings needed)
        batch = collection.get(
            limit   = BATCH_SIZE,
            offset  = offset,
            include = ["metadatas"],
        )
        ids      = batch["ids"]
        metas    = batch["metadatas"]
        offset  += len(ids)

        if not ids:
            break

        new_ids:   list[str] = []
        new_metas: list[dict] = []

        for doc_id, meta in zip(ids, metas):
            frame_path = meta.get("frame_path", "")
            if not frame_path or not os.path.exists(frame_path):
                skipped += 1
                continue

            detections, ppe_tags, person_count = run_yolo(model, frame_path)

            new_meta = dict(meta)
            new_meta["detections"]   = ",".join(detections)
            new_meta["ppe_tags"]     = ",".join(ppe_tags)
            new_meta["person_count"] = person_count

            new_ids.append(doc_id)
            new_metas.append(new_meta)
            processed += 1

        if new_ids:
            collection.update(ids=new_ids, metadatas=new_metas)
            updated += len(new_ids)

        elapsed  = time.time() - t_start
        rate     = processed / elapsed if elapsed > 0 else 0
        eta      = (total - offset) / rate if rate > 0 else 0
        pct      = (offset / total) * 100
        print(f"\r[{pct:5.1f}%] {processed}/{total} frames | {rate:.0f} fps | ETA {eta:.0f}s", end="", flush=True)

    print()
    elapsed = time.time() - t_start
    logger.success(
        f"Done! {updated} frames updated, {skipped} skipped "
        f"in {elapsed:.1f}s ({processed/elapsed:.0f} fps)"
    )


if __name__ == "__main__":
    main()

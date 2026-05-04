"""
Semantic Search Engine — CLIP + ChromaDB.
Indexes video frames as embeddings and searches by natural language.
"""
import asyncio
import time
import os
from pathlib import Path
from typing import Optional
from loguru import logger


class SearchEngine:
    """
    CLIP-based semantic video search.
    - Indexes frames from all cameras periodically
    - Stores embeddings in ChromaDB (local persistent)
    - Queries by natural language text
    """

    def __init__(self):
        self._model = None
        self._preprocess = None
        self._chroma = None
        self._collection = None
        self._ready = False
        self._indexed_count = 0

    def _load(self):
        """Lazy-load CLIP and ChromaDB (heavy imports)."""
        if self._ready:
            return

        import clip
        import torch
        import chromadb

        from backend.config.settings import settings

        logger.info("🔍 Loading CLIP model...")
        self._device = "cuda" if torch.cuda.is_available() else "cpu"
        self._model, self._preprocess = clip.load(settings.clip_model, device=self._device)
        self._model.eval()
        logger.info(f"✅ CLIP loaded ({settings.clip_model}) on {self._device}")

        # ChromaDB persistent client
        self._chroma = chromadb.PersistentClient(path=settings.chroma_persist_dir)
        self._collection = self._chroma.get_or_create_collection(
            name="neobit_frames",
            metadata={"hnsw:space": "cosine"},
        )
        self._indexed_count = self._collection.count()
        logger.info(f"✅ ChromaDB ready — {self._indexed_count} frames indexed")
        self._ready = True

    def embed_text(self, text: str) -> list[float]:
        import clip
        import torch
        self._load()
        with torch.no_grad():
            tokens = clip.tokenize([text]).to(self._device)
            embedding = self._model.encode_text(tokens)
            embedding = embedding / embedding.norm(dim=-1, keepdim=True)
        return embedding.cpu().numpy()[0].tolist()

    def embed_frame(self, frame) -> list[float]:
        """Embed an OpenCV BGR frame using CLIP image encoder."""
        import torch
        from PIL import Image
        import numpy as np
        self._load()
        # Convert BGR → RGB PIL
        rgb = frame[:, :, ::-1]
        pil_img = Image.fromarray(rgb.astype('uint8'))
        tensor = self._preprocess(pil_img).unsqueeze(0).to(self._device)
        with torch.no_grad():
            embedding = self._model.encode_image(tensor)
            embedding = embedding / embedding.norm(dim=-1, keepdim=True)
        return embedding.cpu().numpy()[0].tolist()

    def index_frame(self, camera_id: int, timestamp: float, frame, frame_path: Optional[str] = None):
        """Add a frame to the ChromaDB index."""
        self._load()
        doc_id = f"cam{camera_id}_{int(timestamp * 1000)}"
        embedding = self.embed_frame(frame)
        self._collection.upsert(
            ids=[doc_id],
            embeddings=[embedding],
            metadatas=[{
                "camera_id": str(camera_id),
                "timestamp": timestamp,
                "frame_path": frame_path or "",
            }],
        )
        self._indexed_count = self._collection.count()
        return doc_id

    async def search(
        self,
        query: str,
        top_k: int = 12,
        camera_id: Optional[int] = None,
        timestamp_from: Optional[float] = None,
        timestamp_to: Optional[float] = None,
    ) -> list[dict]:
        """Search frames by natural language query."""
        self._load()

        # Build ChromaDB where filter
        where = {}
        if camera_id is not None:
            where["camera_id"] = str(camera_id)

        text_embedding = self.embed_text(query)

        result = self._collection.query(
            query_embeddings=[text_embedding],
            n_results=min(top_k, max(1, self._indexed_count)),
            where=where if where else None,
            include=["metadatas", "distances"],
        )

        if not result or not result["ids"] or not result["ids"][0]:
            return []

        output = []
        for doc_id, meta, dist in zip(
            result["ids"][0],
            result["metadatas"][0],
            result["distances"][0],
        ):
            score = 1.0 - dist  # cosine distance → similarity
            ts = meta.get("timestamp", 0)

            # Timestamp range filter (post-query since ChromaDB numeric filters vary)
            if timestamp_from and ts < timestamp_from:
                continue
            if timestamp_to and ts > timestamp_to:
                continue

            output.append({
                "chroma_id": doc_id,
                "camera_id": int(meta.get("camera_id", 0)),
                "timestamp": ts,
                "score": round(score, 4),
                "frame_path": meta.get("frame_path") or None,
            })

        output.sort(key=lambda x: x["score"], reverse=True)
        return output

    def get_stats(self) -> dict:
        try:
            self._load()
            return {
                "indexed_frames": self._collection.count(),
                "clip_model": "ViT-B/32",
                "device": self._device,
                "ready": self._ready,
            }
        except Exception as e:
            return {"indexed_frames": 0, "ready": False, "error": str(e)}


class CLIPIndexer:
    """
    Background task that samples frames from all cameras
    at a configured interval and adds them to the semantic index.
    """

    def __init__(self, engine: SearchEngine):
        self._engine = engine
        self._running = False
        self._frames_dir = Path("data/frames")
        self._frames_dir.mkdir(parents=True, exist_ok=True)

    async def start(self):
        from backend.config.settings import settings
        from backend.core.stream_manager import stream_manager
        import cv2

        self._running = True
        interval = settings.clip_sample_interval
        logger.info(f"🎞️  CLIP Indexer started (sample every {interval}s)")

        while self._running:
            await asyncio.sleep(interval)
            for camera_id, stream in list(stream_manager.streams.items()):
                if not stream.connected:
                    continue
                frame = stream_manager.get_latest_frame(camera_id)
                if frame is None:
                    continue
                try:
                    ts = time.time()
                    # Save thumbnail
                    fname = f"cam{camera_id}_{int(ts)}.jpg"
                    fpath = str(self._frames_dir / fname)
                    cv2.imwrite(fpath, cv2.resize(frame, (320, 180)))

                    # Index in background thread (CLIP is CPU-intensive)
                    loop = asyncio.get_event_loop()
                    await loop.run_in_executor(
                        None,
                        self._engine.index_frame,
                        camera_id, ts, frame, fpath
                    )
                    logger.debug(f"🔍 Indexed frame: cam{camera_id} @ {ts:.0f}")
                except Exception as e:
                    logger.warning(f"CLIP indexer error (cam {camera_id}): {e}")

    def stop(self):
        self._running = False


# Global singletons
search_engine = SearchEngine()
clip_indexer = CLIPIndexer(search_engine)

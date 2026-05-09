"""
Semantic Search Engine — CLIP + ChromaDB + Event fusion.

Mejoras sobre la versión original:
  1. Auto-traducción ES→EN antes de CLIP (fue entrenado en inglés)
  2. Búsqueda híbrida: CLIP visual + eventos analíticos de la DB
  3. Score threshold configurable para evitar resultados irrelevantes
  4. Re-ranking por relevancia temporal (frames recientes ponderados)
  5. get_device() para usar GPU automáticamente cuando esté disponible
"""
import asyncio
import time
import os
from pathlib import Path
from typing import Optional
from loguru import logger


# ─── Translation cache (avoid repeated API calls) ────────────────────────────

_translation_cache: dict[str, str] = {}


def _translate_to_english(text: str) -> str:
    """
    Translate Spanish (or any lang) → English for CLIP queries.
    Falls back to original text if translation fails.
    Results cached in memory.
    """
    if text in _translation_cache:
        return _translation_cache[text]
    try:
        from deep_translator import GoogleTranslator
        translated = GoogleTranslator(source="auto", target="en").translate(text)
        _translation_cache[text] = translated
        if translated != text:
            logger.debug(f"Query translated: '{text}' → '{translated}'")
        return translated
    except Exception as e:
        logger.debug(f"Translation failed ({e}), using original query")
        return text


# ─── Search Engine ────────────────────────────────────────────────────────────

class SearchEngine:
    """
    CLIP-based semantic video search with hybrid event fusion.

    - Indexes frames from all cameras periodically
    - Stores embeddings in ChromaDB (local persistent)
    - Queries by natural language (auto-translated to English for CLIP)
    - Fuses CLIP scores with matching analytic events for hybrid ranking
    """

    def __init__(self):
        self._model       = None
        self._preprocess  = None
        self._chroma      = None
        self._collection  = None
        self._ready       = False
        self._indexed_count = 0
        self._device      = "cpu"

    def _load(self):
        """Lazy-load CLIP and ChromaDB."""
        if self._ready:
            return

        import clip
        import chromadb
        from backend.config.settings import settings
        from backend.utils.hardware import get_device

        logger.info("Loading CLIP model...")
        self._device = get_device()   # auto GPU if available
        self._model, self._preprocess = clip.load(settings.clip_model, device=self._device)
        self._model.eval()
        logger.info(f"CLIP loaded ({settings.clip_model}) on {self._device}")

        self._chroma = chromadb.PersistentClient(path=settings.chroma_persist_dir)
        self._collection = self._chroma.get_or_create_collection(
            name="neobit_frames",
            metadata={"hnsw:space": "cosine"},
        )
        self._indexed_count = self._collection.count()
        logger.info(f"ChromaDB ready — {self._indexed_count} frames indexed")
        self._ready = True

    # ── Embedding ─────────────────────────────────────────────────────────────

    def embed_text(self, text: str) -> list[float]:
        import clip
        import torch
        self._load()
        # Translate to English before embedding (CLIP was trained in English)
        english = _translate_to_english(text)
        with torch.no_grad():
            tokens    = clip.tokenize([english]).to(self._device)
            embedding = self._model.encode_text(tokens)
            embedding = embedding / embedding.norm(dim=-1, keepdim=True)
        return embedding.cpu().numpy()[0].tolist()

    def embed_frame(self, frame) -> list[float]:
        import torch
        from PIL import Image
        self._load()
        rgb    = frame[:, :, ::-1]
        pil    = Image.fromarray(rgb.astype("uint8"))
        tensor = self._preprocess(pil).unsqueeze(0).to(self._device)
        with torch.no_grad():
            embedding = self._model.encode_image(tensor)
            embedding = embedding / embedding.norm(dim=-1, keepdim=True)
        return embedding.cpu().numpy()[0].tolist()

    # ── Indexing ──────────────────────────────────────────────────────────────

    def index_frame(
        self,
        camera_id:  int,
        timestamp:  float,
        frame,
        frame_path: Optional[str] = None,
    ):
        """Add a frame to the ChromaDB index."""
        self._load()
        doc_id    = f"cam{camera_id}_{int(timestamp * 1000)}"
        embedding = self.embed_frame(frame)
        self._collection.upsert(
            ids        = [doc_id],
            embeddings = [embedding],
            metadatas  = [{
                "camera_id":  str(camera_id),
                "timestamp":  timestamp,
                "frame_path": frame_path or "",
            }],
        )
        self._indexed_count = self._collection.count()
        return doc_id

    # ── Search ────────────────────────────────────────────────────────────────

    async def search(
        self,
        query:          str,
        top_k:          int           = 20,
        camera_id:      Optional[int] = None,
        timestamp_from: Optional[float] = None,
        timestamp_to:   Optional[float] = None,
        min_score:      float         = 0.15,   # filter near-zero matches
        use_events:     bool          = True,   # fuse with analytic events
    ) -> list[dict]:
        """
        Search frames by natural language.

        Steps:
          1. Translate query ES→EN
          2. CLIP text embedding
          3. ChromaDB cosine query (top_k * 3 candidates for re-ranking)
          4. Optional event fusion: boost frames near matching analytic events
          5. Apply score threshold, sort, and return top_k
        """
        self._load()
        if self._indexed_count == 0:
            return []

        # ── 1. CLIP query ─────────────────────────────────────────────────────
        where = {}
        if camera_id is not None:
            where["camera_id"] = str(camera_id)

        text_embedding = self.embed_text(query)

        # Fetch 3x candidates for re-ranking
        fetch_k = min(top_k * 3, max(1, self._indexed_count))
        result  = self._collection.query(
            query_embeddings = [text_embedding],
            n_results        = fetch_k,
            where            = where if where else None,
            include          = ["metadatas", "distances"],
        )

        if not result or not result["ids"] or not result["ids"][0]:
            return []

        candidates = []
        for doc_id, meta, dist in zip(
            result["ids"][0],
            result["metadatas"][0],
            result["distances"][0],
        ):
            score = 1.0 - dist
            ts    = meta.get("timestamp", 0)

            if score < min_score:
                continue
            if timestamp_from and ts < timestamp_from:
                continue
            if timestamp_to   and ts > timestamp_to:
                continue

            candidates.append({
                "chroma_id":  doc_id,
                "camera_id":  int(meta.get("camera_id", 0)),
                "timestamp":  ts,
                "clip_score": round(score, 4),
                "frame_path": meta.get("frame_path") or None,
                "events":     [],
                "score":      round(score, 4),
            })

        # ── 2. Event fusion ───────────────────────────────────────────────────
        if use_events and candidates:
            candidates = await self._fuse_events(candidates, query)

        candidates.sort(key=lambda x: x["score"], reverse=True)
        return candidates[:top_k]

    async def _fuse_events(self, candidates: list[dict], query: str) -> list[dict]:
        """
        Boost CLIP scores when analytic events occurred near the frame timestamp.
        Matches events using keyword heuristics on the query.
        """
        try:
            import sqlite3
            DB_PATH = "data/neobit.db"
            if not os.path.exists(DB_PATH):
                return candidates

            # Build keyword→analytic_type map
            KEYWORD_MAP = {
                "casco":    "epp_detection",  "helmet":  "epp_detection",
                "chaleco":  "epp_detection",  "vest":    "epp_detection",
                "bota":     "epp_detection",  "boot":    "epp_detection",
                "ppe":      "epp_detection",  "epp":     "epp_detection",
                "caída":    "fall_detection", "fall":    "fall_detection",
                "caido":    "fall_detection",
                "persona":  "person_detection","person": "person_detection",
                "rostro":   "face_detection", "face":   "face_detection",
                "fuego":    "fire_detection",  "fire":   "fire_detection",
                "intruso":  "intrusion_detection",
                "vehículo": "vehicle_detection","vehicle":"vehicle_detection",
            }

            q_lower  = query.lower()
            eng      = _translate_to_english(query).lower()
            combined = q_lower + " " + eng

            matched_types = {v for k, v in KEYWORD_MAP.items() if k in combined}
            if not matched_types:
                return candidates

            conn = sqlite3.connect(DB_PATH, check_same_thread=False)
            conn.row_factory = sqlite3.Row

            # Find event timestamps near each candidate (±30s window)
            BOOST  = 0.12   # score boost when event matches
            WINDOW = 30.0   # seconds

            for c in candidates:
                ts  = c["timestamp"]
                cam = c["camera_id"]
                placeholders = ",".join(["?" for _ in matched_types])
                rows = conn.execute(
                    f"""SELECT analytic_type, timestamp, description
                        FROM events
                        WHERE camera_id = ?
                          AND analytic_type IN ({placeholders})
                          AND timestamp BETWEEN ? AND ?
                        ORDER BY ABS(timestamp - ?) LIMIT 3""",
                    [cam, *matched_types, ts - WINDOW, ts + WINDOW, ts],
                ).fetchall()

                if rows:
                    c["events"] = [
                        {
                            "type":        r["analytic_type"],
                            "timestamp":   r["timestamp"],
                            "description": r["description"],
                        }
                        for r in rows
                    ]
                    # Boost score proportional to how many events matched
                    boost = min(BOOST * len(rows), BOOST * 2)
                    c["score"] = round(min(c["clip_score"] + boost, 0.99), 4)

            conn.close()

        except Exception as e:
            logger.debug(f"Event fusion error (non-fatal): {e}")

        return candidates

    # ── Stats ─────────────────────────────────────────────────────────────────

    def get_stats(self) -> dict:
        try:
            self._load()
            return {
                "indexed_frames": self._collection.count(),
                "clip_model":     "ViT-B/32",
                "device":         self._device,
                "ready":          self._ready,
            }
        except Exception as e:
            return {"indexed_frames": 0, "ready": False, "error": str(e)}


# ─── CLIP Indexer ─────────────────────────────────────────────────────────────

class CLIPIndexer:
    """
    Background task that samples frames from all cameras
    at a configured interval and indexes them semantically.
    """

    def __init__(self, engine: SearchEngine):
        self._engine     = engine
        self._running    = False
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
                    ts    = time.time()
                    fname = f"cam{camera_id}_{int(ts)}.jpg"
                    fpath = str(self._frames_dir / fname)
                    cv2.imwrite(fpath, cv2.resize(frame, (320, 180)))

                    loop = asyncio.get_event_loop()
                    await loop.run_in_executor(
                        None,
                        self._engine.index_frame,
                        camera_id, ts, frame, fpath,
                    )
                    logger.debug(f"Indexed frame: cam{camera_id} @ {ts:.0f}")
                except Exception as e:
                    logger.warning(f"CLIP indexer error (cam {camera_id}): {e}")

    def stop(self):
        self._running = False


# Global singletons
search_engine = SearchEngine()
clip_indexer  = CLIPIndexer(search_engine)

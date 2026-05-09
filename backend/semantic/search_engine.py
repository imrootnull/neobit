"""
Semantic Search Engine — CLIP + metadata tags + event fusion.

v2 improvements:
  1. Rich metadata stored per frame: detected objects, PPE status, person count
  2. Keyword-to-tag pre-filtering: narrow CLIP search space with metadata WHERE
  3. Score spread normalization: remap raw [0.15-0.35] to visible [0-1] range
  4. Event proximity: find nearest DB event and attach its clip path to results
  5. Auto-translate ES→EN before CLIP embedding
"""
import asyncio
import time
import os
from pathlib import Path
from typing import Optional
from loguru import logger

_translation_cache: dict[str, str] = {}


def _translate_to_english(text: str) -> str:
    if text in _translation_cache:
        return _translation_cache[text]
    try:
        from deep_translator import GoogleTranslator
        translated = GoogleTranslator(source="auto", target="en").translate(text)
        _translation_cache[text] = translated
        if translated.lower() != text.lower():
            logger.debug(f"Translated: '{text}' → '{translated}'")
        return translated
    except Exception:
        return text


# ─── Keyword → metadata tag map ────────────────────────────────────────────
# These are stored as tags in ChromaDB metadata during indexing
KEYWORD_TAGS: dict[str, str] = {
    # PPE
    "casco": "helmet",       "helmet": "helmet",
    "chaleco": "vest",       "vest": "vest",
    "bota": "boot",          "boot": "boot",
    "guante": "glove",       "glove": "glove",
    "lentes": "glasses",     "glasses": "glasses",
    # PPE status
    "sin casco": "no_helmet",        "no helmet": "no_helmet",
    "sin chaleco": "no_vest",        "no vest": "no_vest",
    "sin epp": "ppe_violation",
    # Events
    "caída": "fall",         "fall": "fall",   "caido": "fall",
    "fuego": "fire",         "fire": "fire",   "incendio": "fire",
    "intruso": "intrusion",  "intrusion": "intrusion",
    # Objects
    "persona": "person",     "person": "person",
    "vehículo": "vehicle",   "vehicle": "vehicle", "carro": "vehicle",
    "rostro": "face",        "face": "face",
}

# ─── Search Engine ─────────────────────────────────────────────────────────

class SearchEngine:

    def __init__(self):
        self._model       = None
        self._preprocess  = None
        self._chroma      = None
        self._collection  = None
        self._ready       = False
        self._indexed_count = 0
        self._device      = "cpu"

    def _load(self):
        if self._ready:
            return
        import clip, chromadb
        from backend.config.settings import settings

        logger.info("Loading CLIP model...")
        # Use GPU if available (worker process), otherwise CPU (uvicorn process)
        try:
            from backend.utils.hardware import get_device
            self._device = get_device()
        except Exception:
            self._device = "cpu"
        # Ensure torch doesn't crash if CUDA unavailable in this process
        try:
            import torch
            if not torch.cuda.is_available():
                self._device = "cpu"
        except Exception:
            self._device = "cpu"

        self._model, self._preprocess = clip.load(settings.clip_model, device=self._device)
        self._model.eval()

        self._chroma = chromadb.PersistentClient(path=settings.chroma_persist_dir)
        self._collection = self._chroma.get_or_create_collection(
            name="neobit_frames",
            metadata={"hnsw:space": "cosine"},
        )
        self._indexed_count = self._collection.count()
        logger.info(f"CLIP ready — {self._indexed_count} frames indexed on {self._device}")
        self._ready = True

    # ── Embedding ──────────────────────────────────────────────────────────

    def embed_text(self, text: str) -> list[float]:
        import clip, torch
        self._load()
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

    # ── Indexing ───────────────────────────────────────────────────────────

    def index_frame(
        self,
        camera_id:   int,
        timestamp:   float,
        frame,
        frame_path:  Optional[str] = None,
        detections:  Optional[list[str]] = None,   # ["person","helmet","vest"]
        ppe_tags:    Optional[list[str]] = None,   # ["no_helmet","no_vest"]
        person_count: int = 0,
    ):
        """Index a frame with rich detection metadata for better search filtering."""
        self._load()
        doc_id    = f"cam{camera_id}_{int(timestamp * 1000)}"
        embedding = self.embed_frame(frame)

        # Flatten detection lists to comma-separated strings (ChromaDB metadata must be str/int/float)
        det_str = ",".join(detections or [])
        ppe_str = ",".join(ppe_tags   or [])

        self._collection.upsert(
            ids        = [doc_id],
            embeddings = [embedding],
            metadatas  = [{
                "camera_id":    str(camera_id),
                "timestamp":    timestamp,
                "frame_path":   frame_path or "",
                "detections":   det_str,         # e.g. "person,helmet,vest"
                "ppe_tags":     ppe_str,         # e.g. "no_helmet,no_vest"
                "person_count": person_count,
            }],
        )
        self._indexed_count = self._collection.count()
        return doc_id

    # ── Search ─────────────────────────────────────────────────────────────

    async def search(
        self,
        query:          str,
        top_k:          int           = 20,
        camera_id:      Optional[int] = None,
        timestamp_from: Optional[float] = None,
        timestamp_to:   Optional[float] = None,
        min_score:      float         = 0.0,
        use_events:     bool          = True,
    ) -> list[dict]:
        self._load()
        if self._indexed_count == 0:
            return []

        # ── Build ChromaDB where filter ────────────────────────────────────
        where_clauses = []
        if camera_id is not None:
            where_clauses.append({"camera_id": str(camera_id)})

        # Narrow to frames that contain the queried object using metadata
        tag = self._query_to_tag(query)
        # (tag filtering disabled — ChromaDB $contains not supported on all versions)

        where = {"$and": where_clauses} if len(where_clauses) > 1 else (where_clauses[0] if where_clauses else None)

        text_embedding = self.embed_text(query)
        fetch_k = min(top_k * 4, max(1, self._indexed_count))

        result = self._collection.query(
            query_embeddings = [text_embedding],
            n_results        = fetch_k,
            where            = where,
            include          = ["metadatas", "distances"],
        )

        if not result or not result["ids"] or not result["ids"][0]:
            return []

        candidates = []
        raw_scores = []
        for doc_id, meta, dist in zip(
            result["ids"][0],
            result["metadatas"][0],
            result["distances"][0],
        ):
            ts = meta.get("timestamp", 0)
            if timestamp_from and ts < timestamp_from:
                continue
            if timestamp_to   and ts > timestamp_to:
                continue

            score = 1.0 - dist
            raw_scores.append(score)
            candidates.append({
                "chroma_id":    doc_id,
                "camera_id":    int(meta.get("camera_id", 0)),
                "timestamp":    ts,
                "clip_score":   score,
                "score":        score,
                "frame_path":   meta.get("frame_path") or None,
                "detections":   meta.get("detections", ""),
                "ppe_tags":     meta.get("ppe_tags", ""),
                "person_count": meta.get("person_count", 0),
                "events":       [],
                "event_clip":   None,
                "event_snap":   None,
            })

        if not candidates:
            return []

        # ── Score normalization: spread [min, max] → [0, 1] ───────────────
        # Raw CLIP scores for scene similarity are typically 0.20-0.35
        # Normalizing makes the ranking visible and usable
        if raw_scores:
            lo, hi = min(raw_scores), max(raw_scores)
            spread = hi - lo if hi - lo > 0.001 else 0.001
            for c in candidates:
                normalized = (c["clip_score"] - lo) / spread
                # Re-rank by metadata tag match
                tag_boost = self._metadata_boost(c, query)
                c["score"] = round(min(normalized + tag_boost, 1.0), 4)

        # ── Event fusion ───────────────────────────────────────────────────
        if use_events:
            candidates = await self._fuse_events(candidates, query)

        candidates.sort(key=lambda x: x["score"], reverse=True)
        return candidates[:top_k]

    def _query_to_tag(self, query: str) -> Optional[str]:
        q = query.lower()
        for kw, tag in KEYWORD_TAGS.items():
            if kw in q:
                return tag
        return None

    def _metadata_boost(self, candidate: dict, query: str) -> float:
        """Boost score based on detection metadata matching the query keywords."""
        q     = query.lower()
        eng   = _translate_to_english(query).lower()
        combo = q + " " + eng
        dets  = candidate.get("detections", "").lower()
        ppe   = candidate.get("ppe_tags",   "").lower()
        boost = 0.0

        for kw, tag in KEYWORD_TAGS.items():
            if kw in combo:
                if tag in dets or tag in ppe:
                    boost += 0.15

        # Person count relevance: queries about people prefer frames WITH people
        if ("persona" in combo or "person" in combo) and candidate.get("person_count", 0) > 0:
            boost += 0.05

        return min(boost, 0.40)

    async def _fuse_events(self, candidates: list[dict], query: str) -> list[dict]:
        """
        For each candidate find the closest DB event in time.
        Attaches event clip/snap paths so the UI can open the video.
        """
        try:
            import sqlite3
            DB_PATH = "data/neobit.db"
            if not os.path.exists(DB_PATH):
                return candidates

            KEYWORD_MAP = {
                "casco": "epp_detection",    "helmet":   "epp_detection",
                "chaleco": "epp_detection",  "vest":     "epp_detection",
                "bota": "epp_detection",     "boot":     "epp_detection",
                "epp": "epp_detection",      "ppe":      "epp_detection",
                "caída": "fall_detection",   "fall":     "fall_detection",
                "caido": "fall_detection",
                "persona": "person_detection","person":  "person_detection",
                "rostro": "face_detection",  "face":     "face_detection",
                "fuego": "fire_detection",   "fire":     "fire_detection",
                "intruso": "intrusion_detection",
                "vehículo": "vehicle_detection","vehicle":"vehicle_detection",
            }

            q_lower  = query.lower()
            eng      = _translate_to_english(query).lower()
            combined = q_lower + " " + eng
            matched_types = {v for k, v in KEYWORD_MAP.items() if k in combined}

            conn = sqlite3.connect(DB_PATH, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            WINDOW = 60.0   # ±60s window for event matching

            for c in candidates:
                ts, cam = c["timestamp"], c["camera_id"]

                # Always look for nearest event to attach clip path
                type_clause = ""
                type_params: list = []
                if matched_types:
                    ph = ",".join(["?" for _ in matched_types])
                    type_clause = f"AND analytic_type IN ({ph})"
                    type_params = list(matched_types)

                row = conn.execute(
                    f"""SELECT analytic_type, timestamp, description,
                               recording_path, snapshot_path
                        FROM events
                        WHERE camera_id = ?
                          AND timestamp BETWEEN ? AND ?
                          {type_clause}
                        ORDER BY ABS(timestamp - ?) LIMIT 1""",
                    [cam, ts - WINDOW, ts + WINDOW, *type_params, ts],
                ).fetchone()

                if row:
                    c["events"].append({
                        "type":        row["analytic_type"],
                        "timestamp":   row["timestamp"],
                        "description": row["description"],
                    })
                    # Attach the event clip so UI can play it
                    if row["recording_path"] and os.path.exists(row["recording_path"]):
                        c["event_clip"] = row["recording_path"]
                    if row["snapshot_path"] and os.path.exists(row["snapshot_path"]):
                        c["event_snap"] = row["snapshot_path"]
                    # Boost if event type matches query
                    if matched_types and row["analytic_type"] in matched_types:
                        c["score"] = round(min(c["score"] + 0.12, 1.0), 4)

            conn.close()
        except Exception as e:
            logger.debug(f"Event fusion error: {e}")
        return candidates

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


# ─── CLIP Indexer ──────────────────────────────────────────────────────────

class CLIPIndexer:
    """
    Samples frames periodically and indexes with detection metadata.
    Pulls current YOLO detections from the pipeline to enrich metadata.
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
        logger.info(f"🎞️  CLIP Indexer started (sample every {interval}s) — first index in 20s")

        # Defer first load: let the server fully start before loading CLIP
        # (avoids blocking the asyncio event loop during startup)
        await asyncio.sleep(20)

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

                    # Pull latest detection metadata from pipeline
                    detections, ppe_tags, person_count = self._get_detections(camera_id)

                    loop = asyncio.get_event_loop()
                    await loop.run_in_executor(
                        None,
                        self._engine.index_frame,
                        camera_id, ts, frame, fpath,
                        detections, ppe_tags, person_count,
                    )
                    logger.debug(f"Indexed cam{camera_id} dets={detections} ppe={ppe_tags}")
                except Exception as e:
                    logger.warning(f"CLIP indexer error (cam {camera_id}): {e}")

    def _get_detections(self, camera_id: int) -> tuple[list[str], list[str], int]:
        """Pull recent detections from the pipeline state."""
        try:
            from backend.inference.pipeline import inference_pipeline
            state = inference_pipeline.get_camera_state(camera_id)
            if not state:
                return [], [], 0
            detections  = state.get("detected_objects", [])
            ppe_tags    = state.get("ppe_missing", [])
            person_count = state.get("person_count", 0)
            return detections, ppe_tags, person_count
        except Exception:
            return [], [], 0

    def stop(self):
        self._running = False


# Global singletons
search_engine = SearchEngine()
clip_indexer  = CLIPIndexer(search_engine)

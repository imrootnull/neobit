"""
Shared memory frame bridge — zero-copy frame sharing between OS processes.
Inference process writes raw/annotated frames, uvicorn process reads them.
"""
import struct
import numpy as np
from multiprocessing.shared_memory import SharedMemory

MAX_W, MAX_H, MAX_C = 1280, 720, 3
HEADER_FMT  = "4i"          # width, height, channels, frame_id
HEADER_SIZE = struct.calcsize(HEADER_FMT)   # 16 bytes
MAX_DATA    = MAX_W * MAX_H * MAX_C
TOTAL_SIZE  = HEADER_SIZE + MAX_DATA        # ~2.8 MB per slot


class SharedFrame:
    """One frame slot in shared memory."""

    def __init__(self, name: str, create: bool = False):
        if create:
            try:                         # clean stale shm from previous run
                s = SharedMemory(name=name); s.close(); s.unlink()
            except FileNotFoundError:
                pass
            self._shm = SharedMemory(name=name, create=True, size=TOTAL_SIZE)
            self._shm.buf[:HEADER_SIZE] = b"\x00" * HEADER_SIZE
        else:
            self._shm = SharedMemory(name=name, create=False)
            # Prevent Python's resource_tracker from unlinking memory owned
            # by the worker process — causes SIGSEGV on next access
            try:
                from multiprocessing import resource_tracker
                resource_tracker.unregister(f"/{name}", "shared_memory")
            except Exception:
                pass
        self._buf = self._shm.buf
        self._name = name

    def write(self, frame: np.ndarray) -> int:
        if frame is None:
            return 0
        h, w = frame.shape[:2]
        c    = frame.shape[2] if frame.ndim == 3 else 1
        if h * w * c > MAX_DATA:
            import cv2
            scale = (MAX_DATA / (h * w * c)) ** 0.5
            frame = cv2.resize(frame, (int(w * scale), int(h * scale)))
            h, w  = frame.shape[:2]
        size = h * w * c
        *_, fid = struct.unpack_from(HEADER_FMT, self._buf, 0)
        # Write data first, then header (reader sees consistent state)
        np.frombuffer(self._buf, dtype=np.uint8,
                      count=size, offset=HEADER_SIZE)[:] = frame.reshape(-1)
        struct.pack_into(HEADER_FMT, self._buf, 0, w, h, c, fid + 1)
        return fid + 1

    def read(self) -> tuple:
        try:
            w, h, c, fid = struct.unpack_from(HEADER_FMT, self._buf, 0)
            if fid == 0 or w == 0 or h == 0 or c == 0:
                return None, 0
            expected = w * h * c
            if expected > MAX_DATA or expected <= 0:
                return None, 0
            arr = np.frombuffer(self._buf, dtype=np.uint8,
                                count=expected, offset=HEADER_SIZE).copy()
            return arr.reshape(h, w, c), fid
        except Exception:
            return None, 0

    def frame_id(self) -> int:
        return struct.unpack_from(HEADER_FMT, self._buf, 0)[3]

    def close(self):
        self._shm.close()

    def unlink(self):
        try:
            self._shm.unlink()
        except Exception:
            pass


class FrameBridge:
    """
    Per-camera shared memory bridge.

    Process A (uvicorn):
        bridge.write_raw(cid, frame)       ← from RTSP reader thread
        frame = bridge.read_annotated(cid) → to snapshot endpoint

    Process B (inference):
        frame, fid = bridge.read_raw(cid)
        bridge.write_annotated(cid, annotated)
    """

    def __init__(self, create: bool = False):
        self._create = create
        self._raw: dict[int, SharedFrame] = {}
        self._ann: dict[int, SharedFrame] = {}

    def add_camera(self, camera_id: int):
        if camera_id not in self._raw:
            self._raw[camera_id] = SharedFrame(f"nb_raw_{camera_id}", create=self._create)
            self._ann[camera_id] = SharedFrame(f"nb_ann_{camera_id}", create=self._create)

    def write_raw(self, cid: int, frame: np.ndarray) -> int:
        sf = self._raw.get(cid)
        return sf.write(frame) if sf else 0

    def read_raw(self, cid: int):
        sf = self._raw.get(cid)
        return sf.read() if sf else (None, 0)

    def write_annotated(self, cid: int, frame: np.ndarray) -> int:
        sf = self._ann.get(cid)
        return sf.write(frame) if sf else 0

    def read_annotated(self, cid: int):
        sf = self._ann.get(cid)
        return sf.read() if sf else (None, 0)

    def close_all(self):
        for sf in list(self._raw.values()) + list(self._ann.values()):
            sf.close()

    def unlink_all(self):
        for sf in list(self._raw.values()) + list(self._ann.values()):
            sf.unlink()


# Module-level singleton — populated by run.py before fork
bridge: FrameBridge | None = None

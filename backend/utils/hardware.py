"""
Hardware detection utility — auto-selects best inference device.

Priority order:
  1. CUDA      (NVIDIA)   — torch.cuda
  2. ROCm/HIP  (AMD)      — torch.cuda with ROCm build
  3. OpenVINO GPU         — Intel iGPU / Arc / AMD via OpenCL plugin
  4. CPU                  — always available fallback

ONNX Runtime provider priority (for InsightFace):
  CUDAExecutionProvider → MIGraphXExecutionProvider → ROCMExecutionProvider
  → DmlExecutionProvider → OpenVINOExecutionProvider → CPUExecutionProvider
"""
from __future__ import annotations
import os
import subprocess
from loguru import logger

# ─── Cache ────────────────────────────────────────────────────────────────────
_cache: dict = {}


# ─── Public API ───────────────────────────────────────────────────────────────

def get_device() -> str:
    """
    Best device string for YOLO/ultralytics: 'cuda' or 'cpu'.
    AMD ROCm-enabled PyTorch also returns 'cuda'.
    """
    if "device" in _cache:
        return _cache["device"]
    dev = _detect_device()
    _cache["device"] = dev
    logger.info(f"Inference device: {dev}")
    return dev


def get_ort_providers() -> list[str]:
    """Best ONNX Runtime providers for InsightFace, in priority order."""
    if "ort_providers" in _cache:
        return _cache["ort_providers"]
    providers = _detect_ort_providers()
    _cache["ort_providers"] = providers
    logger.info(f"ORT providers: {providers}")
    return providers


def get_best_backend() -> str:
    """Legacy: return best backend key (coral/tensorrt/cuda/cpu)."""
    if detect_coral():     return "coral"
    if detect_tensorrt():  return "tensorrt"
    if detect_cuda():      return "cuda"
    return "cpu"


def get_system_info() -> dict:
    """Full hardware summary for /api/system/hardware."""
    import platform
    info = {
        "platform":       platform.platform(),
        "processor":      platform.processor(),
        "device":         get_device(),
        "ort_providers":  get_ort_providers(),
        "coral":          detect_coral(),
        "cuda":           detect_cuda(),
        "cuda_name":      _cuda_device_name(),
        "rocm":           _rocm_available(),
        "tensorrt":       detect_tensorrt(),
        "openvino_gpu":   _detect_openvino_gpu() is not None,
    }
    try:
        import psutil
        mem = psutil.virtual_memory()
        info["ram_total_gb"]     = round(mem.total / 1e9, 1)
        info["ram_available_gb"] = round(mem.available / 1e9, 1)
        info["cpu_cores"]        = psutil.cpu_count(logical=False)
        info["cpu_threads"]      = psutil.cpu_count(logical=True)
    except ImportError:
        pass
    return info


# ─── Individual detectors ─────────────────────────────────────────────────────

def detect_coral() -> bool:
    """Check if Google Coral USB accelerator is connected."""
    try:
        import usb.core
        coral_ids = [(0x1A6E, 0x089A), (0x18D1, 0x9302)]
        for vendor, product in coral_ids:
            if usb.core.find(idVendor=vendor, idProduct=product) is not None:
                logger.info(f"Coral USB detected")
                return True
    except ImportError:
        pass
    try:
        from pycoral.utils.edgetpu import make_interpreter  # noqa
        return True
    except Exception:
        pass
    return False


def detect_cuda() -> bool:
    """Check if CUDA (NVIDIA or AMD ROCm) is available via torch."""
    try:
        import torch
        if torch.cuda.is_available():
            logger.info(f"CUDA available: {torch.cuda.get_device_name(0)}")
            return True
    except ImportError:
        pass
    return False


def detect_tensorrt() -> bool:
    try:
        import tensorrt as trt  # noqa
        logger.info("TensorRT detected")
        return True
    except ImportError:
        return False


# ─── Internal helpers ─────────────────────────────────────────────────────────

def _cuda_device_name() -> str:
    try:
        import torch
        if torch.cuda.is_available():
            return torch.cuda.get_device_name(0)
    except Exception:
        pass
    return ""


def _rocm_available() -> bool:
    """AMD ROCm: torch.cuda works when PyTorch built with ROCm, or /opt/rocm exists."""
    if detect_cuda():
        name = _cuda_device_name().upper()
        if "AMD" in name or "RADEON" in name or "GFX" in name:
            return True
    return os.path.exists("/opt/rocm")


def _detect_openvino_gpu() -> str | None:
    """Returns 'GPU' if OpenVINO sees a GPU device (Intel/AMD via OpenCL)."""
    try:
        import openvino as ov
        core    = ov.Core()
        devices = core.available_devices
        for d in devices:
            if d.startswith("GPU"):
                try:
                    name = core.get_property(d, "FULL_DEVICE_NAME")
                    logger.info(f"OpenVINO GPU: {name}")
                except Exception:
                    pass
                return d
    except Exception:
        pass
    return None


def _ort_all_providers() -> list[str]:
    try:
        import onnxruntime as ort
        return ort.get_available_providers()
    except ImportError:
        return ["CPUExecutionProvider"]


def _detect_ort_providers() -> list[str]:
    available = _ort_all_providers()

    # NVIDIA CUDA
    if "CUDAExecutionProvider" in available and detect_cuda():
        return ["CUDAExecutionProvider", "CPUExecutionProvider"]

    # AMD ROCm (MIGraphX)
    if "MIGraphXExecutionProvider" in available:
        return ["MIGraphXExecutionProvider", "CPUExecutionProvider"]

    # AMD ROCm (ROCM provider)
    if "ROCMExecutionProvider" in available:
        return ["ROCMExecutionProvider", "CPUExecutionProvider"]

    # DirectML (Windows — AMD/Intel/NVIDIA)
    if "DmlExecutionProvider" in available:
        return ["DmlExecutionProvider", "CPUExecutionProvider"]

    # OpenVINO (Intel iGPU / AMD via OpenCL plugin)
    if "OpenVINOExecutionProvider" in available and _detect_openvino_gpu():
        return ["OpenVINOExecutionProvider", "CPUExecutionProvider"]

    return ["CPUExecutionProvider"]


def _detect_device() -> str:
    if detect_cuda():
        return "cuda"
    if os.path.exists("/opt/rocm"):
        logger.info("ROCm detected — using 'cuda' device for PyTorch")
        return "cuda"
    return "cpu"

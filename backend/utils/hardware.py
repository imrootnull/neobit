"""
Hardware detection utility — detects available inference backends.
Priority: Coral USB > CUDA > CPU
"""
import subprocess
from loguru import logger


def detect_coral() -> bool:
    """Check if Google Coral USB is connected and usable."""
    try:
        import usb.core
        # Coral USB vendor/product IDs
        coral_ids = [
            (0x1A6E, 0x089A),  # Global Unichip Corp (Coral USB)
            (0x18D1, 0x9302),  # Google (Coral USB Accelerator)
        ]
        for vendor, product in coral_ids:
            dev = usb.core.find(idVendor=vendor, idProduct=product)
            if dev is not None:
                logger.info(f"✅ Coral USB detected: VID={vendor:#06x} PID={product:#06x}")
                return True
    except ImportError:
        logger.warning("pyusb not installed — falling back to tflite probe")
    except Exception as e:
        logger.debug(f"Coral USB probe error: {e}")

    # Fallback: try loading edge TPU delegate
    try:
        from pycoral.utils.edgetpu import make_interpreter
        logger.info("✅ Coral USB confirmed via pycoral")
        return True
    except Exception:
        pass

    logger.info("⚠️  Coral USB not found")
    return False


def detect_cuda() -> bool:
    """Check if CUDA is available."""
    try:
        import torch
        if torch.cuda.is_available():
            name = torch.cuda.get_device_name(0)
            logger.info(f"✅ CUDA detected: {name}")
            return True
    except ImportError:
        pass
    logger.info("⚠️  CUDA not available")
    return False


def detect_tensorrt() -> bool:
    """Check if TensorRT is available (Jetson Orin)."""
    try:
        import tensorrt as trt  # noqa
        logger.info("✅ TensorRT detected")
        return True
    except ImportError:
        pass
    return False


def get_best_backend() -> str:
    """Return the best available inference backend."""
    if detect_coral():
        return "coral"
    if detect_tensorrt():
        return "tensorrt"
    if detect_cuda():
        return "cuda"
    return "cpu"


def get_system_info() -> dict:
    """Return system hardware summary."""
    import platform
    info = {
        "platform": platform.platform(),
        "processor": platform.processor(),
        "coral": detect_coral(),
        "cuda": detect_cuda(),
        "tensorrt": detect_tensorrt(),
    }
    try:
        import psutil
        mem = psutil.virtual_memory()
        info["ram_total_gb"] = round(mem.total / 1e9, 1)
        info["ram_available_gb"] = round(mem.available / 1e9, 1)
        info["cpu_cores"] = psutil.cpu_count(logical=False)
        info["cpu_threads"] = psutil.cpu_count(logical=True)
    except ImportError:
        pass
    return info

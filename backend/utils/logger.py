from loguru import logger
import sys
from backend.config.settings import settings


def setup_logger():
    logger.remove()
    logger.add(
        sys.stderr,
        level=settings.log_level,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> — <level>{message}</level>",
        colorize=True,
    )
    logger.add(
        "logs/neobit.log",
        rotation="10 MB",
        retention="7 days",
        level="DEBUG",
        format="{time} | {level} | {name}:{function}:{line} — {message}",
    )
    return logger


setup_logger()

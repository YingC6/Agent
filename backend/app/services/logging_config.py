"""日志配置"""

from pathlib import Path
from loguru import logger
from .cache_service import get_cache_client


def setup_logging(log_level: str = "INFO"):
    log_dir = Path(__file__).parent.parent.parent / "logs"
    log_dir.mkdir(exist_ok=True)
    logger.remove()
    logger.add(lambda msg: print(msg, end=""), level=log_level)
    logger.add(log_dir / "app.log", rotation="10 MB", retention="14 days", encoding="utf-8", level=log_level)

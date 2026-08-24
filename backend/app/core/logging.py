"""Application logging setup.

Log streams are kept separate by logger name so that application events,
executions and audit records can be routed to different destinations later:

- "cronpanel.app"       -> application logs
- "cronpanel.execution" -> script execution logs (Phase 8)
- "cronpanel.audit"     -> audit trail (Phase 11)

Never log passwords, tokens or other credentials.
"""

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from app.core.config import BASE_DIR

LOG_DIR = BASE_DIR / "logs"
LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"

MAX_LOG_BYTES = 5 * 1024 * 1024
BACKUP_COUNT = 3


def _build_console_handler() -> logging.Handler:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter(LOG_FORMAT))
    return handler


def _build_file_handler(log_name: str) -> logging.Handler:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(
        LOG_DIR / f"{log_name}.log",
        maxBytes=MAX_LOG_BYTES,
        backupCount=BACKUP_COUNT,
        encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter(LOG_FORMAT))
    return handler


def setup_logging(level: int = logging.INFO) -> None:
    root = logging.getLogger("cronpanel")
    if root.handlers:
        return

    root.setLevel(level)
    root.addHandler(_build_console_handler())
    root.addHandler(_build_file_handler("app"))

    # Third-party noise reduction.
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Get a child logger under the 'cronpanel' namespace."""
    if not name.startswith("cronpanel"):
        name = f"cronpanel.{name}"
    return logging.getLogger(name)

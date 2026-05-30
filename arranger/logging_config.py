from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from arranger.config import Settings


def setup_logging(settings: Settings) -> None:
    level = getattr(logging, settings.app.log_level.upper(), logging.INFO)
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    if settings.logging.file:
        log_path = Path(settings.logging.file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(RotatingFileHandler(log_path, maxBytes=10_000_000, backupCount=5))
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        handlers=handlers,
        force=True,
    )

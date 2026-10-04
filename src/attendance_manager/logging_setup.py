from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

_FORMAT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"


def configure_logging(logs_dir: Path, level: int = logging.INFO) -> Path:
    """Log to a rotating file in the data directory (and stderr when available)."""
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_file = logs_dir / "attendance-manager.log"
    root = logging.getLogger()
    root.setLevel(level)
    for handler in list(root.handlers):
        root.removeHandler(handler)
    file_handler = RotatingFileHandler(
        log_file, maxBytes=2_000_000, backupCount=5, encoding="utf-8"
    )
    file_handler.setFormatter(logging.Formatter(_FORMAT))
    root.addHandler(file_handler)
    if sys.stderr is not None and not getattr(sys, "frozen", False):
        stream = logging.StreamHandler(sys.stderr)
        stream.setFormatter(logging.Formatter(_FORMAT))
        root.addHandler(stream)
    return log_file

"""
Attaches a WARNING-level rotating file handler to the root logger.
Import and call setup_file_logging() once at server startup.
Only warnings, errors, and criticals are written — normal INFO traffic is excluded.
"""

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path


def setup_file_logging(log_dir: Path) -> Path:
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "aml_errors.log"

    handler = RotatingFileHandler(
        log_path,
        maxBytes=2 * 1024 * 1024,  # 2 MB per file
        backupCount=3,
        encoding="utf-8",
    )
    handler.setLevel(logging.WARNING)
    handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))

    root = logging.getLogger()
    # Avoid adding duplicate handlers on hot-reload
    if not any(isinstance(h, RotatingFileHandler) for h in root.handlers):
        root.addHandler(handler)

    return log_path

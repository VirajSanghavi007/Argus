"""
Dual-log system for error logs and training logs.
Import and call setup_logging() once at startup.
- Error logs: WARNING+ level, written to logs/error_logs/
- Training logs: INFO+ level, written to logs/training_logs/
"""

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path


def setup_logging(log_dir: Path = Path("logs")) -> dict:
    """Setup error and training log handlers. Returns dict with log paths."""
    log_dir.mkdir(parents=True, exist_ok=True)
    error_dir = log_dir / "error_logs"
    training_dir = log_dir / "training_logs"
    error_dir.mkdir(exist_ok=True)
    training_dir.mkdir(exist_ok=True)

    root = logging.getLogger()

    # Error logger (WARNING+)
    error_path = error_dir / "errors.log"
    error_handler = RotatingFileHandler(
        error_path,
        maxBytes=5 * 1024 * 1024,  # 5 MB
        backupCount=5,
        encoding="utf-8",
    )
    error_handler.setLevel(logging.WARNING)
    error_handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))

    # Training logger (INFO+)
    training_path = training_dir / "training.log"
    training_handler = RotatingFileHandler(
        training_path,
        maxBytes=10 * 1024 * 1024,  # 10 MB
        backupCount=5,
        encoding="utf-8",
    )
    training_handler.setLevel(logging.INFO)
    training_handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))

    # Avoid duplicate handlers on hot-reload
    if not any(isinstance(h, RotatingFileHandler) and h.baseFilename.endswith("errors.log")
               for h in root.handlers):
        root.addHandler(error_handler)
    if not any(isinstance(h, RotatingFileHandler) and h.baseFilename.endswith("training.log")
               for h in root.handlers):
        root.addHandler(training_handler)

    return {"error_logs": error_path, "training_logs": training_path}


def get_error_logger(name: str) -> logging.Logger:
    """Get a logger configured for error logging."""
    return logging.getLogger(name)


def get_training_logger(name: str) -> logging.Logger:
    """Get a logger configured for training/model logs."""
    return logging.getLogger(name)

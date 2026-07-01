"""
Central configuration — every path, env var, and tunable lives here.
"""

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
LOGS_DIR = PROJECT_ROOT / "logs"

# Model
MODEL_PATH = DATA_DIR / "multignn_model.pt"
META_PATH = DATA_DIR / "multignn_meta.json"

# Database (PostgreSQL only — see src/database/service.py)
SCHEMA_PATH = PROJECT_ROOT / "src" / "database" / "schemas" / "schema_postgres.sql"

# Pipeline cache / drift
CACHE_PATH = DATA_DIR / "pipeline_cache.json"
DRIFT_LOG = DATA_DIR / "drift_log.json"

# Server
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8000"))

# Pipeline
# HI-Medium's first ~100k rows are mostly low-connectivity Reinvestment
# self-loops near the start of the file and yield zero alert clusters after
# clustering/filtering. 800k rows reaches denser, more connected activity and
# produces a healthy ~40 alerts — verified empirically against the trained model.
MULTIGNN_MAX_ROWS = int(os.getenv("MULTIGNN_MAX_ROWS", "800000"))

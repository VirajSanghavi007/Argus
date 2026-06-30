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

# Database
DB_PATH = DATA_DIR / "argus.db"
SCHEMA_PATH = PROJECT_ROOT / "src" / "database" / "schemas" / "schema.sql"

# Pipeline cache / drift
CACHE_PATH = DATA_DIR / "pipeline_cache.json"
DRIFT_LOG = DATA_DIR / "drift_log.json"

# Server
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8000"))

# Pipeline
MULTIGNN_MAX_ROWS = int(os.getenv("MULTIGNN_MAX_ROWS", "100000"))

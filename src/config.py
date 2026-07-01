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
# HI-Medium's first rows are overwhelmingly low-connectivity Reinvestment
# self-loops with very few "Is Laundering" positives (42 in the first 800k
# rows — 0.005%). A scan of 150k-row windows across the file found rows
# 4,350,000+ to be ~17x denser (707 positives in 800k rows, 0.088%), giving
# the model meaningfully more signal to learn from. Both training
# (scripts/train.py) and the serving pipeline read from this same offset so
# the deployed model and the live-scored graph are drawn from the same slice.
MULTIGNN_ROW_OFFSET = int(os.getenv("MULTIGNN_ROW_OFFSET", "4350000"))
MULTIGNN_MAX_ROWS = int(os.getenv("MULTIGNN_MAX_ROWS", "800000"))

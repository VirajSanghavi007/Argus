#!/usr/bin/env python3
"""
Development server for Argus AML detection API.

Usage:
    python scripts/serve.py [--host 0.0.0.0] [--port 8000]
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "backend.api.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )

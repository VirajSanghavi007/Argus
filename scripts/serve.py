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
from config import HOST, PORT

if __name__ == "__main__":
    uvicorn.run(
        "backend.api.main:app",
        host=HOST,
        port=PORT,
        reload=True,
        reload_includes=["*.py"],
        reload_excludes=["data/*", "logs/*", "*.db", "*.json", "*.pt"],
    )

#!/usr/bin/env python3
"""No-reload server launcher for local preview/verification (avoids watchfiles ghost workers)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import uvicorn

if __name__ == "__main__":
    uvicorn.run("backend.api.main:app", host="127.0.0.1", port=8000, reload=False)

#!/usr/bin/env python3
"""
Training script for Multi-GNN model.

Usage:
    python scripts/train.py --epochs 8 [--max-rows 600000]
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from backend.models.multignn import main

if __name__ == "__main__":
    main()

"""
Live transaction ingestion store.

This is the API layer's persistence side: transactions POSTed to /ingest
(single rows or batches) are appended to a CSV that the Multi-GNN pipeline
can fold into its next scan. Decoupled from the model so the ingestion
endpoint stays fast and never blocks on inference.
"""

import csv
import threading
from datetime import datetime, timezone

import config

LIVE_TX_PATH = config.DATA_DIR / "live_transactions.csv"
_lock = threading.Lock()

# Canonical header — matches the IBM / tx.csv schema the pipeline reads.
FIELDS = [
    "Timestamp", "From Bank", "From Account", "To Bank", "To Account",
    "Amount Received", "Receiving Currency", "Amount Paid",
    "Payment Currency", "Payment Format",
]


def _ensure_file() -> None:
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not LIVE_TX_PATH.exists():
        with LIVE_TX_PATH.open("w", newline="", encoding="utf-8") as f:
            csv.DictWriter(f, fieldnames=FIELDS).writeheader()


def append_transactions(rows: list[dict]) -> int:
    """Append validated transaction rows. Thread-safe. Returns count written."""
    if not rows:
        return 0
    _ensure_file()
    with _lock:
        with LIVE_TX_PATH.open("a", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=FIELDS)
            for r in rows:
                w.writerow({k: r.get(k, "") for k in FIELDS})
    return len(rows)


def count_live() -> int:
    """Number of live transactions queued (excludes header)."""
    if not LIVE_TX_PATH.exists():
        return 0
    with _lock:
        with LIVE_TX_PATH.open("r", encoding="utf-8") as f:
            return max(0, sum(1 for _ in f) - 1)


def clear_live() -> None:
    """Reset the live store (e.g. after a scan has consumed it)."""
    with _lock:
        if LIVE_TX_PATH.exists():
            LIVE_TX_PATH.unlink()
    _ensure_file()


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y/%m/%d %H:%M")

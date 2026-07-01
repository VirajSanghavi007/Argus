"""Small helpers for the /ingest endpoint."""

from datetime import datetime, timezone


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y/%m/%d %H:%M")

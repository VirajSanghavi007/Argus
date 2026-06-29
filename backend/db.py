"""
Persistence layer — SQLite for alerts and the analyst decision audit trail.

Design notes
------------
SQLite is used here for a zero-config, single-file store that ships with Python.
The schema is deliberately plain SQL so it maps 1:1 onto the Oracle Database that
Union Bank's Finacle core-banking stack runs in production — moving from this
prototype to the bank's environment is a connection-string change, not a rewrite.

Two tables:
  * alerts     — the current scan's detection output (replaced on each full scan).
  * decisions  — APPEND-ONLY audit log of every analyst action. Rows are never
                 updated or deleted; the "current" decision for an alert is simply
                 its most recent row. This gives an immutable, regulator-friendly
                 trail (FIU-IND / RBI audit requirements) of who decided what, when.

WAL journal mode is enabled so the background pipeline thread can write alerts
while request threads write decisions, without lock contention.
"""

import json
import logging
import sqlite3
import threading
from pathlib import Path

logger = logging.getLogger("uvicorn.error")

DATA_DIR = Path(__file__).parent.parent / "data"
DB_PATH = DATA_DIR / "argus.db"

# SQLite connections are not safe to share across threads by default. We guard a
# single module-level connection with a lock (check_same_thread=False + lock) so
# the background pipeline thread and FastAPI request threads can both use it.
_conn: sqlite3.Connection | None = None
_lock = threading.Lock()


SCHEMA = """
CREATE TABLE IF NOT EXISTS alerts (
    id           TEXT PRIMARY KEY,
    pattern_type TEXT,
    severity     TEXT,
    confidence   REAL,
    ml_score     REAL,
    total_moved  TEXT,
    node_count   INTEGER,
    txn_count    INTEGER,
    source       TEXT,
    payload      TEXT NOT NULL,           -- full serialized alert JSON
    scan_id      TEXT,
    created_at   TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS decisions (
    seq        INTEGER PRIMARY KEY AUTOINCREMENT,
    alert_id   TEXT NOT NULL,
    decision   TEXT NOT NULL,             -- confirm | review | dismiss
    reason     TEXT,
    analyst    TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_decisions_alert ON decisions(alert_id);
CREATE INDEX IF NOT EXISTS idx_decisions_timestamp ON decisions(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_decisions_analyst ON decisions(analyst);
CREATE INDEX IF NOT EXISTS idx_alerts_pattern  ON alerts(pattern_type);
CREATE INDEX IF NOT EXISTS idx_alerts_severity ON alerts(severity);
CREATE INDEX IF NOT EXISTS idx_alerts_source ON alerts(source);
CREATE INDEX IF NOT EXISTS idx_alerts_created ON alerts(created_at DESC);
"""


def init_db() -> None:
    """Create the database file and tables if they don't exist. Idempotent."""
    global _conn
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    _conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    _conn.row_factory = sqlite3.Row
    with _lock:
        _conn.execute("PRAGMA journal_mode=WAL;")
        _conn.executescript(SCHEMA)
        _conn.commit()
    logger.info(f"SQLite ready -> {DB_PATH}")


def _require_conn() -> sqlite3.Connection:
    if _conn is None:
        init_db()
    assert _conn is not None
    return _conn


# ── alerts ──────────────────────────────────────────────────────────────────

def replace_alerts(alerts: list[dict], scan_id: str = "") -> int:
    """Replace the alerts table with the current scan's output. Returns row count."""
    conn = _require_conn()
    with _lock:
        conn.execute("DELETE FROM alerts;")
        for a in alerts:
            conn.execute(
                """INSERT OR REPLACE INTO alerts
                   (id, pattern_type, severity, confidence, ml_score, total_moved,
                    node_count, txn_count, source, payload, scan_id)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    a["id"],
                    a.get("patternType"),
                    a.get("severity"),
                    a.get("confidence"),
                    a.get("mlScore"),
                    a.get("totalMoved"),
                    len(a.get("nodes", [])),
                    len(a.get("transactions", [])),
                    a.get("source", "labelled"),
                    json.dumps(a),
                    scan_id,
                ),
            )
        conn.commit()
    logger.info(f"Persisted {len(alerts)} alerts to SQLite (scan_id={scan_id or 'n/a'})")
    return len(alerts)


def load_alerts() -> dict:
    """Return {alert_id: full_alert_dict} from the DB. Empty dict if none."""
    conn = _require_conn()
    with _lock:
        rows = conn.execute("SELECT payload FROM alerts").fetchall()
    out: dict = {}
    for r in rows:
        a = json.loads(r["payload"])
        out[a["id"]] = a
    return out


def has_alerts() -> bool:
    conn = _require_conn()
    with _lock:
        return conn.execute("SELECT 1 FROM alerts LIMIT 1").fetchone() is not None


# ── decisions (append-only audit log) ───────────────────────────────────────

def record_decision(alert_id: str, decision: str, reason: str = "", analyst: str = "") -> None:
    """Append a decision to the immutable audit log. Never updates an existing row."""
    conn = _require_conn()
    with _lock:
        conn.execute(
            "INSERT INTO decisions (alert_id, decision, reason, analyst) VALUES (?,?,?,?)",
            (alert_id, decision, reason, analyst),
        )
        conn.commit()


def current_decisions() -> dict:
    """Return {alert_id: {decision, reason, analyst, created_at}} using the latest
    row per alert. This is the 'current state' view over the append-only log."""
    conn = _require_conn()
    with _lock:
        rows = conn.execute(
            """SELECT d.alert_id, d.decision, d.reason, d.analyst, d.created_at
               FROM decisions d
               JOIN (SELECT alert_id, MAX(seq) AS mx FROM decisions GROUP BY alert_id) m
                 ON d.alert_id = m.alert_id AND d.seq = m.mx"""
        ).fetchall()
    return {
        r["alert_id"]: {
            "decision": r["decision"], "reason": r["reason"],
            "analyst": r["analyst"], "created_at": r["created_at"],
        }
        for r in rows
    }


def decision_history(alert_id: str) -> list[dict]:
    """Full chronological audit trail for one alert (oldest first)."""
    conn = _require_conn()
    with _lock:
        rows = conn.execute(
            """SELECT decision, reason, analyst, created_at
               FROM decisions WHERE alert_id = ? ORDER BY seq ASC""",
            (alert_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def decision_counts() -> dict:
    """Aggregate current decisions by type — for dashboard tiles."""
    conn = _require_conn()
    with _lock:
        rows = conn.execute(
            """SELECT d.decision, COUNT(*) as cnt
               FROM decisions d
               JOIN (SELECT alert_id, MAX(seq) AS mx FROM decisions GROUP BY alert_id) m
                 ON d.alert_id = m.alert_id AND d.seq = m.mx
               GROUP BY d.decision"""
        ).fetchall()
    counts = {"confirm": 0, "review": 0, "dismiss": 0}
    for r in rows:
        if r["decision"] in counts:
            counts[r["decision"]] = r["cnt"]
    return counts

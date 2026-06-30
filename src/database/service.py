"""
Database service — SQLite persistence for alerts and decisions.
Separate from backend: owns schema, exposes operations.

TODO: PostgreSQL migration for production
  1. Replace sqlite3 with asyncpg or psycopg[binary]
  2. Use Render managed PostgreSQL (free tier available)
  3. Replace DB_PATH with DATABASE_URL env var (Render sets this automatically)
  4. Replace PRAGMA WAL with PostgreSQL connection pool (asyncpg.create_pool)
  5. Replace threading.Lock with connection pool concurrency
  6. Update schema.sql: INTEGER PRIMARY KEY AUTOINCREMENT → SERIAL PRIMARY KEY,
     DATETIME DEFAULT CURRENT_TIMESTAMP → TIMESTAMPTZ DEFAULT NOW()
"""

import hashlib
import json
import logging
import os
import secrets
import sqlite3
import threading
from datetime import datetime, timedelta, timezone

logger = logging.getLogger("uvicorn.error")

import config

_conn: sqlite3.Connection | None = None
_lock = threading.Lock()


def init_db() -> None:
    """Initialize database and schema. Idempotent."""
    global _conn
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    _conn = sqlite3.connect(config.DB_PATH, check_same_thread=False, timeout=10)
    _conn.row_factory = sqlite3.Row
    with _lock:
        _conn.execute("PRAGMA journal_mode=WAL;")
        _conn.execute("PRAGMA busy_timeout=5000;")
        if not config.SCHEMA_PATH.exists():
            raise FileNotFoundError(f"Schema file missing: {config.SCHEMA_PATH}")
        schema = config.SCHEMA_PATH.read_text()
        _conn.executescript(schema)
        _conn.commit()
    logger.info(f"SQLite ready -> {config.DB_PATH}")


def _require_conn() -> sqlite3.Connection:
    if _conn is None:
        init_db()
    assert _conn is not None
    return _conn


# ── Alerts ──────────────────────────────────────────────────────────────────

def replace_alerts(alerts: list[dict], scan_id: str = "") -> int:
    """Replace alerts table with current scan output."""
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
    logger.info(f"Persisted {len(alerts)} alerts (scan_id={scan_id or 'n/a'})")
    return len(alerts)


def load_alerts() -> dict:
    """Return {alert_id: full_alert_dict}."""
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


# ── Decisions (append-only audit log) ───────────────────────────────────────

def record_decision(alert_id: str, decision: str, reason: str = "", analyst: str = "") -> None:
    """Append decision to audit log."""
    conn = _require_conn()
    with _lock:
        conn.execute(
            "INSERT INTO decisions (alert_id, decision, reason, analyst) VALUES (?,?,?,?)",
            (alert_id, decision, reason, analyst),
        )
        conn.commit()


def current_decisions() -> dict:
    """Latest decision per alert from append-only log."""
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
            "decision": r["decision"],
            "reason": r["reason"],
            "analyst": r["analyst"],
            "created_at": r["created_at"],
        }
        for r in rows
    }


def decision_history(alert_id: str) -> list[dict]:
    """Chronological audit trail for one alert."""
    conn = _require_conn()
    with _lock:
        rows = conn.execute(
            """SELECT decision, reason, analyst, created_at
               FROM decisions WHERE alert_id = ? ORDER BY seq ASC""",
            (alert_id,),
        ).fetchall()
    return [dict(r) for r in rows]


# ── Auth ────────────────────────────────────────────────────────────────────

_SESSION_TTL_HOURS = 8


def _hash_password(password: str) -> str:
    salt = os.environ.get("ARGUS_SECRET", "argus-aml-2026")
    return hashlib.sha256(f"{salt}:{password}".encode()).hexdigest()


def seed_default_users() -> None:
    conn = _require_conn()
    defaults = [
        ("UBI-AML-2026", "admin", "admin123"),
        ("UBI-AML-2026", "analyst1", "analyst2026"),
        ("UBI-AML-2026", "demo", "demo2026"),
    ]
    with _lock:
        for company_id, username, password in defaults:
            pw_hash = _hash_password(password)
            conn.execute(
                "INSERT OR IGNORE INTO users (company_id, username, password_hash) VALUES (?,?,?)",
                (company_id, username, pw_hash),
            )
        conn.commit()


def verify_user(company_id: str, username: str, password: str) -> dict | None:
    conn = _require_conn()
    pw_hash = _hash_password(password)
    with _lock:
        row = conn.execute(
            "SELECT id, company_id, username, role FROM users WHERE company_id=? AND username=? AND password_hash=?",
            (company_id, username, pw_hash),
        ).fetchone()
    return dict(row) if row else None


def create_session(user_id: int, company_id: str, username: str) -> str:
    conn = _require_conn()
    token = secrets.token_urlsafe(32)
    expires = (datetime.now(timezone.utc) + timedelta(hours=_SESSION_TTL_HOURS)).strftime("%Y-%m-%dT%H:%M:%SZ")
    with _lock:
        conn.execute(
            "INSERT INTO sessions (token, user_id, company_id, username, expires_at) VALUES (?,?,?,?,?)",
            (token, user_id, company_id, username, expires),
        )
        conn.commit()
    return token


def validate_session(token: str) -> dict | None:
    conn = _require_conn()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with _lock:
        row = conn.execute(
            "SELECT user_id, company_id, username FROM sessions WHERE token=? AND expires_at > ?",
            (token, now),
        ).fetchone()
    return dict(row) if row else None


def delete_session(token: str) -> None:
    conn = _require_conn()
    with _lock:
        conn.execute("DELETE FROM sessions WHERE token=?", (token,))
        conn.commit()


def decision_counts() -> dict:
    """Current decision aggregate."""
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

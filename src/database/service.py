"""
Database service — dual-backend: PostgreSQL when DATABASE_URL is set, SQLite otherwise.

PostgreSQL is the production backend (Render / Supabase free tier).
SQLite is the local dev fallback so the app runs without any setup.

Usage:
  export DATABASE_URL=postgresql://user:pass@host:5432/argus
  # or for Supabase:
  export DATABASE_URL=postgresql://postgres:<password>@db.<project>.supabase.co:5432/postgres
"""

import hashlib
import json
import logging
import os
import secrets
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

logger = logging.getLogger("uvicorn.error")

import config

# ── Backend selection ────────────────────────────────────────────────────────

DATABASE_URL: str | None = os.environ.get("DATABASE_URL")
_USE_PG = bool(DATABASE_URL)

if _USE_PG:
    try:
        import psycopg2
        import psycopg2.extras
        import psycopg2.pool
        _PG_AVAILABLE = True
    except ImportError:
        logger.warning("psycopg2 not installed — falling back to SQLite. pip install psycopg2-binary")
        _USE_PG = False
        _PG_AVAILABLE = False
else:
    import sqlite3
    _PG_AVAILABLE = False

_lock = threading.Lock()

# ── PostgreSQL pool ──────────────────────────────────────────────────────────

_pg_pool = None


def _get_pg_pool():
    global _pg_pool
    if _pg_pool is None:
        _pg_pool = psycopg2.pool.ThreadedConnectionPool(
            minconn=1, maxconn=10, dsn=DATABASE_URL
        )
    return _pg_pool


class _PGConn:
    """Context manager — borrows a connection from the pool."""
    def __enter__(self):
        self._conn = _get_pg_pool().getconn()
        self._conn.autocommit = False
        return self._conn

    def __exit__(self, exc_type, exc, tb):
        if exc_type:
            self._conn.rollback()
        else:
            self._conn.commit()
        _get_pg_pool().putconn(self._conn)


# ── SQLite connection ────────────────────────────────────────────────────────

_sqlite_conn = None


def _get_sqlite():
    global _sqlite_conn
    if _sqlite_conn is None:
        config.DATA_DIR.mkdir(parents=True, exist_ok=True)
        _sqlite_conn = sqlite3.connect(config.DB_PATH, check_same_thread=False, timeout=10)
        _sqlite_conn.row_factory = sqlite3.Row
        _sqlite_conn.execute("PRAGMA journal_mode=WAL;")
        _sqlite_conn.execute("PRAGMA busy_timeout=5000;")
    return _sqlite_conn


# ── Schema init ──────────────────────────────────────────────────────────────

def init_db() -> None:
    """Initialize database and schema. Idempotent."""
    if _USE_PG:
        schema_path = Path(config.SCHEMA_PATH).parent / "schema_postgres.sql"
        if not schema_path.exists():
            raise FileNotFoundError(f"Postgres schema missing: {schema_path}")
        sql = schema_path.read_text()
        with _PGConn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql)
        logger.info(f"PostgreSQL ready -> {DATABASE_URL.split('@')[-1]}")
    else:
        conn = _get_sqlite()
        with _lock:
            schema = config.SCHEMA_PATH.read_text()
            conn.executescript(schema)
            conn.commit()
        logger.info(f"SQLite ready -> {config.DB_PATH}")


# ── Parameter placeholder helper ─────────────────────────────────────────────

def _ph(n: int) -> str:
    """Return n placeholders for the active backend: %s (PG) or ? (SQLite)."""
    ph = "%s" if _USE_PG else "?"
    return ", ".join([ph] * n)


# ── Alerts ───────────────────────────────────────────────────────────────────

def replace_alerts(alerts: list[dict], scan_id: str = "") -> int:
    if _USE_PG:
        with _PGConn() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM alerts;")
                for a in alerts:
                    cur.execute(
                        f"INSERT INTO alerts (id,pattern_type,severity,confidence,ml_score,"
                        f"total_moved,node_count,txn_count,source,payload,scan_id) "
                        f"VALUES ({_ph(11)}) ON CONFLICT(id) DO UPDATE SET payload=EXCLUDED.payload",
                        (a["id"], a.get("patternType"), a.get("severity"), a.get("confidence"),
                         a.get("mlScore"), a.get("totalMoved"), len(a.get("nodes", [])),
                         len(a.get("transactions", [])), a.get("source","labelled"),
                         json.dumps(a), scan_id)
                    )
    else:
        conn = _get_sqlite()
        with _lock:
            conn.execute("DELETE FROM alerts;")
            for a in alerts:
                conn.execute(
                    "INSERT OR REPLACE INTO alerts "
                    "(id,pattern_type,severity,confidence,ml_score,total_moved,"
                    "node_count,txn_count,source,payload,scan_id) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (a["id"], a.get("patternType"), a.get("severity"), a.get("confidence"),
                     a.get("mlScore"), a.get("totalMoved"), len(a.get("nodes", [])),
                     len(a.get("transactions", [])), a.get("source","labelled"),
                     json.dumps(a), scan_id)
                )
            conn.commit()
    logger.info(f"Persisted {len(alerts)} alerts (scan_id={scan_id or 'n/a'})")
    return len(alerts)


def load_alerts() -> dict:
    if _USE_PG:
        with _PGConn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("SELECT payload FROM alerts")
                rows = cur.fetchall()
    else:
        conn = _get_sqlite()
        with _lock:
            rows = conn.execute("SELECT payload FROM alerts").fetchall()
    return {(a := json.loads(r["payload"]))["id"]: a for r in rows}


def has_alerts() -> bool:
    if _USE_PG:
        with _PGConn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1 FROM alerts LIMIT 1")
                return cur.fetchone() is not None
    else:
        conn = _get_sqlite()
        with _lock:
            return conn.execute("SELECT 1 FROM alerts LIMIT 1").fetchone() is not None


# ── Decisions ────────────────────────────────────────────────────────────────

def record_decision(alert_id: str, decision: str, reason: str = "", analyst: str = "") -> None:
    ph = _ph(4)
    sql = f"INSERT INTO decisions (alert_id,decision,reason,analyst) VALUES ({ph})"
    if _USE_PG:
        with _PGConn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (alert_id, decision, reason, analyst))
    else:
        conn = _get_sqlite()
        with _lock:
            conn.execute(sql, (alert_id, decision, reason, analyst))
            conn.commit()


def current_decisions() -> dict:
    sql = """
        SELECT d.alert_id, d.decision, d.reason, d.analyst, d.created_at
        FROM decisions d
        JOIN (SELECT alert_id, MAX(seq) AS mx FROM decisions GROUP BY alert_id) m
          ON d.alert_id = m.alert_id AND d.seq = m.mx
    """
    if _USE_PG:
        with _PGConn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql)
                rows = cur.fetchall()
    else:
        conn = _get_sqlite()
        with _lock:
            rows = conn.execute(sql).fetchall()
    return {
        r["alert_id"]: {
            "decision": r["decision"], "reason": r["reason"],
            "analyst": r["analyst"], "created_at": str(r["created_at"]),
        }
        for r in rows
    }


def decision_history(alert_id: str) -> list[dict]:
    ph = "%s" if _USE_PG else "?"
    sql = f"SELECT decision,reason,analyst,created_at FROM decisions WHERE alert_id={ph} ORDER BY seq ASC"
    if _USE_PG:
        with _PGConn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql, (alert_id,))
                rows = cur.fetchall()
    else:
        conn = _get_sqlite()
        with _lock:
            rows = conn.execute(sql, (alert_id,)).fetchall()
    return [dict(r) for r in rows]


def decision_counts() -> dict:
    sql = """
        SELECT d.decision, COUNT(*) as cnt
        FROM decisions d
        JOIN (SELECT alert_id, MAX(seq) AS mx FROM decisions GROUP BY alert_id) m
          ON d.alert_id = m.alert_id AND d.seq = m.mx
        GROUP BY d.decision
    """
    if _USE_PG:
        with _PGConn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql)
                rows = cur.fetchall()
    else:
        conn = _get_sqlite()
        with _lock:
            rows = conn.execute(sql).fetchall()
    counts = {"confirm": 0, "review": 0, "dismiss": 0}
    for r in rows:
        if r["decision"] in counts:
            counts[r["decision"]] = r["cnt"]
    return counts


# ── Live transaction ingestion (Postgres only) ────────────────────────────────

def store_live_transactions(rows: list[dict]) -> int:
    """Store ingested transactions in Postgres for neighborhood rescoring."""
    if not _USE_PG:
        return 0  # CSV fallback handled by ingest_store.py
    if not rows:
        return 0
    with _PGConn() as conn:
        with conn.cursor() as cur:
            for r in rows:
                cur.execute(
                    f"INSERT INTO live_transactions "
                    f"(timestamp,from_bank,from_account,to_bank,to_account,"
                    f"amount_paid,amount_received,payment_currency,receiving_currency,payment_format) "
                    f"VALUES ({_ph(10)})",
                    (r.get("Timestamp"), r["From Bank"], r["From Account"],
                     r["To Bank"], r["To Account"], r["Amount Paid"],
                     r.get("Amount Received"), r.get("Payment Currency","US Dollar"),
                     r.get("Receiving Currency","US Dollar"), r.get("Payment Format","ACH"))
                )
    return len(rows)


def fetch_unscanned_transactions() -> list[dict]:
    """Return all live_transactions not yet scored."""
    if not _USE_PG:
        return []
    with _PGConn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM live_transactions WHERE scanned=FALSE ORDER BY ingested_at")
            return [dict(r) for r in cur.fetchall()]


def mark_transactions_scanned(ids: list[int]) -> None:
    if not _USE_PG or not ids:
        return
    with _PGConn() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE live_transactions SET scanned=TRUE WHERE id = ANY(%s)", (ids,))


# ── Auth ──────────────────────────────────────────────────────────────────────

_SESSION_TTL_HOURS = 8


def _hash_password(password: str) -> str:
    salt = os.environ.get("ARGUS_SECRET", "argus-aml-2026")
    return hashlib.sha256(f"{salt}:{password}".encode()).hexdigest()


def seed_default_users() -> None:
    defaults = [
        ("UBI-AML-2026", "admin", "admin123"),
        ("UBI-AML-2026", "analyst1", "analyst2026"),
        ("UBI-AML-2026", "demo", "demo2026"),
    ]
    for company_id, username, password in defaults:
        pw_hash = _hash_password(password)
        if _USE_PG:
            with _PGConn() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "INSERT INTO users (company_id,username,password_hash) VALUES (%s,%s,%s) ON CONFLICT DO NOTHING",
                        (company_id, username, pw_hash)
                    )
        else:
            conn = _get_sqlite()
            with _lock:
                conn.execute(
                    "INSERT OR IGNORE INTO users (company_id,username,password_hash) VALUES (?,?,?)",
                    (company_id, username, pw_hash)
                )
            conn.commit()


def verify_user(company_id: str, username: str, password: str) -> dict | None:
    pw_hash = _hash_password(password)
    ph = "%s" if _USE_PG else "?"
    sql = f"SELECT id,company_id,username,role FROM users WHERE company_id={ph} AND username={ph} AND password_hash={ph}"
    if _USE_PG:
        with _PGConn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql, (company_id, username, pw_hash))
                row = cur.fetchone()
                return dict(row) if row else None
    else:
        conn = _get_sqlite()
        with _lock:
            row = conn.execute(sql, (company_id, username, pw_hash)).fetchone()
        return dict(row) if row else None


def create_session(user_id: int, company_id: str, username: str) -> str:
    token = secrets.token_urlsafe(32)
    expires = datetime.now(timezone.utc) + timedelta(hours=_SESSION_TTL_HOURS)
    if _USE_PG:
        with _PGConn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO sessions (token,user_id,company_id,username,expires_at) VALUES (%s,%s,%s,%s,%s)",
                    (token, user_id, company_id, username, expires)
                )
    else:
        expires_str = expires.strftime("%Y-%m-%dT%H:%M:%SZ")
        conn = _get_sqlite()
        with _lock:
            conn.execute(
                "INSERT INTO sessions (token,user_id,company_id,username,expires_at) VALUES (?,?,?,?,?)",
                (token, user_id, company_id, username, expires_str)
            )
            conn.commit()
    return token


def validate_session(token: str) -> dict | None:
    if _USE_PG:
        with _PGConn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    "SELECT user_id,company_id,username FROM sessions WHERE token=%s AND expires_at > NOW()",
                    (token,)
                )
                row = cur.fetchone()
                return dict(row) if row else None
    else:
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        conn = _get_sqlite()
        with _lock:
            row = conn.execute(
                "SELECT user_id,company_id,username FROM sessions WHERE token=? AND expires_at > ?",
                (token, now)
            ).fetchone()
        return dict(row) if row else None


def delete_session(token: str) -> None:
    ph = "%s" if _USE_PG else "?"
    sql = f"DELETE FROM sessions WHERE token={ph}"
    if _USE_PG:
        with _PGConn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (token,))
    else:
        conn = _get_sqlite()
        with _lock:
            conn.execute(sql, (token,))
            conn.commit()

-- Argus AML Detection — SQLite Schema
-- Two-table design: alerts (current scan) + decisions (append-only audit log)

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

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_decisions_alert ON decisions(alert_id);
CREATE INDEX IF NOT EXISTS idx_decisions_timestamp ON decisions(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_decisions_analyst ON decisions(analyst);
CREATE INDEX IF NOT EXISTS idx_alerts_pattern  ON alerts(pattern_type);
CREATE INDEX IF NOT EXISTS idx_alerts_severity ON alerts(severity);
CREATE INDEX IF NOT EXISTS idx_alerts_source ON alerts(source);
CREATE INDEX IF NOT EXISTS idx_alerts_created ON alerts(created_at DESC);

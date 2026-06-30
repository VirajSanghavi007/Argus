-- Argus AML Detection — PostgreSQL Schema
-- Drop-in replacement for schema.sql when DATABASE_URL is set.

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
    payload      TEXT NOT NULL,
    scan_id      TEXT,
    created_at   TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS decisions (
    seq        SERIAL PRIMARY KEY,
    alert_id   TEXT NOT NULL,
    decision   TEXT NOT NULL,
    reason     TEXT,
    analyst    TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS users (
    id            SERIAL PRIMARY KEY,
    company_id    TEXT NOT NULL,
    username      TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    role          TEXT DEFAULT 'analyst',
    created_at    TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(company_id, username)
);

CREATE TABLE IF NOT EXISTS sessions (
    token      TEXT PRIMARY KEY,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    company_id TEXT NOT NULL,
    username   TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL
);

-- Live ingestion queue (transactions POSTed via /ingest, pending next scan)
CREATE TABLE IF NOT EXISTS live_transactions (
    id               SERIAL PRIMARY KEY,
    timestamp        TIMESTAMPTZ,
    from_bank        TEXT NOT NULL,
    from_account     TEXT NOT NULL,
    to_bank          TEXT NOT NULL,
    to_account       TEXT NOT NULL,
    amount_paid      REAL NOT NULL,
    amount_received  REAL,
    payment_currency TEXT DEFAULT 'US Dollar',
    receiving_currency TEXT DEFAULT 'US Dollar',
    payment_format   TEXT DEFAULT 'ACH',
    ingested_at      TIMESTAMPTZ DEFAULT NOW(),
    scanned          BOOLEAN DEFAULT FALSE
);

CREATE INDEX IF NOT EXISTS idx_decisions_alert    ON decisions(alert_id);
CREATE INDEX IF NOT EXISTS idx_decisions_ts       ON decisions(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_alerts_pattern     ON alerts(pattern_type);
CREATE INDEX IF NOT EXISTS idx_alerts_severity    ON alerts(severity);
CREATE INDEX IF NOT EXISTS idx_alerts_created     ON alerts(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_sessions_token     ON sessions(token);
CREATE INDEX IF NOT EXISTS idx_sessions_expires   ON sessions(expires_at);
CREATE INDEX IF NOT EXISTS idx_live_tx_scanned    ON live_transactions(scanned, ingested_at);

# Database Service Layer — Comprehensive Documentation

**Location:** `src/database/`  
**Technology:** SQLite + Python  
**Schema File:** `src/database/schemas/schema.sql`  
**Service File:** `src/database/service.py`  
**Mode:** WAL (Write-Ahead Logging) for concurrent access

---

## Overview

The database service is a **separate persistence layer** that:
- Owns the database schema (single source of truth)
- Provides thread-safe operations via RLock
- Handles alert storage and querying
- Maintains append-only decision audit trail
- Supports concurrent reads/writes from pipeline and API handlers

**Key Design Principle:** Database is a **client** to the backend, not embedded within it. Backend imports and uses database functions, not the other way around.

---

## Architecture

```
src/database/
├── __init__.py              # Package marker (empty or minimal)
├── service.py               # All persistence functions
└── schemas/
    └── schema.sql           # Database schema (source of truth)
```

**Separation of Concerns:**
```
Frontend ↔ Backend API ↔ Database Service ↔ SQLite File (data/argus.db)
                         (independent module)
```

Backend's `core/db.py` is a thin **client** that delegates to `database.service`:
```python
# src/backend/core/db.py
from database import service

init_db = service.init_db
replace_alerts = service.replace_alerts
load_alerts = service.load_alerts
# ... etc
```

---

## Database Schema

**File:** `src/database/schemas/schema.sql`

```sql
-- ──── ALERTS TABLE ────────────────────────────────────────────────────
CREATE TABLE alerts (
  id TEXT PRIMARY KEY,
  nodes JSON NOT NULL,
  edges JSON NOT NULL,
  pattern_type TEXT NOT NULL,
  confidence REAL NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
  severity TEXT NOT NULL CHECK (severity IN ('critical', 'high', 'medium', 'low')),
  time_span_seconds INTEGER,
  total_amount REAL,
  source TEXT NOT NULL CHECK (source IN ('labelled', 'unlabelled')),
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ──── DECISIONS TABLE (APPEND-ONLY AUDIT LOG) ──────────────────────
CREATE TABLE decisions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  alert_id TEXT NOT NULL,
  decision_type TEXT NOT NULL CHECK (decision_type IN ('confirm', 'review', 'dismiss')),
  reason TEXT,
  analyst TEXT DEFAULT 'system',
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY(alert_id) REFERENCES alerts(id)
);

-- ──── INDEXES (FOR QUERY PERFORMANCE) ──────────────────────────────
CREATE INDEX IF NOT EXISTS idx_alerts_pattern ON alerts(pattern_type);
CREATE INDEX IF NOT EXISTS idx_alerts_severity ON alerts(severity);
CREATE INDEX IF NOT EXISTS idx_alerts_source ON alerts(source);
CREATE INDEX IF NOT EXISTS idx_decisions_alert_id ON decisions(alert_id);
CREATE INDEX IF NOT EXISTS idx_decisions_decision_type ON decisions(decision_type);
```

### Table Details

#### `alerts` Table
Immutable snapshot of detected suspicious transactions.

| Column | Type | Constraints | Purpose |
|--------|------|-----------|---------|
| `id` | TEXT | PRIMARY KEY, NOT NULL | Unique alert ID (UUID) |
| `nodes` | JSON | NOT NULL | Array of account objects with bank, role, severity |
| `edges` | JSON | NOT NULL | Array of transaction objects with src, dst, amount, timestamp |
| `pattern_type` | TEXT | NOT NULL | FAN_OUT, FAN_IN, CYCLE, etc. |
| `confidence` | REAL | [0, 1], NOT NULL | ML model confidence score |
| `severity` | TEXT | CHECK in (critical, high, medium, low) | Risk level |
| `time_span_seconds` | INTEGER | NULL | Duration of the alert pattern |
| `total_amount` | REAL | NULL | Sum of all transaction amounts in alert |
| `source` | TEXT | CHECK in (labelled, unlabelled) | Whether alert came from training data or inference |
| `created_at` | TIMESTAMP | DEFAULT CURRENT_TIMESTAMP | When alert was created |

**Example Alert Record:**
```json
{
  "id": "e8f9a1c2-3d4e-5f6a-7b8c-9d0e1f2a3b4c",
  "nodes": [
    {"node_id": "acct-001", "bank": "JPMORGAN_CHASE", "role": "source", "severity": "high"},
    {"node_id": "acct-002", "bank": "WELLS_FARGO", "role": "destination", "severity": "medium"}
  ],
  "edges": [
    {"src": "acct-001", "dst": "acct-002", "amount": 50000.0, "timestamp": "2026-06-29T10:30:00Z"}
  ],
  "pattern_type": "FAN_OUT",
  "confidence": 0.94,
  "severity": "high",
  "time_span_seconds": 3600,
  "total_amount": 50000.0,
  "source": "unlabelled",
  "created_at": "2026-06-29T10:35:00Z"
}
```

#### `decisions` Table
Append-only audit trail of analyst decisions. **Never modified or deleted—only appended.**

| Column | Type | Constraints | Purpose |
|--------|------|-----------|---------|
| `id` | INTEGER | PRIMARY KEY AUTOINCREMENT | Auto-incrementing record ID |
| `alert_id` | TEXT | NOT NULL, FOREIGN KEY | Links to alert |
| `decision_type` | TEXT | CHECK in (confirm, review, dismiss) | Analyst's determination |
| `reason` | TEXT | NULL | Explanation for decision |
| `analyst` | TEXT | DEFAULT 'system' | Who made the decision |
| `created_at` | TIMESTAMP | DEFAULT CURRENT_TIMESTAMP | When decision was made |

**Example Decision Records:**
```sql
-- Timeline of decisions on same alert
SELECT * FROM decisions WHERE alert_id = 'e8f9a1c2-3d4e-5f6a-7b8c-9d0e1f2a3b4c'
ORDER BY created_at;

id | alert_id | decision_type | reason | analyst | created_at
---+----------+---------------+-----------+-----------+--------------------
1  | e8f9... | review | Initial review required | analyst1@bank.com | 2026-06-29 10:40:00
2  | e8f9... | confirm | Confirmed suspicious pattern | analyst2@bank.com | 2026-06-29 11:15:00
```

---

## Service Module

**File:** `src/database/service.py`

### Global Variables

```python
import sqlite3
import threading
from pathlib import Path
import json

# Database file location
DB_PATH = Path(__file__).parent.parent / "data" / "argus.db"
SCHEMA_PATH = Path(__file__).parent / "schemas" / "schema.sql"

# Thread-safe access
DB_LOCK = threading.RLock()  # Reentrant lock
_connection = None  # Cached connection
```

### Functions

#### Initialization

##### `init_db()`
**Purpose:** Create database file and schema on startup.

```python
def init_db():
    """
    Initialize database: create tables and indexes from schema.sql.
    Safe to call multiple times (idempotent).
    """
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    
    with DB_LOCK:
        conn = sqlite3.connect(str(DB_PATH))
        conn.execute("PRAGMA journal_mode=WAL")  # Write-Ahead Logging
        
        with open(SCHEMA_PATH) as f:
            schema = f.read()
        conn.executescript(schema)
        
        conn.commit()
        conn.close()
```

**When Called:** Application startup (in backend lifespan event)  
**Side Effects:** Creates `data/argus.db`, sets WAL mode, creates tables + indexes  
**Returns:** None  
**Exceptions:** `sqlite3.Error` if schema is invalid

---

#### Alert Operations

##### `replace_alerts(alerts: list[dict]) -> None`
**Purpose:** Bulk replace all alerts (used after each scan).

```python
def replace_alerts(alerts: list[dict]) -> None:
    """
    Atomically delete all existing alerts and insert new ones.
    Preserves decisions table (append-only).
    
    Args:
        alerts: List of alert dicts with keys:
            id, nodes, edges, pattern_type, confidence, severity,
            time_span_seconds, total_amount, source
    """
    with DB_LOCK:
        conn = _get_connection()
        conn.execute("DELETE FROM alerts")
        
        for alert in alerts:
            conn.execute(
                """
                INSERT INTO alerts (id, nodes, edges, pattern_type, 
                    confidence, severity, time_span_seconds, 
                    total_amount, source)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    alert['id'],
                    json.dumps(alert['nodes']),
                    json.dumps(alert['edges']),
                    alert['pattern_type'],
                    alert['confidence'],
                    alert['severity'],
                    alert.get('time_span_seconds'),
                    alert.get('total_amount'),
                    alert['source']
                )
            )
        
        conn.commit()
```

**When Called:** After ML pipeline scan completes (POST /scan)  
**Parameters:** List of alert dicts (from `detection.py`)  
**Returns:** None  
**Side Effects:** Deletes old alerts, inserts new ones  
**Thread Safety:** RLock prevents concurrent writes

---

##### `load_alerts(filters: dict = None) -> list[dict]`
**Purpose:** Query alerts with optional filtering.

```python
def load_alerts(filters: dict = None) -> list[dict]:
    """
    Load alerts from database with optional filtering.
    
    Args:
        filters: Dict with optional keys:
            - pattern_type: str (e.g., 'FAN_OUT')
            - severity: str (e.g., 'high')
            - source: str (e.g., 'unlabelled')
            - limit: int (default 1000)
            - offset: int (default 0)
    
    Returns:
        List of alert dicts with JSON fields parsed
    """
    filters = filters or {}
    query = "SELECT * FROM alerts WHERE 1=1"
    params = []
    
    if 'pattern_type' in filters:
        query += " AND pattern_type = ?"
        params.append(filters['pattern_type'])
    
    if 'severity' in filters:
        query += " AND severity = ?"
        params.append(filters['severity'])
    
    if 'source' in filters:
        query += " AND source = ?"
        params.append(filters['source'])
    
    query += " ORDER BY created_at DESC"
    
    limit = filters.get('limit', 1000)
    offset = filters.get('offset', 0)
    query += " LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    
    with DB_LOCK:
        conn = _get_connection()
        cursor = conn.execute(query, params)
        rows = cursor.fetchall()
    
    # Convert to dicts, parse JSON
    alerts = []
    for row in rows:
        alert = dict(row)
        alert['nodes'] = json.loads(alert['nodes'])
        alert['edges'] = json.loads(alert['edges'])
        alerts.append(alert)
    
    return alerts
```

**When Called:** GET /alerts endpoint  
**Parameters:** Optional filters (pattern_type, severity, source, limit, offset)  
**Returns:** List of alert dicts (JSON fields parsed)  
**Thread Safety:** RLock prevents dirty reads  
**Example:**
```python
alerts = load_alerts({'pattern_type': 'FAN_OUT', 'limit': 50})
```

---

##### `has_alerts() -> bool`
**Purpose:** Check if database contains any alerts.

```python
def has_alerts() -> bool:
    """Returns True if alerts table is not empty."""
    with DB_LOCK:
        conn = _get_connection()
        cursor = conn.execute("SELECT COUNT(*) FROM alerts")
        count = cursor.fetchone()[0]
    return count > 0
```

**When Called:** Health check endpoint  
**Returns:** Boolean  
**Performance:** O(1) with index

---

#### Decision Operations

##### `record_decision(alert_id: str, decision: str, reason: str = "", analyst: str = "system") -> int`
**Purpose:** Log an analyst decision (append-only).

```python
def record_decision(
    alert_id: str,
    decision: str,
    reason: str = "",
    analyst: str = "system"
) -> int:
    """
    Record an analyst decision for an alert.
    Appends to decisions table (never modifies existing records).
    
    Args:
        alert_id: UUID of alert
        decision: 'confirm', 'review', or 'dismiss'
        reason: Optional explanation
        analyst: Who made the decision (defaults to 'system')
    
    Returns:
        ID of inserted decision record
    
    Raises:
        ValueError: If decision not in valid set
        sqlite3.IntegrityError: If alert_id doesn't exist
    """
    if decision not in ('confirm', 'review', 'dismiss'):
        raise ValueError(f"Invalid decision: {decision}")
    
    with DB_LOCK:
        conn = _get_connection()
        cursor = conn.execute(
            """
            INSERT INTO decisions (alert_id, decision_type, reason, analyst)
            VALUES (?, ?, ?, ?)
            """,
            (alert_id, decision, reason, analyst)
        )
        conn.commit()
        return cursor.lastrowid
```

**When Called:** POST /alerts/{id}/decision endpoint  
**Side Effects:** Appends row to decisions table  
**Returns:** Row ID of inserted decision  
**Append-Only:** Never modifies or deletes existing decisions

---

##### `current_decisions() -> dict`
**Purpose:** Get latest decision for each alert.

```python
def current_decisions() -> dict:
    """
    Get the most recent decision for each alert.
    
    Returns:
        Dict: { alert_id: decision_type, ... }
        Example: { 'alert-123': 'confirm', 'alert-456': None }
    """
    query = """
    SELECT alert_id, decision_type FROM (
        SELECT alert_id, decision_type,
               ROW_NUMBER() OVER (PARTITION BY alert_id ORDER BY created_at DESC) as rn
        FROM decisions
    )
    WHERE rn = 1
    """
    
    with DB_LOCK:
        conn = _get_connection()
        cursor = conn.execute(query)
        rows = cursor.fetchall()
    
    # Build dict
    result = {}
    for alert_id, decision_type in rows:
        result[alert_id] = decision_type
    
    return result
```

**When Called:** GET /decisions endpoint, GET /status endpoint  
**Returns:** Dict of { alert_id → latest decision_type }  
**Handles:** Multiple decisions per alert (returns most recent)

---

##### `decision_history(alert_id: str) -> list[dict]`
**Purpose:** Get full audit trail of decisions for one alert.

```python
def decision_history(alert_id: str) -> list[dict]:
    """
    Get all decisions for an alert in chronological order.
    
    Args:
        alert_id: UUID of alert
    
    Returns:
        List of decision dicts: [
            {
                'id': 1,
                'decision_type': 'review',
                'reason': '...',
                'analyst': '...',
                'created_at': '2026-06-29T10:40:00'
            },
            ...
        ]
    """
    query = """
    SELECT id, alert_id, decision_type, reason, analyst, created_at
    FROM decisions
    WHERE alert_id = ?
    ORDER BY created_at ASC
    """
    
    with DB_LOCK:
        conn = _get_connection()
        cursor = conn.execute(query, (alert_id,))
        rows = cursor.fetchall()
    
    return [dict(row) for row in rows]
```

**When Called:** GET /alerts/{id}/decision/history endpoint  
**Returns:** List of decision dicts (chronological order)  
**Use Case:** Audit trail display

---

##### `decision_counts() -> dict`
**Purpose:** Count decisions by type (for status dashboard).

```python
def decision_counts() -> dict:
    """
    Aggregate counts of decisions.
    
    Returns:
        Dict: {
            'confirmed': int,
            'reviewed': int,
            'dismissed': int,
            'pending': int (alerts with no decision)
        }
    """
    with DB_LOCK:
        conn = _get_connection()
        
        # Count by decision type
        cursor = conn.execute("""
            SELECT decision_type, COUNT(DISTINCT alert_id) as count
            FROM decisions
            GROUP BY decision_type
        """)
        decision_counts = {row[0]: row[1] for row in cursor.fetchall()}
        
        # Count alerts with no decision
        cursor = conn.execute("""
            SELECT COUNT(*) FROM alerts a
            WHERE NOT EXISTS (SELECT 1 FROM decisions d WHERE d.alert_id = a.id)
        """)
        pending = cursor.fetchone()[0]
    
    return {
        'confirmed': decision_counts.get('confirm', 0),
        'reviewed': decision_counts.get('review', 0),
        'dismissed': decision_counts.get('dismiss', 0),
        'pending': pending
    }
```

**When Called:** GET /status endpoint  
**Returns:** Dict with counts by decision type  
**Use Case:** Dashboard summary cards

---

### Helper Functions

#### `_get_connection() -> sqlite3.Connection`
**Purpose:** Get or create cached database connection.

```python
def _get_connection() -> sqlite3.Connection:
    """
    Get cached connection, or create one if missing.
    Must be called within DB_LOCK context.
    """
    global _connection
    
    if _connection is None:
        _connection = sqlite3.connect(str(DB_PATH))
        _connection.row_factory = sqlite3.Row  # Return rows as dicts
        _connection.execute("PRAGMA foreign_keys = ON")  # Enable FK constraints
        _connection.execute("PRAGMA journal_mode = WAL")  # Write-Ahead Logging
    
    return _connection
```

**Caching:** Single connection reused across all operations (thread-safe via RLock)  
**Features:** Row factory for dict-like access, foreign keys enabled, WAL mode

---

## Concurrency & Thread Safety

### RLock (Reentrant Lock)
```python
DB_LOCK = threading.RLock()  # Can be acquired multiple times by same thread
```

**Why RLock?** Allows nested lock acquisition:
```python
def outer():
    with DB_LOCK:
        inner()  # Same thread can acquire again

def inner():
    with DB_LOCK:  # No deadlock
        conn.execute(...)
```

### WAL Mode
```python
conn.execute("PRAGMA journal_mode=WAL")
```

**Benefits:**
- Concurrent reads while writes are in progress
- Faster writes (append-only log)
- Atomic transactions

---

## Integration with Backend

### Backend Delegation Pattern
**File:** `src/backend/core/db.py`

```python
from database import service

# Backend exposes service functions as module-level functions
init_db = service.init_db
replace_alerts = service.replace_alerts
load_alerts = service.load_alerts
has_alerts = service.has_alerts
record_decision = service.record_decision
current_decisions = service.current_decisions
decision_history = service.decision_history
decision_counts = service.decision_counts
```

**Why?** Backward compatibility. All existing imports still work:
```python
from backend.core import db
db.init_db()  # Actually calls database.service.init_db()
```

---

## Data Lifecycle

```
1. SCAN
   └─ ML Pipeline detects suspicious transactions
   └─ Outputs alert JSON objects

2. PERSIST
   └─ Backend calls db.replace_alerts(alerts)
   └─ Database deletes old alerts, inserts new ones

3. QUERY
   └─ Frontend requests GET /alerts
   └─ Backend calls db.load_alerts(filters)
   └─ Database returns filtered alert list

4. ANALYZE
   └─ Analyst reviews alert in Investigate tab

5. DECIDE
   └─ Analyst clicks "Confirm" button
   └─ Frontend POSTs to /alerts/{id}/decision
   └─ Backend calls db.record_decision(...)
   └─ Database appends to decisions table (immutable)

6. AUDIT
   └─ Analyst clicks decision history
   └─ Backend calls db.decision_history(alert_id)
   └─ Database returns chronological list of decisions
```

---

## Backup & Maintenance

### WAL Files
WAL mode creates additional files:
```
data/argus.db       # Main database file
data/argus.db-wal   # Write-ahead log
data/argus.db-shm   # Shared memory file
```

**All three files must be backed up together.**

### Checkpoint
```python
# Periodically merge WAL into main file
conn.execute("PRAGMA wal_checkpoint(RESTART)")
```

---

## Query Examples

### Query: Find all FAN_OUT alerts with HIGH severity
```python
results = load_alerts({
    'pattern_type': 'FAN_OUT',
    'severity': 'high',
    'limit': 50
})
```

### Query: Get decision audit trail for alert
```python
history = decision_history('alert-uuid-123')
for decision in history:
    print(f"{decision['analyst']} → {decision['decision_type']}: {decision['reason']}")
```

### Query: Dashboard summary
```python
counts = decision_counts()
print(f"Confirmed: {counts['confirmed']}, Pending: {counts['pending']}")
```

---

## Performance Characteristics

| Operation | Complexity | Notes |
|-----------|-----------|-------|
| `init_db()` | O(1) | One-time setup |
| `replace_alerts(n)` | O(n) | Deletes all, inserts n |
| `load_alerts()` | O(k log n) | k = result set, indexes used |
| `has_alerts()` | O(1) | COUNT with index |
| `record_decision()` | O(1) | Single row insert |
| `current_decisions()` | O(d) | d = distinct decisions |
| `decision_history()` | O(d) | d = decisions for alert |
| `decision_counts()` | O(d) | d = total decisions |

---

## Future Enhancements

- [ ] Database migrations in `src/database/migrations/`
- [ ] Connection pooling for high-concurrency scenarios
- [ ] Read replicas for analytics
- [ ] Compression of old alerts
- [ ] Time-series retention policies
- [ ] Backup automation (S3, etc.)

---

**End of Database Service Documentation**

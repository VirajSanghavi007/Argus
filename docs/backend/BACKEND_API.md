# Backend API Layer — Comprehensive Documentation

**File:** `src/backend/api/main.py`  
**Technology:** FastAPI + Uvicorn  
**Port:** 8000  
**Lines of Code:** 574  

---

## Overview

The backend API layer is the central hub that:
- Validates incoming HTTP requests
- Coordinates business logic
- Delegates database operations
- Manages whitelist filtering
- Runs the ML pipeline asynchronously
- Serves the React frontend (SPA with fallback routing)

---

## Core Dependencies

```python
# Framework & Async
fastapi            # Web framework
uvicorn            # ASGI server
asyncio            # Async runtime
threading          # Background tasks

# Validation & Serialization
pydantic           # Request/response schemas
json               # JSON handling

# Middleware & Security
fastapi.middleware.cors.CORSMiddleware  # Cross-origin requests
slowapi             # Rate limiting (100 req/min)

# Static Files
fastapi.staticfiles.StaticFiles         # Serve frontend
fastapi.responses.FileResponse          # SPA routing

# Context & Tracking
contextvars.ContextVar  # Request context (request_id)
uuid                    # Unique ID generation
hashlib.md5             # ETag generation for caching

# External Modules (imported from sibling packages)
backend.core.db        # Database operations (delegates to database.service)
backend.core.whitelist # Exemption filtering
backend.pipeline       # ML detection pipeline
backend.models         # Multi-GNN model
backend.utils.logging  # Structured logging
```

---

## Global State & Configuration

### Paths & Directories
```python
DATA_DIR = Path(__file__).parent.parent / "data"
LOGS_DIR = Path(__file__).parent.parent / "logs"
CACHE_PATH = DATA_DIR / "pipeline_cache.json"
DRIFT_LOG = DATA_DIR / "drift_log.json"
MODEL_PATH = DATA_DIR / "multignn_model.pt"
FRONTEND_DIST = Path(__file__).parent.parent / "frontend" / "dist"
FRONTEND_PUBLIC = Path(__file__).parent.parent / "frontend" / "public"
```

### Constants
```python
MULTIGNN_MAX_ROWS = 600_000  # Max transactions per scan
DECISION_THRESHOLD = 0.5      # Confidence threshold
```

### Concurrency & Synchronization
```python
ALERTS: dict = {}             # In-memory alert cache
SUPPRESSED: dict = {}         # Suppressed (whitelist-filtered) alerts
DECISIONS: dict = {}          # Decision audit state
ALERTS_LOCK = threading.RLock()  # Thread-safe locking
ALERTS_ETAG = ""              # Cache hash (for GET /alerts)
PIPELINE_READY = threading.Event()  # Signal when pipeline loads
PIPELINE_ERROR: str = ""      # Error message if pipeline fails
PIPELINE_START_TIME = 0.0     # Timestamp of last scan start
ML_METRICS: dict = {}         # Model performance metrics
```

### Request Tracking
```python
logger: logging.Logger = logging.getLogger("uvicorn.error")
request_id: ContextVar[str] = ContextVar("request_id", default="")
```

---

## Enums (Validation)

### PatternType
Detectable AML patterns:
```python
FAN_OUT = "FAN_OUT"              # One source → many destinations
FAN_IN = "FAN_IN"                # Many sources → one destination
CYCLE = "CYCLE"                  # Circular flow (A→B→C→A)
SCATTER_GATHER = "SCATTER_GATHER"  # Fanout + fanin
GATHER_SCATTER = "GATHER_SCATTER"  # Fanin + fanout
BIPARTITE = "BIPARTITE"          # Two groups, cross-group only
STACK = "STACK"                  # Sequential chain
RANDOM = "RANDOM"                # No clear pattern
```

### SeverityLevel
Alert severity classification:
```python
CRITICAL = "critical"  # Immediate action required
HIGH = "high"          # Review soon
MEDIUM = "medium"      # Monitor
LOW = "low"            # Informational
```

### AlertSource
Alert origin:
```python
LABELLED = "labelled"        # From training data labels
UNLABELLED = "unlabelled"    # From inference on production data
```

### DecisionType
Analyst decisions on alerts:
```python
CONFIRM = "confirm"  # Confirmed as AML
REVIEW = "review"    # Requires further review
DISMISS = "dismiss"  # False positive / safe
```

---

## Pydantic Models (Request/Response Schemas)

### Request Models
```python
class DecisionRequest(BaseModel):
    """POST /alerts/{alert_id}/decision"""
    decision: DecisionType  # Required: confirm|review|dismiss
    reason: str            # Required: explanation
    analyst: str = "system"  # Optional: who made decision

class ScanRequest(BaseModel):
    """POST /scan"""
    max_rows: int = MULTIGNN_MAX_ROWS  # Optional: max transactions to scan
```

### Response Models
```python
class AlertSchema(BaseModel):
    """Alert with metadata"""
    id: str
    nodes: list[dict]          # Accounts involved
    edges: list[dict]          # Transactions
    pattern_type: PatternType
    confidence: float          # 0.0 - 1.0
    severity: SeverityLevel
    time_span_seconds: int
    total_amount: float
    source: AlertSource
    created_at: str            # ISO timestamp

class DecisionSchema(BaseModel):
    """Decision record"""
    alert_id: str
    decision: DecisionType
    reason: str
    analyst: str
    created_at: str            # ISO timestamp

class StatusSchema(BaseModel):
    """System status"""
    model_loaded: bool
    n_alerts_total: int
    n_alerts_after_whitelist: int
    last_scan_ms: float
    pipeline_error: str = ""
```

---

## Helper Functions

### Data Initialization
```python
def _ensure_data_dir():
    """Create data directory and default whitelist if missing"""
    # Creates: DATA_DIR, whitelist.json
```

### Cache Loading
```python
def _load_cache() -> bool:
    """Load cached alerts from previous scan"""
    # Reads: CACHE_PATH
    # Sets: ALERTS, SUPPRESSED (via whitelist)
    # Returns: True if cache loaded, False if new
```

### Cache Persistence
```python
def _save_cache():
    """Persist current alerts to disk cache"""
    # Writes to: CACHE_PATH
    # Called after each scan
```

### ETag Generation
```python
def _compute_etag(data: dict) -> str:
    """Generate MD5 hash of data for cache validation"""
    # Input: Any JSON-serializable dict
    # Output: Hex string (32 chars)
    # Usage: If-None-Match header for GET /alerts
```

---

## API Endpoints

### Health & Status

#### `GET /health`
**Purpose:** Check if pipeline is ready and model is loaded.

**Response:**
```json
{
  "model_loaded": true,
  "pipeline_ready": true,
  "last_scan_ms": 325.4,
  "error": null
}
```

**Implementation:**
```python
@app.get("/health", tags=["status"])
async def get_health():
    return {
        "model_loaded": PIPELINE_READY.is_set(),
        "pipeline_ready": not PIPELINE_ERROR,
        "last_scan_ms": time.time() - PIPELINE_START_TIME if PIPELINE_START_TIME else 0,
        "error": PIPELINE_ERROR or None
    }
```

---

#### `GET /status`
**Purpose:** Get summary of current alerts and decisions.

**Query Parameters:**
- None required

**Response:**
```json
{
  "model_loaded": true,
  "n_alerts_total": 47,
  "n_alerts_after_whitelist": 42,
  "last_scan_ms": 325.4,
  "pipeline_error": "",
  "pattern_breakdown": {
    "FAN_OUT": 15,
    "FAN_IN": 12,
    "CYCLE": 8,
    "SCATTER_GATHER": 7
  },
  "severity_breakdown": {
    "CRITICAL": 5,
    "HIGH": 18,
    "MEDIUM": 19,
    "LOW": 0
  },
  "decision_summary": {
    "confirmed": 10,
    "reviewed": 8,
    "dismissed": 5,
    "pending": 19
  }
}
```

**Implementation:**
```python
@app.get("/status", tags=["alerts"])
async def get_status():
    with ALERTS_LOCK:
        total = len(ALERTS)
        after_wl = len(SUPPRESSED)
        patterns = {}
        severities = {}
        for alert in SUPPRESSED.values():
            patterns[alert.get("pattern_type")] = patterns.get(...) + 1
            # ... similar for severities
    
    decisions = core.db.decision_counts()
    return {
        "model_loaded": PIPELINE_READY.is_set(),
        "n_alerts_total": total,
        "n_alerts_after_whitelist": after_wl,
        "last_scan_ms": ...,
        "pattern_breakdown": patterns,
        "severity_breakdown": severities,
        "decision_summary": decisions
    }
```

---

### Alerts Management

#### `GET /alerts`
**Purpose:** Query alerts with optional filtering.

**Query Parameters:**
```
pattern: str (optional)    # Filter by pattern type (FAN_OUT, etc.)
severity: str (optional)   # Filter by severity (critical, high, medium, low)
source: str (optional)     # Filter by source (labelled, unlabelled)
limit: int = 100           # Max results
offset: int = 0            # Pagination offset
```

**Response:**
```json
[
  {
    "id": "alert-uuid-123",
    "nodes": [
      { "node_id": "acct-456", "bank": "BANK_A", "role": "source", "severity": "high" },
      { "node_id": "acct-789", "bank": "BANK_B", "role": "destination", "severity": "medium" }
    ],
    "edges": [
      { "src": "acct-456", "dst": "acct-789", "amount": 50000.0, "timestamp": "2026-06-29T10:30:00Z" }
    ],
    "pattern_type": "FAN_OUT",
    "confidence": 0.94,
    "severity": "high",
    "time_span_seconds": 3600,
    "total_amount": 50000.0,
    "source": "unlabelled",
    "created_at": "2026-06-29T10:35:00Z"
  }
]
```

**Implementation:**
```python
@app.get("/alerts", tags=["alerts"])
@limiter.limit("100/minute")
async def get_alerts(
    request: Request,
    pattern: str | None = Query(None),
    severity: str | None = Query(None),
    source: str | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0)
):
    with ALERTS_LOCK:
        results = list(SUPPRESSED.values())
    
    # Apply filters
    if pattern:
        results = [a for a in results if a["pattern_type"] == pattern]
    if severity:
        results = [a for a in results if a["severity"] == severity]
    if source:
        results = [a for a in results if a["source"] == source]
    
    return results[offset : offset + limit]
```

---

#### `GET /alerts/{alert_id}`
**Purpose:** Get details of a single alert.

**Parameters:**
- `alert_id` (path): UUID of alert

**Response:** Single alert object (same schema as GET /alerts)

---

#### `POST /alerts/{alert_id}/decision`
**Purpose:** Record an analyst decision on an alert.

**Parameters:**
- `alert_id` (path): UUID of alert

**Request Body:**
```json
{
  "decision": "confirm",  // confirm | review | dismiss
  "reason": "Multiple suspicious transfers in 1 hour",
  "analyst": "analyst@bank.com"  // Optional, defaults to "system"
}
```

**Response:**
```json
{
  "alert_id": "alert-uuid-123",
  "decision": "confirm",
  "reason": "Multiple suspicious transfers in 1 hour",
  "analyst": "analyst@bank.com",
  "created_at": "2026-06-29T10:40:00Z",
  "decision_history": [
    { "decision": "confirm", "reason": "...", "created_at": "..." }
  ]
}
```

**Implementation:**
```python
@app.post("/alerts/{alert_id}/decision", tags=["decisions"])
@limiter.limit("30/minute")
async def post_decision(
    alert_id: str,
    body: DecisionRequest
):
    # Validate decision type
    if body.decision not in [dt.value for dt in DecisionType]:
        raise HTTPException(status_code=400, detail="Invalid decision type")
    
    # Record in database
    core.db.record_decision(alert_id, body.decision, body.reason, body.analyst)
    
    # Get current decision state
    current = core.db.decision_history(alert_id)
    
    return {
        "alert_id": alert_id,
        "decision": body.decision,
        "reason": body.reason,
        "analyst": body.analyst,
        "created_at": datetime.now().isoformat(),
        "decision_history": current
    }
```

---

#### `GET /alerts/{alert_id}/decision/history`
**Purpose:** Get audit trail of all decisions on an alert.

**Response:**
```json
{
  "alert_id": "alert-uuid-123",
  "decisions": [
    { "decision": "review", "reason": "Initial review", "analyst": "user1@bank.com", "created_at": "2026-06-29T10:35:00Z" },
    { "decision": "confirm", "reason": "Confirmed AML", "analyst": "user2@bank.com", "created_at": "2026-06-29T11:00:00Z" }
  ]
}
```

---

### Decisions

#### `GET /decisions`
**Purpose:** Get current decision state for all alerts.

**Response:**
```json
{
  "alert-uuid-1": "confirm",
  "alert-uuid-2": "review",
  "alert-uuid-3": "dismiss",
  "alert-uuid-4": null  // No decision yet
}
```

---

#### `GET /decisions/{alert_id}`
**Purpose:** Get latest decision for a specific alert.

**Response:**
```json
{
  "alert_id": "alert-uuid-123",
  "decision": "confirm",
  "reason": "Multiple suspicious transfers",
  "analyst": "user1@bank.com",
  "created_at": "2026-06-29T10:40:00Z"
}
```

---

### ML Pipeline

#### `POST /scan`
**Purpose:** Trigger the Multi-GNN detection pipeline asynchronously.

**Query Parameters:**
```
max_rows: int = 600000  # Maximum transactions to scan
```

**Response:**
```json
{
  "scan_id": "scan-uuid-456",
  "status": "running",
  "n_alerts": 47,
  "n_transactions_scanned": 450000,
  "inference_ms": 325.4,
  "drift": {
    "kl": 0.12,
    "js": 0.08,
    "score_shift": 0.03
  }
}
```

**Implementation:**
```python
@app.post("/scan", tags=["pipeline"])
@limiter.limit("5/minute")
async def post_scan(max_rows: int = MULTIGNN_MAX_ROWS):
    request_id.set(str(uuid.uuid4()))
    
    # Check if model is loaded
    if not PIPELINE_READY.is_set():
        raise HTTPException(status_code=503, detail="Model not ready")
    
    # Spawn background task
    asyncio.create_task(multignn_pipeline.scan(max_rows))
    
    return {
        "scan_id": request_id.get(),
        "status": "running",
        "n_alerts": len(SUPPRESSED),
        "inference_ms": ...,
        "drift": ML_METRICS.get("drift", {})
    }
```

---

### Whitelist Management

#### `GET /whitelist`
**Purpose:** Get current exemptions (accounts, banks, patterns).

**Response:**
```json
{
  "exempt_accounts": ["FEDERAL_RESERVE", "CENTRAL_BANK", "TREASURY"],
  "exempt_banks": ["JPMORGAN_CHASE", "BANK_OF_AMERICA"],
  "exempt_patterns": ["FAN_OUT"]
}
```

---

#### `POST /whitelist/account`
**Purpose:** Add an account to exemption list.

**Request Body:**
```json
{
  "account_id": "NEW_ACCOUNT_ID",
  "bank": "BANK_NAME",
  "reason": "Known safe account"
}
```

**Response:**
```json
{
  "status": "added",
  "account_id": "NEW_ACCOUNT_ID",
  "exempt_accounts": [...]
}
```

---

#### `DELETE /whitelist/account/{account_id}`
**Purpose:** Remove an account from exemption list.

**Response:**
```json
{
  "status": "removed",
  "account_id": "OLD_ACCOUNT_ID",
  "exempt_accounts": [...]
}
```

---

#### `GET /whitelist/suppressed`
**Purpose:** Get alerts that are suppressed (filtered) due to whitelist.

**Response:**
```json
[
  {
    "alert_id": "alert-uuid-123",
    "reason": "Account FEDERAL_RESERVE is exempt"
  }
]
```

---

### Model Metrics

#### `GET /ml-metrics`
**Purpose:** Get model performance metrics from last training.

**Response:**
```json
{
  "f1_score": 0.85,
  "precision": 0.88,
  "recall": 0.82,
  "auc": 0.91,
  "loss": 0.15,
  "epochs_trained": 8,
  "training_time_s": 420.3
}
```

---

#### `GET /drift`
**Purpose:** Get distribution shift metrics.

**Response:**
```json
{
  "kl_divergence": 0.12,
  "js_divergence": 0.08,
  "score_shift": 0.03,
  "baseline_mean": 0.52,
  "current_mean": 0.49,
  "baseline_std": 0.18,
  "current_std": 0.20
}
```

---

## Middleware & Integration

### CORS Middleware
```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins (frontend dev & production)
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

### Rate Limiting
```python
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter

# Applied per-endpoint:
@app.get("/alerts")
@limiter.limit("100/minute")
async def get_alerts(...):
    pass
```

### Static File Serving (SPA)
```python
# Serve built React frontend
if FRONTEND_DIST.exists():
    app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")
else:
    app.mount("/", StaticFiles(directory=FRONTEND_PUBLIC, html=True), name="frontend")

# SPA fallback: unknown paths → index.html
@app.get("/{path_name:path}")
async def serve_spa(path_name: str):
    file_path = FRONTEND_PUBLIC / path_name
    if file_path.is_file():
        return FileResponse(file_path)
    return FileResponse(FRONTEND_PUBLIC / "index.html")
```

---

## Lifespan Events (Startup/Shutdown)

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    # ──── STARTUP ────
    _ensure_data_dir()
    _load_cache()
    PIPELINE_READY.set()  # Signal that we're ready
    
    yield
    
    # ──── SHUTDOWN ────
    _save_cache()
    # Close database connections, etc.
```

---

## Error Handling

### Common HTTP Exceptions
```python
HTTPException(status_code=400, detail="Invalid request")   # Bad request
HTTPException(status_code=404, detail="Alert not found")   # Not found
HTTPException(status_code=429, detail="Too many requests") # Rate limit
HTTPException(status_code=503, detail="Model not ready")   # Service unavailable
```

### Structured Logging
```python
logger.info(f"[{request_id.get()}] POST /alerts/{alert_id}/decision → {decision}")
logger.error(f"[{request_id.get()}] Pipeline failed: {error}")
```

---

## Performance Considerations

1. **ETag Caching:** GET /alerts returns same ETag if unchanged → client can skip processing
2. **Rate Limiting:** 100 req/min on read endpoints, 5 req/min on /scan (expensive)
3. **Thread-Safe Locking:** RLock prevents race conditions on ALERTS dict
4. **Async I/O:** Database operations don't block request handler
5. **In-Memory Cache:** ALERTS dict avoids repeated database queries

---

## Testing Examples

### Test GET /health
```python
def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["model_loaded"] is True
```

### Test POST /alerts/{id}/decision
```python
def test_post_decision():
    response = client.post(
        "/alerts/alert-123/decision",
        json={"decision": "confirm", "reason": "Test"}
    )
    assert response.status_code == 200
    assert response.json()["decision"] == "confirm"
```

### Test Rate Limiting
```python
def test_rate_limit():
    for _ in range(101):
        client.get("/alerts")
    response = client.get("/alerts")
    assert response.status_code == 429  # Too many requests
```

---

## Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `PORT` | 8000 | Server port (overridden by Render) |
| `DATABASE_URL` | (local) | External database URL (future) |
| `MODEL_PATH` | data/multignn_model.pt | Path to trained model |
| `LOG_LEVEL` | INFO | Logging verbosity |
| `CORS_ORIGINS` | * | Comma-separated CORS allowed origins |

---

**End of Backend API Documentation**

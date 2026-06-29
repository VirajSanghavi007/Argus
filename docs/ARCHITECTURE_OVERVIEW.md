# Argus AML Detection — Complete Architecture Documentation

**Version:** 1.0  
**Last Updated:** 2026-06-29  
**Project:** Argus — Multi-GNN Anti-Money Laundering Detection System

---

## System Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          BROWSER / CLIENT                               │
│                      (React 18 + Vite SPA)                              │
├─────────────────────────────────────────────────────────────────────────┤
│  Components: Dashboard | Investigate | CaseManager | Search | Whitelist │
│  State: alerts, decisions, status, mlMetrics                            │
│  Data Flow: fetch() → /api/* endpoints                                  │
├─────────────────────────────────────────────────────────────────────────┤
                              ↓ HTTPS/HTTP ↓
├─────────────────────────────────────────────────────────────────────────┤
│                      BACKEND API LAYER                                  │
│                   (FastAPI + Uvicorn)                                   │
│                    Port: 8000 (production)                              │
├─────────────────────────────────────────────────────────────────────────┤
│  Core Responsibilities:                                                 │
│  • Request routing & validation (Pydantic schemas)                      │
│  • Rate limiting (slowapi)                                              │
│  • CORS handling                                                        │
│  • Static file serving (React build)                                    │
│  • Business logic coordination                                          │
│  • Whitelist filtering                                                  │
├─────────────────────────────────────────────────────────────────────────┤
                    ↓ Internal Function Calls ↓
┌─────────────────────────────────────────────────────────────────────────┐
│            DATABASE SERVICE LAYER (Separate)                            │
│              (SQLite + Thread-Safe Persistence)                         │
└─────────────────────────────────────────────────────────────────────────┘
│  Location: src/database/service.py                                      │
│  Schema: src/database/schemas/schema.sql                                │
│  Features:                                                              │
│  • Alert persistence & queries                                         │
│  • Decision audit trail (append-only)                                  │
│  • Thread-safe locking (RLock)                                         │
│  • WAL mode for concurrent writes                                      │
│  • Connection pooling & caching                                        │
├─────────────────────────────────────────────────────────────────────────┤
                    ↓ Internal Function Calls ↓
┌─────────────────────────────────────────────────────────────────────────┐
│              ML MODELING & DETECTION PIPELINE                           │
│                  (Multi-GNN + Graph Analysis)                           │
└─────────────────────────────────────────────────────────────────────────┘
│  Location: src/backend/pipeline/detection.py                           │
│  Model: src/backend/models/multignn.py                                 │
│  Model File: data/multignn_model.pt                                    │
│  Features:                                                              │
│  • Transaction graph construction                                      │
│  • Multi-GNN inference (PNAConv + GINE layers)                        │
│  • Topology-based pattern detection                                    │
│  • Confidence scoring & thresholding                                   │
│  • Drift detection (KL & JS divergence)                               │
│  • Batch processing (up to 600k transactions)                          │
├─────────────────────────────────────────────────────────────────────────┤
                    ↓ External Data Access ↓
┌─────────────────────────────────────────────────────────────────────────┐
│                     DATA LAYER (File-Based)                            │
└─────────────────────────────────────────────────────────────────────────┘
│  Data Directory: data/                                                  │
│  • HI-Small_Trans.csv — Transaction dataset                            │
│  • HI-Small_accounts.csv — Account metadata                            │
│  • argus.db — SQLite database (alerts + decisions)                    │
│  • multignn_model.pt — Trained model weights                          │
│  • whitelist.json — Exemption rules                                    │
│  • pipeline_cache.json — Recent scan results                          │
│  • drift_log.json — Distribution metrics history                       │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Layer Breakdown

### 1. **Frontend Layer** (`src/frontend/`)
- **Technology:** React 18 + Vite + Axios
- **Port:** 5173 (dev), served from backend at 8000 (prod)
- **Routing:** Client-side (React Router pattern, SPA)
- **State:** Global state in App.jsx (alerts, decisions, status, metrics)
- **Components:** 6 modular components (Navigation, Dashboard, Investigate, CaseManager, Search, Whitelist)
- **API Client:** `src/frontend/src/utils/api.js` (centralized HTTP layer)

**Key Files:**
- `src/frontend/package.json` — Dependencies (React, Vite, Axios, Chart.js)
- `src/frontend/vite.config.js` — Build config, API proxy, dev server settings
- `src/frontend/src/index.jsx` — React entry point
- `src/frontend/src/App.jsx` — Main app, state management, data fetching
- `src/frontend/src/components/*.jsx` — 6 reusable components

**Data Flow:**
```
User Action → Component State Update → API Call (api.js) → Backend Response → App State → Re-render
```

---

### 2. **Backend API Layer** (`src/backend/api/main.py`)
- **Technology:** FastAPI + Uvicorn
- **Port:** 8000
- **Concurrency:** asyncio + threading for long-running tasks
- **Rate Limiting:** slowapi (100 req/min default)
- **Static Files:** Serves React dist/ or public/ (SPA with fallback routing)

**Key Responsibilities:**
1. Request validation (Pydantic models)
2. Authentication/Authorization (if enabled)
3. Rate limiting enforcement
4. CORS handling
5. Database delegation (calls → core.db.*)
6. Whitelist filtering
7. SPA routing (index.html fallback for unknown paths)

**Endpoints Overview:**
```
GET  /health                              — Pipeline health check
GET  /status                              — Alert counts, pattern breakdown
GET  /alerts                              — Query alerts (with filters)
GET  /alerts/{alert_id}                   — Single alert details
POST /alerts/{alert_id}/decision          — Record analyst decision
GET  /alerts/{alert_id}/decision/history  — Audit trail
GET  /decisions                           — All current decisions
GET  /decisions/{alert_id}                — Single decision
GET  /whitelist                           — Current exempt accounts/banks
POST /whitelist/account                   — Add account to whitelist
DELETE /whitelist/account/{account_id}    — Remove account
GET  /whitelist/suppressed                — Alerts affected by whitelist
POST /scan                                — Trigger ML pipeline
GET  /ml-metrics                          — Model performance metrics
GET  /drift                               — Distribution shift detection
```

---

### 3. **Database Service Layer** (`src/database/`)
- **Technology:** SQLite + Python
- **Schema:** `src/database/schemas/schema.sql`
- **Concurrency:** Thread-safe locking (RLock)
- **Mode:** WAL (Write-Ahead Logging) for concurrent access
- **Tables:** `alerts`, `decisions` (append-only audit log)

**Key Functions:**
- `init_db()` — Initialize database, create schema
- `replace_alerts(alerts_data)` — Bulk insert/replace alerts
- `load_alerts(filters)` — Query alerts with optional filtering
- `has_alerts()` — Check if database contains alerts
- `record_decision(alert_id, decision, reason, analyst)` — Log decision
- `current_decisions()` — Get latest decision per alert
- `decision_history(alert_id)` — Get all decisions for an alert
- `decision_counts()` — Aggregate counts by decision type

**Database Schema:**
```sql
CREATE TABLE alerts (
  id TEXT PRIMARY KEY,
  nodes JSON,
  edges JSON,
  pattern_type TEXT,
  confidence REAL,
  severity TEXT,
  time_span_seconds INTEGER,
  total_amount REAL,
  source TEXT,
  created_at TIMESTAMP
);

CREATE TABLE decisions (
  id INTEGER PRIMARY KEY,
  alert_id TEXT,
  decision_type TEXT,
  reason TEXT,
  analyst TEXT,
  created_at TIMESTAMP,
  FOREIGN KEY(alert_id) REFERENCES alerts(id)
);
```

---

### 4. **ML Modeling & Detection Pipeline** (`src/backend/pipeline/`, `src/backend/models/`)
- **Technology:** PyTorch + PyTorch Geometric
- **Architecture:** Multi-GNN (PNAConv + GINE layers)
- **Input:** Transaction multigraph (nodes = accounts, edges = transactions)
- **Output:** Flagged transactions scored by ML, clustered by topology

**Key Components:**
1. **Graph Building** (`detection.py:build_graph()`)
   - Reads transaction CSV
   - Creates directed multigraph (NetworkX)
   - Computes edge features (14-dim: amount, time, currency, etc.)

2. **ML Inference** (`detection.py:score_transactions()`)
   - Loads trained model from data/multignn_model.pt
   - Runs inference on batch
   - Returns edge-level confidence scores

3. **Topology Detection** (`detection.py:_classify_topology()`)
   - Clusters flagged edges by connectivity
   - Classifies clusters by in/out degree patterns
   - Detects: FAN_OUT, FAN_IN, CYCLE, SCATTER_GATHER, BIPARTITE, etc.

4. **Whitelist Filtering** (`core/whitelist.py`)
   - Exempts known-good accounts/banks
   - Filters alert results before returning to frontend

5. **Drift Detection** (`detection.py`)
   - Computes KL divergence of score distributions
   - Compares to baseline (JS divergence)
   - Alerts if distribution shift detected

---

### 5. **Deployment Layer** (Render)
- **Environment:** Render.com (PaaS)
- **Build Command:** `pip install -r config/requirements.txt && npm run build`
- **Start Command:** `python scripts/serve.py --host 0.0.0.0 --port $PORT`
- **Environment Variables:**
  - `DATABASE_URL` (if using external DB)
  - `MODEL_PATH` (path to trained model, must be uploaded)
  - `API_BASE` (frontend config for backend URL)

**Key Considerations:**
- Model file (500MB) must be uploaded separately (Git LFS or Render storage)
- Cold start: ~5-10s (model loading into memory)
- Single dyno runs both backend + static frontend

---

## Data Flow Examples

### Example 1: Query Alerts with Whitelist Filtering
```
Frontend (Investigate.jsx)
  ↓
API GET /alerts?pattern=FAN_OUT
  ↓
Backend main.py::get_alerts()
  ├─ Calls core.db.load_alerts(filters)
  │   ↓
  │   Database service.load_alerts()
  │     └─ Queries SQLite → returns alert rows
  ├─ Calls filter_alerts() from whitelist module
  │   └─ Removes alerts with exempt accounts/banks
  └─ Returns filtered JSON
  ↓
Frontend updates state, re-renders table
```

### Example 2: Record Decision (Audit Trail)
```
Frontend (Investigate.jsx)
  ↓
API POST /alerts/{alert_id}/decision
  │ Payload: { decision: "confirm", reason: "..." }
  ↓
Backend main.py::post_decision()
  ├─ Validates decision type (CONFIRM, REVIEW, DISMISS)
  ├─ Calls core.db.record_decision(alert_id, decision, reason, analyst)
  │   ↓
  │   Database service.record_decision()
  │     └─ INSERTs row into decisions table (append-only)
  └─ Returns success + current decision state
  ↓
Frontend updates decision UI
```

### Example 3: Trigger ML Pipeline
```
Frontend (Dashboard.jsx)
  ↓
API POST /scan
  │ Query: ?max_rows=600000
  ↓
Backend main.py::post_scan()
  ├─ Spawns async task (multignn_pipeline.scan())
  │   ├─ Calls build_graph(transaction_csv)
  │   ├─ Calls score_transactions(graph, model)
  │   ├─ Calls _classify_topology(flagged_edges)
  │   ├─ Calls filter_alerts(whitelist)
  │   └─ Calls core.db.replace_alerts(alert_json)
  │       ↓
  │       Database service.replace_alerts()
  │         └─ DELETEs old alerts, INSERTs new ones
  └─ Returns scan summary (n_alerts, inference_ms, drift metrics)
  ↓
Frontend polls /status to show progress
```

---

## Integration Points

| Layer | Calls | Called By | Method |
|-------|-------|-----------|--------|
| Frontend | api.js fetch() | Backend HTTP | async fetch with JSON |
| Backend | core.db.* | Database | Direct Python imports |
| Backend | pipeline.* | Own module | Direct Python imports |
| Backend | whitelist.* | Own module | Direct Python imports |
| Database | sqlite3 | Backend via service | SQL + thread locks |
| Pipeline | torch, torch_geometric | Backend | Direct imports |

---

## Backward Compatibility & Import Paths

All backend imports follow a consistent pattern:

```python
# Backend → Database (delegates to service)
from backend.core import db
db.init_db()  # Actually calls database.service.init_db()

# Backend → Pipeline
from backend.pipeline.detection import multignn_pipeline
multignn_pipeline.scan(max_rows=600_000)

# Backend → Whitelist
from backend.core.whitelist import load_whitelist, filter_alerts
whitelist = load_whitelist()
alerts = filter_alerts(alerts, whitelist)
```

**Why:** Separation of concerns + testability. Database is independent; backend uses it as a client.

---

## Environment & Configuration

### Development
```bash
python scripts/serve.py  # Runs on :8000
# Frontend (separate terminal):
cd src/frontend && npm run dev  # Runs on :5173
```

### Production (Render)
```bash
# Environment variables:
PORT=8000  # Provided by Render
DATABASE_URL=...  # If using external DB
MODEL_PATH=data/multignn_model.pt

# Model size: ~500MB (must be uploaded separately)
# Cold start: ~5-10 seconds (model loading)
```

---

## Key Design Decisions

1. **Separate Database Service:** Enables future migration to PostgreSQL, easier scaling, clear schema ownership.
2. **React SPA:** Modern frontend, client-side routing, hot reload in development.
3. **Vite Build System:** Fast dev server, tree-shaking, minimal bundle size.
4. **Thread-Safe Locking:** Database operations can handle concurrent reads/writes from pipeline + request handlers.
5. **Append-Only Decisions:** Audit trail is immutable; decisions are never modified, only logged.
6. **Whitelist Filtering:** Post-processing step to suppress false positives without modifying alerts.

---

## Next Steps

- [ ] Wire up Cytoscape in Investigate component for transaction graph visualization
- [ ] Implement timeline animation in Investigate component
- [ ] Create database migrations in `src/database/migrations/`
- [ ] Add error boundaries + toast notifications in React
- [ ] Performance: memoize components, lazy load routes
- [ ] Add Jest tests for React components
- [ ] Set up CI/CD pipeline (GitHub Actions → Render)

---

**End of Document**

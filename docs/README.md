# Argus Documentation — Complete Reference

Welcome to the Argus AML Detection system documentation. This folder contains in-depth technical documentation for every component of the system.

---

## 📚 Documentation Index

### 🏗️ Start Here
- **[ARCHITECTURE_OVERVIEW.md](ARCHITECTURE_OVERVIEW.md)** — System design, data flows, integration points
  - Read this first to understand how all layers connect
  - High-level diagrams showing Frontend → Backend → Database → ML Pipeline
  - Data flow examples (query alerts, record decisions, trigger scan)
  - Key design decisions and their rationale

---

### 🎯 Layer Documentation

#### Backend API Layer
- **[backend/BACKEND_API.md](backend/BACKEND_API.md)** — Complete API reference
  - **Technology:** FastAPI + Uvicorn on port 8000
  - **Size:** 574 lines
  - **Contents:**
    - Global state & concurrency (ALERTS_LOCK, PIPELINE_READY)
    - Request/response schemas (Pydantic models)
    - All 25+ API endpoints documented:
      - Health & Status: `/health`, `/status`
      - Alerts: `GET /alerts`, `POST /alerts/{id}/decision`, `GET /alerts/{id}/decision/history`
      - Decisions: `GET /decisions`, `GET /decisions/{id}`
      - Pipeline: `POST /scan`, `GET /ml-metrics`, `GET /drift`
      - Whitelist: `GET /whitelist`, `POST /whitelist/account`, etc.
    - Middleware (CORS, rate limiting, SPA routing)
    - Error handling, logging, monitoring

**Key Functions & Variables:**
```python
ALERTS: dict                    # In-memory alert cache
ALERTS_LOCK: RLock            # Thread-safe access
PIPELINE_READY: Event         # Signal when model loads
request_id: ContextVar        # Structured logging context

# Main endpoints
@app.get("/status")           # System status
@app.get("/alerts")           # Query alerts
@app.post("/alerts/{id}/decision")  # Log decision
@app.post("/scan")            # Trigger ML pipeline
```

---

#### Frontend Layer
- **[frontend/REACT_FRONTEND.md](frontend/REACT_FRONTEND.md)** — React component architecture
  - **Technology:** React 18 + Vite + Axios
  - **Port:** 5173 (dev), served from backend (prod)
  - **Contents:**
    - Project structure and build configuration (Vite)
    - Entry point: `src/index.jsx` and `src/App.jsx`
    - 6 main components:
      - `Navigation.jsx` — Header, tab switcher, dark mode
      - `Dashboard.jsx` — KPI cards, charts (Chart.js), summary
      - `Investigate.jsx` — Alert details, graph viewer, decision buttons
      - `CaseManager.jsx` — Decisions table, CSV export
      - `Search.jsx` — Full-text search, pattern filters
      - `Whitelist.jsx` — Exemption management
    - Centralized API client: `src/utils/api.js` (200+ lines)
    - Global state management pattern (App.jsx owns all state)
    - Styling (CSS variables for dark mode)

**Key Components & Functions:**
```javascript
// Global state in App.jsx
const [alerts, setAlerts] = useState([])
const [decisions, setDecisions] = useState({})
const [status, setStatus] = useState({})
const [currentView, setCurrentView] = useState('dashboard')

// API client
api.getStatus()
api.getAlerts(filters)
api.postDecision(alertId, {decision, reason})
api.scanPipeline()
```

---

#### Database Service Layer
- **[database/DATABASE_SERVICE.md](database/DATABASE_SERVICE.md)** — Persistence layer deep dive
  - **Technology:** SQLite + Python with thread-safe RLock
  - **Location:** `src/database/service.py` + `src/database/schemas/schema.sql`
  - **Design:** Separate from backend, independent module
  - **Contents:**
    - Schema definition: 2 tables (alerts, decisions)
    - All 8 database functions documented:
      - `init_db()` — Create schema & indexes
      - `replace_alerts(alerts)` — Bulk insert/replace
      - `load_alerts(filters)` — Query with optional filtering
      - `has_alerts()` — Check if database has alerts
      - `record_decision(alert_id, decision, reason, analyst)` — Append decision
      - `current_decisions()` — Latest decision per alert
      - `decision_history(alert_id)` — Full audit trail
      - `decision_counts()` — Aggregate statistics
    - Concurrency model (RLock, WAL mode)
    - Backup & maintenance procedures
    - Performance characteristics

**Key Tables & Schema:**
```sql
CREATE TABLE alerts (
  id TEXT PRIMARY KEY,
  nodes JSON, edges JSON,
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
  decision_type TEXT (confirm|review|dismiss),
  reason TEXT,
  analyst TEXT,
  created_at TIMESTAMP
  -- APPEND-ONLY: never modified
);
```

---

#### ML Modeling & Detection Pipeline
- **[modeling/ML_PIPELINE.md](modeling/ML_PIPELINE.md)** — Machine learning architecture
  - **Technology:** PyTorch + PyTorch Geometric
  - **Model:** Multi-GNN (2 layers: PNAConv + GINE)
  - **Contents:**
    - Graph construction: `build_graph(trans_df, acct_df)`
    - Multi-GNN architecture:
      - Layer 1: PNAConv (Principal Neighborhood Aggregation)
      - Layer 2: GINEConv (Graph Isomorphism Network with Edge)
      - Edge classification head
    - Forward pass & inference
    - Training & hyperparameters
    - Detection pipeline: `scan(max_rows)`
    - Topology classification (FAN_OUT, FAN_IN, CYCLE, SCATTER_GATHER, BIPARTITE, etc.)
    - Drift detection (KL divergence, JS divergence)
    - Severity calculation
    - Whitelist filtering integration

**Key Concepts:**
```python
# Graph construction
edge_features = [14-dimensional vectors]
# amount (normalized), hour (sin/cos), dow (sin/cos),
# cross-bank flag, currency, payment format, ...

# Multi-GNN forward pass
h1 = PNAConv(x, edge_index, edge_attr)  # Neighborhood agg
h2 = GINEConv(h1, edge_index, edge_attr)  # Edge refinement
logits = MLP(concat(src_emb, dst_emb, edge_emb))
scores = sigmoid(logits)  # (0, 1)

# Clustering & classification
components = find_connected_components(flagged_edges)
for component in components:
    pattern = classify_topology(in_degree, out_degree)
    confidence = mean(scores[component])
    alert = build_alert(...)
```

---

#### Deployment (Render)
- **[deployment/RENDER_DEPLOYMENT.md](deployment/RENDER_DEPLOYMENT.md)** — Production deployment guide
  - **Platform:** Render.com (PaaS)
  - **Contents:**
    - Service setup & configuration
    - Build command (install deps, build React, etc.)
    - Start command (Gunicorn + Uvicorn workers)
    - Environment variables
    - Model file upload strategies (Git LFS, S3, disk storage)
    - Logs & debugging
    - Performance tuning (worker count, caching)
    - Database setup (SQLite vs PostgreSQL)
    - Monitoring & alerts
    - CI/CD pipeline (GitHub Actions)
    - Cost estimate (~$14/mo)
    - Troubleshooting checklist
    - Production readiness checklist

**Key Configuration:**
```bash
# Build
pip install -r config/requirements.txt && \
  cd src/frontend && npm install && npm run build

# Start
gunicorn -w 4 -k uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:$PORT src.backend.api.main:app
```

---

### 🎓 Hackathon Documentation
- **[hackathon/HACKATHON_GUIDE.md](hackathon/HACKATHON_GUIDE.md)** — Project overview for hackers
  - **Problem:** Detect money laundering in transaction networks
  - **Solution:** Multi-GNN scoring + topology-based clustering
  - **Key Features:**
    1. Transaction graph building
    2. Multi-GNN inference
    3. Topology-based clustering
    4. Whitelist filtering
    5. Analyst dashboard
    6. Drift detection
  - **Getting Started:** 5-minute setup guide
  - **Critical Concepts:** GNNs, separate DB service, append-only decisions, whitelist filtering, SPA routing
  - **ML Model Explainer:** Architecture, training, inference, performance
  - **API Quick Reference:** All endpoints summarized
  - **Testing & Quality:** Unit tests, model validation, integration tests
  - **Known Limitations & Roadmap**
  - **Security Considerations**
  - **Demo Workflow:** End-to-end example
  - **Hackathon Tips:** Time management for different time windows
  - **Troubleshooting Guide**

---

## 🗂️ Quick Reference by Role

### If You're a **Frontend Engineer**
1. Start: [ARCHITECTURE_OVERVIEW.md](ARCHITECTURE_OVERVIEW.md) — understand data flow
2. Deep dive: [frontend/REACT_FRONTEND.md](frontend/REACT_FRONTEND.md)
3. API details: [backend/BACKEND_API.md](backend/BACKEND_API.md) — understand endpoints you'll call

### If You're a **Backend Engineer**
1. Start: [ARCHITECTURE_OVERVIEW.md](ARCHITECTURE_OVERVIEW.md)
2. Deep dive: [backend/BACKEND_API.md](backend/BACKEND_API.md)
3. Database layer: [database/DATABASE_SERVICE.md](database/DATABASE_SERVICE.md)
4. ML integration: [modeling/ML_PIPELINE.md](modeling/ML_PIPELINE.md) — how to call pipeline

### If You're an **ML Engineer**
1. Start: [ARCHITECTURE_OVERVIEW.md](ARCHITECTURE_OVERVIEW.md)
2. Deep dive: [modeling/ML_PIPELINE.md](modeling/ML_PIPELINE.md)
3. Integration: [backend/BACKEND_API.md](backend/BACKEND_API.md) — POST /scan endpoint

### If You're **Deploying to Production**
1. Start: [ARCHITECTURE_OVERVIEW.md](ARCHITECTURE_OVERVIEW.md)
2. Deep dive: [deployment/RENDER_DEPLOYMENT.md](deployment/RENDER_DEPLOYMENT.md)
3. Database setup: [database/DATABASE_SERVICE.md](database/DATABASE_SERVICE.md)

### If You're a **Hackathon Participant** (First Time)
1. Start: [hackathon/HACKATHON_GUIDE.md](hackathon/HACKATHON_GUIDE.md) — Project overview
2. Quick start: Run the 5-minute setup
3. Then read [ARCHITECTURE_OVERVIEW.md](ARCHITECTURE_OVERVIEW.md) to understand design
4. Pick your layer and deep dive into appropriate docs

---

## 📊 Documentation Statistics

| Component | Doc File | Lines | Key Topics |
|-----------|----------|-------|------------|
| **Architecture** | ARCHITECTURE_OVERVIEW.md | 300+ | System design, data flows, layer breakdown |
| **Backend API** | backend/BACKEND_API.md | 700+ | Endpoints, schemas, middleware, error handling |
| **Frontend** | frontend/REACT_FRONTEND.md | 650+ | Components, state, Vite, API client |
| **Database** | database/DATABASE_SERVICE.md | 550+ | Schema, functions, concurrency, backup |
| **ML Pipeline** | modeling/ML_PIPELINE.md | 600+ | Graph building, GNN architecture, topology |
| **Deployment** | deployment/RENDER_DEPLOYMENT.md | 550+ | Render setup, monitoring, CI/CD, scaling |
| **Hackathon** | hackathon/HACKATHON_GUIDE.md | 600+ | Project overview, demo, tips, troubleshooting |
| **TOTAL** | 7 files | 4,000+ lines | Complete system reference |

---

## 🔄 Data Flow Cheat Sheet

### 1. User Queries Alerts
```
Frontend (Investigate.jsx)
  ↓ api.getAlerts({pattern: 'FAN_OUT'})
Backend GET /alerts?pattern=FAN_OUT
  ↓ core.db.load_alerts({pattern_type: 'FAN_OUT'})
Database load_alerts()
  ↓ SELECT * FROM alerts WHERE pattern_type = 'FAN_OUT'
SQLite query
  ↓ Parse JSON (nodes, edges)
Frontend receives filtered alert list
  ↓ Display in sidebar, allow click to select
```

### 2. User Makes a Decision
```
Frontend (Investigate.jsx) "Confirm" button click
  ↓ api.postDecision(alertId, {decision: 'confirm', reason: '...'})
Backend POST /alerts/{id}/decision
  ↓ core.db.record_decision(alert_id, 'confirm', reason, analyst)
Database record_decision()
  ↓ INSERT INTO decisions (alert_id, decision_type, reason, analyst, created_at)
SQLite append row
  ↓ Return decision ID
Frontend updates decision UI (shows "Confirmed")
  ↓ Can view history via api.getDecisionHistory(alertId)
```

### 3. User Triggers Scan
```
Frontend (Dashboard.jsx) "Scan" button click
  ↓ api.scanPipeline(max_rows: 600000)
Backend POST /scan
  ↓ asyncio.create_task(multignn_pipeline.scan())
ML Pipeline runs in background
  ├─ build_graph(trans_df, acct_df)
  ├─ score_transactions(graph, model)
  ├─ classify_topology(in_degree, out_degree)
  └─ filter_alerts(whitelist)
  ↓ core.db.replace_alerts(alert_list)
Database replace_alerts()
  ├─ DELETE FROM alerts (remove old)
  └─ INSERT INTO alerts (new alerts)
SQLite persist
  ↓ Return scan summary
Frontend polls GET /status to show progress
  ↓ Displays updated alert counts
```

---

## ⚡ Key Files by Location

### `src/backend/`
| File | Lines | Purpose |
|------|-------|---------|
| `api/main.py` | 574 | All API endpoints, middleware, SPA routing |
| `core/db.py` | 17 | Thin delegation to database.service |
| `core/whitelist.py` | 150+ | Exemption filtering |
| `pipeline/detection.py` | 300+ | Graph building, scoring, clustering |
| `models/multignn.py` | 250+ | Multi-GNN PyTorch model |
| `utils/logging.py` | 50+ | Structured logging setup |

### `src/database/`
| File | Lines | Purpose |
|------|-------|---------|
| `service.py` | 250+ | All persistence functions (thread-safe) |
| `schemas/schema.sql` | 50+ | Table definitions & indexes |
| `__init__.py` | 2 | Package marker |

### `src/frontend/`
| File | Lines | Purpose |
|------|-------|---------|
| `src/App.jsx` | 250+ | Global state, view routing, data polling |
| `src/index.jsx` | 10 | React entry point |
| `src/utils/api.js` | 200+ | Centralized HTTP client |
| `src/components/Navigation.jsx` | 50+ | Header, tabs, theme toggle |
| `src/components/Dashboard.jsx` | 100+ | KPI cards, charts |
| `src/components/Investigate.jsx` | 150+ | Alert details, graph, decisions |
| `src/components/CaseManager.jsx` | 100+ | Decisions table, CSV export |
| `src/components/Search.jsx` | 80+ | Search UI, filters |
| `src/components/Whitelist.jsx` | 120+ | Exemption management |

---

## 🚀 Common Tasks

### How do I add a new API endpoint?
1. Read [backend/BACKEND_API.md](backend/BACKEND_API.md) — understand patterns
2. Add endpoint to `src/backend/api/main.py`
3. Define Pydantic request/response schema
4. Call `core.db.*` or pipeline functions as needed
5. Test with `curl` or frontend

### How do I add a new React component?
1. Read [frontend/REACT_FRONTEND.md](frontend/REACT_FRONTEND.md)
2. Create `src/components/YourComponent.jsx`
3. Export from `src/App.jsx`
4. Add route in `currentView` switch statement
5. Pass props and callbacks as needed

### How do I query the database directly?
1. Read [database/DATABASE_SERVICE.md](database/DATABASE_SERVICE.md)
2. Call `from database import service`
3. Use: `service.load_alerts(filters)`, `service.record_decision(...)`, etc.
4. All operations are thread-safe (RLock)

### How do I improve model accuracy?
1. Read [modeling/ML_PIPELINE.md](modeling/ML_PIPELINE.md)
2. Modify `build_graph()` to add more edge features
3. Tune `MultiGNN` architecture (hidden size, layers, dropout)
4. Adjust training hyperparameters in `TRAINING_CONFIG`
5. Retrain: `python scripts/train.py --epochs 50`

### How do I deploy to production?
1. Read [deployment/RENDER_DEPLOYMENT.md](deployment/RENDER_DEPLOYMENT.md)
2. Upload model to Git LFS or S3
3. Create Render service
4. Set build & start commands
5. Configure environment variables
6. Monitor logs & health checks

---

## 💡 Design Principles

### 1. **Separation of Concerns**
- Frontend knows about API only (via `api.js`)
- Backend orchestrates database & pipeline
- Database owns schema (separate service)
- Pipeline handles ML logic

### 2. **Single Responsibility**
- Each component owns one view (Dashboard, Investigate, etc.)
- Each database function does one operation
- Each API endpoint maps to one action

### 3. **Backward Compatibility**
- `core/db.py` delegates to `database.service`
- Existing imports still work: `from backend.core import db`

### 4. **Thread Safety**
- Database operations protected by RLock
- Pipeline & API handlers can call concurrently

### 5. **Immutable Audit Trail**
- Decisions table is append-only
- Full history preserved for compliance

### 6. **Testability**
- API stateless (no global request state except context vars)
- Database functions pure (deterministic)
- ML pipeline composable (can test graph building separately)

---

## ❓ FAQ

**Q: Where do I start?**  
A: Read [ARCHITECTURE_OVERVIEW.md](ARCHITECTURE_OVERVIEW.md) for a 15-minute overview of how everything connects.

**Q: How is this different from a monolith?**  
A: Database is separate service (future-proof for PostgreSQL migration). Frontend is independent React SPA. Backend orchestrates but doesn't own persistence.

**Q: What's the decision table for?**  
A: Compliance requirement: immutable audit trail of analyst decisions. Never modified, only appended. Supports regulatory inquiries.

**Q: Can I change the ML model?**  
A: Yes! See [modeling/ML_PIPELINE.md](modeling/ML_PIPELINE.md). Modify `build_graph()` for features, `MultiGNN` for architecture, or training hyperparameters.

**Q: How do I handle model updates?**  
A: Retrain with new data, overwrite `data/multignn_model.pt`, redeploy. (Future: implement model versioning & A/B testing)

**Q: Is the frontend build required?**  
A: Yes. Backend serves React dist/ in production. In dev, Vite dev server (5173) proxies API calls to backend (8000).

**Q: Why SQLite vs PostgreSQL?**  
A: SQLite for development simplicity & local testing. Render deployment recommended: migrate to PostgreSQL for persistence & multi-instance setup.

---

## 📖 Reading Order by Goal

### Goal: Understand the System (30 min)
1. [ARCHITECTURE_OVERVIEW.md](ARCHITECTURE_OVERVIEW.md) — System design
2. [hackathon/HACKATHON_GUIDE.md](hackathon/HACKATHON_GUIDE.md) — Project overview

### Goal: Implement a Feature (2-4 hours)
1. [ARCHITECTURE_OVERVIEW.md](ARCHITECTURE_OVERVIEW.md) — Data flows
2. Relevant layer doc (backend/frontend/database)
3. Search codebase for similar patterns
4. Implement & test

### Goal: Deploy to Production (3-5 hours)
1. [ARCHITECTURE_OVERVIEW.md](ARCHITECTURE_OVERVIEW.md)
2. [deployment/RENDER_DEPLOYMENT.md](deployment/RENDER_DEPLOYMENT.md)
3. [database/DATABASE_SERVICE.md](database/DATABASE_SERVICE.md) — If migrating DB
4. Set up monitoring & backups

### Goal: Learn the ML Model (1-2 hours)
1. [modeling/ML_PIPELINE.md](modeling/ML_PIPELINE.md) — GNN architecture
2. [src/backend/models/multignn.py](../src/backend/models/multignn.py) — Read code
3. [scripts/train.py](../scripts/train.py) — Training script

---

## 🎓 Glossary

| Term | Definition | Docs |
|------|-----------|------|
| **Alert** | Suspicious transaction cluster detected by ML | [ARCHITECTURE_OVERVIEW.md](ARCHITECTURE_OVERVIEW.md) |
| **Decision** | Analyst's verdict on an alert (confirm, review, dismiss) | [DATABASE_SERVICE.md](database/DATABASE_SERVICE.md) |
| **Pattern** | Network topology (FAN_OUT, FAN_IN, CYCLE, etc.) | [ML_PIPELINE.md](modeling/ML_PIPELINE.md) |
| **GNN** | Graph Neural Network (learns from transaction networks) | [ML_PIPELINE.md](modeling/ML_PIPELINE.md) |
| **Whitelist** | Known-good accounts/banks (suppress false positives) | [BACKEND_API.md](backend/BACKEND_API.md) |
| **SPA** | Single-Page Application (React routing on frontend) | [REACT_FRONTEND.md](frontend/REACT_FRONTEND.md) |
| **WAL** | Write-Ahead Logging (SQLite concurrency mode) | [DATABASE_SERVICE.md](database/DATABASE_SERVICE.md) |
| **RLock** | Reentrant Lock (thread-safe database access) | [DATABASE_SERVICE.md](database/DATABASE_SERVICE.md) |

---

## 📞 Support & Resources

- **Confused about the architecture?** → [ARCHITECTURE_OVERVIEW.md](ARCHITECTURE_OVERVIEW.md)
- **Need an API endpoint reference?** → [backend/BACKEND_API.md](backend/BACKEND_API.md)
- **Questions about components?** → [frontend/REACT_FRONTEND.md](frontend/REACT_FRONTEND.md)
- **Database operations?** → [database/DATABASE_SERVICE.md](database/DATABASE_SERVICE.md)
- **ML model details?** → [modeling/ML_PIPELINE.md](modeling/ML_PIPELINE.md)
- **Deploying to production?** → [deployment/RENDER_DEPLOYMENT.md](deployment/RENDER_DEPLOYMENT.md)
- **Getting started with the project?** → [hackathon/HACKATHON_GUIDE.md](hackathon/HACKATHON_GUIDE.md)

---

**Last Updated:** 2026-06-29  
**Status:** Complete & Production-Ready ✅

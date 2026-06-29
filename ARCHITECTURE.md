# Architecture

Argus is a single-service AML detection platform: a FastAPI backend serves both the API and the vanilla JS frontend as static files.

The system ingests transaction CSVs, scores every transaction edge with a Multi-GNN, clusters flagged transactions into alerts, and presents them in a dashboard for analyst review.

## Data Flow

1. **Startup:** FastAPI lifespan initializes SQLite (WAL mode), checks for cached alerts
2. **Pipeline thread:** If no cache, loads trained Multi-GNN model from `data/multignn_model.pt`
3. **Graph construction:** Reads `HI-Small_Trans.csv`, builds NetworkX directed multigraph with reverse edges and port numbering
4. **Scoring:** Multi-GNN (PNAConv + GINEConv) classifies each edge as laundering/legitimate
5. **Filtering:** Edges above threshold (max of model F1-optimal threshold, 0.90 floor) are flagged
6. **Clustering:** Flagged edges grouped by weakly connected components → alert clusters
7. **Topology:** Each cluster classified (FAN_OUT, FAN_IN, CYCLE, SCATTER_GATHER, etc.)
8. **Serialization:** Raw clusters → frontend JSON shape with camelCase keys
9. **Whitelist:** Known-good accounts/banks filtered out, suppressed alerts tracked separately
10. **Persistence:** Alerts stored in SQLite, decisions recorded in append-only audit trail
11. **Frontend:** Vanilla JS dashboard polls `/status`, renders alerts, supports analyst decisions

## Component Map

```
┌─────────────────────────────────────────────────────┐
│  FastAPI (src/backend/api/main.py)                  │
│  ├─ /health, /status, /alerts, /decisions, ...      │
│  ├─ Static file serving (css, js, lib, public)      │
│  └─ SPA fallback (index.html)                       │
├─────────────────────────────────────────────────────┤
│  Pipeline (src/backend/pipeline/detection.py)       │
│  └─ build_graph → score → cluster → classify → ser │
├─────────────────────────────────────────────────────┤
│  Multi-GNN (src/backend/models/multignn.py)         │
│  └─ PNAConv + GINEConv edge classifier              │
├─────────────────────────────────────────────────────┤
│  Database (src/database/service.py)                 │
│  └─ SQLite WAL: alerts table + decisions audit log  │
├─────────────────────────────────────────────────────┤
│  Frontend (src/frontend/)                           │
│  └─ Vanilla JS dashboard served as static files     │
└─────────────────────────────────────────────────────┘
```

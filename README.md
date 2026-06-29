# Argus — AML Intelligence Platform

Real-time anti-money laundering detection using a Multi-GNN (Graph Neural Network) that classifies transactions as laundering/legitimate directly on the transaction multigraph. Built for the iDEA 2.0 hackathon, judged by Union Bank of India.

## Folder Structure

```
src/
  backend/
    api/main.py          FastAPI application (all routes, lifespan, static serving)
    core/
      serializer.py      Raw alert → frontend JSON shape
      whitelist.py        Account/bank exemption logic
    models/multignn.py   Multi-GNN model (PNAConv + GINEConv, edge-level classifier)
    pipeline/detection.py Detection pipeline (graph build → score → cluster → serialize)
    utils/logging.py     Structured logging setup
  database/
    service.py           SQLite persistence (alerts, decisions, audit trail)
    schemas/schema.sql   Database schema
  frontend/
    public/index.html    Dashboard HTML
    js/app.js            Vanilla JS frontend (deployed)
    css/style.css        Styles
    lib/                 Vendor libraries (Chart.js, Cytoscape)
  config.py              Central configuration (all paths, env vars, tunables)
config/
  requirements.txt       Production dependencies
  requirements-dev.txt   CI/test dependencies (no torch)
  deployment.yaml        Render config reference (documentation only)
scripts/
  serve.py               Dev server launcher
  train.py               Model training CLI
```

## Running Locally

```bash
# 1. Create virtual environment
python -m venv venv
venv\Scripts\activate  # Windows
# source venv/bin/activate  # Linux/Mac

# 2. Install dependencies
pip install -r config/requirements.txt

# 3. Place dataset
# Download HI-Small_Trans.csv into data/active/
# (475MB — not in repo, gitignored)

# 4. Train the model (optional — app runs in degraded mode without it)
python scripts/train.py --epochs 8

# 5. Start the server
python scripts/serve.py
# Open http://localhost:8000
```

## Deploying to Render

Render uses dashboard settings, not `deployment.yaml`. Configure manually:

1. **Build command:** `pip install -r config/requirements.txt`
2. **Start command:** `uvicorn src.backend.api.main:app --host 0.0.0.0 --port $PORT`
3. **Environment variables:**
   - `PYTHONPATH=src` (required for imports)
   - `PORT` is set automatically by Render
4. **Python version:** 3.14 (set via `.python-version` file)

The model file (`data/multignn_model.pt`) is not in the repo. Without it, the app starts in degraded mode — `/health` returns 200, but no alerts are generated. Upload the trained model to Render's disk or use the pipeline cache.

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `PORT` | `8000` | Server port (Render sets this) |
| `HOST` | `0.0.0.0` | Bind address |
| `MULTIGNN_MAX_ROWS` | `600000` | Max transactions to process |

## Key Endpoints

| Endpoint | Description |
|---|---|
| `GET /health` | Health check (always 200) |
| `GET /status` | Pipeline status + alert breakdown |
| `GET /alerts` | List all alerts |
| `POST /alerts/{id}/decision` | Record analyst decision |
| `GET /decisions` | Current decisions |
| `GET /whitelist` | View whitelisted accounts |

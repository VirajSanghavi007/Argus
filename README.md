# Argus — AML Intelligence Platform

Real-time anti-money laundering detection using a Multi-GNN (Graph Neural Network) that classifies transactions as laundering/legitimate directly on the transaction multigraph. Built for the iDEA 2.0 hackathon, judged by Union Bank of India.

## Folder Structure

```
src/
  backend/
    api/main.py          FastAPI application (all routes, lifespan, static serving)
    core/
      serializer.py      Raw alert → frontend JSON shape
      whitelist.py        Account/bank exemption logic (rules in code, accounts in Postgres)
    models/multignn.py   Multi-GNN model (PNAConv + GINEConv, edge-level classifier)
    pipeline/detection.py Detection pipeline (graph build → score → cluster → serialize)
    utils/logging.py     Structured logging setup
    tests/               Pytest suite (pure logic only — no DB, no torch)
  database/
    service.py           PostgreSQL persistence (alerts, decisions, audit trail, whitelist, sessions)
    schemas/schema_postgres.sql   Database schema
  frontend/
    public/index.html    Dashboard HTML
    js/app.js            Vanilla JS frontend (deployed)
    css/style.css        Styles
    lib/                 Vendor libraries (Chart.js, Cytoscape)
  config.py              Central configuration (all paths, env vars, tunables)
config/
  requirements-dev.txt   CI/test dependencies (no torch)
scripts/
  train.py               Model training CLI (offline — not used by the running server)
requirements.txt         Production dependencies (used by Dockerfile and local installs)
```

## Running Locally

```bash
# 1. Create virtual environment
python -m venv venv
venv\Scripts\activate  # Windows
# source venv/bin/activate  # Linux/Mac

# 2. Install dependencies
pip install -r requirements.txt

# 3. Point at a Postgres database (required — there is no SQLite fallback)
export DATABASE_URL=postgresql://user:pass@host:5432/dbname

# 4. Place dataset
# HI-Medium_Trans.csv under data/archive/datasets/IBM/ (gitignored, not in repo)

# 5. Train the model (optional — app runs in degraded mode without it)
python scripts/train.py --epochs 6 --datasets data/archive/datasets/IBM/HI-Medium_Trans.csv --max-rows 1500000

# 6. Start the server (no --reload: watchfiles spawns duplicate workers
#    that fight over the port when the pipeline writes to data/ on startup)
PYTHONPATH=src python -m uvicorn backend.api.main:app --host 0.0.0.0 --port 8000
# Open http://localhost:8000
```

## Deploying

Live deployment is Hugging Face Spaces (Docker SDK) — see `deploy-hf.ps1` for the one-command redeploy. The Dockerfile installs `requirements.txt` for the core API, then installs CPU `torch` + `torch_geometric` separately for the ML path. `DATABASE_URL` must be set as an HF Space **secret** (never committed to a file).

The model file (`data/multignn_model.pt`) and `data/pipeline_cache.json` are gitignored but force-added by `deploy-hf.ps1` so the deployed app serves alerts immediately without re-running the pipeline cold.

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | *(required)* | Postgres connection string — no local fallback |
| `PORT` | `8000` | Server port |
| `HOST` | `0.0.0.0` | Bind address |
| `MULTIGNN_MAX_ROWS` | `800000` | Max transactions read from the dataset at pipeline startup |
| `ARGUS_INGEST_KEY` | *(unset)* | If set, required as `X-API-Key` header on `POST /ingest` |
| `ARGUS_SECRET` | `argus-aml-2026` | Salt for password hashing |

## Key Endpoints

| Endpoint | Description |
|---|---|
| `GET /health` | Health check (always 200) |
| `GET /status` | Pipeline status + alert breakdown |
| `GET /alerts` | List all alerts |
| `POST /alerts/{id}/decision` | Record analyst decision |
| `GET /decisions` | Current decisions |
| `GET /whitelist` | View whitelisted accounts |
| `GET /accounts/risky` | Top accounts by aggregate laundering-edge risk |
| `GET /account/{id}/history` | Full flagged-transaction history for one account |
| `POST /ingest` | Stream live transactions in (single, batch, or `{transactions: [...]}`) |
| `POST /predict` | Score an uploaded CSV/Excel of transactions on demand |

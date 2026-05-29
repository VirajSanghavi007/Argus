# AML Intelligence Platform

> Graph-native money laundering detection — labelled **and** unsupervised — on IBM's synthetic transaction dataset, with whitelist-based false-positive reduction

![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-0.136%2B-green)
![NetworkX](https://img.shields.io/badge/NetworkX-3.x-orange)
![MIT License](https://img.shields.io/badge/License-MIT-yellow)

---

## Overview

This system detects money laundering patterns in transaction graphs without requiring any trained model. It runs two detection pipelines in parallel, cross-validates their output, and filters results through a whitelist system to suppress known false positives before alerts reach the investigator.

| Mode | Input | Method |
|------|-------|--------|
| **Labelled** | `Is Laundering == 1` rows | Pre-filter, build graph, classify topology |
| **Unlabelled** | All transactions | 7 behavioural signals, score ≥ 2 → suspicious |

Both pipelines feed the same 8-topology classifier. Alerts found by both modes are marked `source: "both"` — the strongest cross-validation signal without ground truth.

---

## Detection Modes

### Labelled Mode

Filters the 48-hour window to rows where `Is Laundering == 1`, builds a directed graph, and classifies each weakly-connected component (≥3 nodes) by topology. High precision, lower recall (48-hour window clips multi-day schemes).

### Unlabelled Mode — 7 Behavioural Signals

| # | Signal | Description | Window |
|---|--------|-------------|--------|
| 1 | **Rapid Fan-Out** | Account sends to 3+ distinct recipients | 2 hours |
| 2 | **Round-Trip** | Money returns to originator (A→B→A) | 24 hours |
| 3 | **Structuring** | 3+ transactions clustering just below $10k or $50k | 1 hour |
| 4 | **Layering Velocity** | Account re-forwards ≥90% of received funds | 6 hours |
| 5 | **Dormant Activation** | Account silent in first 24h, then 3+ txns in 2h burst | 24h midpoint |
| 6 | **Currency Mismatch** | Receives in one currency set, forwards in a different set | per-account |
| 7 | **Smurfing** | 5+ accounts each send $1k–$10k to same dest in 4h | 4 hours |

Accounts scoring **≥ 2 signals** are flagged. `G_unlabelled` includes all edges touching at least one flagged account.

### Overlap / Cross-Validation

After both pipelines complete, alerts are deduplicated by **>80% account-set overlap**. If found by both modes, the labelled alert is upgraded to `source: "both"`.

---

## Whitelist / Exemption System

Business accounts and known financial institutions that legitimately trigger detection patterns are held in `data/whitelist.json`. The whitelist filter runs after the pipeline completes and before alerts reach the API.

**Exemption rules by pattern:**

| Pattern | Exempt If |
|---------|-----------|
| FAN_IN | Account is a business entity or exempt bank |
| FAN_OUT | Account is a business entity or exempt bank |
| BIPARTITE | Account belongs to an exempt bank |

**Full suppression vs. partial exemption:**
- All nodes in cluster are exempt → alert moved to `SUPPRESSED` dict (viewable at `/alerts/suppressed`)
- Only some nodes exempt → alert kept but flagged with `partial_exemption: true`

Default exempt banks: `Federal Reserve`, `Central Bank`, `RBI`, `ECB`

Manage the whitelist via the **Whitelist tab** in the UI or through the REST API.

---

## Architecture

```
HI-Small_Trans.csv
        │
   load_and_build()
        │
   ┌────┴────────────────────────────────┐
   │  48-hr window, no self-loops        │
   └────────────┬────────────────────────┘
                │
   ┌────────────▼──────────┐   ┌──────────────────────────────────────────────┐
   │   LABELLED MODE       │   │   UNLABELLED MODE                            │
   │                       │   │                                              │
   │  df[Is Laundering==1] │   │  find_suspicious_unlabelled()                │
   │  → G_suspicious       │   │  ⚡ Rapid Fan-Out (2h)                       │
   │                       │   │  🔁 Round-Trip (24h)                         │
   │                       │   │  💰 Structuring (1h)                         │
   │                       │   │  🌊 Layering Velocity (6h)                   │
   │                       │   │  😴 Dormant Activation (24h midpoint)        │
   │                       │   │  💱 Currency Mismatch (per-account)          │
   │                       │   │  🐚 Smurfing (4h)                            │
   │                       │   │  Score ≥ 2 → G_unlabelled                    │
   └──────────┬────────────┘   └──────────────────┬───────────────────────────┘
              │                                   │
              └──────────┬────────────────────────┘
                         │
              detect_all_patterns()
              (same topology classifier)
                         │
                 _merge_raw_alerts()
              (>80% overlap → source:"both")
                         │
              filter_alerts()  ←── whitelist.json
              ┌──────────┴────────────┐
              │                       │
           KEPT alerts          SUPPRESSED alerts
           /alerts               /alerts/suppressed
                         │
               serialize_alerts()
                         │
            FastAPI  /alerts  /status  /whitelist
                         │
               frontend/index.html
          ┌──────────────────────────────┐
          │  Dashboard · Investigate     │
          │  Case Manager · Search       │
          │  Validation · Whitelist      │
          └──────────────────────────────┘
```

---

## Quick Start

### 1. Setup

```bash
cd aml-prototype
python -m venv venv
venv\Scripts\pip install -r backend\requirements.txt
```

Download the dataset (Kaggle account required), or the backend will auto-download on first start if `KAGGLE_USERNAME` / `KAGGLE_KEY` env vars are set:

```bash
kaggle datasets download -d ealtman2019/ibm-transactions-for-anti-money-laundering-aml \
  -f HI-Small_Trans.csv -p data/ --unzip
```

### 2. Run

**Windows (double-click):**
```
Bootup.bat
```

**Manual:**
```bash
cd backend
..\venv\Scripts\python.exe -m uvicorn main:app --host 0.0.0.0 --port 8000
```

Then open `frontend/index.html` in Chrome. The UI shows an animated loading screen while both pipelines run (~5–8 minutes on first launch), then transitions to the dashboard automatically.

### 3. UI Views

| Tab | Description |
|-----|-------------|
| Dashboard | Stat cards, pattern breakdown, source distribution |
| Investigate | Alert list with graph visualiser and transaction timeline |
| Case Manager | Decision tracking table |
| Search | Full-text + filter search across all alerts |
| Validation | Ground-truth comparison metrics |
| Whitelist | Manage exemptions, view suppressed alerts |

---

## API

| Endpoint | Description |
|----------|-------------|
| `GET /health` | Always 200 |
| `GET /status` | Pipeline state + alert counts + suppressed count |
| `GET /alerts` | All alerts. Filters: `?severity=HIGH`, `?source=unlabelled`, `?pattern_type=fanOut` |
| `GET /alerts/{id}` | Full alert detail |
| `GET /alerts/suppressed` | Alerts suppressed by whitelist rules |
| `POST /alerts/{id}/decision` | `{"decision":"confirm","reason":"..."}` |
| `GET /whitelist` | Current whitelist JSON |
| `POST /whitelist/account` | Add account to exempt list |
| `DELETE /whitelist/account/{id}` | Remove account from exempt list |
| `GET /validation` | Reads `data/validation_results.json` |

---

## Tests

```bash
cd aml-prototype

# Unit — pipeline + detector (requires CSV)
venv\Scripts\python.exe -m pytest tests/test_pipeline.py tests/test_detector.py -v

# End-to-end (starts server on port 8001)
venv\Scripts\python.exe -m pytest tests/test_e2e.py -v --timeout=900
```

---

## Project Structure

```
aml-prototype/
├── backend/
│   ├── pipeline.py      # load_and_build() + find_suspicious_unlabelled() (7 signals)
│   ├── detector.py      # detect_all_patterns() — topology classifier
│   ├── serializer.py    # JSON formatting for frontend
│   ├── whitelist.py     # Exemption logic, load/save, filter_alerts()
│   ├── main.py          # FastAPI app — whitelist endpoints, suppressed alerts
│   ├── validator.py     # Ground-truth comparison vs HI-Small_Patterns.txt
│   └── requirements.txt
├── frontend/
│   └── index.html       # 6-view light-theme dashboard (Syne + DM Mono)
├── tests/
│   ├── test_pipeline.py # Pipeline tests
│   ├── test_detector.py # Detector tests
│   └── test_e2e.py      # End-to-end API tests
├── data/
│   ├── HI-Small_Trans.csv     (gitignored — download separately)
│   ├── HI-Small_Patterns.txt  (ground truth)
│   ├── whitelist.json         (committed — default exemptions)
│   └── validation_results.json
├── docs/
│   ├── ARCHITECTURE.md
│   └── API.md
├── render.yaml          # Render deployment config
├── DEPLOYMENT.md        # Deployment instructions
├── Bootup.bat
└── README.md
```

---

## Deployment

See [DEPLOYMENT.md](DEPLOYMENT.md) for full Render + Netlify instructions.

**Backend (Render):** Set `KAGGLE_USERNAME` and `KAGGLE_KEY` env vars. The pipeline auto-downloads the CSV on first deploy.

**Frontend (Netlify):** Drag `frontend/` into Netlify. The `API_BASE` constant auto-detects localhost vs. production.

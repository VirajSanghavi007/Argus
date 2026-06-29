# Argus AML — Professional Project Structure

## Directory Organization

```
argus-aml/
├── src/                          # Source code
│   ├── backend/
│   │   ├── api/
│   │   │   └── main.py          # FastAPI server (port 8000)
│   │   ├── models/
│   │   │   └── multignn.py      # GNN architecture & training
│   │   ├── pipeline/
│   │   │   └── detection.py     # Transaction scoring & clustering
│   │   ├── core/
│   │   │   ├── db.py            # SQLite ORM (decisions, alerts)
│   │   │   ├── serializer.py    # Alert JSON transformation
│   │   │   └── whitelist.py     # Exemption rules & filtering
│   │   ├── utils/
│   │   │   └── logging.py       # Structured logging setup
│   │   └── tests/
│   │       ├── test_api.py      # API endpoint tests
│   │       └── test_e2e.py      # Integration tests
│   └── frontend/
│       ├── public/
│       │   └── index.html       # SPA dashboard
│       ├── js/
│       │   └── app.js           # Frontend logic (React-like patterns)
│       ├── css/
│       │   └── style.css        # Styling + dark mode
│       └── lib/                 # Vendor libraries (Cytoscape, Chart.js)
│
├── config/                       # Configuration & dependencies
│   ├── requirements.txt         # Production dependencies
│   ├── requirements-dev.txt     # Dev/test dependencies
│   └── deployment.yaml          # Render.com config
│
├── scripts/                      # Entry points
│   ├── train.py                 # python scripts/train.py --epochs 8
│   └── serve.py                 # python scripts/serve.py (localhost:8000)
│
├── data/                         # Data directory
│   ├── active/                  # Training datasets
│   │   ├── HI-Small_Trans.csv   # 268k transactions
│   │   └── HI-Small_accounts.csv
│   ├── archive/                 # Alternative datasets (Elliptic, SAML-D, etc.)
│   ├── multignn_model.pt        # Trained weights (985 KB)
│   ├── multignn_meta.json       # Model metadata
│   ├── argus.db                 # SQLite decision audit trail
│   ├── argus.db-wal             # WAL checkpoint
│   ├── argus.db-shm             # Shared memory
│   └── whitelist.json           # Exemption rules
│
├── logs/                         # Log files
│   ├── api/
│   └── pipeline/
│
├── docs/                         # Documentation
│   └── README.md
│
├── archive/                      # Legacy files
│   └── legacy/                   # Old .bat scripts, notebooks, analysis scripts
│
├── README.md                     # Root README
├── CLAUDE.md                     # AI assistant instructions
└── .gitignore
```

## Quick Start

### Install
```bash
pip install -r config/requirements.txt
```

### Train (GPU-friendly)
```bash
python scripts/train.py --epochs 8 --max-rows 600000
```

### Run Server
```bash
python scripts/serve.py
# Open http://localhost:8000
```

### Test
```bash
pytest src/backend/tests/
```

## Key Improvements

✅ **Modular Architecture**
- Clear separation: API layer → Pipeline → Models → Core services
- Each module is testable and reusable

✅ **Professional Naming**
- `multignn_model.py` → `models/multignn.py`
- `multignn_pipeline.py` → `pipeline/detection.py`
- `log_setup.py` → `utils/logging.py`
- `main.py` → `api/main.py`

✅ **Clean Data Management**
- `data/active/` for current training data
- `data/archive/` for alternative datasets (100GB preserved)
- All production files at `data/` root level

✅ **Centralized Config**
- `config/requirements.txt` (single source of truth)
- `config/requirements-dev.txt` for testing
- `config/deployment.yaml` for production

✅ **Entry Point Scripts**
- `scripts/train.py` - Training wrapper
- `scripts/serve.py` - Development server wrapper

✅ **Organized Logs**
- Structured logging with request IDs
- `logs/api/` for API events
- `logs/pipeline/` for detection pipeline

## Import Patterns

**Backend (use relative imports within package):**
```python
from ..core.db import init_db
from ..models.multignn import load_multignn
from ..utils.logging import setup_logging
```

**From external (use absolute imports via PYTHONPATH):**
```python
import sys; sys.path.insert(0, 'src')
from backend.api.main import app
```

## Production Deployment

1. Push to GitHub
2. Create Render service pointing to `scripts/serve.py`
3. Set environment: `PORT=10000`
4. Render auto-installs `config/requirements.txt`

---

**Status:** ✅ Ready for hackathon demo
**Model:** Multi-GNN (F1=0.0235, AUC=0.5974)
**Scale:** 268k transactions, 180k accounts

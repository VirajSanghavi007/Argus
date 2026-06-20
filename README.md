# AML Intelligence Platform

An investigation platform for tracing suspicious fund flows and detecting anti-money laundering patterns in transaction networks. The system converts transaction records into directed graphs, combines rule-based typology detection with machine learning risk scoring, and presents investigation-ready alerts in an interactive dashboard.

Built by Team Zeta for iDEA 2.0, Problem Statement 3: Fund Flow Tracking for Fraud Detection.

## Live application

[Open the deployed application](https://ideahackathon-1.onrender.com)

The application is hosted on Render. A cold start on the free tier can take up to a minute.

## What the platform does

- Builds account relationship graphs from IBM synthetic transaction data
- Detects labelled laundering components and suspicious unlabelled activity
- Classifies fund flows into eight structural AML typologies
- Scores alerts with a supervised model trained on 22 graph and transaction features
- Optionally blends Random Forest or XGBoost scores with a GraphSAGE model
- Suppresses known entities through account, bank, and business whitelist rules
- Records analyst decisions and retrains after enough feedback is collected
- Tracks score distribution drift with KL divergence
- Visualizes accounts, transactions, alert severity, and model evidence
- Provides validation metrics and standalone model benchmarks

## Detection pipeline

The application runs two complementary detection paths.

### Labelled detection

Transactions marked as laundering in the source dataset are converted into connected graph components. Each component is classified as one of the following:

| Typology | Structure |
| --- | --- |
| Cycle | Funds return through a closed directed path |
| Fan-out | One account distributes funds to several recipients |
| Fan-in | Several accounts send funds to one aggregator |
| Scatter-gather | One origin routes funds through intermediaries to one destination |
| Gather-scatter | One hub receives from and sends to multiple accounts |
| Bipartite | Two coordinated account groups transact across partitions |
| Stack | Funds move through multiple directed layers |
| Random chain | Suspicious structure that does not match a canonical pattern |

### Behavioural detection

The full transaction graph is evaluated for seven behavioural signals:

1. Rapid fan-out
2. Round-trip transfers
3. Structuring below common reporting thresholds
4. Layering velocity
5. Dormant account activation
6. Currency mismatch
7. Smurfing

Accounts that trigger at least two signals are expanded into subgraphs and passed through the same typology classifier.

### Risk scoring

Each alert is scored using graph structure, transaction amounts, timing, bank and currency diversity, degree distribution, betweenness centrality, and amount inequality. The default model is a 200-tree Random Forest. XGBoost is used when installed, and an optional GraphSAGE model can provide a second score for blending.

## Technology

| Area | Technology |
| --- | --- |
| API | FastAPI, Uvicorn, Pydantic |
| Data processing | Pandas, NumPy, SciPy |
| Graph analysis | NetworkX |
| Machine learning | scikit-learn, optional XGBoost |
| Graph neural network | optional PyTorch and PyTorch Geometric |
| Frontend | HTML, CSS, JavaScript |
| Visualization | Cytoscape.js, Chart.js |
| Testing | pytest, requests, httpx |
| Deployment | Render |

## Run locally

### Requirements

- Python 3.11 or newer
- The IBM `HI-Small_Trans.csv` dataset

### 1. Clone the repository

```bash
git clone https://github.com/VirajSanghavi007/IdeaHackathon.git
cd IdeaHackathon
```

### 2. Create and activate a virtual environment

On Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

On macOS or Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r backend/requirements.txt
```

### 4. Add the dataset

Download the IBM AML dataset from [Kaggle](https://www.kaggle.com/datasets/ealtman2019/ibm-transactions-for-anti-money-laundering-aml), then place the file at either of these locations:

```text
data/IBM/HI-Small_Trans.csv
data/HI-Small_Trans.csv
```

Dataset files and generated runtime artifacts are excluded from Git.

### 5. Start the application

```bash
cd backend
uvicorn main:app --host 0.0.0.0 --port 8000
```

Open [http://localhost:8000](http://localhost:8000). The first run builds the graphs, trains or loads the model, detects alerts, and creates a local cache. Later starts use the cache when available.

Windows users can also run `Bootup.bat` from the project root.

## API

| Method | Endpoint | Purpose |
| --- | --- | --- |
| GET | `/health` | Lightweight service health check |
| GET | `/status` | Pipeline state and alert summary |
| GET | `/alerts` | List and filter alerts |
| GET | `/alerts/suppressed` | View whitelist-suppressed alerts |
| GET | `/alerts/{alert_id}` | Retrieve complete alert details |
| POST | `/alerts/{alert_id}/decision` | Save an analyst decision and feedback |
| GET | `/whitelist` | Retrieve whitelist configuration |
| POST | `/whitelist/account` | Add an exempt account |
| DELETE | `/whitelist/account/{account_id}` | Remove an exempt account |
| GET | `/ml-metrics` | Retrieve model metrics and feature importance |
| GET | `/drift` | Retrieve model score drift history |
| GET | `/validation` | Retrieve ground truth validation results |

`GET /alerts` supports `pattern_type`, `severity`, and `source` query parameters.

## Project structure

```text
IdeaHackathon/
|-- backend/
|   |-- main.py                 FastAPI application and orchestration
|   |-- pipeline.py             Data loading and behavioural detection
|   |-- detector.py             Structural AML typology classifier
|   |-- ml_model.py             Feature extraction and supervised scoring
|   |-- gnn_model.py            Optional GraphSAGE scoring layer
|   |-- retrainer.py            Analyst feedback and model retraining
|   |-- whitelist.py            Exemption and suppression rules
|   |-- validator.py            Ground truth validation
|   |-- benchmark.py            Standalone model benchmark runner
|   |-- serializer.py           Frontend alert serialization
|   `-- requirements.txt
|-- frontend/
|   |-- index.html              Dashboard markup
|   |-- style.css               Dashboard styles
|   `-- app.js                  Dashboard behaviour and API client
|-- tests/                      Dataset-backed integration tests
|-- AML_RESEARCH_FINDINGS.md    Background domain research
|-- run_benchmarks.ps1          Benchmark helper
|-- Bootup.bat                  Windows startup helper
`-- render.yaml                 Render deployment configuration
```

## Testing

Run the fast backend unit suite used by CI:

```bash
pytest backend/tests -v
```

Run the broader pipeline tests when the dataset is available:

```bash
pytest tests/test_pipeline.py tests/test_detector.py -v
```

## Benchmarking

The benchmark runner supports IBM and TransXion-style datasets:

```bash
python backend/benchmark.py --dataset data/IBM/HI-Medium_Trans.csv
```

On Windows, `run_benchmarks.ps1` can be used to run the configured benchmark set.

## Data and model limitations

- The project uses synthetic research data, not real Union Bank customer data.
- Reported model performance does not establish production performance on live banking traffic.
- The application processes batch CSV files rather than a real-time event stream.
- Authentication, durable case storage, and enterprise audit controls are outside the current proof-of-concept scope.
- Analyst decisions are held in memory for the current process, while retraining feedback and model artifacts are written locally.
- A production deployment would require secure data ingestion, role-based access control, persistent storage, monitoring, and validation against institution-specific data.

## Team

| Member | Contribution |
| --- | --- |
| Viraj | Backend, graph detection, machine learning, frontend, deployment |
| Sonal | Domain research, problem analysis, documentation |
| Archit | Data analysis, signal design, validation testing |
| Suruchi | UI and UX design, frontend testing, demo and presentation |

Team Zeta, K. J. Somaiya College of Engineering

## Documentation

This README is the canonical technical overview for the current architecture. Background research remains available in [AML_RESEARCH_FINDINGS.md](AML_RESEARCH_FINDINGS.md).

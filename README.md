# AML Intelligence Platform

**iDEA 2.0 | PS3: Fund Flow Tracking for Fraud Detection | Team Zeta**

A graph-native Anti-Money Laundering detection and investigation system. It ingests IBM synthetic bank transaction data, constructs a directed account-relationship graph, runs a dual detection pipeline (labelled pattern classification + unlabelled behavioural signal scoring), trains a Random Forest fraud classifier, and presents investigation-ready alerts on an interactive visual dashboard.

---

## Problem Statement

This project addresses **PS3: Fund Flow Tracking for Fraud Detection** for Union Bank of India.

Union Bank processes millions of interbank transactions daily through NEFT, RTGS, UPI, and correspondent banking channels. Fraud investigation teams have no automated system to trace and visualise how illicit funds move between accounts. Investigators must manually reconstruct transaction trails, a process that takes 3 to 5 days per case, making it impossible to detect coordinated money laundering schemes (circular routing, rapid layering, smurfing) before funds exit the banking system.

This platform replaces manual investigation with automated graph-based detection, interactive visualisation, and ML-powered risk scoring.

---

## Live Demo

**Live App:** [https://ideahackathon-1.onrender.com](https://ideahackathon-1.onrender.com)

> Note: The app runs on Render free tier. First load may take 30 to 60 seconds if the instance has spun down. Subsequent loads are instant as results are cached.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Language | Python 3.12 |
| API Backend | FastAPI + Uvicorn |
| Graph Engine | NetworkX |
| ML Model | scikit-learn (Random Forest, 200 trees) |
| Data Processing | Pandas 3.0, NumPy |
| Frontend | HTML5 / CSS3 / Vanilla JS (single file) |
| Graph Visualisation | Cytoscape.js |
| Charts | Chart.js |
| Deployment | Render (free tier) |
| Dataset | IBM HI-Small Transactions (synthetic AML research data) |

---

## How to Run Locally

**Requirements:** Python 3.10 or higher

**1. Clone the repository**
```bash
git clone https://github.com/VirajSanghavi007/IdeaHackathon.git
cd IdeaHackathon
```

**2. Install dependencies**
```bash
pip install -r backend/requirements.txt
```

**3. Add the dataset**

The IBM HI-Small_Trans.csv file must be placed in the `data/` directory. It is committed to this repo. If it is missing, download it from Kaggle:

[https://www.kaggle.com/datasets/ealtman2019/ibm-transactions-for-anti-money-laundering-aml](https://www.kaggle.com/datasets/ealtman2019/ibm-transactions-for-anti-money-laundering-aml)

Download `HI-Small_Trans.csv` and place it at `data/HI-Small_Trans.csv`.

**4. Start the backend**
```bash
cd backend
uvicorn main:app --host 0.0.0.0 --port 8000
```

**5. Open the app**

Navigate to [http://localhost:8000](http://localhost:8000) in your browser.

On first run, the pipeline takes 2 to 4 minutes to process the dataset, train the ML model, and build all alerts. Results are cached to `data/pipeline_cache.json` so subsequent starts load in under 2 seconds.

---

## Project Structure

```
IdeaHackathon/
├── backend/
│   ├── main.py           # FastAPI app, pipeline orchestration, REST endpoints
│   ├── pipeline.py       # CSV loading, graph construction (NetworkX)
│   ├── detector.py       # 8-pattern AML classifier (structural graph analysis)
│   ├── ml_model.py       # Random Forest fraud classifier (16 graph features)
│   ├── serializer.py     # Converts raw alerts to frontend JSON format
│   ├── whitelist.py      # False positive suppression and exemption rules
│   ├── validator.py      # Ground truth validation against HI-Small_Patterns.txt
│   └── requirements.txt
├── frontend/
│   └── index.html        # Full single-page app (Cytoscape.js + Chart.js)
├── data/
│   ├── HI-Small_Trans.csv          # IBM synthetic transaction dataset
│   └── HI-Small_Patterns.txt       # Ground truth labels for validation
├── render.yaml           # Render deployment config
└── README.md
```

---

## Dataset

All data used in this project is **100% synthetic** from IBM's publicly available AML research dataset.

- **Source:** [IBM Transactions for Anti-Money Laundering (AML)](https://www.kaggle.com/datasets/ealtman2019/ibm-transactions-for-anti-money-laundering-aml)
- **File used:** `HI-Small_Trans.csv`
- **Size:** ~500,000 transactions across thousands of synthetic accounts
- **Window:** The pipeline filters to a 48-hour window (2022-09-01 to 2022-09-02)
- **Labels:** `Is Laundering` column identifies ground truth suspicious transactions
- **Patterns file:** `HI-Small_Patterns.txt` contains ground truth cluster definitions for validation

No real Union Bank data was used at any stage.

---

## Detection Pipeline

### Labelled Mode

Loads transactions where `Is Laundering == 1`, constructs a directed graph, and classifies each weakly-connected component (3+ nodes) into one of 8 AML typologies using structural graph analysis:

| Pattern | Detection Method |
|---|---|
| Cycle | All nodes have in-degree 1 and out-degree 1, cycle confirmed |
| Fan-Out | Single hub with out-degree 3+, all recipients are leaves |
| Fan-In | Single aggregator with in-degree 3+, all senders are roots |
| Scatter-Gather | One origin, one destination, all middle nodes are pass-through |
| Gather-Scatter | Single hub with in-degree 2+ and out-degree 2+ |
| Bipartite | Graph is bipartite (two-group coordinated structure) |
| Stack | Directed acyclic graph with 3+ topological layers |
| Random Chain | Does not match any canonical typology |

### Unlabelled Mode

Scores every account in the full transaction graph against 7 behavioural signals:

1. **Rapid Fan-Out** - sends to 3+ recipients within any 2-hour bucket
2. **Round-Trip** - money returns to originator within 24 hours
3. **Structuring** - 3+ transactions in 1 hour with amounts just below $10k or $50k
4. **Layering Velocity** - receives then re-sends 90%+ of amount within 6 hours
5. **Dormant Activation** - silent in first 24 hours, then 3+ transactions in a 2-hour window
6. **Currency Mismatch** - receives in one currency set, forwards in a different set
7. **Smurfing** - 5+ different accounts send $1k to $10k to same destination within 4 hours

Accounts triggering 2 or more signals are flagged and their subgraph is passed through the same 8-pattern classifier.

---

## ML Model Performance (on IBM Synthetic Test Set)

A Random Forest classifier (200 trees, `class_weight="balanced"`) is trained on 16 graph-level features extracted from each subgraph:

**Features used:** node count, edge count, graph density, cycle presence, max in-degree, max out-degree, average clustering coefficient, topological layer count, total/max/avg/std transaction amount, time span in hours, bank count, currency count, edge-to-node ratio

| Metric | Score |
|---|---|
| F1 Score | ~0.85 |
| Precision | ~0.87 |
| Recall | ~0.83 |
| Accuracy | ~0.91 |

> Results are on IBM synthetic data. Performance on real bank data would require retraining with actual transaction records.

The trained model is saved to `data/fraud_model.pkl` and loaded on subsequent startups. Model metrics and per-feature importances are available at the `/ml-metrics` endpoint.

---

## API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| GET | `/` | Serves the frontend dashboard |
| GET | `/status` | Pipeline status, alert counts, pattern breakdown |
| GET | `/alerts` | All alerts, filterable by pattern/severity/source |
| GET | `/alerts/{id}` | Full alert with graph, transactions, nodes |
| POST | `/alerts/{id}/decision` | Record analyst decision (confirm/review/dismiss) |
| GET | `/alerts/suppressed` | Whitelist-suppressed alerts audit trail |
| GET | `/whitelist` | Current whitelist configuration |
| POST | `/whitelist/account` | Add account to whitelist |
| DELETE | `/whitelist/account/{id}` | Remove account from whitelist |
| GET | `/ml-metrics` | Random Forest performance and feature importances |
| GET | `/validation` | Ground truth precision/recall comparison |

---

## Known Limitations

- Trained and tested on IBM synthetic data only. Real-world performance would require retraining on actual Union Bank transaction records.
- The pipeline processes a batch CSV snapshot. A production system would need real-time stream ingestion (Apache Kafka or similar).
- Detection covers 8 structural AML typologies. A full production system would require 15 to 20+ patterns including trade-based laundering and crypto-fiat conversion chains.
- No user authentication on the dashboard. Acceptable for a POC demo; production would require role-based access control and audit logging.
- The 48-hour transaction window is used for graph construction. A deployed system would operate on a rolling window or full transaction history.
- Whitelist exemption uses bank name pattern matching. A production system would integrate with a verified KYC/KYB entity database.
- Analyst decisions are stored in memory and reset on server restart. Production would persist these to a database.

---

## Team

**Team Zeta**

| Member | Contribution |
|---|---|
| Viraj   | Backend, ML model, graph detection pipeline, frontend, deployment |
| Sonal   | |
| Archit  | |
| Suruchi | |

---

## Contact

**Team Name:** Zeta
**Problem Statement:** PS3 - Fund Flow Tracking for Fraud Detection
**Institute:** K.J. Somaiya College of Engineering
**Event:** iDEA 2.0 Phase 2 - POC Stage

---

*iDEA 2.0 Phase 2 Submission | Union Bank of India x K.J. Somaiya School of Engineering*

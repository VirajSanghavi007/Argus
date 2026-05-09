# Deployment Guide

## Live URLs

| Service | URL |
|---------|-----|
| Backend API | `https://aml-backend.onrender.com` |
| Frontend | Open `frontend/index.html` locally, or host on Netlify |

> Replace the URLs above with your actual Render service URL after first deploy.

---

## Backend — Render

### First Deploy

1. Push this repo to GitHub.
2. Go to [render.com](https://render.com) → **New** → **Web Service**.
3. Connect your GitHub repo and select the `aml-prototype` directory.
4. Render will detect `render.yaml` automatically.
5. Under **Environment Variables**, add:
   - `KAGGLE_USERNAME` — your Kaggle username
   - `KAGGLE_KEY` — your Kaggle API key (from `kaggle.json`)
6. Click **Deploy**. The first deploy downloads `HI-Small_Trans.csv` (~150 MB) and runs the full pipeline (~8 min). Watch the logs.

### Redeploying After Changes

```bash
git add -A
git commit -m "your change"
git push origin main
```

Render auto-deploys on every push to `main`.

### Checking Render Logs

1. Go to your Render dashboard.
2. Click the **aml-backend** service.
3. Click **Logs** in the left sidebar.

Key log lines to look for:

```
Pipeline starting in background thread...
Loaded: 1800000 rows, 9 columns
48-hr window: XXXXX rows
Unlabelled detection — running 7 signals...
  Signal 1 (Rapid Fan-Out):    X,XXX accounts
  ...
  Suspicious (≥2 signals):     X,XXX accounts
Labelled: 46 | Unlabelled: X | Overlap: Y | Suppressed: Z | Total: W
```

---

## Frontend — Netlify (optional)

The frontend is a single static HTML file with no build step.

1. Go to [netlify.com](https://netlify.com) → **Add new site** → **Deploy manually**.
2. Drag the `frontend/` folder into the Netlify drop zone.
3. The site deploys instantly. The `API_BASE` in `index.html` auto-detects the backend URL based on hostname.

To point to your Render backend, the frontend uses:

```javascript
const API_BASE = (hostname === 'localhost' || hostname === '' || protocol === 'file:')
  ? 'http://localhost:8000'
  : 'https://aml-backend.onrender.com';
```

Update the production URL in `frontend/index.html` if your Render service URL differs.

---

## Whitelist Management

The whitelist controls which accounts and banks are exempted from triggering alerts.

### Via the UI (Whitelist Tab)

1. Open the app and click **Whitelist** in the nav.
2. The **verdict banner** shows how many alerts were suppressed.
3. To add an account: enter the account ID in the **Add Account** form and click Add.
4. To remove an account: click the **×** next to any listed exempt account.

### Via the API

```bash
# View current whitelist
curl http://localhost:8000/whitelist

# Add an account
curl -X POST http://localhost:8000/whitelist/account \
  -H "Content-Type: application/json" \
  -d '{"account_id": "80012345", "reason": "Verified payroll account"}'

# Remove an account
curl -X DELETE http://localhost:8000/whitelist/account/80012345

# View suppressed alerts
curl http://localhost:8000/alerts/suppressed
```

### Persistent Storage

`data/whitelist.json` is committed to the repo and loaded on startup. Changes made via the API are written back to disk immediately. On Render, the `/data` directory is backed by a persistent disk (5 GB) so whitelist changes survive redeploys.

---

## Local Development

```bash
cd aml-prototype
python -m venv venv
venv\Scripts\pip install -r backend\requirements.txt

# Place HI-Small_Trans.csv in data/ or set KAGGLE credentials
cd backend
..\venv\Scripts\python.exe -m uvicorn main:app --reload --port 8000

# Open frontend
start frontend\index.html
```

Run tests:

```bash
cd aml-prototype
venv\Scripts\python.exe -m pytest tests/ -v
```

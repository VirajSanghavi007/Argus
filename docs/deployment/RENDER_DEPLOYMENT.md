# Render Deployment — Production Guide

**Platform:** Render.com (PaaS)  
**Service Type:** Web Service (Gunicorn + FastAPI)  
**Cost Tier:** Standard (default recommended)  
**Environment:** Linux (Ubuntu 20.04)

---

## Quick Start

### 1. Create Render Account
- Sign up at [render.com](https://render.com)
- Connect GitHub account
- Create new Web Service

### 2. Service Configuration

**Service Details:**
```
Name:              argus-aml-detection
Repository:        your-github-repo
Branch:            main
Runtime:           Python 3.11
Build Command:     see below
Start Command:     see below
```

### 3. Build Command
```bash
pip install -r config/requirements.txt && cd src/frontend && npm install && npm run build && cd ../..
```

**What it does:**
1. Install Python dependencies (PyTorch, FastAPI, etc.)
2. Install Node dependencies (React, Vite, etc.)
3. Build React production bundle to `src/frontend/dist/`
4. Return to project root

**Build Time:** ~10-15 minutes (longer on first deployment due to PyTorch)

### 4. Start Command
```bash
gunicorn -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:$PORT src.backend.api.main:app
```

**What it does:**
- Runs 4 worker processes (for concurrency)
- Uses Uvicorn as ASGI server
- Binds to Render's dynamic PORT environment variable
- Points to FastAPI app in `src/backend/api/main.py`

---

## Environment Variables

### Required
```bash
PORT=8000  # Set by Render automatically
```

### Recommended
```bash
# Python
PYTHONUNBUFFERED=1  # Log directly without buffering

# Model Path
MODEL_PATH=data/multignn_model.pt

# Logging
LOG_LEVEL=INFO

# API
CORS_ORIGINS=*  # Allow any origin (update in production)

# Database
DATABASE_URL=  # Leave empty for SQLite (local file)
```

**Set these in Render Dashboard:**
1. Go to Service Settings
2. Environment tab
3. Add each variable

---

## File Uploads (Model & Data)

### Problem
The trained model (`data/multignn_model.pt`) is ~500MB. GitHub has a 100MB file limit (unless using Git LFS).

### Solution Options

#### Option A: Git LFS (Recommended)
```bash
# Install Git LFS
git lfs install

# Track large files
git lfs track "data/multignn_model.pt"
git lfs track "data/active/*.csv"

# Commit and push
git add .gitattributes data/
git commit -m "Add model via Git LFS"
git push
```

**Pros:** Seamless Render integration  
**Cons:** GitHub cost ($5/mo for LFS bandwidth)

#### Option B: Render Disk Storage
1. Go to Service Settings → Disk tab
2. Create persistent disk: `/data` (10GB recommended)
3. Manually upload model via SFTP or copy script

#### Option C: AWS S3 / Cloud Storage
Create initialization script that downloads model on startup:

```python
# scripts/fetch_model.py
import boto3
import os

if not os.path.exists('data/multignn_model.pt'):
    s3 = boto3.client('s3')
    s3.download_file(
        Bucket='your-bucket',
        Key='multignn_model.pt',
        Filename='data/multignn_model.pt'
    )
```

Update build command to call this before starting.

---

## Deployment Process

### 1. Initial Deploy
```bash
# Push code to GitHub
git push origin main

# Render auto-detects and deploys
# Watch logs in Render dashboard
```

### 2. Logs
**Render Dashboard → Service → Logs**

Common startup logs:
```
=== BUILD STARTED ===
Installing Python dependencies...
Installing Node dependencies...
Building React...
=== BUILD SUCCESSFUL ===

=== DEPLOYMENT STARTED ===
Starting application...
INFO: Started Uvicorn server process
INFO: Waiting for application startup.
INFO: Application startup complete.
=== DEPLOYMENT SUCCESSFUL ===
```

### 3. Health Check
Render will test: `GET http://your-service.onrender.com/health`

Expected response:
```json
{
  "model_loaded": true,
  "pipeline_ready": true,
  "last_scan_ms": 0,
  "error": null
}
```

If health check fails, deployment is rolled back.

---

## Monitoring & Debugging

### Application Logs
```bash
# View logs in Render dashboard (real-time)
# Or SSH into service:
render logs <service-id>
```

### Common Issues

#### 1. Build Fails: "PyTorch wheel not found"
**Cause:** Render's Python environment is not compatible with pre-built PyTorch wheel

**Solution:** Build from source (slow) or use CPU-only build
```bash
# In config/requirements.txt
torch==2.0.0+cpu  # CPU variant
torch-geometric  # Source build
```

#### 2. Model Load Fails: "CUDA not available"
**Cause:** Model was trained with CUDA but Render runs CPU-only

**Solution:** Add device detection in `detection.py`
```python
device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
model.load_state_dict(checkpoint['model_state_dict'])
model = model.to(device)
```

#### 3. Build Timeout (30 min limit)
**Cause:** PyTorch build takes too long

**Solution:** Pre-build in Docker image or use pre-compiled wheels
```dockerfile
# Dockerfile (if using custom image)
FROM pytorch/pytorch:2.0-cuda11.8-runtime-ubuntu22.04
COPY . .
RUN pip install -r config/requirements.txt
```

#### 4. Out of Memory (512MB limit)
**Cause:** PyTorch model + React build exceeds available RAM

**Solution:** Upgrade to higher tier or optimize:
```bash
# Reduce build parallelism
npm run build -- --mode=development  # Smaller bundle
```

---

## Performance Tuning

### Gunicorn Workers
```bash
gunicorn -w 4 -k uvicorn.workers.UvicornWorker ...
```

**Calculate optimal workers:** `(2 × CPU_cores) + 1`
- Standard tier (1 vCPU): `w 3`
- Professional tier (2 vCPU): `w 5`

### Database Caching
Enable in-memory caching to reduce SQLite queries:

```python
# In main.py
ALERTS_CACHE = {}
CACHE_TTL = 60  # 1 minute

async def get_alerts(...):
    if time.time() - LAST_CACHE_TIME < CACHE_TTL:
        return ALERTS_CACHE
    # Query database, update cache
```

### Model Inference Optimization
Load model once at startup:
```python
# In lifespan event
async def lifespan(app):
    app.state.model = load_model('data/multignn_model.pt')
    app.state.model.eval()
    yield
```

---

## Scaling Considerations

### Current Limits (Standard Tier)
| Metric | Limit | Notes |
|--------|-------|-------|
| **Memory** | 512 MB | PyTorch + Flask process |
| **CPU** | 1 vCPU | 0.5-1 vCPU average |
| **Disk** | 1 GB | Auto-wipes on redeploy |
| **Concurrency** | ~10 concurrent reqs | 4 Gunicorn workers × 2.5 capacity |

### Scale-Up Path
1. **Professional Tier** (2 vCPU, 2 GB RAM)
   - Increase workers to 5
   - Add second dyno for redundancy

2. **PostgreSQL Database** (separate service)
   - Replace SQLite for multi-instance deployment
   - Connection pooling for efficiency

3. **Redis Cache** (separate service)
   - Cache alerts, model metrics
   - Shared cache across instances

---

## Database Setup

### SQLite (Default)
```bash
# Works out-of-box
# Database stored in: /data/argus.db (ephemeral)
```

**Limitation:** Data lost on redeploy (unless using persistent disk)

### PostgreSQL (Recommended for Production)
```bash
# Create PostgreSQL on Render
1. Dashboard → New PostgreSQL
2. Get connection string: postgres://user:pass@host/dbname
3. Set DATABASE_URL environment variable
4. Update code to use PostgreSQL driver

# Update requirements.txt
psycopg2-binary==2.9.0

# Update database service
DB_PATH = os.getenv('DATABASE_URL')
conn = psycopg2.connect(DB_PATH)
```

---

## Environment-Specific Configuration

### Development (Local)
```python
# .env or environment
API_BASE = http://localhost:8000
FRONTEND_PORT = 5173
DATABASE_URL =  # Use local SQLite
LOG_LEVEL = DEBUG
```

### Production (Render)
```python
# Set in Render dashboard
API_BASE = https://argus-aml-detection.onrender.com
DATABASE_URL = postgres://...
LOG_LEVEL = INFO
CORS_ORIGINS = https://your-frontend-domain.com
```

---

## Monitoring & Alerts

### Render Built-in
- Deployment status notifications
- Health check status
- Performance metrics (CPU, memory, requests)

### Recommended External Tools
1. **Sentry** (error tracking)
   ```python
   import sentry_sdk
   sentry_sdk.init("https://key@sentry.io/project")
   ```

2. **LogRocket** (session replay)
   ```javascript
   LogRocket.init("your-app-id");
   ```

3. **Datadog** (full-stack monitoring)
   ```python
   from datadog import initialize, api
   initialize()
   ```

---

## CI/CD Pipeline (GitHub Actions)

**File:** `.github/workflows/deploy.yml`

```yaml
name: Deploy to Render

on:
  push:
    branches: [ main ]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Trigger Render deploy
        run: |
          curl -X POST https://api.render.com/deploy/srv-${{ secrets.RENDER_SERVICE_ID }}?key=${{ secrets.RENDER_API_KEY }}
      
      - name: Wait for deploy
        run: sleep 30
      
      - name: Health check
        run: |
          curl -f https://argus-aml-detection.onrender.com/health || exit 1
```

**Setup:**
1. Generate Render API key in account settings
2. Add to GitHub Secrets: `RENDER_API_KEY`, `RENDER_SERVICE_ID`
3. Commit workflow file
4. Each push to `main` auto-deploys

---

## DNS & Custom Domain

```bash
# 1. Buy domain (Namecheap, Route53, etc.)
# 2. In Render dashboard, go to Service Settings → Custom Domain
# 3. Add domain: argus.yourdomain.com
# 4. Get CNAME record: *.onrender.com
# 5. Add to DNS provider CNAME settings
# 6. Wait 24-48 hours for propagation
```

---

## Cost Estimate (Monthly)

| Component | Tier | Cost |
|-----------|------|------|
| **Web Service** | Standard (512MB, 0.5 vCPU) | $7.00 |
| **PostgreSQL** (optional) | Mini (512MB) | $7.00 |
| **Outbound Data** | First 100 GB free | — |
| **Domain** | (varies) | ~$10/year |
| **Total** | — | ~$14/mo |

---

## Backup & Disaster Recovery

### Database Backups
```bash
# PostgreSQL automated backups (Render)
# Retention: 7 days free tier

# Manual backup
pg_dump $DATABASE_URL > backup.sql
```

### Model Backups
```bash
# Store in Git LFS or S3
# Versioning: tag releases with model version
git tag v1.0-model-20260629
```

### Disaster Recovery Plan
1. **Failure:** Model corrupted or database lost
2. **Detection:** Health check fails
3. **Recovery:**
   - Restore database from backup
   - Redeploy with Git commit hash
   - Validate /health endpoint
   - Roll back if issues

---

## SSL/TLS Certificates

**Automatic:** Render provides free SSL via Let's Encrypt

```bash
# Certificate auto-renewed every 60 days
# Verify: https://argus-aml-detection.onrender.com/health
# Should not show certificate warnings
```

---

## Troubleshooting Checklist

- [ ] Build command successful? Check Render logs
- [ ] Health endpoint returns 200? `curl /health`
- [ ] Model file exists? Check disk usage in logs
- [ ] Environment variables set? Check Render dashboard
- [ ] Database connection working? Check PostgreSQL status
- [ ] Frontend build generated? Check for `dist/` folder
- [ ] API endpoints accessible? Try `curl /status`
- [ ] CORS configured correctly? Check browser console

---

## Production Readiness Checklist

- [ ] Error logging (Sentry) configured
- [ ] Database backed up and tested
- [ ] Model versioning in Git LFS
- [ ] HTTPS/SSL enabled (automatic on Render)
- [ ] Rate limiting enforced
- [ ] Monitoring alerts set up
- [ ] Incident response plan documented
- [ ] Load testing completed
- [ ] Security audit passed
- [ ] Documentation updated

---

**End of Render Deployment Documentation**

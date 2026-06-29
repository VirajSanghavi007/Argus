# Known Issues

## DEMO_BLOCKER

_(none currently)_

## HIGH

### No authentication
All API endpoints are publicly accessible. No API key, session, or token authentication.
**Why not fixed:** Demo-only deployment for competition judges on controlled URL.
**What fixing requires:** Add FastAPI dependency function checking `X-API-Key` header against env var, apply globally. ~30 min.

### Model file not in repo
`data/multignn_model.pt` is gitignored (too large). App starts in degraded mode without it — no alerts generated.
**Why not fixed:** Git LFS or external storage needed. Model must be uploaded manually to deployment.
**What fixing requires:** Git LFS setup, or Render persistent disk, or S3 model registry.

### Dataset not in repo
Transaction CSVs (`HI-Small_Trans.csv`, 475MB+) are gitignored. Pipeline fails without them.
**Why not fixed:** Too large for git. Datasets must be provisioned separately.
**What fixing requires:** Git LFS, S3 bucket, or Render persistent disk with data provisioning script.

## MEDIUM

### Render free tier memory constraints
PyTorch + PyTorch Geometric + pandas loading a 475MB CSV may exceed 512MB RAM on Render free tier.
**Why not fixed:** Needs paid instance ($7/mo) or model optimization. Demo works with cached alerts.
**What fixing requires:** Profile memory usage, potentially switch to Render starter plan, or implement streaming inference.

### No RBI/GDPR compliance audit
Logging may include transaction metadata. No PII masking, no data retention policy, no audit trail for data access.
**Why not fixed:** Out of scope for hackathon demo.
**What fixing requires:** Full compliance review, PII masking in logs, data retention policies, access audit trail.

### SQLite not suitable for production scale
SQLite with WAL mode works for demo but won't scale beyond single-writer concurrency.
**Why not fixed:** Adequate for demo. PostgreSQL migration TODO documented in `src/database/service.py`.
**What fixing requires:** Follow the 6-step migration plan in service.py TODO block.

### slowapi uses deprecated asyncio.iscoroutinefunction
`slowapi==0.1.9` calls `asyncio.iscoroutinefunction` which is deprecated in 3.14, removed in 3.16.
**Why not fixed:** Upstream library issue. Works currently, will break on Python 3.16.
**What fixing requires:** Update slowapi when they release a fix, or replace with custom rate limiting.

## LOW

### Hardcoded Render health check assumptions
Health endpoint always returns 200 regardless of pipeline state. This is intentional for Render but may mask real failures.
**Why not fixed:** Required for Render free tier health checks. Pipeline errors visible via `/health` warnings field.

### No HTTPS enforcement
App serves over HTTP locally. HTTPS handled by Render's proxy in production.
**Why not fixed:** Standard for Render deployments. No action needed unless self-hosting.

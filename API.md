# Argus — API Reference

Written for a human reviewer, not generated from the OpenAPI schema (though `/docs` — Swagger UI — is also available on the running server for interactive testing).

**Base URL:** the deployed Space root, e.g. `https://virajsanghavi-argus.hf.space`, or `http://localhost:8000` locally.

**Auth:** every endpoint except `/auth/login`, `/health`, `/status`, `/`, and static files requires a session. Log in first, then send the returned token on every request as the `X-Session-Token` header (the browser frontend also gets it as an `httpOnly` cookie automatically).

---

## Auth

### `POST /auth/login`
Body: `{"company_id": "UBI-AML-2026", "username": "admin", "password": "admin123"}`
Returns: `{"token": "...", "username": "admin", "company_id": "UBI-AML-2026"}` and sets a session cookie.

### `POST /auth/logout`
Send the session token (header or cookie). Invalidates it server-side.

### `GET /auth/me`
Returns the current session's `{username, company_id}` — used by the frontend to confirm a token is still valid.

---

## Alerts (the core detection output)

### `GET /status`
No auth required. Returns pipeline readiness, alert counts, and a pattern-type breakdown. The frontend polls this while the pipeline is warming up on a cold start.

### `GET /alerts`
List every current alert (summary shape — pattern, severity, total moved, hop count, timestamps). This is what populates the Investigate sidebar and dashboard charts.

### `GET /alerts/{alert_id}`
Full detail for one alert: the account graph (nodes + edges), every underlying transaction, the human-readable pattern description, and `riskIndicators` — the cited evidence list (structuring, pass-through/mule behavior, velocity, cross-currency layering, etc.) that answers "why is this actually suspicious," not just "what shape is the graph."

### `GET /alerts/suppressed`
Alerts that *would* have been raised but were suppressed because every account involved is whitelisted.

### `POST /alerts/{alert_id}/decision`
Body: `{"decision": "confirm" | "review" | "dismiss", "reason": "optional free text"}`
Appends to the audit trail (never overwrites — `GET /alerts/{alert_id}/decision/history` shows the full sequence if an analyst changes their mind).

### `GET /alerts/{alert_id}/decision/history`
Chronological list of every decision ever recorded for this alert.

### `GET /decisions`
The *current* (latest) decision per alert, across all alerts — powers the Case Manager view.

---

## Node-level (account) analysis

The model scores individual **transactions** (edges). These endpoints aggregate that into a per-**account** view, so an analyst can ask "how risky is this account overall," not just "was this one transfer suspicious."

### `GET /accounts/risky?limit=8`
Top accounts ranked by their single highest laundering-edge score, with total volume moved and how many distinct alerts they appear in. This is the "Top Risky Accounts" list.

### `GET /account/{account_id}/history`
Every flagged transaction touching this account — in or out, counterparty, amount, currency, format, timestamp — plus the account's aggregate risk score. This is what powers "click a node in the graph → see its whole transaction history."

### `GET /account/{account_id}/network?hops=2`
Breadth-first search outward from one account across *every* flagged transaction (not just one alert's subgraph), up to `hops` hops (max 2). Returns a node/edge set suitable for rendering a wider account-relationship graph than a single alert shows.

---

## Whitelist

### `GET /whitelist`
Current exemption rules + the list of explicitly whitelisted accounts.

### `POST /whitelist/account`
Body: `{"account_id": "A123", "reason": "verified payroll account"}`
Adding an account here causes any alert touching *only* whitelisted accounts to move to the suppressed list on the next evaluation.

### `DELETE /whitelist/account/{account_id}`
Removes the exemption.

---

## Live ingestion & on-demand scoring

### `POST /ingest`
Body: a single transaction object, a bare array, or `{"transactions": [...]}`. Accepts either the canonical IBM column names (`"From Bank"`, `"Account"`, `"Amount Paid"`, ...) or snake_case aliases.
Every row is validated, then written to the `live_transactions` table as an audit trail. **Note:** ingested rows do not automatically trigger re-scoring mid-session — they enter the alert set on the next full pipeline run. If `ARGUS_INGEST_KEY` is set, requests must include a matching `X-API-Key` header.

### `POST /predict`
Multipart form: either a `file` (CSV or Excel upload) or `data` (pasted CSV text — JSON paste is intentionally rejected). Scores every row through the live model immediately and returns per-row `ml_score` + `flagged`. Capped at 5,000 rows. This is the "bring your own transactions and see them scored right now" tool — distinct from `/ingest`, which is for building up the live audit queue rather than instant one-off scoring.

---

## Diagnostics

### `GET /health`
Always 200 if the process is alive. No auth.

### `GET /ml-metrics`
Training-time metrics for the currently loaded model (precision/recall/F1/AUC, decision threshold, epoch count). 404 if no model is loaded.

### `GET /drift`
Score-distribution drift check comparing the current pipeline run's confidence distribution against the model's training-time baseline — a rough signal for "does this data still look like what the model was trained on."

---

## A note on rate limits

Most endpoints carry a `slowapi` rate limit (visible as a decorator on each route in `main.py`, typically 20–100 requests/minute depending on cost). This protects the single-container deployment from being overwhelmed, not a security boundary — don't rely on it to prevent abuse from an authenticated, motivated user.

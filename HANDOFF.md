# Argus — Hackathon Handoff & 8-Hour Battle Plan

> **Goal:** A working, demo-able AML detection web platform by first evaluation (8 hours).
> **Golden rule:** The biggest risk is the **demo breaking**, not the model F1. The model is already a winning story (AUC ~0.97). **Lock it early and protect the demo path.**

---

## 0. What Argus is (the pitch)

A **web-based AML (anti-money-laundering) compliance dashboard**. A Multi-GNN scores every transaction in a banking graph for laundering probability, clusters the flagged ones into rings, classifies each ring's pattern (fan-out, fan-in, cycle, layering chain…), explains *why* it was flagged, and surfaces them as analyst-ready alerts.

**3-minute pitch:** *Problem* (banks drown in transactions, laundering hides in the graph structure) → *Solution* (graph neural network that detects laundering rings, not just suspicious single transactions) → *How* (Multi-GNN on the transaction multigraph + topology classification + explainability) → *Number* ("0.97 AUC across multiple AML datasets, with per-alert explanations").

**Framing for judges:** recall-leaning (catching launderers > analyst review time), interpretable (we show *why*), trained across multiple datasets (generalizes).

---

## 1. PRIORITY PLAN — do these in order

### MUST-HAVE (demo-critical path — lose these, lose the eval)

- [ ] **Lock ONE model.** Pick the best checkpoint (≈0.45 F1 / 0.98 AUC is fine). Put `multignn_model.pt` + `multignn_meta.json` in `data/`. Delete `data/pipeline_cache.json`. Restart server. Confirm alerts appear. **Do this by hour 2 and stop chasing F1.**
- [ ] **End-to-end demo path works, no crash.** Auth → loading → dashboard renders alerts → click an alert → graph + details show. Walk *every* screen.
- [ ] **Kill the blank-dashboard bug for real** (browser caching old `app.js` — hard refresh / cache-bust). See §4.
- [ ] **Rehearse the 3-min demo** with 2–3 curated example alerts.

### SHOULD-HAVE (the points-winners)

- [ ] **Interpretability visible** — the "why flagged" (GNNExplainer edge importance) + pattern labels on each alert. This is the differentiator vs a black box.
- [ ] **Curated alerts** — one clean fan-out, one cycle, one layering chain to walk through.
- [ ] **Stat cards correct** — total flagged, money moved, high-severity count, decisions made.
- [ ] **README + one architecture diagram.**

### DON'T BOTHER (for first eval)

- ❌ Squeezing F1 past ~0.6 — demo won't show the difference.
- ❌ SAML-D tuning — weakest, non-production dataset.
- ❌ Perfect transparent logo / pixel polish.
- ❌ Fighting Render — a rock-solid **local** demo + a **backup screen recording** beats a flaky deploy.

### Rough time shape (8h, ~0.5h buffer)

| Hours | Focus |
|-------|-------|
| 0–2 | Lock model in `data/`, verify pipeline emits alerts |
| 2–4 | End-to-end demo path solid, blank-screen killed, click through every screen |
| 4–5.5 | Interpretability + pattern labels + curated alerts + stat cards correct |
| 5.5–6.5 | Deploy (Render + `PYTHONPATH=src`) **or** lock local + record backup video |
| 6.5–7.5 | README, architecture diagram, rehearse 3-min demo |
| 7.5–8 | Buffer — dry run, fix whatever breaks |

---

## 2. Current state (what works / what's shaky)

**Works:**
- FastAPI backend (`src/backend/api/main.py`) + web frontend (`src/frontend/` — `index.html`, `css/style.css`, `js/app.js`).
- `start.bat` one-click local launcher (health check fixed to use `127.0.0.1`, not `localhost` — IPv6 was timing out).
- Auth + loading screens with UBI logo.
- Detection pipeline produces alerts when a model + dataset are present.

**Shaky / needs verification:**
- **Render deployment** crashed on import (`attempted relative import with no known parent package`). Fixes applied this session (see §3) but **must verify live + set `PYTHONPATH=src` in Render dashboard**.
- **Dashboard blank screen** — browser caching old `app.js`. Needs cache-bust (see §4).
- **Model is currently weak** (deployed `multignn_meta.json` shows F1 0.023). A better one is training — must be locked into `data/` (see §5).

---

## 3. Deployment (Render)

- Start command: `uvicorn src.backend.api.main:app --host 0.0.0.0 --port $PORT`
- **`config/deployment.yaml` is documentation only.** Render uses **dashboard settings**, not this file.
- **REQUIRED on Render → Environment tab:** `PYTHONPATH = src`. Without it, `database`/`config` imports fail.
- Fixes applied this session so the dotted module path resolves:
  - Created `src/__init__.py` (makes `src` a package so `from ..core.whitelist` works under `src.backend.api.main`).
  - `main.py`: `from database import service` wrapped in try/except → falls back to `from ...database import service`.
- **Build:** `pip install -r config/requirements.txt`
- ⚠️ **Datasets are NOT in git** (gitignored, too large). The deployed instance has no CSV unless uploaded separately. For first eval, **demo locally** where the data exists. If you need Render live, you must get a dataset + model onto it (Git LFS or manual upload) — low priority.

---

## 4. The blank-dashboard bug

**Symptom:** auth + loading work, then dashboard is blank grey.
**Cause:** browser serves a cached old `app.js` (`GET /static/js/app.js 304 Not Modified` in logs). The updated JS (with the empty-state handling in `renderDashboard()`) never reaches the browser.
**Immediate fix for demo:** hard refresh — **Ctrl+Shift+R**. Regular F5 won't bust the cache.
**Durable fix (do this so it never bites during the demo):** add a cache-busting query to the script/style tags in `src/frontend/public/index.html`, e.g. `app.js?v=2`, OR serve static files with `Cache-Control: no-store`. Verify `loadAllAlerts()` has error handling so a fetch failure doesn't silently leave a blank screen.

---

## 5. The model (lock it, then optionally improve)

**Current deployed model:** F1 0.023, AUC 0.60 — garbage, 8 epochs, only 305 positives. Replace it.
**Best so far:** ~0.45 F1, **0.97–0.98 AUC**. Good enough for the demo story.

**To lock a model:**
1. Get `multignn_model.pt` + `multignn_meta.json` from the Kaggle/Colab run (Output tab).
2. Drop both into `data/`.
3. Delete `data/pipeline_cache.json` (it caches stale results).
4. Restart the server. Confirm alerts render.

**⚠️ Inference contract:** the `.pt` must match `MultiGNN(**config, deg=deg)` in `src/backend/models/multignn.py`. If the training notebook changed the architecture (layers/hidden/features/conv type), mirror that change in `multignn.py` or it won't load. Keep `currencies`/`formats` encoder lists in the meta.

**If time allows, ONE better run** (don't block the demo on it):
- Train on **HI-Medium** (same IBM generator family as production HI-Small).
- **Fix the `pos_weight` bug:** in `train()`, `effective_pw = max(pos_weight_val, auto_pw)` ignores your setting (auto caps at 200, which floods positives and kills precision). Change to `effective_pw = pos_weight_val` and use `POS_WEIGHT = 8`.
- **Fix threshold leakage:** `_evaluate(sweep=True)` picks the F1-max threshold on the *test* set. Sweep on **validation**, freeze, then report test.
- Full deep dive in **`MODEL_TRAINING_BRIEF.md`** (paste-able into a fresh Claude). Datasets in use: SAML-D, TransXion, HI-Medium, LI-Medium; production scores HI-Small — keep a HI-Small slice in eval.
- Namespacing when combining datasets: node key must be `dataset:bank:account` or accounts collide across datasets.

---

## 6. Demo script (rehearse this)

1. **Open the dashboard** — "This is Argus, an AML monitoring platform for a bank's compliance team."
2. **Stat cards** — "It's scanned N transactions, flagged X laundering rings moving $Y."
3. **Open a fan-out alert** — "Here's a single account distributing to many — classic structuring. The graph shows the ring; these highlighted edges are *why* the model flagged it."
4. **Open a cycle/layering alert** — "Money returns to origin — layering to obscure the trail."
5. **The number** — "Across multiple AML datasets we hit 0.97 AUC, recall-tuned because missing a launderer costs far more than reviewing a clean transaction."
6. **Close** — "Analyst-ready alerts, explainable, deployable as a web service."

Have a **backup screen recording** of this exact flow in case live breaks.

---

## 7. Hard constraints (do not violate)

- **Never commit datasets or large model files to git** — they're gitignored; the user pushes manually.
- **No `git push`** — the user controls the remote.
- **Demo safety:** if a change risks breaking the running demo, log it in `KNOWN_ISSUES.md` instead of shipping it.
- **`config/deployment.yaml` is docs only** — Render uses dashboard settings.
- Keep the model **inference contract** intact (§5).

---

## 8. Key file map

- `src/backend/api/main.py` — FastAPI app, `/alerts`, `/status`, `/health`, static serving.
- `src/backend/pipeline/detection.py` — alert generation. `ALERT_THRESHOLD_FLOOR = 0.10`, `MAX_ALERTS = 200`.
- `src/backend/models/multignn.py` — model, graph build, train, inference, explainability.
- `src/frontend/public/index.html` — auth / loading / dashboard shell + UBI logo.
- `src/frontend/js/app.js` — `loadAllAlerts()`, `renderDashboard()`.
- `src/frontend/css/style.css` — styles.
- `src/config.py` — paths (`DATA_DIR`, `MODEL_PATH`, `META_PATH`, `CACHE_PATH`).
- `data/multignn_model.pt`, `data/multignn_meta.json` — model artifacts (swap to upgrade).
- `data/pipeline_cache.json` — **delete after swapping the model.**
- `start.bat` — local launcher.
- `train_multignn.ipynb` — Kaggle/Colab training notebook.
- `MODEL_TRAINING_BRIEF.md` — full modeling deep-dive for a fresh Claude.

---

## 9. Definition of done (first eval)

- [ ] Better model locked in `data/`, pipeline emits sensible alerts.
- [ ] Full demo path works end-to-end with zero crashes (auth → dashboard → alert detail).
- [ ] Blank-screen bug cannot recur (cache-bust in place).
- [ ] Interpretability + pattern labels visible on alerts.
- [ ] 3-min demo rehearsed; backup recording exists.
- [ ] README + architecture diagram present.
- [ ] Either deployed on Render (with `PYTHONPATH=src`) **or** a bulletproof local setup.

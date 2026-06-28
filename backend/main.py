import json
import threading
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import logging
import numpy as np

from whitelist import (
    load_whitelist, save_whitelist, filter_alerts,
    add_to_whitelist, remove_from_whitelist,
    DEFAULT_WHITELIST,
)
from log_setup import setup_logging
import db

logger     = logging.getLogger("uvicorn.error")
DATA_DIR   = Path(__file__).parent.parent / "data"
LOGS_DIR   = Path(__file__).parent.parent / "logs"
CACHE_PATH = DATA_DIR / "pipeline_cache.json"
DRIFT_LOG  = DATA_DIR / "drift_log.json"

MULTIGNN_MAX_ROWS = 600_000

ALERTS:    dict = {}
SUPPRESSED: dict = {}
DECISIONS: dict = {}
PIPELINE_READY = threading.Event()
PIPELINE_ERROR: str = ""
ML_METRICS: dict = {}
DECISION_THRESHOLD: float = 0.5


# ── helpers ───────────────────────────────────────────────────────────────────

def _ensure_data_dir():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    wl_path = DATA_DIR / "whitelist.json"
    if not wl_path.exists():
        save_whitelist(DEFAULT_WHITELIST)
        logger.info("Created default whitelist.json")


def _load_cache() -> bool:
    if not CACHE_PATH.exists():
        return False
    try:
        global ALERTS, SUPPRESSED, ML_METRICS
        cache = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
        ALERTS     = {a["id"]: a for a in cache["alerts"]}
        SUPPRESSED = {a["id"]: a for a in cache.get("suppressed", [])}
        ML_METRICS = cache.get("ml_metrics", {})
        logger.info(f"Loaded from cache: {len(ALERTS)} alerts, {len(SUPPRESSED)} suppressed")
        return True
    except Exception as e:
        logger.warning(f"Cache load failed ({e}), running full pipeline")
        return False


def _save_cache():
    try:
        cache = {
            "alerts":     list(ALERTS.values()),
            "suppressed": list(SUPPRESSED.values()),
            "ml_metrics": ML_METRICS,
        }
        CACHE_PATH.write_text(json.dumps(cache), encoding="utf-8")
        logger.info(f"Pipeline cache saved to {CACHE_PATH}")
    except Exception as e:
        logger.warning(f"Could not save cache: {e}")


# ── pipeline thread ───────────────────────────────────────────────────────────

def _check_drift(ml_scores: list) -> None:
    if not ml_scores:
        return

    scores = np.array(ml_scores, dtype=float)
    bins   = np.linspace(0.0, 1.0, 21)
    hist, _ = np.histogram(scores, bins=bins)
    hist    = hist / hist.sum() if hist.sum() > 0 else hist

    drift_data: dict = {}
    if DRIFT_LOG.exists():
        try:
            drift_data = json.loads(DRIFT_LOG.read_text(encoding="utf-8"))
        except Exception:
            pass

    if "baseline_hist" not in drift_data:
        drift_data["baseline_hist"]  = hist.tolist()
        drift_data["baseline_count"] = int(len(scores))
        drift_data["baseline_mean"]  = float(np.mean(scores))
        drift_data["runs"]           = []
        logger.info("Drift baseline stored.")
    else:
        baseline = np.array(drift_data["baseline_hist"])
        eps      = 1e-10
        p        = baseline + eps
        q        = hist + eps
        p       /= p.sum()
        q       /= q.sum()
        kl_div   = float(np.sum(p * np.log(p / q)))

        m_mix  = 0.5 * (p + q)
        js_nat = 0.5 * float(np.sum(p * np.log(p / m_mix))) + 0.5 * float(np.sum(q * np.log(q / m_mix)))
        js_div = js_nat / np.log(2)

        baseline_mean = drift_data.get("baseline_mean", float(np.mean(scores)))
        score_shift   = float(np.mean(scores) - baseline_mean)

        alert_rate = float(np.mean(scores > DECISION_THRESHOLD))
        kl_flag    = kl_div > 0.1
        js_flag    = js_div > 0.1
        shift_flag = abs(score_shift) > 0.05
        run_entry  = {
            "kl_divergence":  round(kl_div, 4),
            "js_divergence":  round(js_div, 4),
            "score_shift":    round(score_shift, 4),
            "alert_rate":     round(alert_rate, 4),
            "n_scores":       int(len(scores)),
            "flags":          {"kl": kl_flag, "js": js_flag, "score_shift": shift_flag},
        }
        drift_data.setdefault("runs", []).append(run_entry)

        if kl_flag or js_flag or shift_flag:
            logger.warning(
                f"DRIFT DETECTED — KL={kl_div:.4f} JS={js_div:.4f} score_shift={score_shift:+.4f} "
                f"(thresholds KL/JS>0.1, |shift|>0.05). Alert rate: {alert_rate:.4f}. Consider retraining."
            )
        else:
            logger.info(
                f"Drift check: KL={kl_div:.4f} JS={js_div:.4f} score_shift={score_shift:+.4f} "
                f"(ok), alert_rate={alert_rate:.4f}"
            )

    DRIFT_LOG.write_text(json.dumps(drift_data, indent=2), encoding="utf-8")


def _run_pipeline():
    global ALERTS, SUPPRESSED, PIPELINE_ERROR, ML_METRICS, DECISION_THRESHOLD, DECISIONS

    try:
        if _load_cache():
            DECISIONS = db.current_decisions()
            PIPELINE_READY.set()
            return

        logger.info("No cache found — running Multi-GNN pipeline...")
        from multignn_pipeline import run_multignn_pipeline

        serialized, ML_METRICS = run_multignn_pipeline(max_rows=MULTIGNN_MAX_ROWS)
        DECISION_THRESHOLD = float(ML_METRICS.get("threshold", 0.5))

        ALERTS     = {a["id"]: a for a in serialized}
        SUPPRESSED = {}

        logger.info(f"Multi-GNN alerts: {len(ALERTS)} clusters")

        # Persist alerts and restore the analyst decision audit trail from SQLite.
        import time as _time
        db.replace_alerts(serialized, scan_id=str(int(_time.time())))
        DECISIONS = db.current_decisions()

        _check_drift([a["mlScore"] for a in serialized if a.get("mlScore") is not None])
        _save_cache()

    except Exception as e:
        PIPELINE_ERROR = str(e)
        logger.error(f"Pipeline failed: {e}")

    PIPELINE_READY.set()


# ── app ───────────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    _ensure_data_dir()
    db.init_db()
    log_paths = setup_logging(LOGS_DIR)
    logger.info(f"Error logs -> {log_paths['error_logs']}")
    logger.info(f"Training logs -> {log_paths['training_logs']}")
    t = threading.Thread(target=_run_pipeline, daemon=True)
    t.start()
    yield


app = FastAPI(title="AML Intelligence Platform API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)

FRONTEND_DIR = Path(__file__).parent.parent / "frontend"
app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

@app.get("/")
def serve_frontend():
    return FileResponse(str(FRONTEND_DIR / "index.html"))


# ── core endpoints ────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/status")
def status():
    ready = PIPELINE_READY.is_set()
    patterns: dict[str, int] = {}
    for a in ALERTS.values():
        pt = a["patternType"]
        patterns[pt] = patterns.get(pt, 0) + 1
    result = {
        "status":           "error" if (ready and PIPELINE_ERROR) else ("ready" if ready else "loading"),
        "alert_count":      len(ALERTS),
        "suppressed_count": len(SUPPRESSED),
        "patterns":         patterns,
    }
    if PIPELINE_ERROR:
        result["error"] = PIPELINE_ERROR
    return result


@app.get("/alerts")
def list_alerts(
    pattern_type: str | None = Query(default=None),
    severity:     str | None = Query(default=None),
    source:       str | None = Query(default=None),
):
    results = []
    for a in ALERTS.values():
        if pattern_type and a["patternType"] != pattern_type:
            continue
        if severity and a["severity"] != severity.upper():
            continue
        if source and a.get("source") != source:
            continue
        results.append({
            "id":               a["id"],
            "name":             a["name"],
            "sub":              a["sub"],
            "severity":         a["severity"],
            "confidence":       a["confidence"],
            "patternType":      a["patternType"],
            "totalMoved":       a["totalMoved"],
            "timeSpan":         a["timeSpan"],
            "hops":             a["hops"],
            "node_count":       len(a["nodes"]),
            "txn_count":        len(a["transactions"]),
            "source":           a.get("source", "labelled"),
        })
    return results


@app.get("/alerts/suppressed")
def list_suppressed():
    return list(SUPPRESSED.values())


@app.get("/alerts/{alert_id}")
def get_alert(alert_id: str):
    if alert_id not in ALERTS:
        raise HTTPException(status_code=404, detail="Alert not found")
    return ALERTS[alert_id]


class DecisionBody(BaseModel):
    decision: str
    reason: str = ""
    analyst: str = ""


@app.post("/alerts/{alert_id}/decision")
def post_decision(alert_id: str, body: DecisionBody):
    if alert_id not in ALERTS:
        raise HTTPException(status_code=404, detail="Alert not found")
    # Append to the immutable SQLite audit log, then refresh the in-memory view.
    db.record_decision(alert_id, body.decision, body.reason, body.analyst)
    DECISIONS[alert_id] = {"decision": body.decision, "reason": body.reason}
    return {"status": "saved", "alert_id": alert_id, "decision": body.decision}


@app.get("/alerts/{alert_id}/decision/history")
def get_decision_history(alert_id: str):
    """Full chronological audit trail of every decision made on this alert."""
    return {"alert_id": alert_id, "history": db.decision_history(alert_id)}


@app.get("/decisions")
def get_decisions():
    """Current analyst decision per alert (latest row from the audit log).
    The frontend hydrates from this on load so decisions survive restarts."""
    return db.current_decisions()


# ── whitelist endpoints ───────────────────────────────────────────────────────

@app.get("/whitelist")
def get_whitelist():
    return load_whitelist()


class WhitelistAddBody(BaseModel):
    account_id: str
    reason: str = ""


@app.post("/whitelist/account")
def whitelist_add(body: WhitelistAddBody):
    wl = add_to_whitelist(body.account_id)
    return {"status": "added", "account_id": body.account_id, "whitelist": wl}


@app.delete("/whitelist/account/{account_id}")
def whitelist_remove(account_id: str):
    wl = remove_from_whitelist(account_id)
    return {"status": "removed", "account_id": account_id}


# ── ml metrics ────────────────────────────────────────────────────────────────

@app.get("/ml-metrics")
def get_ml_metrics():
    if not ML_METRICS:
        raise HTTPException(status_code=404, detail="ML model not trained yet")
    return {**ML_METRICS, "decision_threshold": DECISION_THRESHOLD}


@app.get("/drift")
def get_drift():
    if not DRIFT_LOG.exists():
        return {"status": "no_data", "message": "Pipeline has not completed a full run yet."}
    try:
        return json.loads(DRIFT_LOG.read_text(encoding="utf-8"))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

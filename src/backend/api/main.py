import asyncio
import json
import threading
import time
import uuid
import logging
from contextlib import asynccontextmanager
from contextvars import ContextVar
from enum import Enum
from hashlib import md5
from pathlib import Path

import numpy as np
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from slowapi import Limiter
from slowapi.util import get_remote_address

from ..core.whitelist import (
    load_whitelist, save_whitelist, filter_alerts,
    add_to_whitelist, remove_from_whitelist,
    DEFAULT_WHITELIST,
)
from ..utils.logging import setup_logging
from database import service as db
from config import (
    DATA_DIR, LOGS_DIR, CACHE_PATH, DRIFT_LOG, MODEL_PATH, MULTIGNN_MAX_ROWS,
)

# ── Structured Logging with Context (Issue #6) ─────────────────────────────
logger = logging.getLogger("uvicorn.error")
request_id: ContextVar[str] = ContextVar("request_id", default="")

# ── Concurrency Safety (Issue #10) ──────────────────────────────────────────
ALERTS: dict = {}
SUPPRESSED: dict = {}
DECISIONS: dict = {}
ALERTS_LOCK = threading.RLock()
ALERTS_ETAG = ""

PIPELINE_READY = threading.Event()
PIPELINE_ERROR: str = ""
PIPELINE_START_TIME = 0.0
ML_METRICS: dict = {}
DECISION_THRESHOLD: float = 0.5


# ── Validation Enums (Issue #5) ─────────────────────────────────────────────
class PatternType(str, Enum):
    FAN_OUT = "FAN_OUT"
    FAN_IN = "FAN_IN"
    CYCLE = "CYCLE"
    SCATTER_GATHER = "SCATTER_GATHER"
    GATHER_SCATTER = "GATHER_SCATTER"
    BIPARTITE = "BIPARTITE"
    STACK = "STACK"
    RANDOM = "RANDOM"


class SeverityLevel(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class AlertSource(str, Enum):
    LABELLED = "labelled"
    UNLABELLED = "unlabelled"


class DecisionType(str, Enum):
    CONFIRM = "confirm"
    REVIEW = "review"
    DISMISS = "dismiss"


# ── Rate Limiting (Issue #1) ────────────────────────────────────────────────
limiter = Limiter(key_func=get_remote_address)


# ── Helpers ─────────────────────────────────────────────────────────────────

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
        with ALERTS_LOCK:
            ALERTS = {a["id"]: a for a in cache["alerts"]}
            SUPPRESSED = {a["id"]: a for a in cache.get("suppressed", [])}
        ML_METRICS = cache.get("ml_metrics", {})
        rid = request_id.get()
        logger.info(f"[{rid}] Loaded from cache: {len(ALERTS)} alerts, {len(SUPPRESSED)} suppressed")
        return True
    except Exception as e:
        rid = request_id.get()
        logger.warning(f"[{rid}] Cache load failed ({e}), running full pipeline")
        return False


def _save_cache():
    try:
        with ALERTS_LOCK:
            cache = {
                "alerts": list(ALERTS.values()),
                "suppressed": list(SUPPRESSED.values()),
                "ml_metrics": ML_METRICS,
            }
        CACHE_PATH.write_text(json.dumps(cache), encoding="utf-8")
        rid = request_id.get()
        logger.info(f"[{rid}] Pipeline cache saved to {CACHE_PATH}")
    except Exception as e:
        rid = request_id.get()
        logger.warning(f"[{rid}] Could not save cache: {e}")


def _compute_alerts_etag() -> str:
    """Compute ETag from current ALERTS state (Issue #2)."""
    with ALERTS_LOCK:
        data = json.dumps(list(ALERTS.values()), sort_keys=True)
    return md5(data.encode()).hexdigest()


def _check_drift(ml_scores: list) -> None:
    if not ml_scores:
        return

    scores = np.array(ml_scores, dtype=float)
    bins = np.linspace(0.0, 1.0, 21)
    hist, _ = np.histogram(scores, bins=bins)
    hist = hist / hist.sum() if hist.sum() > 0 else hist

    drift_data: dict = {}
    if DRIFT_LOG.exists():
        try:
            drift_data = json.loads(DRIFT_LOG.read_text(encoding="utf-8"))
        except Exception:
            pass

    if "baseline_hist" not in drift_data:
        drift_data["baseline_hist"] = hist.tolist()
        drift_data["baseline_count"] = int(len(scores))
        drift_data["baseline_mean"] = float(np.mean(scores))
        drift_data["runs"] = []
        rid = request_id.get()
        logger.info(f"[{rid}] Drift baseline stored.")
    else:
        baseline = np.array(drift_data["baseline_hist"])
        eps = 1e-10
        p = baseline + eps
        q = hist + eps
        p /= p.sum()
        q /= q.sum()
        kl_div = float(np.sum(p * np.log(p / q)))

        m_mix = 0.5 * (p + q)
        js_nat = 0.5 * float(np.sum(p * np.log(p / m_mix))) + 0.5 * float(np.sum(q * np.log(q / m_mix)))
        js_div = js_nat / np.log(2)

        baseline_mean = drift_data.get("baseline_mean", float(np.mean(scores)))
        score_shift = float(np.mean(scores) - baseline_mean)

        alert_rate = float(np.mean(scores > DECISION_THRESHOLD))
        kl_flag = kl_div > 0.1
        js_flag = js_div > 0.1
        shift_flag = abs(score_shift) > 0.05
        run_entry = {
            "kl_divergence": round(kl_div, 4),
            "js_divergence": round(js_div, 4),
            "score_shift": round(score_shift, 4),
            "alert_rate": round(alert_rate, 4),
            "n_scores": int(len(scores)),
            "flags": {"kl": kl_flag, "js": js_flag, "score_shift": shift_flag},
        }
        drift_data.setdefault("runs", []).append(run_entry)

        rid = request_id.get()
        if kl_flag or js_flag or shift_flag:
            logger.warning(
                f"[{rid}] DRIFT DETECTED — KL={kl_div:.4f} JS={js_div:.4f} score_shift={score_shift:+.4f} "
                f"(thresholds KL/JS>0.1, |shift|>0.05). Alert rate: {alert_rate:.4f}. Consider retraining."
            )
        else:
            logger.info(
                f"[{rid}] Drift check: KL={kl_div:.4f} JS={js_div:.4f} score_shift={score_shift:+.4f} "
                f"(ok), alert_rate={alert_rate:.4f}"
            )

    DRIFT_LOG.write_text(json.dumps(drift_data, indent=2), encoding="utf-8")


def _run_pipeline():
    """Pipeline execution with better error handling (Issues #3, #7, #9)."""
    global ALERTS, SUPPRESSED, PIPELINE_ERROR, ML_METRICS, DECISION_THRESHOLD, DECISIONS, PIPELINE_START_TIME

    PIPELINE_START_TIME = time.time()
    try:
        if _load_cache():
            DECISIONS = db.current_decisions()
            PIPELINE_READY.set()
            return

        rid = request_id.get()
        logger.info(f"[{rid}] No cache found — running Multi-GNN pipeline...")
        from ..pipeline.detection import run_multignn_pipeline

        try:
            serialized, ML_METRICS = run_multignn_pipeline(max_rows=MULTIGNN_MAX_ROWS)
        except FileNotFoundError as e:
            raise RuntimeError(
                f"Transaction data not found. Check data ingestion pipeline. Error: {e}"
            )
        except Exception as e:
            raise RuntimeError(
                f"Pipeline execution failed: {str(e)}. Check model and data integrity."
            )

        DECISION_THRESHOLD = float(ML_METRICS.get("threshold", 0.5))

        # Apply whitelist filtering
        wl = load_whitelist()
        kept, suppressed = filter_alerts(serialized, wl)

        with ALERTS_LOCK:
            ALERTS = {a["id"]: a for a in kept}
            SUPPRESSED = {a["id"]: a for a in suppressed}

        rid = request_id.get()
        logger.info(
            f"[{rid}] Multi-GNN alerts: {len(kept)} kept, {len(suppressed)} suppressed (whitelist)"
        )

        # Persist alerts
        db.replace_alerts(serialized, scan_id=str(int(time.time())))
        DECISIONS = db.current_decisions()

        _check_drift([a["mlScore"] for a in serialized if a.get("mlScore") is not None])
        _save_cache()

    except Exception as e:
        PIPELINE_ERROR = str(e)
        rid = request_id.get()
        logger.error(f"[{rid}] Pipeline failed: {e}", exc_info=True)

    PIPELINE_READY.set()


# ── FastAPI App with Async Lifespan (Issue #3, #7) ──────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and graceful shutdown logic."""
    _ensure_data_dir()
    db.init_db()
    log_paths = setup_logging(LOGS_DIR)
    logger.info(f"Error logs -> {log_paths['error_logs']}")
    logger.info(f"Training logs -> {log_paths['training_logs']}")

    if not MODEL_PATH.exists():
        logger.warning(f"Model file not found at {MODEL_PATH} — app will run in degraded mode (no ML inference)")
    else:
        logger.info(f"Model file found at {MODEL_PATH}")

    # Start pipeline as non-daemon thread for graceful shutdown (Issue #7)
    pipeline_thread = threading.Thread(target=_run_pipeline, daemon=False)
    pipeline_thread.start()
    logger.info("Pipeline thread started (non-daemon for graceful shutdown)")

    yield

    # Graceful shutdown: wait for pipeline to complete
    logger.info("Shutting down: waiting for pipeline to complete...")
    pipeline_thread.join(timeout=30)
    if pipeline_thread.is_alive():
        logger.warning("Pipeline thread did not finish in time, but shutdown proceeding")


app = FastAPI(title="AML Intelligence Platform API", lifespan=lifespan)

# Add rate limiting to app state
app.state.limiter = limiter

app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)


@app.middleware("http")
async def add_request_context(request: Request, call_next):
    """Inject request ID and structured logging (Issue #6)."""
    rid = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    request_id.set(rid)
    logger.info(f"[{rid}] {request.method} {request.url.path}")
    response = await call_next(request)
    response.headers["X-Request-ID"] = rid
    return response


FRONTEND_DIR = Path(__file__).parent.parent.parent / "frontend"
FRONTEND_PUBLIC = FRONTEND_DIR / "public"

# Serve static assets: CSS, JS, and vendor libraries
_css_dir = FRONTEND_DIR / "css"
_js_dir = FRONTEND_DIR / "js"
_lib_dir = FRONTEND_DIR / "lib"
if _css_dir.exists():
    app.mount("/static/css", StaticFiles(directory=str(_css_dir)), name="static-css")
if _js_dir.exists():
    app.mount("/static/js", StaticFiles(directory=str(_js_dir)), name="static-js")
if _lib_dir.exists():
    app.mount("/static/lib", StaticFiles(directory=str(_lib_dir)), name="static-lib")
if FRONTEND_PUBLIC.exists():
    app.mount("/static/public", StaticFiles(directory=str(FRONTEND_PUBLIC)), name="static-public")

def get_frontend_dir():
    return FRONTEND_PUBLIC


# ── Core endpoints ──────────────────────────────────────────────────────────

@app.get("/health")
def health():
    """Enhanced health check with model age and monitoring (Issue #8)."""
    ready = PIPELINE_READY.is_set()
    model_age_hours = None
    model_warning = None

    if MODEL_PATH.exists():
        model_age_hours = round((time.time() - MODEL_PATH.stat().st_mtime) / 3600, 1)
        if model_age_hours > 24:
            model_warning = "Model older than 24 hours — consider retraining"

    pipeline_age_hours = None
    if PIPELINE_START_TIME > 0:
        pipeline_age_hours = round((time.time() - PIPELINE_START_TIME) / 3600, 1)

    result = {
        "status": "ok",
        "pipeline_status": "error" if (ready and PIPELINE_ERROR) else ("ready" if ready else "loading"),
        "alerts_count": len(ALERTS),
        "model_age_hours": model_age_hours,
        "pipeline_age_hours": pipeline_age_hours,
    }

    warnings = []
    if model_warning:
        warnings.append(model_warning)
    if PIPELINE_ERROR:
        warnings.append(f"Pipeline error: {PIPELINE_ERROR[:100]}")

    if warnings:
        result["warnings"] = warnings

    return result


@app.get("/status")
@limiter.limit("100/minute")
def status(request: Request):
    """Alert status and pattern breakdown (Issue #1: rate limited)."""
    ready = PIPELINE_READY.is_set()
    patterns: dict[str, int] = {}

    with ALERTS_LOCK:
        for a in ALERTS.values():
            pt = a["patternType"]
            patterns[pt] = patterns.get(pt, 0) + 1

        labelled = sum(1 for a in ALERTS.values() if a.get("source") == "labelled")
        unlabelled = sum(1 for a in ALERTS.values() if a.get("source") == "unlabelled")

    result = {
        "status": "error" if (ready and PIPELINE_ERROR) else ("ready" if ready else "loading"),
        "alert_count": len(ALERTS),
        "suppressed_count": len(SUPPRESSED),
        "labelled_count": labelled,
        "unlabelled_count": unlabelled,
        "overlap_count": 0,
        "patterns": patterns,
    }
    if PIPELINE_ERROR:
        result["error"] = PIPELINE_ERROR
    return result


@app.get("/alerts")
@limiter.limit("100/minute")
def list_alerts(
    request: Request,
    pattern_type: PatternType | None = Query(default=None),
    severity: SeverityLevel | None = Query(default=None),
    source: AlertSource | None = Query(default=None),
):
    """List alerts with ETag caching (Issues #1, #2, #5)."""
    global ALERTS_ETAG

    # Check ETag cache
    current_etag = _compute_alerts_etag()
    ALERTS_ETAG = current_etag

    if_none_match = request.headers.get("If-None-Match")
    if if_none_match == current_etag:
        return JSONResponse(status_code=304)  # Not Modified

    results = []
    with ALERTS_LOCK:
        for a in ALERTS.values():
            if pattern_type and a["patternType"] != pattern_type:
                continue
            if severity and a["severity"].lower() != severity.value:
                continue
            if source and a.get("source") != source.value:
                continue
            results.append({
                "id": a["id"],
                "name": a["name"],
                "sub": a["sub"],
                "severity": a["severity"],
                "confidence": a["confidence"],
                "patternType": a["patternType"],
                "totalMoved": a["totalMoved"],
                "timeSpan": a["timeSpan"],
                "hops": a["hops"],
                "node_count": len(a["nodes"]),
                "txn_count": len(a["transactions"]),
                "source": a.get("source", "labelled"),
            })

    response = JSONResponse(content=results)
    response.headers["ETag"] = current_etag
    response.headers["Cache-Control"] = "public, max-age=60"
    return response


@app.get("/alerts/suppressed")
@limiter.limit("50/minute")
def list_suppressed(request: Request):
    """List suppressed alerts (Issue #1: rate limited)."""
    with ALERTS_LOCK:
        return list(SUPPRESSED.values())


@app.get("/alerts/{alert_id}")
@limiter.limit("100/minute")
def get_alert(request: Request, alert_id: str):
    """Retrieve a single alert (Issue #10: thread-safe access)."""
    with ALERTS_LOCK:
        if alert_id not in ALERTS:
            raise HTTPException(status_code=404, detail="Alert not found")
        return ALERTS[alert_id]


class DecisionBody(BaseModel):
    decision: DecisionType
    reason: str = ""
    analyst: str = ""


@app.post("/alerts/{alert_id}/decision")
@limiter.limit("50/minute")
def post_decision(request: Request, alert_id: str, body: DecisionBody):
    """Record analyst decision (Issue #1, #10)."""
    with ALERTS_LOCK:
        if alert_id not in ALERTS:
            raise HTTPException(status_code=404, detail="Alert not found")

    db.record_decision(alert_id, body.decision.value, body.reason, body.analyst)

    with ALERTS_LOCK:
        DECISIONS[alert_id] = {
            "decision": body.decision.value,
            "reason": body.reason,
            "analyst": body.analyst,
        }

    return {
        "status": "saved",
        "alert_id": alert_id,
        "decision": body.decision.value,
    }


@app.get("/alerts/{alert_id}/decision/history")
@limiter.limit("100/minute")
def get_decision_history(request: Request, alert_id: str):
    """Chronological audit trail (Issue #1)."""
    with ALERTS_LOCK:
        if alert_id not in ALERTS:
            raise HTTPException(status_code=404, detail="Alert not found")

    return {"alert_id": alert_id, "history": db.decision_history(alert_id)}


@app.get("/decisions")
@limiter.limit("50/minute")
def get_decisions(request: Request):
    """Current decision state (Issue #1)."""
    return db.current_decisions()


# ── Whitelist endpoints ─────────────────────────────────────────────────────

@app.get("/whitelist")
@limiter.limit("50/minute")
def get_whitelist(request: Request):
    return load_whitelist()


class WhitelistAddBody(BaseModel):
    account_id: str = Field(..., min_length=1)
    reason: str = ""


@app.post("/whitelist/account")
@limiter.limit("20/minute")
def whitelist_add(request: Request, body: WhitelistAddBody):
    """Add account to whitelist (Issue #1: rate limited)."""
    wl = add_to_whitelist(body.account_id)
    return {"status": "added", "account_id": body.account_id, "whitelist": wl}


@app.delete("/whitelist/account/{account_id}")
@limiter.limit("20/minute")
def whitelist_remove(request: Request, account_id: str):
    """Remove account from whitelist (Issue #1: rate limited)."""
    wl = remove_from_whitelist(account_id)
    return {"status": "removed", "account_id": account_id}


# ── ML Metrics ──────────────────────────────────────────────────────────────

@app.get("/ml-metrics")
@limiter.limit("50/minute")
def get_ml_metrics(request: Request):
    """ML model metrics (Issue #1)."""
    if not ML_METRICS:
        raise HTTPException(status_code=404, detail="ML model not trained yet")
    return {**ML_METRICS, "decision_threshold": DECISION_THRESHOLD}


@app.get("/drift")
@limiter.limit("50/minute")
def get_drift(request: Request):
    """Data drift metrics (Issue #1)."""
    if not DRIFT_LOG.exists():
        return {
            "status": "no_data",
            "message": "Pipeline has not completed a full run yet.",
        }
    try:
        return json.loads(DRIFT_LOG.read_text(encoding="utf-8"))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/validation")
@limiter.limit("50/minute")
def get_validation(request: Request):
    validation_path = DATA_DIR / "validation_results.json"
    if not validation_path.exists():
        raise HTTPException(status_code=404, detail="Run validator.py first to generate validation data.")
    try:
        return json.loads(validation_path.read_text(encoding="utf-8"))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── SPA fallback (must be last — catches all unmatched paths) ─────────────

@app.get("/")
def serve_frontend():
    frontend = get_frontend_dir()
    return FileResponse(str(frontend / "index.html"))

@app.get("/{path_name:path}")
def serve_spa_fallback(path_name: str):
    frontend = get_frontend_dir()
    file_path = frontend / path_name
    if file_path.exists() and file_path.is_file():
        return FileResponse(str(file_path))
    return FileResponse(str(frontend / "index.html"))

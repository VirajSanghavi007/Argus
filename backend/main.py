import json
import math
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

from pipeline import load_and_build, find_suspicious_unlabelled
from detector import detect_all_patterns
from serializer import serialize_alerts
from whitelist import (
    load_whitelist, save_whitelist, filter_alerts,
    add_to_whitelist, remove_from_whitelist,
    DEFAULT_WHITELIST,
)
from ml_model import train_or_load, score_subgraph, extract_features
from retrainer import persist_decision, check_retrain_trigger, retrain_from_feedback
from log_setup import setup_file_logging

try:
    from gnn_model import load_gnn, score_subgraph_gnn
    _GNN_AVAILABLE = True
except Exception:
    _GNN_AVAILABLE = False
    def load_gnn(): return None
    def score_subgraph_gnn(sub, model): return 0.5

logger     = logging.getLogger("uvicorn.error")
DATA_DIR   = Path(__file__).parent.parent / "data"
LOGS_DIR   = Path(__file__).parent.parent / "logs"
CACHE_PATH = DATA_DIR / "pipeline_cache.json"
DRIFT_LOG  = DATA_DIR / "drift_log.json"

ALERTS:    dict = {}
SUPPRESSED: dict = {}
DECISIONS: dict = {}
PIPELINE_READY = threading.Event()
PIPELINE_ERROR: str = ""
ML_METRICS: dict = {}
DECISION_THRESHOLD: float = 0.5

# Graphs kept in memory so retrainer can rebuild training set after decisions
_G_SUSPICIOUS: object = None
_G_FULL:       object = None

LABELLED_COUNT   = 0
UNLABELLED_COUNT = 0
OVERLAP_COUNT    = 0


# ── helpers ───────────────────────────────────────────────────────────────────

def _overlap_ratio(a: frozenset, b: frozenset) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / max(len(a), len(b))


def _merge_raw_alerts(labelled_raw: list, unlabelled_raw: list) -> tuple[list, int]:
    labelled_sets = [
        frozenset(n["node_id"] for n in a["nodes_list"])
        for a in labelled_raw
    ]
    merged = [dict(a) for a in labelled_raw]
    overlap_count = 0
    for u in unlabelled_raw:
        u_set = frozenset(n["node_id"] for n in u["nodes_list"])
        matched = False
        for i, l_set in enumerate(labelled_sets):
            if _overlap_ratio(u_set, l_set) > 0.8:
                merged[i]["source"] = "both"
                overlap_count += 1
                matched = True
                break
        if not matched:
            merged.append(dict(u))
    return merged, overlap_count


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
        global ALERTS, SUPPRESSED, LABELLED_COUNT, UNLABELLED_COUNT, OVERLAP_COUNT, ML_METRICS
        cache = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
        ALERTS           = {a["id"]: a for a in cache["alerts"]}
        SUPPRESSED       = {a["id"]: a for a in cache["suppressed"]}
        LABELLED_COUNT   = cache["labelled_count"]
        UNLABELLED_COUNT = cache["unlabelled_count"]
        OVERLAP_COUNT    = cache["overlap_count"]
        ML_METRICS       = cache.get("ml_metrics", {})
        logger.info(f"Loaded from cache: {len(ALERTS)} alerts, {len(SUPPRESSED)} suppressed")
        return True
    except Exception as e:
        logger.warning(f"Cache load failed ({e}), running full pipeline")
        return False


def _save_cache():
    try:
        cache = {
            "alerts":           list(ALERTS.values()),
            "suppressed":       list(SUPPRESSED.values()),
            "labelled_count":   LABELLED_COUNT,
            "unlabelled_count": UNLABELLED_COUNT,
            "overlap_count":    OVERLAP_COUNT,
            "ml_metrics":       ML_METRICS,
        }
        CACHE_PATH.write_text(json.dumps(cache), encoding="utf-8")
        logger.info(f"Pipeline cache saved to {CACHE_PATH}")
    except Exception as e:
        logger.warning(f"Could not save cache: {e}")


# ── pipeline thread ───────────────────────────────────────────────────────────

def _check_drift(ml_scores: list) -> None:
    """
    Phase 7 — Drift detection.
    Compare current ml_score distribution to baseline via KL divergence.
    Logs WARNING and writes to drift_log.json if KL > 0.1.
    """
    if not ml_scores:
        return

    scores = np.array(ml_scores, dtype=float)
    bins   = np.linspace(0.0, 1.0, 21)  # 20 buckets
    hist, _ = np.histogram(scores, bins=bins)
    hist    = hist / hist.sum() if hist.sum() > 0 else hist

    drift_data: dict = {}
    if DRIFT_LOG.exists():
        try:
            drift_data = json.loads(DRIFT_LOG.read_text(encoding="utf-8"))
        except Exception:
            pass

    if "baseline_hist" not in drift_data:
        # First run — store as baseline
        drift_data["baseline_hist"]  = hist.tolist()
        drift_data["baseline_count"] = int(len(scores))
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

        alert_rate = float(np.mean(scores > DECISION_THRESHOLD))
        run_entry  = {"kl_divergence": round(kl_div, 4), "alert_rate": round(alert_rate, 4),
                      "n_scores": int(len(scores))}
        drift_data.setdefault("runs", []).append(run_entry)

        if kl_div > 0.1:
            logger.warning(
                f"DRIFT DETECTED — KL divergence: {kl_div:.4f} (threshold 0.1). "
                f"Alert rate: {alert_rate:.4f}. Consider retraining."
            )
        else:
            logger.info(f"Drift check: KL={kl_div:.4f} (ok), alert_rate={alert_rate:.4f}")

    DRIFT_LOG.write_text(json.dumps(drift_data, indent=2), encoding="utf-8")


def _run_pipeline():
    global ALERTS, SUPPRESSED, LABELLED_COUNT, UNLABELLED_COUNT, OVERLAP_COUNT
    global PIPELINE_ERROR, ML_METRICS, DECISION_THRESHOLD, _G_SUSPICIOUS, _G_FULL

    try:
        # Fast path: load from cache if available
        if _load_cache():
            PIPELINE_READY.set()
            return

        # Slow path: run full pipeline
        logger.info("No cache found — running full pipeline...")
        from pipeline import CSV_PATH
        if not CSV_PATH.exists():
            raise FileNotFoundError(
                f"Dataset not found at {CSV_PATH}. "
                "Expected at data/IBM/HI-Small_Trans.csv or data/HI-Small_Trans.csv."
            )

        df_suspicious, df_full, G_suspicious, G_full = load_and_build()
        _G_SUSPICIOUS = G_suspicious
        _G_FULL       = G_full

        # Train / load ML fraud classifier + optional GNN second layer
        model, ML_METRICS = train_or_load(G_suspicious, G_full)
        DECISION_THRESHOLD = ML_METRICS.get("decision_threshold", 0.5)
        gnn_model = load_gnn()
        if gnn_model is not None:
            logger.info("GNN second layer loaded.")
        else:
            logger.info("GNN not trained yet — using ML model only.")

        labelled_raw = detect_all_patterns(
            G_suspicious, df_suspicious, source="labelled", id_prefix="",
        )
        G_unlabelled, account_signals = find_suspicious_unlabelled(df_full)
        unlabelled_raw = detect_all_patterns(
            G_unlabelled, df_full,
            source="unlabelled", account_signals=account_signals, id_prefix="u_",
        )

        merged_raw, overlap = _merge_raw_alerts(labelled_raw, unlabelled_raw)

        # Score each alert with the ML model (+ GNN blend if available)
        logger.info("Scoring alerts with ML model...")
        ml_scores = []
        for alert in merged_raw:
            comp   = set(n["node_id"] for n in alert["nodes_list"])
            G_ref  = G_unlabelled if alert.get("source") == "unlabelled" else G_suspicious
            sub    = G_ref.subgraph(comp).copy()

            if sub.number_of_nodes() >= 2:
                ml_s = score_subgraph(sub, model)
                if gnn_model is not None:
                    gnn_s = score_subgraph_gnn(sub, gnn_model)
                    final_score = round(0.5 * ml_s + 0.5 * gnn_s, 4)
                else:
                    gnn_s       = None
                    final_score = ml_s
            else:
                ml_s = gnn_s = 0.5
                final_score = 0.5

            alert["ml_score"]    = final_score
            alert["ml_score_rf"] = ml_s
            alert["ml_score_gnn"] = gnn_s
            alert["risk_flagged"] = final_score >= DECISION_THRESHOLD
            ml_scores.append(final_score)

        whitelist = load_whitelist()
        kept_raw, supp_raw = filter_alerts(merged_raw, whitelist)

        serialized     = serialize_alerts(kept_raw)
        suppressed_ser = serialize_alerts(supp_raw)

        ALERTS     = {a["id"]: a for a in serialized}
        SUPPRESSED = {a["id"]: a for a in suppressed_ser}

        LABELLED_COUNT   = sum(1 for a in ALERTS.values() if a["source"] in ("labelled", "both"))
        UNLABELLED_COUNT = sum(1 for a in ALERTS.values() if a["source"] in ("unlabelled", "both"))
        OVERLAP_COUNT    = overlap

        logger.info(
            f"Labelled: {len(labelled_raw)} | Unlabelled: {len(unlabelled_raw)} | "
            f"Overlap: {overlap} | Suppressed: {len(SUPPRESSED)} | Total: {len(ALERTS)}"
        )

        _check_drift(ml_scores)
        _save_cache()

    except Exception as e:
        PIPELINE_ERROR = str(e)
        logger.error(f"Pipeline failed: {e}")

    PIPELINE_READY.set()


# ── app ───────────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    _ensure_data_dir()
    log_path = setup_file_logging(LOGS_DIR)
    logger.info(f"Error log -> {log_path}")
    t = threading.Thread(target=_run_pipeline, daemon=True)
    t.start()
    yield


app = FastAPI(title="AML Intelligence Platform API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)

# Serve frontend
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
        "labelled_count":   LABELLED_COUNT,
        "unlabelled_count": UNLABELLED_COUNT,
        "overlap_count":    OVERLAP_COUNT,
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
            "partialExemption": a.get("partial_exemption", False),
        })
    return results


# NOTE: /alerts/suppressed MUST be before /alerts/{alert_id} in route order
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


@app.post("/alerts/{alert_id}/decision")
def post_decision(alert_id: str, body: DecisionBody):
    if alert_id not in ALERTS:
        raise HTTPException(status_code=404, detail="Alert not found")

    alert = ALERTS[alert_id]
    DECISIONS[alert_id] = {"decision": body.decision, "reason": body.reason}

    # Phase 5 — persist analyst decision with subgraph features
    try:
        true_label = 1 if body.decision.lower() in ("confirmed", "true_positive", "fraud") else 0
        comp = set(n["node_id"] for n in alert.get("nodes_list", []))
        if comp and _G_SUSPICIOUS is not None:
            G_ref = _G_SUSPICIOUS
            sub   = G_ref.subgraph(comp).copy()
            if sub.number_of_nodes() >= 2:
                feats = extract_features(sub)
                persist_decision(alert_id, feats, true_label, body.decision, body.reason)

                # Trigger retraining in background if threshold met
                if check_retrain_trigger() and _G_SUSPICIOUS is not None and _G_FULL is not None:
                    import threading
                    t = threading.Thread(
                        target=retrain_from_feedback,
                        args=(_G_SUSPICIOUS, _G_FULL),
                        daemon=True,
                    )
                    t.start()
                    logger.info("Retraining triggered in background.")
    except Exception as exc:
        logger.warning(f"Decision persistence failed for {alert_id}: {exc}")

    return {"status": "saved", "alert_id": alert_id, "decision": body.decision}


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


# ── validation ────────────────────────────────────────────────────────────────

@app.get("/validation")
def get_validation():
    results_path = DATA_DIR / "validation_results.json"
    if results_path.exists():
        return json.loads(results_path.read_text(encoding="utf-8"))

    if not PIPELINE_READY.is_set() or not ALERTS:
        raise HTTPException(status_code=503, detail="Pipeline not ready yet")

    from validator import _parse_patterns, _validate_alert_set
    from collections import defaultdict

    patterns_path = DATA_DIR / "IBM" / "HI-Small_Patterns.txt"
    if not patterns_path.exists():
        patterns_path = DATA_DIR / "HI-Small_Patterns.txt"  # backwards compat
    if not patterns_path.exists():
        raise HTTPException(status_code=404, detail="HI-Small_Patterns.txt not found in data/IBM/")

    ground_truth = _parse_patterns(patterns_path)

    all_alerts      = list(ALERTS.values())
    labelled_ser    = [a for a in all_alerts if a.get("source") in ("labelled", "both")]
    unlabelled_ser  = [a for a in all_alerts if a.get("source") in ("unlabelled", "both")]

    lab_metrics   = _validate_alert_set(labelled_ser,   ground_truth)
    unlab_metrics = _validate_alert_set(unlabelled_ser, ground_truth)

    lab_sets = [frozenset(n["id"] for n in a["nodes"]) for a in labelled_ser]
    overlap_count = 0
    for u in unlabelled_ser:
        u_set = frozenset(n["id"] for n in u["nodes"])
        for l_set in lab_sets:
            denom = max(len(u_set), len(l_set))
            if denom and len(u_set & l_set) / denom > 0.8:
                overlap_count += 1
                break

    results = {
        "total_gt_blocks": len(ground_truth),
        "labelled":        lab_metrics,
        "unlabelled":      unlab_metrics,
        "overlap_count":   overlap_count,
        "comparison": {
            "labelled_alerts":      len(labelled_ser),
            "unlabelled_alerts":    len(unlabelled_ser),
            "overlap_count":        overlap_count,
            "labelled_precision":   lab_metrics["overall_precision"],
            "labelled_recall":      lab_metrics["overall_recall"],
            "unlabelled_precision": unlab_metrics["overall_precision"],
            "unlabelled_recall":    unlab_metrics["overall_recall"],
        },
    }

    results_path.write_text(json.dumps(results, indent=2), encoding="utf-8")
    logger.info(f"Validation results computed and saved to {results_path}")
    return results

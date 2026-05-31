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

from pipeline import load_and_build, find_suspicious_unlabelled
from detector import detect_all_patterns
from serializer import serialize_alerts
from whitelist import (
    load_whitelist, save_whitelist, filter_alerts,
    add_to_whitelist, remove_from_whitelist,
    DEFAULT_WHITELIST,
)
from ml_model import train_or_load, score_subgraph

logger     = logging.getLogger("uvicorn.error")
DATA_DIR   = Path(__file__).parent.parent / "data"
CACHE_PATH = DATA_DIR / "pipeline_cache.json"

ALERTS:    dict = {}
SUPPRESSED: dict = {}
DECISIONS: dict = {}
PIPELINE_READY = threading.Event()
PIPELINE_ERROR: str = ""
ML_METRICS: dict = {}

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

def _run_pipeline():
    global ALERTS, SUPPRESSED, LABELLED_COUNT, UNLABELLED_COUNT, OVERLAP_COUNT, PIPELINE_ERROR, ML_METRICS

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
                "Ensure HI-Small_Trans.csv is in the data/ directory."
            )

        df_suspicious, df_full, G_suspicious, G_full = load_and_build()

        # Train / load ML fraud classifier
        model, ML_METRICS = train_or_load(G_suspicious, G_full)

        labelled_raw = detect_all_patterns(
            G_suspicious, df_suspicious, source="labelled", id_prefix="",
        )
        G_unlabelled, account_signals = find_suspicious_unlabelled(df_full)
        unlabelled_raw = detect_all_patterns(
            G_unlabelled, df_full,
            source="unlabelled", account_signals=account_signals, id_prefix="u_",
        )

        merged_raw, overlap = _merge_raw_alerts(labelled_raw, unlabelled_raw)

        # Score each alert with the ML model
        logger.info("Scoring alerts with ML model...")
        for alert in merged_raw:
            comp   = set(n["node_id"] for n in alert["nodes_list"])
            G_ref  = G_unlabelled if alert.get("source") == "unlabelled" else G_suspicious
            sub    = G_ref.subgraph(comp).copy()
            alert["ml_score"] = score_subgraph(sub, model) if sub.number_of_nodes() >= 2 else 0.5

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
        _save_cache()

    except Exception as e:
        PIPELINE_ERROR = str(e)
        logger.error(f"Pipeline failed: {e}")

    PIPELINE_READY.set()


# ── app ───────────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    _ensure_data_dir()
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
    DECISIONS[alert_id] = {"decision": body.decision, "reason": body.reason}
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
    return ML_METRICS


# ── validation ────────────────────────────────────────────────────────────────

@app.get("/validation")
def get_validation():
    results_path = DATA_DIR / "validation_results.json"
    if not results_path.exists():
        raise HTTPException(status_code=404, detail="Validation not run yet")
    return json.loads(results_path.read_text(encoding="utf-8"))

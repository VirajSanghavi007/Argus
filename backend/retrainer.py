"""
Human-in-the-loop retraining module.

Analyst decisions are persisted to data/analyst_decisions.json.
After RETRAIN_THRESHOLD confirmed decisions accumulate since the last retrain,
the ML model is automatically retrained incorporating the analyst-labelled examples.

Called from main.py after each POST /alerts/{id}/decision.
"""

import json
import logging
import pickle
import time
import numpy as np
import pandas as pd
import networkx as nx

from pathlib import Path
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import f1_score

logger    = logging.getLogger("uvicorn.error")
DATA_DIR  = Path(__file__).parent.parent / "data"

DECISIONS_PATH    = DATA_DIR / "analyst_decisions.json"
MODEL_PATH        = DATA_DIR / "fraud_model.pkl"
RETRAIN_THRESHOLD = 50   # decisions since last retrain before triggering


# ── Persistence ───────────────────────────────────────────────────────────────

def persist_decision(
    alert_id: str,
    features: dict,
    true_label: int,          # 1 = analyst confirmed fraud, 0 = false positive
    decision: str,
    reason: str = "",
) -> None:
    """Append one analyst decision to the decisions JSON file."""
    decisions = _load_decisions()
    decisions[alert_id] = {
        "features":   features,
        "true_label": true_label,
        "decision":   decision,
        "reason":     reason,
        "timestamp":  time.time(),
        "used_in_retrain": False,
    }
    DECISIONS_PATH.write_text(json.dumps(decisions, indent=2), encoding="utf-8")
    logger.info(f"Decision persisted: {alert_id} -> label={true_label}")


def _load_decisions() -> dict:
    if not DECISIONS_PATH.exists():
        return {}
    try:
        return json.loads(DECISIONS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


# ── Trigger check ─────────────────────────────────────────────────────────────

def check_retrain_trigger() -> bool:
    """True if ≥RETRAIN_THRESHOLD decisions have not yet been used in a retrain."""
    decisions = _load_decisions()
    unused = sum(1 for d in decisions.values() if not d.get("used_in_retrain", False))
    logger.info(f"Retrainer: {unused} unused decisions (threshold={RETRAIN_THRESHOLD})")
    return unused >= RETRAIN_THRESHOLD


# ── Retraining ────────────────────────────────────────────────────────────────

def retrain_from_feedback(G_suspicious: nx.DiGraph, G_full: nx.DiGraph) -> dict | None:
    """
    Retrain the fraud model by appending analyst-confirmed labels to the
    original training distribution.

    Returns updated metrics dict, or None if training failed.
    """
    from ml_model import extract_features, FEATURE_COLS, _calibrate_threshold

    decisions = _load_decisions()
    unused = {aid: d for aid, d in decisions.items() if not d.get("used_in_retrain", False)}
    if len(unused) < RETRAIN_THRESHOLD:
        return None

    logger.info(f"Retraining with {len(unused)} analyst decisions...")

    # Build analyst rows
    analyst_X, analyst_y = [], []
    for aid, d in unused.items():
        feats = d.get("features")
        if feats and len(feats) == len(FEATURE_COLS):
            analyst_X.append([feats[c] for c in FEATURE_COLS])
            analyst_y.append(int(d["true_label"]))

    if not analyst_X:
        logger.warning("No usable analyst features found; skipping retrain.")
        return None

    susp_nodes = set(G_suspicious.nodes())
    pos_comps  = [c for c in nx.weakly_connected_components(G_suspicious) if len(c) >= 3]
    neg_comps  = [
        c for c in nx.weakly_connected_components(G_full)
        if len(c) >= 3 and len(c & susp_nodes) == 0
    ]

    import random
    random.seed(42)
    neg_sample = random.sample(neg_comps, min(len(neg_comps), len(pos_comps) * 3))

    orig_rows, orig_labels = [], []
    for comp in pos_comps:
        orig_rows.append(extract_features(G_suspicious.subgraph(comp).copy()))
        orig_labels.append(1)
    for comp in neg_sample:
        orig_rows.append(extract_features(G_full.subgraph(comp).copy()))
        orig_labels.append(0)

    X_orig = pd.DataFrame(orig_rows)[FEATURE_COLS].values
    y_orig = np.array(orig_labels)

    # Combine original + analyst labels (analyst labels get 5× weight via oversampling)
    X_analyst = np.array(analyst_X)
    y_analyst = np.array(analyst_y)
    X_analyst_rep = np.tile(X_analyst, (5, 1))
    y_analyst_rep = np.tile(y_analyst, 5)

    X_combined = np.vstack([X_orig, X_analyst_rep])
    y_combined = np.concatenate([y_orig, y_analyst_rep])

    # Train with noise injection
    rng   = np.random.default_rng(99)
    noise = rng.normal(0, 0.02 * np.std(X_combined, axis=0), X_combined.shape)
    X_aug = X_combined + noise

    model = RandomForestClassifier(
        n_estimators=200, max_depth=10, class_weight="balanced",
        random_state=99, n_jobs=-1,
    )
    model.fit(X_aug, y_combined)

    # Eval on analyst holdout (not perfect but indicative)
    y_pred    = model.predict(X_analyst)
    analyst_f1 = f1_score(y_analyst, y_pred, zero_division=0)
    threshold  = _calibrate_threshold(model, X_analyst, y_analyst)

    # Version the old model
    _version_old_model()

    metrics = {
        "f1":                round(float(analyst_f1), 4),
        "n_train":           int(len(X_combined)),
        "n_analyst":         int(len(analyst_X)),
        "n_features":        len(FEATURE_COLS),
        "decision_threshold": round(threshold, 4),
        "retrain_timestamp": int(time.time()),
    }

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(MODEL_PATH, "wb") as f:
        pickle.dump({"model": model, "metrics": metrics}, f)

    # Mark all used decisions
    for aid in unused:
        decisions[aid]["used_in_retrain"] = True
    DECISIONS_PATH.write_text(json.dumps(decisions, indent=2), encoding="utf-8")

    logger.info(
        f"Retrain complete — analyst F1: {analyst_f1:.4f} | "
        f"threshold: {threshold:.4f} | model saved -> {MODEL_PATH}"
    )
    return metrics


def _version_old_model():
    """Keep last 3 old model versions as fraud_model_v{n}.pkl."""
    if not MODEL_PATH.exists():
        return
    for i in range(2, 0, -1):
        src = DATA_DIR / f"fraud_model_v{i}.pkl"
        dst = DATA_DIR / f"fraud_model_v{i+1}.pkl"
        if src.exists():
            src.rename(dst)
    MODEL_PATH.rename(DATA_DIR / "fraud_model_v1.pkl")

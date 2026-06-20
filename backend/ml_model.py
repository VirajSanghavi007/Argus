import logging
import pickle
import random
import warnings
import numpy as np

warnings.filterwarnings("ignore", category=UserWarning, module="sklearn")
import pandas as pd
import networkx as nx
from pathlib import Path
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, f1_score

try:
    from xgboost import XGBClassifier
    _HAS_XGB = True
except ImportError:
    _HAS_XGB = False

logger     = logging.getLogger("uvicorn.error")
DATA_DIR   = Path(__file__).parent.parent / "data"
MODEL_PATH = DATA_DIR / "fraud_model.pkl"

FEATURE_COLS = [
    # --- original 16 ---
    "n_nodes", "n_edges", "density", "has_cycle",
    "max_in_degree", "max_out_degree", "avg_clustering", "n_layers",
    "total_amount", "max_amount", "avg_amount", "amount_std",
    "time_span_hours", "n_banks", "n_currencies", "edge_node_ratio",
    # --- new 6 (Phase 1) ---
    "amount_gini",
    "max_betweenness", "avg_betweenness", "hub_betweenness",
    "in_degree_std", "out_degree_std",
]


def _gini(amounts: list) -> float:
    if not amounts or sum(amounts) == 0:
        return 0.0
    arr = sorted(amounts)
    n   = len(arr)
    return (2 * sum((i + 1) * v for i, v in enumerate(arr))) / (n * sum(arr)) - (n + 1) / n


def extract_features(sub: nx.DiGraph) -> dict:
    n = sub.number_of_nodes()
    m = sub.number_of_edges()
    if n == 0:
        return {col: 0.0 for col in FEATURE_COLS}

    in_degrees  = [d for _, d in sub.in_degree()]
    out_degrees = [d for _, d in sub.out_degree()]
    has_cycle   = not nx.is_directed_acyclic_graph(sub)
    density     = nx.density(sub)

    try:
        avg_clustering = nx.average_clustering(sub.to_undirected())
    except Exception:
        avg_clustering = 0.0

    n_layers = 0
    if not has_cycle:
        try:
            n_layers = len(list(nx.topological_generations(sub)))
        except Exception:
            pass

    amounts      = [d.get("amount_paid", 0) for _, _, d in sub.edges(data=True)]
    total_amount = sum(amounts)
    max_amount   = max(amounts) if amounts else 0.0
    avg_amount   = total_amount / m if m > 0 else 0.0
    amount_std   = float(np.std(amounts)) if amounts else 0.0

    timestamps      = [d.get("timestamp") for _, _, d in sub.edges(data=True) if d.get("timestamp") is not None]
    time_span_hours = 0.0
    if len(timestamps) >= 2:
        time_span_hours = (max(timestamps) - min(timestamps)).total_seconds() / 3600.0

    banks, currencies = set(), set()
    for _, _, d in sub.edges(data=True):
        if d.get("from_bank"):          banks.add(d["from_bank"])
        if d.get("to_bank"):            banks.add(d["to_bank"])
        if d.get("receiving_currency"): currencies.add(d["receiving_currency"])

    # ── new features ──────────────────────────────────────────────────────────
    amount_gini = _gini(amounts)

    try:
        bc = nx.betweenness_centrality(sub, normalized=True)
    except Exception:
        bc = {v: 0.0 for v in sub.nodes()}
    bc_values       = list(bc.values())
    max_betweenness = max(bc_values) if bc_values else 0.0
    avg_betweenness = float(np.mean(bc_values)) if bc_values else 0.0
    hub             = max(sub.nodes(), key=lambda v: sub.in_degree(v) + sub.out_degree(v))
    hub_betweenness = bc.get(hub, 0.0)

    in_degree_std  = float(np.std(in_degrees))  if in_degrees  else 0.0
    out_degree_std = float(np.std(out_degrees)) if out_degrees else 0.0

    return {
        "n_nodes":          float(n),
        "n_edges":          float(m),
        "density":          density,
        "has_cycle":        float(int(has_cycle)),
        "max_in_degree":    float(max(in_degrees) if in_degrees else 0),
        "max_out_degree":   float(max(out_degrees) if out_degrees else 0),
        "avg_clustering":   avg_clustering,
        "n_layers":         float(n_layers),
        "total_amount":     total_amount,
        "max_amount":       max_amount,
        "avg_amount":       avg_amount,
        "amount_std":       amount_std,
        "time_span_hours":  time_span_hours,
        "n_banks":          float(len(banks)),
        "n_currencies":     float(len(currencies)),
        "edge_node_ratio":  m / n,
        "amount_gini":      amount_gini,
        "max_betweenness":  max_betweenness,
        "avg_betweenness":  avg_betweenness,
        "hub_betweenness":  hub_betweenness,
        "in_degree_std":    in_degree_std,
        "out_degree_std":   out_degree_std,
    }


def train_or_load(G_suspicious: nx.DiGraph, G_full: nx.DiGraph) -> tuple:
    """Returns (model, metrics_dict). Loads from disk if available, otherwise trains."""
    if MODEL_PATH.exists():
        logger.info("Loading ML fraud classifier from disk...")
        try:
            with open(MODEL_PATH, "rb") as f:
                saved = pickle.load(f)
            model = saved["model"]
            # Retrain if feature count changed
            if hasattr(model, "n_features_in_") and model.n_features_in_ != len(FEATURE_COLS):
                logger.warning(
                    f"Saved model has {model.n_features_in_} features, "
                    f"expected {len(FEATURE_COLS)}. Retraining..."
                )
                raise ValueError("feature mismatch")
            logger.info(f"  Model loaded — F1: {saved['metrics']['f1']}")
            return model, saved["metrics"]
        except Exception as e:
            logger.warning(f"Could not load model ({e}), retraining...")

    return _train(G_suspicious, G_full)


def _train(G_suspicious: nx.DiGraph, G_full: nx.DiGraph) -> tuple:
    logger.info("Training Random Forest fraud classifier...")

    susp_nodes = set(G_suspicious.nodes())

    # Positive examples: suspicious components (≥3 nodes)
    pos_comps = [c for c in nx.weakly_connected_components(G_suspicious) if len(c) >= 3]

    # Negative examples: clean components with zero overlap with suspicious nodes
    neg_comps = [
        c for c in nx.weakly_connected_components(G_full)
        if len(c) >= 3 and len(c & susp_nodes) == 0
    ]

    logger.info(f"  Positives: {len(pos_comps)} | Negatives (available): {len(neg_comps)}")

    # Sample negatives up to 3× positives to keep classes manageable
    random.seed(42)
    neg_sample = random.sample(neg_comps, min(len(neg_comps), len(pos_comps) * 3))

    rows, labels = [], []
    for comp in pos_comps:
        rows.append(extract_features(G_suspicious.subgraph(comp).copy()))
        labels.append(1)
    for comp in neg_sample:
        rows.append(extract_features(G_full.subgraph(comp).copy()))
        labels.append(0)

    X = pd.DataFrame(rows)[FEATURE_COLS].values
    y = np.array(labels)

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y,
    )

    # Phase 8: feature noise injection — prevents reliance on generator-specific exact values
    rng = np.random.default_rng(42)
    noise = rng.normal(0, 0.02 * np.std(X_train, axis=0), X_train.shape)
    X_train_aug = X_train + noise

    # Phase 2 winner: XGBoost outperforms RF on HI-Small (F1 0.861 vs 0.833)
    # Falls back to RandomForest if XGBoost not installed
    if _HAS_XGB:
        model = XGBClassifier(
            n_estimators=200, max_depth=6, learning_rate=0.1, subsample=1.0,
            eval_metric="logloss", random_state=42, n_jobs=-1, verbosity=0,
        )
        logger.info("  Using XGBoost classifier.")
    else:
        model = RandomForestClassifier(
            n_estimators=200, max_depth=10, class_weight="balanced",
            random_state=42, n_jobs=-1,
        )
        logger.info("  XGBoost not available, using RandomForest.")
    model.fit(X_train_aug, y_train)

    y_pred  = model.predict(X_test)
    report  = classification_report(y_test, y_pred, output_dict=True)
    # Phase 4: calibrate decision threshold to real-world illicit rate (~1/10000)
    threshold = _calibrate_threshold(model, X_test, y_test)

    metrics = {
        "f1":                round(f1_score(y_test, y_pred), 4),
        "precision":         round(report["1"]["precision"], 4),
        "recall":            round(report["1"]["recall"], 4),
        "accuracy":          round(report["accuracy"], 4),
        "n_train":           int(len(X_train)),
        "n_test":            int(len(X_test)),
        "n_features":        len(FEATURE_COLS),
        "decision_threshold": round(threshold, 4),
        "feature_importances": {
            col: round(float(imp), 4)
            for col, imp in zip(FEATURE_COLS, model.feature_importances_)
        },
    }

    logger.info(
        f"  F1: {metrics['f1']} | Precision: {metrics['precision']} "
        f"| Recall: {metrics['recall']} | Threshold: {threshold:.4f}"
    )

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(MODEL_PATH, "wb") as f:
        pickle.dump({"model": model, "metrics": metrics}, f)
    logger.info(f"  Model saved -> {MODEL_PATH}")

    return model, metrics


def _calibrate_threshold(model, X_test: np.ndarray, y_test: np.ndarray,
                          target_illicit_rate: float = 0.0001) -> float:
    """
    Find the score threshold matching the expected real-world illicit base rate.
    IBM HI ratio is ~1/900; real banks are ~1/10,000 — using the model at 0.5 fires too aggressively.
    """
    probs = model.predict_proba(X_test)[:, 1]
    n = len(probs)
    target_count = max(1, int(n * target_illicit_rate))
    sorted_desc = np.sort(probs)[::-1]
    threshold = float(sorted_desc[min(target_count, n - 1)])
    logger.info(f"  Calibrated threshold: {threshold:.4f} (targets {target_count}/{n} positives)")
    return threshold


def score_subgraph(sub: nx.DiGraph, model) -> float:
    """Returns fraud probability [0.0, 1.0] for a subgraph."""
    feats = extract_features(sub)
    X     = pd.DataFrame([feats])[FEATURE_COLS].values
    prob  = model.predict_proba(X)[0][1]
    return round(float(prob), 4)

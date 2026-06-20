"""
ML-based AML pattern classifier.

Trains a multiclass GBT classifier on IBM HI Patterns.txt files to replace
the rigid rule-based _classify() in detector.py with a data-driven model that
handles approximate / near-miss patterns.

Standalone training:
    python backend/pattern_classifier.py

Programmatic use in detector.py:
    from pattern_classifier import load_pattern_classifier, classify_subgraph_ml
"""

import logging
import pickle
import sys
import warnings
import numpy as np
import pandas as pd
import networkx as nx

warnings.filterwarnings("ignore")

from pathlib import Path
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.preprocessing import LabelEncoder
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report

logger     = logging.getLogger("uvicorn.error")
DATA_DIR   = Path(__file__).parent.parent / "data"
MODEL_PATH = DATA_DIR / "pattern_classifier.pkl"

# Map from pattern file header strings → canonical pattern names used in detector.py
PATTERN_MAP: dict[str, str] = {
    "FAN-OUT":        "FAN_OUT",
    "FAN_OUT":        "FAN_OUT",
    "FAN-IN":         "FAN_IN",
    "FAN_IN":         "FAN_IN",
    "CYCLE":          "CYCLE",
    "SCATTER-GATHER": "SCATTER_GATHER",
    "SCATTER_GATHER": "SCATTER_GATHER",
    "GATHER-SCATTER": "GATHER_SCATTER",
    "GATHER_SCATTER": "GATHER_SCATTER",
    "BIPARTITE":      "BIPARTITE",
    "STACK":          "STACK",
    "RANDOM":         "RANDOM",
}

# Default pattern files to train on (HI datasets only — cleaner labels)
DEFAULT_PATTERN_FILES = [
    DATA_DIR / "IBM" / "HI-Small_Patterns.txt",
    DATA_DIR / "IBM" / "HI-Medium_Patterns.txt",
]


# ── Feature extraction (mirrors ml_model.py) ─────────────────────────────────

def _gini(amounts: list) -> float:
    if not amounts or sum(amounts) == 0:
        return 0.0
    arr = sorted(amounts)
    n   = len(arr)
    return (2 * sum((i + 1) * v for i, v in enumerate(arr))) / (n * sum(arr)) - (n + 1) / n


FEATURE_COLS = [
    "n_nodes", "n_edges", "density", "has_cycle",
    "max_in_degree", "max_out_degree", "avg_clustering", "n_layers",
    "total_amount", "max_amount", "avg_amount", "amount_std",
    "time_span_hours", "n_banks", "n_currencies", "edge_node_ratio",
    "amount_gini", "max_betweenness", "avg_betweenness", "hub_betweenness",
    "in_degree_std", "out_degree_std",
]


def _extract_features(sub: nx.DiGraph) -> dict:
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

    timestamps = [d.get("timestamp") for _, _, d in sub.edges(data=True) if d.get("timestamp") is not None]
    time_span_hours = 0.0
    if len(timestamps) >= 2:
        time_span_hours = (max(timestamps) - min(timestamps)).total_seconds() / 3600.0

    banks, currencies = set(), set()
    for _, _, d in sub.edges(data=True):
        if d.get("from_bank"):          banks.add(d["from_bank"])
        if d.get("to_bank"):            banks.add(d["to_bank"])
        if d.get("receiving_currency"): currencies.add(d["receiving_currency"])

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
        "in_degree_std":    float(np.std(in_degrees))  if in_degrees  else 0.0,
        "out_degree_std":   float(np.std(out_degrees)) if out_degrees else 0.0,
    }


# ── Pattern file parsing ──────────────────────────────────────────────────────

def _parse_pattern_key(header_line: str) -> str:
    """Extract canonical pattern name from 'BEGIN LAUNDERING ATTEMPT - FAN-OUT: ...'"""
    rest = header_line[len("BEGIN LAUNDERING ATTEMPT - "):]
    key  = rest.split(":")[0].strip()
    return PATTERN_MAP.get(key, "RANDOM")


def _rows_to_graph(rows: list[str]) -> nx.DiGraph:
    """Build a DiGraph from raw CSV-like rows (no header) in IBM column order."""
    G = nx.DiGraph()
    for row in rows:
        parts = row.strip().split(",")
        if len(parts) < 11:
            continue
        try:
            ts         = pd.to_datetime(parts[0].strip(), format="%Y/%m/%d %H:%M")
            from_bank  = parts[1].strip()
            from_acct  = parts[2].strip()
            to_bank    = parts[3].strip()
            to_acct    = parts[4].strip()
            amount_paid = float(parts[7].strip())
            recv_ccy   = parts[6].strip()
            pay_fmt    = parts[9].strip()
            G.add_edge(from_acct, to_acct,
                amount_paid=amount_paid, timestamp=ts,
                from_bank=from_bank, to_bank=to_bank,
                payment_format=pay_fmt, receiving_currency=recv_ccy,
            )
        except (ValueError, IndexError):
            continue
    return G


def parse_patterns_file(path: Path) -> list[tuple[str, nx.DiGraph]]:
    """Parse one HI-*_Patterns.txt → list of (pattern_name, subgraph)."""
    entries: list[tuple[str, nx.DiGraph]] = []
    current_pattern: str | None = None
    current_rows: list[str] = []

    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("BEGIN LAUNDERING ATTEMPT - "):
            if current_pattern and current_rows:
                G = _rows_to_graph(current_rows)
                if G.number_of_nodes() >= 3:
                    entries.append((current_pattern, G))
            current_pattern = _parse_pattern_key(line)
            current_rows = []
        elif "," in line and current_pattern:
            current_rows.append(line)

    if current_pattern and current_rows:
        G = _rows_to_graph(current_rows)
        if G.number_of_nodes() >= 3:
            entries.append((current_pattern, G))

    return entries


# ── Training ──────────────────────────────────────────────────────────────────

def train_pattern_classifier(pattern_files: list[Path] | None = None) -> tuple:
    """
    Train a multiclass GBT pattern classifier on IBM Patterns.txt files.
    Returns (model, label_encoder, metrics).
    """
    if pattern_files is None:
        pattern_files = [p for p in DEFAULT_PATTERN_FILES if p.exists()]

    if not pattern_files:
        raise FileNotFoundError(
            "No pattern files found. Expected HI-Small_Patterns.txt or HI-Medium_Patterns.txt in data/IBM/"
        )

    rows, labels = [], []
    for pf in pattern_files:
        print(f"  Parsing {pf.name}...")
        for pattern_name, sub in parse_patterns_file(pf):
            rows.append(_extract_features(sub))
            labels.append(pattern_name)

    print(f"  Total patterns: {len(rows)}")
    if len(rows) < 20:
        raise ValueError(f"Too few patterns ({len(rows)}) to train a classifier.")

    label_counts = {}
    for l in labels:
        label_counts[l] = label_counts.get(l, 0) + 1
    print(f"  Distribution: {label_counts}")

    le = LabelEncoder()
    y  = le.fit_transform(labels)
    X  = pd.DataFrame(rows)[FEATURE_COLS].values

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y,
    )

    model = GradientBoostingClassifier(
        n_estimators=200, max_depth=4, learning_rate=0.1, random_state=42,
    )
    model.fit(X_train, y_train)

    y_pred  = model.predict(X_test)
    report  = classification_report(y_test, y_pred, target_names=le.classes_, output_dict=True)
    accuracy = report["accuracy"]
    f1_macro = report["macro avg"]["f1-score"]

    metrics = {
        "accuracy":  round(float(accuracy), 4),
        "f1_macro":  round(float(f1_macro), 4),
        "n_train":   int(len(X_train)),
        "n_test":    int(len(X_test)),
        "classes":   list(le.classes_),
        "per_class_f1": {
            cls: round(report[cls]["f1-score"], 4)
            for cls in le.classes_
            if cls in report
        },
    }

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(MODEL_PATH, "wb") as f:
        pickle.dump({"model": model, "encoder": le, "metrics": metrics}, f)
    print(f"  Saved -> {MODEL_PATH}")
    print(f"  Accuracy: {accuracy:.4f} | Macro F1: {f1_macro:.4f}")

    return model, le, metrics


# ── Inference ─────────────────────────────────────────────────────────────────

def load_pattern_classifier():
    """Load saved model. Returns (model, encoder) or None if not trained yet."""
    if not MODEL_PATH.exists():
        return None
    try:
        with open(MODEL_PATH, "rb") as f:
            saved = pickle.load(f)
        return saved["model"], saved["encoder"]
    except Exception as e:
        logger.warning(f"Could not load pattern classifier ({e})")
        return None


def classify_subgraph_ml(sub: nx.DiGraph, model_encoder) -> tuple[str, float]:
    """
    Classify a subgraph using the ML pattern classifier.
    Returns (pattern_name, confidence_prob).
    """
    model, le = model_encoder
    feats = _extract_features(sub)
    X     = pd.DataFrame([feats])[FEATURE_COLS].values
    probs = model.predict_proba(X)[0]
    best  = int(np.argmax(probs))
    return le.classes_[best], float(probs[best])


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    print("Training AML pattern classifier...")
    try:
        _, _, metrics = train_pattern_classifier()
        print("\nPer-class F1:")
        for cls, f1 in metrics["per_class_f1"].items():
            print(f"  {cls:<20} {f1:.4f}")
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

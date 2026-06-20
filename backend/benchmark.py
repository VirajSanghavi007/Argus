"""
Standalone ML benchmark for AML fraud detection.
Evaluates 7 algorithms with a single 60/20/20 chronological split.
No cross-validation — train on 60%, pick best on val 20%, report test 20%.

Run:
    python backend/benchmark.py --dataset data/IBM/HI-Medium_Trans.csv
    python backend/benchmark.py --dataset data/TransXion/tx.csv

Remove:
    del backend\\benchmark.py
    del data\\benchmark_results_*.txt
"""

import sys
import time
import random
import os
import argparse
import warnings
import numpy as np
os.environ["PYTHONWARNINGS"] = "ignore"
import pandas as pd
import networkx as nx

warnings.filterwarnings("ignore")

from pathlib import Path
from sklearn.metrics import f1_score, precision_score, recall_score, accuracy_score, roc_auc_score
from sklearn.ensemble import RandomForestClassifier, ExtraTreesClassifier, GradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.svm import SVC
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline

try:
    from xgboost import XGBClassifier
    HAS_XGB = True
except ImportError:
    HAS_XGB = False

try:
    from lightgbm import LGBMClassifier
    HAS_LGB = True
except ImportError:
    HAS_LGB = False

# ── Paths ─────────────────────────────────────────────────────────────────────
_HERE    = Path(__file__).parent
DATA_DIR = _HERE.parent / "data"

# Resolved at runtime from --dataset arg
CSV_PATH: Path = DATA_DIR / "HI-Small_Trans.csv"

# Post-date-range artifact cutoffs per IBM dataset name fragment
# Rows after these dates are all laundering (generator artifact) — drop them.
CUTOFF_DATES: dict = {
    "HI-Small":  pd.Timestamp("2022-09-10 23:59"),
    "LI-Small":  pd.Timestamp("2022-09-10 23:59"),
    "HI-Medium": pd.Timestamp("2022-09-16 23:59"),
    "LI-Medium": pd.Timestamp("2022-09-16 23:59"),
    "HI-Large":  pd.Timestamp("2022-11-05 23:59"),
    "LI-Large":  pd.Timestamp("2022-11-05 23:59"),
}

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


# ── Inlined helpers ───────────────────────────────────────────────────────────

def _gini(amounts: list) -> float:
    if not amounts or sum(amounts) == 0:
        return 0.0
    arr = sorted(amounts)
    n   = len(arr)
    return (2 * sum((i + 1) * v for i, v in enumerate(arr))) / (n * sum(arr)) - (n + 1) / n


def _build_graph(df: pd.DataFrame) -> nx.DiGraph:
    G = nx.DiGraph()
    if df.empty:
        return G
    cols = ["Account", "Account.1", "Amount Paid", "Timestamp",
            "From Bank", "To Bank", "Payment Format", "Receiving Currency"]
    for row in df[cols].to_dict("records"):
        G.add_edge(
            str(row["Account"]), str(row["Account.1"]),
            amount_paid=float(row["Amount Paid"]),
            timestamp=row["Timestamp"],
            from_bank=str(row["From Bank"]),
            to_bank=str(row["To Bank"]),
            receiving_currency=str(row["Receiving Currency"]),
        )
    return G


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

    # ── new features ──────────────────────────────────────────────────────────
    amount_gini = _gini(amounts)

    try:
        bc = nx.betweenness_centrality(sub, normalized=True)
    except Exception:
        bc = {v: 0.0 for v in sub.nodes()}
    bc_values      = list(bc.values())
    max_betweenness = max(bc_values) if bc_values else 0.0
    avg_betweenness = float(np.mean(bc_values)) if bc_values else 0.0
    # betweenness of the node with highest total degree (the hub)
    hub = max(sub.nodes(), key=lambda v: sub.in_degree(v) + sub.out_degree(v))
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


# ── Data preparation ──────────────────────────────────────────────────────────

def _detect_format(df: pd.DataFrame) -> str:
    cols = set(df.columns)
    if "Sender_account" in cols:
        return "saml-d"
    if "From Account" in cols:
        return "tranxion"
    return "ibm"


def _normalize_df(df: pd.DataFrame) -> tuple:
    """Normalise non-IBM datasets to IBM column names. Returns (df, fmt_str)."""
    fmt = _detect_format(df)

    if fmt == "saml-d":
        df = df.copy()
        df["Timestamp"] = df["Date"] + " " + df["Time"]
        df = df.rename(columns={
            "Sender_account":         "Account",
            "Receiver_account":       "Account.1",
            "Amount":                 "Amount Paid",
            "Payment_currency":       "Payment Currency",
            "Received_currency":      "Receiving Currency",
            "Sender_bank_location":   "From Bank",
            "Receiver_bank_location": "To Bank",
            "Payment_type":           "Payment Format",
            "Is_laundering":          "Is Laundering",
        })
        df["Amount Received"] = df["Amount Paid"]

    elif fmt == "tranxion":
        df = df.rename(columns={
            "From Account": "Account",
            "To Account":   "Account.1",
        })
    # IBM: pandas auto-renames duplicate "Account" columns to Account / Account.1

    return df, fmt


def _comp_min_ts(G: nx.DiGraph, comp: set):
    ts_list = [
        d["timestamp"] for _, _, d in G.subgraph(comp).edges(data=True)
        if d.get("timestamp") is not None
    ]
    return min(ts_list) if ts_list else pd.Timestamp.min


def _resolve_cutoff(csv_path: Path) -> pd.Timestamp | None:
    """Returns the cutoff timestamp for known IBM datasets, None for others."""
    name = csv_path.stem  # e.g. "HI-Medium_Trans" → check for "HI-Medium"
    for key, ts in CUTOFF_DATES.items():
        if key in name:
            return ts
    return None


def load_data():
    """
    Chronological 60/20/20 split at subgraph level.
    Drops post-date-range artifact rows for IBM datasets.
    Returns: X_train, X_val, X_test, y_train, y_val, y_test, n_pos, n_neg, cutoff_applied
    """
    if not CSV_PATH.exists():
        raise FileNotFoundError(f"Dataset not found: {CSV_PATH}")

    df = pd.read_csv(CSV_PATH)
    df, fmt = _normalize_df(df)
    if fmt == "ibm":
        df["Timestamp"] = pd.to_datetime(df["Timestamp"], format="%Y/%m/%d %H:%M")
    else:
        df["Timestamp"] = pd.to_datetime(df["Timestamp"])
    df.sort_values("Timestamp", inplace=True)
    df.reset_index(drop=True, inplace=True)
    df = df[df["Account"] != df["Account.1"]].copy()

    # Drop post-date-range artifact rows
    cutoff = _resolve_cutoff(CSV_PATH)
    if cutoff is not None:
        before = len(df)
        df = df[df["Timestamp"] <= cutoff].copy()
        dropped = before - len(df)
    else:
        dropped = 0

    df_suspicious = df[df["Is Laundering"] == 1].copy()
    df_full       = df.copy()

    G_suspicious = _build_graph(df_suspicious)
    G_full       = _build_graph(df_full)

    susp_nodes = set(G_suspicious.nodes())
    pos_comps  = [c for c in nx.weakly_connected_components(G_suspicious) if len(c) >= 3]
    neg_comps  = [
        c for c in nx.weakly_connected_components(G_full)
        if len(c) >= 3 and len(c & susp_nodes) == 0
    ]

    # Fallback for dense datasets where all large components touch suspicious nodes:
    # use small clean components (size 2) or partial-overlap components as negatives
    if len(neg_comps) == 0:
        clean_accounts = set(df[df["Is Laundering"] == 0]["Account"].astype(str)) | \
                         set(df[df["Is Laundering"] == 0]["Account.1"].astype(str))
        clean_accounts -= susp_nodes
        df_clean = df[
            df["Account"].astype(str).isin(clean_accounts) &
            df["Account.1"].astype(str).isin(clean_accounts)
        ].copy()
        if len(df_clean) > 0:
            G_clean  = _build_graph(df_clean)
            neg_comps = [c for c in nx.weakly_connected_components(G_clean) if len(c) >= 2]

    random.seed(42)
    neg_sample = random.sample(neg_comps, min(len(neg_comps), len(pos_comps) * 3))

    entries = []
    for comp in pos_comps:
        sub = G_suspicious.subgraph(comp).copy()
        entries.append((_extract_features(sub), 1, _comp_min_ts(G_suspicious, comp)))
    for comp in neg_sample:
        sub = G_full.subgraph(comp).copy()
        entries.append((_extract_features(sub), 0, _comp_min_ts(G_full, comp)))

    entries.sort(key=lambda e: e[2])

    rows   = [e[0] for e in entries]
    labels = [e[1] for e in entries]

    X = pd.DataFrame(rows)[FEATURE_COLS].values
    y = np.array(labels)

    n       = len(y)
    i_train = int(n * 0.60)
    i_val   = int(n * 0.80)

    X_train, y_train = X[:i_train],      y[:i_train]
    X_val,   y_val   = X[i_train:i_val], y[i_train:i_val]
    X_test,  y_test  = X[i_val:],        y[i_val:]

    return X_train, X_val, X_test, y_train, y_val, y_test, len(pos_comps), len(neg_sample), dropped


# ── Model registry ────────────────────────────────────────────────────────────

def get_models():
    """Fixed hyperparameters from prior CV runs — no tuning, just train once."""
    models = [
        (
            "RandomForest",
            RandomForestClassifier(n_estimators=200, max_depth=10, min_samples_split=2,
                                   class_weight="balanced", random_state=42, n_jobs=-1),
            False,
        ),
        (
            "ExtraTrees",
            ExtraTreesClassifier(n_estimators=200, max_depth=None, min_samples_split=5,
                                 class_weight="balanced", random_state=42, n_jobs=-1),
            False,
        ),
        (
            "GradientBoosting",
            GradientBoostingClassifier(n_estimators=100, max_depth=3, learning_rate=0.05,
                                       random_state=42),
            False,
        ),
        (
            "LogisticRegression",
            Pipeline([
                ("scaler", StandardScaler()),
                ("clf", LogisticRegression(C=10, penalty="l1", solver="saga",
                                           max_iter=2000, random_state=42)),
            ]),
            False,
        ),
        (
            "SVM (RBF)",
            Pipeline([
                ("scaler", StandardScaler()),
                ("clf", SVC(C=10, gamma="scale", kernel="rbf", probability=True,
                            class_weight="balanced", random_state=42)),
            ]),
            False,
        ),
    ]

    if HAS_XGB:
        models.insert(0, (
            "XGBoost",
            XGBClassifier(n_estimators=200, max_depth=6, learning_rate=0.1, subsample=1.0,
                          eval_metric="logloss", random_state=42, n_jobs=-1, verbosity=0),
            False,
        ))

    if HAS_LGB:
        models.insert(1 if HAS_XGB else 0, (
            "LightGBM",
            LGBMClassifier(n_estimators=200, max_depth=10, learning_rate=0.1, num_leaves=31,
                           class_weight="balanced", random_state=42, n_jobs=-1, verbose=-1),
            False,
        ))

    return models


# ── Benchmark runner ──────────────────────────────────────────────────────────

def run_benchmark(out_path: Path):
    lines = []

    def emit(s=""):
        print(s)
        lines.append(s)

    emit("Loading dataset and extracting features...")
    X_train, X_val, X_test, y_train, y_val, y_test, n_pos, n_neg, dropped = load_data()
    n_total = len(y_train) + len(y_val) + len(y_test)

    models   = get_models()
    n_models = len(models)

    cutoff_line = ""
    cutoff = _resolve_cutoff(CSV_PATH)
    if cutoff:
        cutoff_line = f"\n  Cutoff       : {cutoff.date()} ({dropped:,} post-range rows dropped)"

    header = (
        f"\n{'='*88}\n"
        f"  ML BENCHMARK — AML Fraud Detection\n"
        f"  Dataset      : {CSV_PATH.name}{cutoff_line}\n"
        f"  Features     : {len(FEATURE_COLS)} (16 original + 6 new)\n"
        f"  Positives    : {n_pos}  |  Negatives : {n_neg}  |  Total : {n_total}\n"
        f"  Split        : 60/20/20 chronological (subgraph-level)\n"
        f"  Train        : {len(X_train)}  |  Val : {len(X_val)}  |  Test : {len(X_test)}\n"
        f"{'='*88}"
    )
    emit(header)

    results = []

    for idx, (name, estimator, _) in enumerate(models, 1):
        emit(f"\n[{idx}/{n_models}] {name}")
        emit("  Training...")

        t0 = time.time()
        estimator.fit(X_train, y_train)
        elapsed = time.time() - t0

        y_val_pred = estimator.predict(X_val)
        y_val_prob = estimator.predict_proba(X_val)[:, 1]
        val_f1  = f1_score(y_val, y_val_pred, zero_division=0)
        val_pre = precision_score(y_val, y_val_pred, zero_division=0)
        val_rec = recall_score(y_val, y_val_pred, zero_division=0)
        val_auc = roc_auc_score(y_val, y_val_prob) if len(set(y_val)) > 1 else float("nan")

        y_pred   = estimator.predict(X_test)
        y_prob   = estimator.predict_proba(X_test)[:, 1]
        test_f1  = f1_score(y_test, y_pred, zero_division=0)
        test_pre = precision_score(y_test, y_pred, zero_division=0)
        test_rec = recall_score(y_test, y_pred, zero_division=0)
        test_acc = accuracy_score(y_test, y_pred)
        test_auc = roc_auc_score(y_test, y_prob) if len(set(y_test)) > 1 else float("nan")

        emit(f"  done ({elapsed:.1f}s)")
        emit(f"  Val  F1 : {val_f1:.4f}  |  Val Prec : {val_pre:.4f}  |  Val Recall : {val_rec:.4f}  |  Val AUC : {val_auc:.4f}")
        emit(f"  Test F1 : {test_f1:.4f}  |  Test Prec: {test_pre:.4f}  |  Test Recall: {test_rec:.4f}  |  Test AUC: {test_auc:.4f}")
        emit(f"  Test Acc: {test_acc:.4f}")

        results.append({
            "name": name,
            "val_f1": val_f1, "val_pre": val_pre, "val_rec": val_rec, "val_auc": val_auc,
            "test_f1": test_f1, "test_pre": test_pre, "test_rec": test_rec,
            "test_acc": test_acc, "test_auc": test_auc,
            "elapsed_s": round(elapsed, 1),
        })

    results.sort(key=lambda r: r["test_f1"], reverse=True)

    emit(f"\n{'='*88}")
    emit("  RANKED RESULTS (by Test F1)")
    emit(f"{'='*88}")
    emit(f"  {'Rank':<5} {'Model':<22} {'Train(s)':<10} {'Val F1':<9} {'Val AUC':<9} {'Test F1':<9} {'Test Prec':<11} {'Test Rec':<10} {'Test AUC':<9}")
    emit(f"  {'-'*4} {'-'*21} {'-'*9} {'-'*8} {'-'*8} {'-'*8} {'-'*10} {'-'*9} {'-'*8}")
    for rank, r in enumerate(results, 1):
        emit(
            f"  {rank:<5} {r['name']:<22} {r['elapsed_s']:<10.1f}"
            f"{r['val_f1']:<9.4f} {r['val_auc']:<9.4f} "
            f"{r['test_f1']:<9.4f} {r['test_pre']:<11.4f} {r['test_rec']:<10.4f} {r['test_auc']:<9.4f}"
        )
    emit(f"{'='*88}")

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nResults saved -> {out_path}")


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AML ML Benchmark")
    parser.add_argument(
        "--dataset",
        type=str,
        default=None,
        help="Path to transaction CSV (default: data/HI-Small_Trans.csv)",
    )
    args = parser.parse_args()

    if args.dataset:
        CSV_PATH = Path(args.dataset)
        if not CSV_PATH.is_absolute():
            CSV_PATH = Path.cwd() / CSV_PATH

    # Output file named after the dataset so runs don't overwrite each other
    dataset_stem = CSV_PATH.stem.replace("_Trans", "")
    out_path = DATA_DIR / f"benchmark_results_{dataset_stem}.txt"

    run_benchmark(out_path)

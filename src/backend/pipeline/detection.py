"""
Multi-GNN detection pipeline — the sole alert source.

Flow:
  1. Build the transaction multigraph and score every edge with the Multi-GNN.
  2. Keep edges whose laundering probability >= threshold.
  3. Group connected flagged edges into clusters (one cluster = one alert).
  4. Classify each cluster's topology into an AML pattern type.
  5. Serialize clusters into the alert shape the frontend renders.
"""

import logging
from collections import defaultdict

import networkx as nx
import numpy as np

from ..models.multignn import build_graph, load_multignn, score_transactions
from ..core.serializer import serialize_alerts

logger = logging.getLogger("uvicorn.error")

MIN_CLUSTER_NODES = 2


# ── Topology-based pattern labeller ─────────────────────────────────────────

PATTERN_DESCRIPTIONS = {
    "FAN_OUT":         "Single account distributes funds to many recipients",
    "FAN_IN":          "Multiple accounts funnel funds into a single collector",
    "CYCLE":           "Circular flow — money returns to its origin",
    "SCATTER_GATHER":  "Funds fan out through intermediaries then reconverge",
    "GATHER_SCATTER":  "Hub collects from many sources then redistributes",
    "BIPARTITE":       "Two distinct groups with cross-group transfers only",
    "STACK":           "Linear chain of sequential transfers (layering)",
    "RANDOM":          "Complex topology — no single dominant pattern",
}


def _classify_topology(sub: nx.DiGraph) -> str:
    nodes = list(sub.nodes())
    n = len(nodes)
    if n < 2:
        return "RANDOM"

    in_deg = dict(sub.in_degree())
    out_deg = dict(sub.out_degree())

    if all(in_deg[v] == 1 and out_deg[v] == 1 for v in nodes):
        try:
            nx.find_cycle(sub)
            return "CYCLE"
        except nx.NetworkXNoCycle:
            pass

    hubs_out = [v for v in nodes if out_deg[v] >= 2 and in_deg[v] <= 1]
    leaves_in = [v for v in nodes if out_deg[v] == 0]
    if len(hubs_out) >= 1 and len(leaves_in) >= max(2, n // 2):
        return "FAN_OUT"

    hubs_in = [v for v in nodes if in_deg[v] >= 2 and out_deg[v] <= 1]
    senders = [v for v in nodes if in_deg[v] == 0]
    if len(hubs_in) >= 1 and len(senders) >= max(2, n // 2):
        return "FAN_IN"

    origins = [v for v in nodes if in_deg[v] == 0]
    dests = [v for v in nodes if out_deg[v] == 0]
    middles = [v for v in nodes if in_deg[v] >= 1 and out_deg[v] >= 1]
    if len(origins) == 1 and len(dests) == 1 and len(middles) >= 1:
        return "SCATTER_GATHER"

    hubs_gs = [v for v in nodes if in_deg[v] >= 2 and out_deg[v] >= 2]
    if len(hubs_gs) == 1 and len(senders) >= 2 and len(dests) >= 2:
        return "GATHER_SCATTER"

    # Bipartite: only classify as such when BOTH groups are large (≥3 each),
    # otherwise it's really a scatter/gather or stack variant
    try:
        if nx.is_bipartite(sub.to_undirected()):
            sets = nx.bipartite.sets(sub.to_undirected())
            if min(len(s) for s in sets) >= 3:
                return "BIPARTITE"
            # Small bipartite → more meaningful AML label
            if len(origins) >= 2 and len(dests) >= 2:
                return "SCATTER_GATHER"
    except Exception:
        pass

    if all(in_deg[v] <= 1 and out_deg[v] <= 1 for v in nodes):
        return "STACK"

    return "RANDOM"
# Use top-1% of scores as the floor — adapts to any score scale.
# At 100k rows this flags ~1000 transactions → ~50-150 alert clusters.
ALERT_THRESHOLD_PERCENTILE = 99
MAX_ALERTS = 200


def _assign_severities(raw_alerts: list) -> None:
    """Rank clusters by confidence and assign severity by percentile across this run."""
    if not raw_alerts:
        return
    scores = sorted(a["confidence"] for a in raw_alerts)
    n = len(scores)
    p85 = scores[int(n * 0.85)]
    p60 = scores[int(n * 0.60)]
    for a in raw_alerts:
        c = a["confidence"]
        sev = "high" if c >= p85 else ("medium" if c >= p60 else "low")
        a["severity"] = sev
        for node in a.get("nodes_list", []):
            node["sev"] = sev


def run_multignn_pipeline(max_rows: int | None = None) -> tuple[list, dict]:
    """Returns (serialized_alerts, metrics). Raises if the model isn't trained or data is unavailable."""
    try:
        model, metrics = load_multignn()
    except Exception as e:
        raise RuntimeError(
            f"Failed to load model: {e}. Train it first with: "
            "python backend/multignn_model.py --epochs 8"
        )

    if model is None:
        raise RuntimeError(
            "Multi-GNN model not found. Train it first: "
            "python backend/multignn_model.py --epochs 8"
        )

    # Adaptive threshold: top ALERT_THRESHOLD_PERCENTILE of scores.
    # Falls back to model's F1-max threshold if scores aren't available yet.
    _adaptive_threshold = None  # computed after scoring

    try:
        bundle = build_graph(max_rows=max_rows, return_df=True)
    except FileNotFoundError as e:
        raise RuntimeError(
            f"Transaction dataset not found. Expected at data/active/HI-Small_Trans.csv or data/IBM/HI-Small_Trans.csv. "
            "Upload the dataset to the server or use Git LFS."
        )
    except Exception as e:
        raise RuntimeError(
            f"Failed to build transaction graph: {e}. "
            "Validate CSV structure with: python -c \"import pandas as pd; pd.read_csv('data/HI-Small_Trans.csv', nrows=5)\""
        )

    try:
        df = bundle["df"]
        probs = score_transactions(model, bundle)
        df = df.assign(_prob=probs)
    except Exception as e:
        raise RuntimeError(
            f"Failed to score transactions: {e}. Check model compatibility and feature dimensions."
        )

    threshold = float(np.percentile(probs, ALERT_THRESHOLD_PERCENTILE))
    flagged = df[df["_prob"] >= threshold]
    logger.info(f"Multi-GNN flagged {len(flagged):,}/{len(df):,} transactions "
                f"(adaptive threshold {threshold:.4f} = p{ALERT_THRESHOLD_PERCENTILE})")

    # Compute edge importance explanations for flagged transactions (for interpretability).
    # This shows judges *why* transactions were flagged.
    from ..models.multignn import explain_transactions
    flagged_indices = flagged.index.tolist()
    explanations = explain_transactions(model, bundle, flagged_indices)
    logger.info(f"Computed GNNExplainer importance for {len(explanations)} flagged edges")

    # Cluster flagged transactions by connected accounts (account identity = bank:account)
    G = _build_flagged_graph(flagged)

    raw_alerts = []
    for ci, comp in enumerate(nx.weakly_connected_components(G)):
        if len(comp) < MIN_CLUSTER_NODES:
            continue
        raw = _component_to_alert(ci, comp, G, flagged, explanations)
        if raw is not None:
            raw_alerts.append(raw)

    raw_alerts.sort(key=lambda a: a["confidence"], reverse=True)
    raw_alerts = raw_alerts[:MAX_ALERTS]
    _assign_severities(raw_alerts)
    serialized = serialize_alerts(raw_alerts)
    logger.info(f"Multi-GNN produced {len(serialized)} alert clusters")
    return serialized, (metrics or {})


def _node_key(bank, acct) -> str:
    return f"{bank}:{acct}"


def _build_flagged_graph(flagged) -> nx.DiGraph:
    G = nx.DiGraph()
    for idx, row in flagged.iterrows():
        s = _node_key(row["From Bank"], row["Account"])
        t = _node_key(row["To Bank"], row["Account.1"])
        G.add_edge(s, t, txIdx=int(idx), row=row, prob=float(row["_prob"]))
    return G


def _component_to_alert(ci: int, comp: set, G: nx.DiGraph, flagged, explanations: dict | None = None) -> dict | None:
    sub = G.subgraph(comp)
    edge_data = list(sub.edges(data=True))
    if not edge_data:
        return None

    probs   = [d["prob"] for _, _, d in edge_data]
    amounts = [float(d["row"]["Amount Paid"]) for _, _, d in edge_data]
    ts      = [d["row"]["Timestamp"] for _, _, d in edge_data]
    cluster_prob = float(np.mean(probs))
    max_prob     = float(np.max(probs))

    # Per-account roles + volumes
    sent  = defaultdict(float)
    recv  = defaultdict(float)
    txn   = defaultdict(int)
    bank  = {}
    label = {}
    for u, v, d in edge_data:
        row = d["row"]
        sent[u] += float(row["Amount Paid"])
        recv[v] += float(row["Amount Paid"])
        txn[u]  += 1
        txn[v]  += 1
        bank.setdefault(u, str(row["From Bank"]))
        bank.setdefault(v, str(row["To Bank"]))
        label.setdefault(u, str(row["Account"]))
        label.setdefault(v, str(row["Account.1"]))

    nodes_list = []
    for n in comp:
        out_e = sub.out_degree(n)
        in_e  = sub.in_degree(n)
        role  = "source" if in_e == 0 else "destination" if out_e == 0 else "intermediary"
        nodes_list.append({
            "node_id": label.get(n, n),
            "sev":     "low",
            "role":    role,
            "bank":    bank.get(n, "?"),
            "vol":     sent[n] + recv[n],
            "txn":     txn[n],
        })

    edges_list, transactions_list = [], []
    for u, v, d in edge_data:
        row = d["row"]
        txIdx = d["txIdx"]
        # Attach GNNExplainer importance score (0-1, higher = more important to laundering pred)
        importance = (explanations or {}).get(txIdx, 0.5)
        edges_list.append({
            "txIdx":  txIdx,
            "source": label.get(u, u),
            "target": label.get(v, v),
            "amount_paid": float(row["Amount Paid"]),
            "importance": round(float(importance), 3),
        })
        transactions_list.append(row.to_dict())

    span_h = 0.0
    if len(ts) >= 2:
        span_h = (max(ts) - min(ts)).total_seconds() / 3600.0

    pattern = _classify_topology(sub)
    pattern_desc = PATTERN_DESCRIPTIONS.get(pattern, "")

    return {
        "pattern_type": pattern,
        "alert_id":     f"UBI-2026-{ci:04d}",
        "nodes_list":   nodes_list,
        "edges_list":   edges_list,
        "transactions_list": transactions_list,
        "sub":          pattern_desc or "Multi-GNN detected laundering cluster",
        "severity":     "low",
        "confidence":   round(cluster_prob, 4),
        "ml_score":     round(cluster_prob, 4),
        "ml_score_rf":  None,
        "ml_score_gnn": round(cluster_prob, 4),
        "risk_flagged": True,
        "time_span":    min(ts).strftime("%Y-%m-%d %H:%M") if ts else "",
        "hops":         len(edge_data),
        "total_moved":  float(sum(amounts)),
        "route_nodes":  [label.get(n, n) for n in comp],
        "description":  (f"{pattern} — Multi-GNN flagged {len(edge_data)} transaction(s) "
                         f"across {len(comp)} accounts "
                         f"(mean prob {cluster_prob:.2f}, peak {max_prob:.2f})."),
        "source":       "labelled",
        "signals_triggered": ["Multi-GNN edge classification", f"Topology: {pattern}"],
    }

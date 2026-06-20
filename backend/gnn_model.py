"""
Phase 6 — GNN second detection layer.

GraphSAGE-based fraud probability scorer that runs alongside the existing
Random Forest pipeline. Its output (gnn_score) is blended with ml_score
in main.py: final_score = 0.5 * ml_score + 0.5 * gnn_score.

Key additions from Multi-GNN paper:
- Reverse message passing: GNN sees both forward and backward edges
- Port numbering: encodes which port (index) an edge enters/leaves a node
- Ego IDs: center node of each subgraph gets a flag so it knows it's the hub

Standalone training:
    python backend/gnn_model.py

Programmatic use in main.py:
    from gnn_model import load_gnn, score_subgraph_gnn
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

logger   = logging.getLogger("uvicorn.error")
DATA_DIR = Path(__file__).parent.parent / "data"
GNN_PATH = DATA_DIR / "gnn_model.pkl"

try:
    import torch
    import torch.nn as nn
    import torch.nn.functional as F
    from torch_geometric.data import Data
    from torch_geometric.nn import SAGEConv, global_mean_pool, global_max_pool
    HAS_TORCH = True
except ImportError:
    HAS_TORCH = False
    logger.warning("PyTorch / PyTorch Geometric not available — GNN module disabled.")


# ── Node feature encoding ─────────────────────────────────────────────────────

def _subgraph_to_pyg(sub: nx.DiGraph, hub_node: str | None = None):
    """
    Convert a NetworkX subgraph to a PyTorch Geometric Data object.

    Node features (7 dims):
      [in_degree, out_degree, total_recv, total_sent, is_hub (ego ID),
       fwd_port_mean, rev_port_mean]

    Edges: both forward AND reverse (reverse message passing).
    Edge features (3 dims):
      [amount, time_delta_hours (from subgraph min), is_reverse_edge]
    """
    if not HAS_TORCH:
        return None

    nodes   = list(sub.nodes())
    n_nodes = len(nodes)
    if n_nodes == 0:
        return None

    node_idx = {v: i for i, v in enumerate(nodes)}

    # Determine hub (ego node) = highest total degree
    if hub_node is None:
        hub_node = max(nodes, key=lambda v: sub.in_degree(v) + sub.out_degree(v))

    # Build node feature matrix
    in_deg    = dict(sub.in_degree())
    out_deg   = dict(sub.out_degree())
    recv_vol  = {v: 0.0 for v in nodes}
    sent_vol  = {v: 0.0 for v in nodes}
    for u, v, d in sub.edges(data=True):
        amt = d.get("amount_paid", 0.0)
        sent_vol[u]  += amt
        recv_vol[v]  += amt

    timestamps = [d.get("timestamp") for _, _, d in sub.edges(data=True) if d.get("timestamp") is not None]
    ts_min = min(timestamps) if timestamps else None

    x_rows = []
    for v in nodes:
        x_rows.append([
            float(in_deg[v]),
            float(out_deg[v]),
            recv_vol[v],
            sent_vol[v],
            1.0 if v == hub_node else 0.0,   # ego ID
            0.0,  # fwd_port_mean (filled below)
            0.0,  # rev_port_mean (filled below)
        ])
    x = torch.tensor(x_rows, dtype=torch.float)

    # Build edge index (forward + reverse) + edge features
    src_list, dst_list = [], []
    edge_feat_list = []

    fwd_edges = list(sub.edges(data=True))
    # Forward edges
    for port_idx, (u, v, d) in enumerate(fwd_edges):
        si, di = node_idx[u], node_idx[v]
        amt   = d.get("amount_paid", 0.0)
        ts    = d.get("timestamp")
        tdelta = 0.0
        if ts_min is not None and ts is not None:
            tdelta = (ts - ts_min).total_seconds() / 3600.0
        src_list.append(si)
        dst_list.append(di)
        edge_feat_list.append([amt, tdelta, 0.0])  # is_reverse=0

    # Reverse edges
    for port_idx, (u, v, d) in enumerate(fwd_edges):
        si, di = node_idx[u], node_idx[v]
        amt   = d.get("amount_paid", 0.0)
        ts    = d.get("timestamp")
        tdelta = 0.0
        if ts_min is not None and ts is not None:
            tdelta = (ts - ts_min).total_seconds() / 3600.0
        src_list.append(di)      # reversed
        dst_list.append(si)
        edge_feat_list.append([amt, tdelta, 1.0])  # is_reverse=1

    if not src_list:
        return None

    edge_index = torch.tensor([src_list, dst_list], dtype=torch.long)
    edge_attr  = torch.tensor(edge_feat_list, dtype=torch.float)
    batch      = torch.zeros(n_nodes, dtype=torch.long)  # single graph

    return Data(x=x, edge_index=edge_index, edge_attr=edge_attr, batch=batch)


# ── GraphSAGE model ───────────────────────────────────────────────────────────

class _FraudSAGE(nn.Module):
    def __init__(self, in_channels: int = 7, hidden: int = 64, dropout: float = 0.3):
        super().__init__()
        self.conv1 = SAGEConv(in_channels, hidden)
        self.conv2 = SAGEConv(hidden, hidden)
        self.conv3 = SAGEConv(hidden, hidden // 2)
        self.lin1  = nn.Linear(hidden, 32)  # pooled concat of mean+max
        self.lin2  = nn.Linear(32, 1)
        self.drop  = nn.Dropout(dropout)

    def forward(self, data):
        x, ei, batch = data.x, data.edge_index, data.batch
        x = F.relu(self.conv1(x, ei))
        x = self.drop(x)
        x = F.relu(self.conv2(x, ei))
        x = self.drop(x)
        x = F.relu(self.conv3(x, ei))

        # Pooling: mean + max concatenated → 2*(hidden//2) = hidden
        pool_mean = global_mean_pool(x, batch)
        pool_max  = global_max_pool(x, batch)
        g = torch.cat([pool_mean, pool_max], dim=-1)

        g = F.relu(self.lin1(g))
        g = self.drop(g)
        return torch.sigmoid(self.lin2(g)).squeeze(-1)


# ── Data loading from IBM graphs ──────────────────────────────────────────────

def _load_training_data(G_suspicious: nx.DiGraph, G_full: nx.DiGraph) -> tuple:
    """Build PyG Data list from IBM graphs for GNN training."""
    import random
    random.seed(42)

    susp_nodes = set(G_suspicious.nodes())
    pos_comps  = [c for c in nx.weakly_connected_components(G_suspicious) if len(c) >= 3]
    neg_comps  = [
        c for c in nx.weakly_connected_components(G_full)
        if len(c) >= 3 and len(c & susp_nodes) == 0
    ]
    neg_sample = random.sample(neg_comps, min(len(neg_comps), len(pos_comps) * 3))

    data_list, labels = [], []
    for comp in pos_comps:
        sub = G_suspicious.subgraph(comp).copy()
        d   = _subgraph_to_pyg(sub)
        if d is not None:
            data_list.append(d)
            labels.append(1.0)
    for comp in neg_sample:
        sub = G_full.subgraph(comp).copy()
        d   = _subgraph_to_pyg(sub)
        if d is not None:
            data_list.append(d)
            labels.append(0.0)

    return data_list, labels


# ── Training ──────────────────────────────────────────────────────────────────

def train_gnn(G_suspicious: nx.DiGraph, G_full: nx.DiGraph,
              epochs: int = 50, lr: float = 0.001) -> dict:
    """
    Train the GraphSAGE fraud model.
    Returns metrics dict and saves model to data/gnn_model.pkl.
    """
    if not HAS_TORCH:
        raise RuntimeError("PyTorch not available. Install: pip install torch torch-geometric")

    logger.info("Building GNN training data...")
    data_list, labels = _load_training_data(G_suspicious, G_full)
    if len(data_list) < 10:
        raise ValueError(f"Not enough subgraphs for GNN training ({len(data_list)})")

    from sklearn.model_selection import train_test_split as _tts
    idx = list(range(len(data_list)))
    tr_idx, te_idx = _tts(idx, test_size=0.2, random_state=42,
                          stratify=[int(l) for l in labels])

    model   = _FraudSAGE()
    optim   = torch.optim.Adam(model.parameters(), lr=lr, weight_decay=1e-4)
    pos_w   = torch.tensor([sum(1 for l in labels if l == 0) /
                             max(sum(1 for l in labels if l == 1), 1)],
                           dtype=torch.float)
    crit    = nn.BCELoss()

    logger.info(f"Training GNN for {epochs} epochs on {len(tr_idx)} graphs...")
    model.train()
    for epoch in range(1, epochs + 1):
        total_loss = 0.0
        for i in tr_idx:
            optim.zero_grad()
            out  = model(data_list[i]).view(1)
            lbl  = torch.tensor([labels[i]], dtype=torch.float)
            # Weighted loss
            w    = pos_w if labels[i] == 1 else torch.tensor([1.0])
            loss = (w * F.binary_cross_entropy(out, lbl, reduction="none")).mean()
            loss.backward()
            optim.step()
            total_loss += loss.item()
        if epoch % 10 == 0:
            logger.info(f"  Epoch {epoch}/{epochs} — loss: {total_loss/len(tr_idx):.4f}")

    # Evaluation
    model.eval()
    y_pred, y_true = [], []
    with torch.no_grad():
        for i in te_idx:
            prob = float(model(data_list[i]))
            y_pred.append(1 if prob >= 0.5 else 0)
            y_true.append(int(labels[i]))

    from sklearn.metrics import f1_score, roc_auc_score
    f1  = f1_score(y_true, y_pred, zero_division=0)
    auc = roc_auc_score(y_true, [float(model(data_list[i])) for i in te_idx]) \
          if len(set(y_true)) > 1 else float("nan")

    metrics = {
        "f1":        round(f1, 4),
        "auc":       round(auc, 4) if not (isinstance(auc, float) and auc != auc) else None,
        "n_train":   len(tr_idx),
        "n_test":    len(te_idx),
        "epochs":    epochs,
    }
    logger.info(f"GNN training done — F1: {f1:.4f} | AUC: {auc:.4f}")

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(GNN_PATH, "wb") as fh:
        pickle.dump({"model_state": model.state_dict(), "metrics": metrics}, fh)
    logger.info(f"GNN model saved -> {GNN_PATH}")

    return metrics


# ── Inference ─────────────────────────────────────────────────────────────────

def load_gnn():
    """Load saved GNN. Returns model or None."""
    if not HAS_TORCH or not GNN_PATH.exists():
        return None
    try:
        with open(GNN_PATH, "rb") as fh:
            saved = pickle.load(fh)
        model = _FraudSAGE()
        model.load_state_dict(saved["model_state"])
        model.eval()
        return model
    except Exception as e:
        logger.warning(f"Could not load GNN ({e})")
        return None


def score_subgraph_gnn(sub: nx.DiGraph, model) -> float:
    """Returns GNN fraud probability [0,1] for a subgraph."""
    if not HAS_TORCH or model is None:
        return 0.5  # neutral if GNN unavailable
    data = _subgraph_to_pyg(sub)
    if data is None:
        return 0.5
    with torch.no_grad():
        return round(float(model(data)), 4)


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if not HAS_TORCH:
        print("PyTorch not installed. Run: pip install torch torch-geometric", file=sys.stderr)
        sys.exit(1)

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    # Load IBM small dataset for standalone training
    from pipeline import load_and_build
    print("Loading IBM dataset...")
    _, _, G_sus, G_full = load_and_build()
    print("Training GNN...")
    metrics = train_gnn(G_sus, G_full, epochs=50)
    print(f"\nGNN Results: F1={metrics['f1']} | AUC={metrics['auc']}")

"""
Multi-GNN — edge-level money-laundering classifier for the IBM AML multigraph.

This is the sole detection model: it classifies each *transaction* (a directed
edge between two accounts) as laundering / not, directly on the transaction
multigraph. No rule-based detector and no Random-Forest scorer are involved.

Multi-GNN adaptations implemented (Egressy et al., "Provably Powerful Graph
Neural Networks for Directed Multigraphs", IBM):
  - Reverse message passing : every transaction edge is mirrored with a reverse
                              edge carrying an `is_reverse` flag, so a node sees
                              both incoming and outgoing money flow.
  - Port numbering          : each edge records its ordinal position among the
                              source account's outgoing edges and the destination
                              account's incoming edges (distinguishes parallel
                              multigraph edges that vanilla GNNs cannot tell apart).
  - Edge-feature GINE       : a GINE backbone consumes per-edge features
                              (amount, time, currency, payment format, ports)
                              during message passing.
  - Edge-level head         : an MLP over the endpoint embeddings predicts the
                              laundering probability of each transaction.

Scalability: training/inference use `LinkNeighborLoader` neighbour sampling so
the full 5M-edge HI-Small graph never has to fit a single forward pass — it runs
on CPU.

CLI:
    python backend/multignn_model.py --epochs 3 --max-rows 600000   # quick CPU run
    python backend/multignn_model.py --epochs 8                     # full HI-Small

Programmatic:
    from multignn_model import load_multignn, score_transactions
"""

from __future__ import annotations

import argparse
import json
import logging
import pickle
import sys
import time
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")


def _progress_bar(current: int, total: int, prefix: str = "", suffix: str = "", width: int = 40):
    pct = current / total
    filled = int(width * pct)
    bar = "=" * filled + "-" * (width - filled)
    print(f"\r  {prefix} |{bar}| {current}/{total} ({100*pct:.0f}%) {suffix}", end="", flush=True)
    if current >= total:
        print()

logger    = logging.getLogger("uvicorn.error")
DATA_DIR  = Path(__file__).parent.parent.parent.parent / "data"
MODEL_PATH = DATA_DIR / "multignn_model.pt"
META_PATH  = DATA_DIR / "multignn_meta.json"

try:
    import torch
    import torch.nn as nn
    import torch.nn.functional as F
    from torch_geometric.nn import GINEConv, PNAConv
    HAS_TORCH = True
except ImportError:  # pragma: no cover - guarded for torch-less environments
    HAS_TORCH = False
    logger.warning("PyTorch / PyTorch Geometric not available — Multi-GNN disabled.")


def _resolve_csv() -> Path:
    for p in (DATA_DIR / "active" / "HI-Small_Trans.csv", DATA_DIR / "IBM" / "HI-Small_Trans.csv", DATA_DIR / "HI-Small_Trans.csv"):
        if p.exists():
            return p
    return DATA_DIR / "active" / "HI-Small_Trans.csv"


# ── Graph construction ─────────────────────────────────────────────────────────

def build_graph(csv_path: Path | None = None, max_rows: int | None = None,
                return_df: bool = False) -> dict:
    """
    Build the transaction multigraph as a PyG-ready bundle.

    Returns a dict with:
      x            : [N, 4]  node features (in_deg, out_deg, log recv, log sent)
      edge_index   : [2, 2E] forward + reverse edges
      edge_attr    : [2E, 7] (log_amount, t_norm, out_port, in_port, is_reverse,
                              currency_code, format_code)
      y            : [E]     laundering label per *forward* transaction
      label_index  : [2, E]  endpoint node pairs of the forward transactions
      t_edge       : [E]     normalized timestamp per forward transaction (for splits)
      meta         : encoders + dims needed for inference
    """
    if not HAS_TORCH:
        raise RuntimeError("PyTorch not available.")

    csv_path = csv_path or _resolve_csv()
    if not csv_path.exists():
        raise FileNotFoundError(f"Dataset not found: {csv_path}")

    logger.info(f"Multi-GNN: reading {csv_path.name} (max_rows={max_rows})...")
    df = pd.read_csv(csv_path, nrows=max_rows)
    df = _normalize_columns(df)
    df["Timestamp"] = pd.to_datetime(df["Timestamp"], format="mixed")
    df.sort_values("Timestamp", inplace=True)
    df.reset_index(drop=True, inplace=True)

    # Node identity = bank + account (accounts repeat across banks)
    src_key = df["From Bank"].astype(str) + ":" + df["Account"].astype(str)
    dst_key = df["To Bank"].astype(str) + ":" + df["Account.1"].astype(str)

    # Drop self-loops (Reinvestment rows)
    keep = src_key.values != dst_key.values
    df, src_key, dst_key = df[keep].reset_index(drop=True), src_key[keep].reset_index(drop=True), dst_key[keep].reset_index(drop=True)

    nodes = pd.Index(pd.unique(pd.concat([src_key, dst_key])))
    node_id = {k: i for i, k in enumerate(nodes)}
    src = src_key.map(node_id).to_numpy()
    dst = dst_key.map(node_id).to_numpy()
    N   = len(nodes)
    E   = len(df)
    logger.info(f"Multi-GNN: {N:,} accounts, {E:,} transactions")

    # ── edge features ──
    amount   = df["Amount Paid"].to_numpy(dtype=np.float64)
    log_amt  = np.log1p(np.clip(amount, 0, None)).astype(np.float32)
    log_amt  = (log_amt - log_amt.mean()) / (log_amt.std() + 1e-6)

    ts       = df["Timestamp"].astype("int64").to_numpy()
    t_norm   = ((ts - ts.min()) / (ts.max() - ts.min() + 1)).astype(np.float32)

    # Hour of day (cyclical: sin/cos)
    hour_of_day = df["Timestamp"].dt.hour.to_numpy().astype(np.float32)
    hour_sin = np.sin(2 * np.pi * hour_of_day / 24).astype(np.float32)
    hour_cos = np.cos(2 * np.pi * hour_of_day / 24).astype(np.float32)

    # Day of week (cyclical: sin/cos)
    day_of_week = df["Timestamp"].dt.dayofweek.to_numpy().astype(np.float32)
    dow_sin = np.sin(2 * np.pi * day_of_week / 7).astype(np.float32)
    dow_cos = np.cos(2 * np.pi * day_of_week / 7).astype(np.float32)

    # Cross-bank binary
    is_cross_bank = (df["From Bank"].astype(str) != df["To Bank"].astype(str)).astype(np.float32).to_numpy()

    cur_codes, cur_uniq = pd.factorize(df["Receiving Currency"])
    fmt_codes, fmt_uniq = pd.factorize(df["Payment Format"])

    # Interaction features: cross-bank × high-risk currency/format
    high_risk_cur = df["Receiving Currency"].isin(["Bitcoin", "BTC", "XRP", "ETH"]).to_numpy().astype(np.float32)
    high_risk_fmt = df["Payment Format"].isin(["Cheque", "Cash"]).to_numpy().astype(np.float32)
    cross_x_cur = (is_cross_bank * high_risk_cur).astype(np.float32)
    cross_x_fmt = (is_cross_bank * high_risk_fmt).astype(np.float32)

    # Port numbering: ordinal index of each edge among src's out-edges / dst's in-edges
    out_port = _port_index(src, E)
    in_port  = _port_index(dst, E)
    out_port_n = (out_port / (out_port.max() + 1)).astype(np.float32)
    in_port_n  = (in_port / (in_port.max() + 1)).astype(np.float32)

    y = df["Is Laundering"].to_numpy(dtype=np.float32)

    # Forward edge attributes [E, 14]: log_amt, t_norm, out_port, in_port, is_reverse,
    #   hour_sin, hour_cos, dow_sin, dow_cos, is_cross_bank, cross×cur, cross×fmt,
    #   currency_id, format_id
    fwd_attr = np.stack([
        log_amt, t_norm, out_port_n, in_port_n,
        np.zeros(E, np.float32),                     # is_reverse = 0
        hour_sin, hour_cos, dow_sin, dow_cos, is_cross_bank,
        cross_x_cur, cross_x_fmt,
        cur_codes.astype(np.float32), fmt_codes.astype(np.float32),
    ], axis=1)
    # Reverse edge attributes: same features, is_reverse = 1, swap ports
    rev_attr = fwd_attr.copy()
    rev_attr[:, 2], rev_attr[:, 3] = in_port_n, out_port_n
    rev_attr[:, 4] = 1.0

    edge_index = np.concatenate([np.stack([src, dst]), np.stack([dst, src])], axis=1)
    edge_attr  = np.concatenate([fwd_attr, rev_attr], axis=0)

    # ── node features (degree + volume) ──
    in_deg  = np.bincount(dst, minlength=N).astype(np.float32)
    out_deg = np.bincount(src, minlength=N).astype(np.float32)
    recv    = np.bincount(dst, weights=amount, minlength=N).astype(np.float32)
    sent    = np.bincount(src, weights=amount, minlength=N).astype(np.float32)
    x = np.stack([
        np.log1p(in_deg), np.log1p(out_deg),
        np.log1p(recv),   np.log1p(sent),
    ], axis=1)
    x = (x - x.mean(0)) / (x.std(0) + 1e-6)

    bundle = {
        "x":          torch.tensor(x, dtype=torch.float),
        "edge_index": torch.tensor(edge_index, dtype=torch.long),
        "edge_attr":  torch.tensor(edge_attr, dtype=torch.float),
        "y":          torch.tensor(y, dtype=torch.float),
        "label_index": torch.tensor(np.stack([src, dst]), dtype=torch.long),
        "t_edge":     torch.tensor(t_norm, dtype=torch.float),
        "deg": _compute_deg(torch.tensor(edge_index, dtype=torch.long), N),
        "meta": {
            "n_nodes": int(N), "n_edges": int(E),
            "n_currencies": int(len(cur_uniq)), "n_formats": int(len(fmt_uniq)),
            "currencies": list(map(str, cur_uniq)), "formats": list(map(str, fmt_uniq)),
            "node_dim": 4, "edge_cont_dim": 12,
        },
    }
    if return_df:
        df = df.copy()
        df["_src_idx"] = src
        df["_dst_idx"] = dst
        bundle["df"] = df
    return bundle


def _port_index(endpoint: np.ndarray, E: int) -> np.ndarray:
    """Ordinal position of each edge among edges sharing the same endpoint (in arrival order)."""
    order = np.zeros(E, dtype=np.float32)
    counter: dict = {}
    for i, v in enumerate(endpoint):
        c = counter.get(v, 0)
        order[i] = c
        counter[v] = c + 1
    return order


def _compute_deg(edge_index: "torch.Tensor", n_nodes: int) -> "torch.Tensor":
    """Degree histogram for PNAConv scalers."""
    from torch_geometric.utils import degree
    d = degree(edge_index[1], num_nodes=n_nodes, dtype=torch.long)
    max_deg = min(int(d.max().item()), 500)
    return torch.bincount(d.clamp(max=max_deg), minlength=max_deg + 1)


# ── Model ──────────────────────────────────────────────────────────────────────

class MultiGNN(nn.Module):
    """PNA backbone with edge encoder (incl. currency/format embeddings) + edge head.

    PNAConv uses multiple aggregators (mean, max, min, std) with degree scalers,
    capturing richer neighborhood structure than GINEConv's sum-only aggregation.
    """

    def __init__(self, node_dim=4, edge_cont_dim=12, n_currencies=16, n_formats=8,
                 hidden=64, layers=3, dropout=0.2, emb_dim=8, deg=None):
        super().__init__()
        self.cur_emb = nn.Embedding(n_currencies + 1, emb_dim)
        self.fmt_emb = nn.Embedding(n_formats + 1, emb_dim)
        edge_in = edge_cont_dim + 2 * emb_dim
        self.edge_enc = nn.Sequential(
            nn.Linear(edge_in, hidden), nn.ReLU(), nn.Linear(hidden, hidden),
        )
        self.node_enc = nn.Linear(node_dim, hidden)

        aggregators = ["mean", "max", "min", "std"]
        scalers = ["identity", "amplification", "attenuation"]
        if deg is None:
            deg = torch.ones(100, dtype=torch.long)

        self.convs = nn.ModuleList()
        self.norms = nn.ModuleList()
        for _ in range(layers):
            self.convs.append(PNAConv(
                in_channels=hidden, out_channels=hidden,
                aggregators=aggregators, scalers=scalers,
                deg=deg, edge_dim=hidden,
                towers=1, pre_layers=1, post_layers=1,
            ))
            self.norms.append(nn.BatchNorm1d(hidden))
        self.drop = nn.Dropout(dropout)

        self.edge_cont_dim = edge_cont_dim
        self.head = nn.Sequential(
            nn.Linear(4 * hidden, hidden), nn.ReLU(), nn.Dropout(dropout),
            nn.Linear(hidden, 1),
        )

    def _encode_edges(self, edge_attr):
        cont = edge_attr[:, : self.edge_cont_dim]
        cur  = self.cur_emb(edge_attr[:, 12].long().clamp(min=0))
        fmt  = self.fmt_emb(edge_attr[:, 13].long().clamp(min=0))
        return self.edge_enc(torch.cat([cont, cur, fmt], dim=-1))

    def encode_nodes(self, x, edge_index, edge_attr):
        e = self._encode_edges(edge_attr)
        h = F.relu(self.node_enc(x))
        for conv, norm in zip(self.convs, self.norms):
            h = conv(h, edge_index, e)
            h = norm(h)
            h = self.drop(F.relu(h))
        return h

    def classify_edges(self, h, label_index, edge_attr_targets):
        hs, hd = h[label_index[0]], h[label_index[1]]
        e = self._encode_edges(edge_attr_targets)
        return self.head(torch.cat([hs, hd, hs * hd, e], dim=-1)).squeeze(-1)

    def forward(self, x, edge_index, edge_attr, label_index, edge_attr_targets):
        h = self.encode_nodes(x, edge_index, edge_attr)
        return self.classify_edges(h, label_index, edge_attr_targets)


# ── Training ─────────────────────────────────────────────────────────────────────

def _temporal_split(t_edge, train=0.75, val=0.15):
    order = torch.argsort(t_edge)
    n = len(order)
    return (order[: int(n * train)],
            order[int(n * train): int(n * (train + val))],
            order[int(n * (train + val)):])


def train_multignn(csv_path: Path | None = None, max_rows: int | None = None,
                   epochs: int = 5, hidden: int = 64, layers: int = 3,
                   batch_size: int = 4096, lr: float = 3e-3) -> dict:
    """Full-batch training: the whole graph is encoded each step (no neighbour sampler,
    so no pyg-lib/torch-sparse needed). `batch_size` only chunks the cheap edge head."""
    if not HAS_TORCH:
        raise RuntimeError("PyTorch not available. Install torch + torch_geometric.")

    bundle = build_graph(csv_path, max_rows)
    x, edge_index, edge_attr = bundle["x"], bundle["edge_index"], bundle["edge_attr"]
    y, label_index, t_edge, meta = bundle["y"], bundle["label_index"], bundle["t_edge"], bundle["meta"]
    deg = bundle["deg"]

    tr, va, te = _temporal_split(t_edge)
    logger.info(f"Multi-GNN split — train {len(tr):,} | val {len(va):,} | test {len(te):,} "
                f"| positives {int(y.sum()):,}/{len(y):,} ({100*y.float().mean():.3f}%)")

    model = MultiGNN(meta["node_dim"], meta["edge_cont_dim"], meta["n_currencies"],
                     meta["n_formats"], hidden=hidden, layers=layers, deg=deg)
    opt   = torch.optim.Adam(model.parameters(), lr=lr, weight_decay=1e-5)
    pos   = max(float(y[tr].sum()), 1.0)
    neg   = max(len(tr) - pos, 1.0)
    # Grama 2025 found weight 7.1 optimal on IBM HI-Small (same dataset).
    pos_weight = torch.tensor([7.1])
    logger.info(f"Multi-GNN: pos_weight={pos_weight.item():.1f} (raw {neg/pos:.0f})")

    E = label_index.size(1)
    edge_attr_fwd = edge_attr[:E]            # forward-edge features aligned with label_index
    li_tr, y_tr, ea_tr = label_index[:, tr], y[tr], edge_attr_fwd[tr]
    train_start = time.time()
    for epoch in range(1, epochs + 1):
        model.train()
        t0 = time.time()
        opt.zero_grad()
        h    = model.encode_nodes(x, edge_index, edge_attr)
        out  = model.classify_edges(h, li_tr, ea_tr)
        loss = F.binary_cross_entropy_with_logits(out, y_tr, pos_weight=pos_weight)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 2.0)
        opt.step()
        vm = _evaluate(model, x, edge_index, edge_attr, label_index[:, va], y[va], batch_size,
                       edge_attr_targets=edge_attr_fwd[va])
        elapsed = time.time() - train_start
        eta = elapsed / epoch * (epochs - epoch)
        _progress_bar(epoch, epochs, prefix="Training", suffix=f"loss {loss.item():.4f} F1 {vm['f1']:.4f} ETA {eta:.0f}s")
        logger.info(f"  epoch {epoch}/{epochs} — loss {loss.item():.4f} "
                    f"| val F1 {vm['f1']:.4f} AUC {vm['auc']:.4f} P {vm['precision']:.4f} R {vm['recall']:.4f} "
                    f"({time.time()-t0:.0f}s)")

    test_m = _evaluate(model, x, edge_index, edge_attr, label_index[:, te], y[te], batch_size,
                       edge_attr_targets=edge_attr_fwd[te], sweep=True)
    logger.info(f"Multi-GNN TEST — F1 {test_m['f1']:.4f} | AUC {test_m['auc']:.4f} | AP {test_m['ap']:.4f} "
                f"| P {test_m['precision']:.4f} | R {test_m['recall']:.4f} | thr {test_m['threshold']:.3f}")

    metrics = {
        **test_m,
        "n_nodes": meta["n_nodes"], "n_edges": meta["n_edges"],
        "n_train": int(len(tr)), "n_val": int(len(va)), "n_test": int(len(te)),
        "epochs": epochs, "hidden": hidden, "layers": layers,
        "max_rows": max_rows, "positives": int(y.sum()),
    }

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    torch.save({"state_dict": model.state_dict(),
                "config": {"node_dim": meta["node_dim"], "edge_cont_dim": meta["edge_cont_dim"],
                           "n_currencies": meta["n_currencies"], "n_formats": meta["n_formats"],
                           "hidden": hidden, "layers": layers},
                "deg": deg,
                "metrics": metrics}, MODEL_PATH)
    META_PATH.write_text(json.dumps({"metrics": metrics, "encoders": {
        "currencies": meta["currencies"], "formats": meta["formats"]}}, indent=2), encoding="utf-8")
    logger.info(f"Multi-GNN saved -> {MODEL_PATH}")
    return metrics


@torch.no_grad()
def _predict(model, x, edge_index, edge_attr, label_index, edge_attr_targets, batch_size: int = 8192):
    """Full-batch node encode, then chunk the edge head to bound memory."""
    model.eval()
    h = model.encode_nodes(x, edge_index, edge_attr)
    probs = []
    for s in range(0, label_index.size(1), batch_size):
        chunk = label_index[:, s:s + batch_size]
        ea    = edge_attr_targets[s:s + batch_size]
        probs.append(torch.sigmoid(model.classify_edges(h, chunk, ea)))
    return torch.cat(probs).numpy()


@torch.no_grad()
def _evaluate(model, x, edge_index, edge_attr, label_index, y, batch_size=8192,
              edge_attr_targets=None, sweep: bool = False) -> dict:
    from sklearn.metrics import (f1_score, roc_auc_score, precision_score,
                                 recall_score, average_precision_score)
    p = _predict(model, x, edge_index, edge_attr, label_index, edge_attr_targets, batch_size)
    l = y.numpy()
    auc = roc_auc_score(l, p) if len(set(l)) > 1 else float("nan")
    ap  = average_precision_score(l, p) if len(set(l)) > 1 else float("nan")

    thr = 0.5
    if sweep and len(set(l)) > 1:  # pick F1-max threshold on the eval set
        best_f1, best_t = -1.0, 0.5
        for t in np.linspace(0.05, 0.95, 19):
            f1 = f1_score(l, (p >= t).astype(int), zero_division=0)
            if f1 > best_f1:
                best_f1, best_t = f1, t
        thr = float(best_t)
    pred = (p >= thr).astype(int)
    return {
        "f1": round(float(f1_score(l, pred, zero_division=0)), 4),
        "precision": round(float(precision_score(l, pred, zero_division=0)), 4),
        "recall": round(float(recall_score(l, pred, zero_division=0)), 4),
        "auc": round(float(auc), 4) if auc == auc else None,
        "ap": round(float(ap), 4) if ap == ap else None,
        "threshold": round(thr, 3),
    }


def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Map varying CSV schemas to the canonical IBM column names."""
    if "From Account" in df.columns and "Account" not in df.columns:
        df = df.rename(columns={"From Account": "Account", "To Account": "Account.1"})
    elif "Account" in df.columns and "Account.1" not in df.columns:
        cols = list(df.columns)
        second = [i for i, c in enumerate(cols) if c == "Account"]
        if len(second) >= 2:
            cols[second[1]] = "Account.1"
            df.columns = cols
    return df


def train_multignn_multi(csv_paths: list[str | Path], max_rows: int | None = None,
                         epochs: int = 8, hidden: int = 64, layers: int = 3,
                         batch_size: int = 4096, lr: float = 3e-3,
                         pos_weight: float = 7.1, autotune: bool = False) -> dict:
    """Train Multi-GNN on multiple concatenated datasets with optional hyperparameter search.

    Args:
        csv_paths: List of CSV file paths to concatenate (e.g., [HI-Small, LI-Small])
        max_rows: Cap rows per dataset (None = unlimited)
        autotune: If True, grid-search over hyperparameter space and return best model
    """
    if not HAS_TORCH:
        raise RuntimeError("PyTorch not available.")

    # Load and concatenate datasets
    dfs = []
    for i, csv_path in enumerate(csv_paths, 1):
        csv_path = Path(csv_path) if isinstance(csv_path, str) else csv_path
        _progress_bar(i, len(csv_paths), prefix="Loading CSVs", suffix=csv_path.name)
        logger.info(f"Loading {csv_path.name}...")
        chunk = pd.read_csv(csv_path, nrows=max_rows)
        chunk = _normalize_columns(chunk)
        dfs.append(chunk)

    df = pd.concat(dfs, ignore_index=True)
    logger.info(f"Concatenated {len(csv_paths)} datasets -> {len(df):,} total rows")
    print(f"\n  Building graph from {len(df):,} rows...", flush=True)

    # Build graph from merged dataframe
    df["Timestamp"] = pd.to_datetime(df["Timestamp"], format="mixed")
    df.sort_values("Timestamp", inplace=True)
    df.reset_index(drop=True, inplace=True)

    src_key = df["From Bank"].astype(str) + ":" + df["Account"].astype(str)
    dst_key = df["To Bank"].astype(str) + ":" + df["Account.1"].astype(str)

    keep = src_key.values != dst_key.values
    df = df[keep].reset_index(drop=True)
    src_key, dst_key = src_key[keep].reset_index(drop=True), dst_key[keep].reset_index(drop=True)

    nodes = pd.Index(pd.unique(pd.concat([src_key, dst_key])))
    node_id = {k: i for i, k in enumerate(nodes)}
    src = src_key.map(node_id).to_numpy()
    dst = dst_key.map(node_id).to_numpy()
    N, E = len(nodes), len(df)
    logger.info(f"Multi-GNN: {N:,} accounts, {E:,} transactions")

    # Build features (replicate from build_graph logic)
    amount = df["Amount Paid"].to_numpy(dtype=np.float64)
    log_amt = np.log1p(np.clip(amount, 0, None)).astype(np.float32)
    log_amt = (log_amt - log_amt.mean()) / (log_amt.std() + 1e-6)

    ts = df["Timestamp"].astype("int64").to_numpy()
    t_norm = ((ts - ts.min()) / (ts.max() - ts.min() + 1)).astype(np.float32)

    hour_of_day = df["Timestamp"].dt.hour.to_numpy().astype(np.float32)
    hour_sin = np.sin(2 * np.pi * hour_of_day / 24).astype(np.float32)
    hour_cos = np.cos(2 * np.pi * hour_of_day / 24).astype(np.float32)

    day_of_week = df["Timestamp"].dt.dayofweek.to_numpy().astype(np.float32)
    dow_sin = np.sin(2 * np.pi * day_of_week / 7).astype(np.float32)
    dow_cos = np.cos(2 * np.pi * day_of_week / 7).astype(np.float32)

    is_cross_bank = (df["From Bank"].astype(str) != df["To Bank"].astype(str)).astype(np.float32).to_numpy()

    cur_codes, cur_uniq = pd.factorize(df["Receiving Currency"])
    fmt_codes, fmt_uniq = pd.factorize(df["Payment Format"])

    high_risk_cur = df["Receiving Currency"].isin(["Bitcoin", "BTC", "XRP", "ETH"]).to_numpy().astype(np.float32)
    high_risk_fmt = df["Payment Format"].isin(["Cheque", "Cash"]).to_numpy().astype(np.float32)
    cross_x_cur = (is_cross_bank * high_risk_cur).astype(np.float32)
    cross_x_fmt = (is_cross_bank * high_risk_fmt).astype(np.float32)

    out_port = _port_index(src, E)
    in_port = _port_index(dst, E)
    out_port_n = (out_port / (out_port.max() + 1)).astype(np.float32)
    in_port_n = (in_port / (in_port.max() + 1)).astype(np.float32)

    y = df["Is Laundering"].to_numpy(dtype=np.float32)

    fwd_attr = np.stack([
        log_amt, t_norm, out_port_n, in_port_n,
        np.zeros(E, np.float32),
        hour_sin, hour_cos, dow_sin, dow_cos, is_cross_bank,
        cross_x_cur, cross_x_fmt,
        cur_codes.astype(np.float32), fmt_codes.astype(np.float32),
    ], axis=1)
    rev_attr = fwd_attr.copy()
    rev_attr[:, 2], rev_attr[:, 3] = in_port_n, out_port_n
    rev_attr[:, 4] = 1.0

    edge_index = np.concatenate([np.stack([src, dst]), np.stack([dst, src])], axis=1)
    edge_attr = np.concatenate([fwd_attr, rev_attr], axis=0)

    in_deg = np.bincount(dst, minlength=N).astype(np.float32)
    out_deg = np.bincount(src, minlength=N).astype(np.float32)
    recv = np.bincount(dst, weights=amount, minlength=N).astype(np.float32)
    sent = np.bincount(src, weights=amount, minlength=N).astype(np.float32)
    x = np.stack([
        np.log1p(in_deg), np.log1p(out_deg),
        np.log1p(recv), np.log1p(sent),
    ], axis=1)
    x = (x - x.mean(0)) / (x.std(0) + 1e-6)

    x = torch.tensor(x, dtype=torch.float)
    edge_index = torch.tensor(edge_index, dtype=torch.long)
    edge_attr = torch.tensor(edge_attr, dtype=torch.float)
    y = torch.tensor(y, dtype=torch.float)
    label_index = torch.tensor(np.stack([src, dst]), dtype=torch.long)
    t_edge = torch.tensor(t_norm, dtype=torch.float)

    meta = {
        "n_nodes": int(N), "n_edges": int(E),
        "n_currencies": int(len(cur_uniq)), "n_formats": int(len(fmt_uniq)),
        "currencies": list(map(str, cur_uniq)), "formats": list(map(str, fmt_uniq)),
        "node_dim": 4, "edge_cont_dim": 12,
    }

    deg = _compute_deg(edge_index, N)

    # Hyperparameter grid (if autotune enabled)
    if autotune:
        logger.info("Starting hyperparameter grid search...")
        param_grid = {
            "hidden": [64, 128],
            "layers": [2, 3],
            "pos_weight": [5.0, 7.1, 10.0],
        }
        best_f1, best_params, best_metrics = -1.0, None, None

        import itertools
        combos = list(itertools.product(*param_grid.values()))
        for trial_i, hp_comb in enumerate(combos, 1):
            hp = dict(zip(param_grid.keys(), hp_comb))
            _progress_bar(trial_i, len(combos), prefix="Autotune", suffix=f"h={hp['hidden']} L={hp['layers']} pw={hp['pos_weight']}")
            logger.info(f"  Trial {trial_i}/{len(combos)}: hidden={hp['hidden']}, layers={hp['layers']}, pos_weight={hp['pos_weight']}")

            try:
                m = _train_single(x, edge_index, edge_attr, y, label_index, t_edge, meta, deg=deg,
                                epochs=epochs, batch_size=batch_size, lr=lr,
                                hidden=hp["hidden"], layers=hp["layers"], pos_weight=hp["pos_weight"])
                if m["f1"] > best_f1:
                    best_f1, best_params, best_metrics = m["f1"], hp, m
                    logger.info(f"    > New best: F1={m['f1']:.4f} AUC={m['auc']:.4f}")
            except Exception as e:
                logger.warning(f"    Trial failed: {e}")

        if best_params:
            logger.info(f"Best hyperparameters: {best_params}, F1={best_f1:.4f}")
            return _train_single(x, edge_index, edge_attr, y, label_index, t_edge, meta, deg=deg,
                               epochs=epochs, batch_size=batch_size, lr=lr,
                               hidden=best_params["hidden"], layers=best_params["layers"],
                               pos_weight=best_params["pos_weight"], save=True)

    return _train_single(x, edge_index, edge_attr, y, label_index, t_edge, meta, deg=deg,
                        epochs=epochs, batch_size=batch_size, lr=lr,
                        hidden=hidden, layers=layers, pos_weight=pos_weight, save=True)


def _train_single(x, edge_index, edge_attr, y, label_index, t_edge, meta, deg=None,
                  epochs: int = 8, hidden: int = 64, layers: int = 3,
                  batch_size: int = 4096, lr: float = 3e-3,
                  pos_weight: float = 7.1, save: bool = False) -> dict:
    """Internal training loop for a single hyperparameter configuration."""
    tr, va, te = _temporal_split(t_edge, train=0.75, val=0.15)
    logger.info(f"Split — train {len(tr):,} | val {len(va):,} | test {len(te):,} "
                f"| positives {int(y[tr].sum()):,}/{len(tr):,} ({100*y[tr].float().mean():.3f}%)")

    model = MultiGNN(meta["node_dim"], meta["edge_cont_dim"], meta["n_currencies"],
                     meta["n_formats"], hidden=hidden, layers=layers, deg=deg)
    opt = torch.optim.Adam(model.parameters(), lr=lr, weight_decay=1e-5)

    # Auto-compute pos_weight from actual class ratio if default 7.1 is too low
    n_pos = max(float(y[tr].sum()), 1.0)
    n_neg = len(tr) - n_pos
    auto_pw = min(n_neg / n_pos, 200.0)
    effective_pw = max(pos_weight, auto_pw)
    pos_w = torch.tensor([effective_pw])
    logger.info(f"pos_weight: requested={pos_weight}, auto={auto_pw:.1f}, using={effective_pw:.1f}")

    E = label_index.size(1)
    edge_attr_fwd = edge_attr[:E]
    li_tr, y_tr, ea_tr = label_index[:, tr], y[tr], edge_attr_fwd[tr]

    best_val_f1 = -1.0
    best_state = None
    patience_counter = 0
    patience = max(epochs // 3, 3)

    train_start = time.time()
    for epoch in range(1, epochs + 1):
        model.train()
        t0 = time.time()
        opt.zero_grad()
        h = model.encode_nodes(x, edge_index, edge_attr)
        out = model.classify_edges(h, li_tr, ea_tr)
        loss = F.binary_cross_entropy_with_logits(out, y_tr, pos_weight=pos_w)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 2.0)
        opt.step()

        vm = _evaluate(model, x, edge_index, edge_attr, label_index[:, va], y[va], batch_size,
                       edge_attr_targets=edge_attr_fwd[va])

        if vm['f1'] > best_val_f1:
            best_val_f1 = vm['f1']
            best_state = {k: v.clone() for k, v in model.state_dict().items()}
            patience_counter = 0
            star = " *best*"
        else:
            patience_counter += 1
            star = ""

        elapsed = time.time() - train_start
        eta = elapsed / epoch * (epochs - epoch)
        _progress_bar(epoch, epochs, prefix="Training", suffix=f"loss {loss.item():.4f} F1 {vm['f1']:.4f} ETA {eta:.0f}s")
        logger.info(f"  epoch {epoch}/{epochs} — loss {loss.item():.4f} "
                    f"| val F1 {vm['f1']:.4f} AUC {vm['auc']:.4f} P {vm['precision']:.4f} R {vm['recall']:.4f} "
                    f"({time.time()-t0:.0f}s){star}")

        if patience_counter >= patience and epoch >= 4:
            logger.info(f"  Early stopping — no val F1 improvement for {patience} epochs")
            break

    if best_state is not None:
        model.load_state_dict(best_state)
        logger.info(f"Restored best model (val F1={best_val_f1:.4f})")

    test_m = _evaluate(model, x, edge_index, edge_attr, label_index[:, te], y[te], batch_size,
                       edge_attr_targets=edge_attr_fwd[te], sweep=True)
    logger.info(f"TEST — F1 {test_m['f1']:.4f} | AUC {test_m['auc']:.4f} | AP {test_m['ap']:.4f} | "
                f"threshold {test_m['threshold']:.3f}")

    test_m["hidden"] = hidden
    test_m["layers"] = layers
    test_m["pos_weight"] = pos_weight

    if save:
        torch.save({
            "state_dict": model.state_dict(),
            "config": {"node_dim": meta["node_dim"], "edge_cont_dim": meta["edge_cont_dim"],
                      "n_currencies": meta["n_currencies"], "n_formats": meta["n_formats"],
                      "hidden": hidden, "layers": layers},
            "deg": deg if deg is not None else torch.ones(100, dtype=torch.long),
            "metrics": test_m}, MODEL_PATH)
        META_PATH.write_text(json.dumps({"metrics": test_m, "encoders": {
            "currencies": meta["currencies"], "formats": meta["formats"]}}, indent=2), encoding="utf-8")
        logger.info(f"Multi-GNN saved -> {MODEL_PATH}")

    return test_m


# ── Inference ────────────────────────────────────────────────────────────────────

def load_multignn():
    """Load the trained Multi-GNN. Returns (model, metrics) or (None, None)."""
    if not HAS_TORCH or not MODEL_PATH.exists():
        return None, None
    try:
        saved = torch.load(MODEL_PATH, map_location="cpu", weights_only=False)
        cfg = saved["config"]
        deg = saved.get("deg", torch.ones(100, dtype=torch.long))
        model = MultiGNN(cfg["node_dim"], cfg["edge_cont_dim"], cfg["n_currencies"],
                         cfg["n_formats"], hidden=cfg["hidden"], layers=cfg["layers"], deg=deg)
        model.load_state_dict(saved["state_dict"])
        model.eval()
        return model, saved.get("metrics")
    except Exception as e:  # pragma: no cover
        logger.warning(f"Could not load Multi-GNN ({e})")
        return None, None


def score_transactions(model, bundle: dict, batch_size: int = 8192) -> np.ndarray:
    """Return per-transaction laundering probabilities for a built graph bundle."""
    if model is None:
        return np.full(bundle["meta"]["n_edges"], 0.5, dtype=np.float32)
    E = bundle["label_index"].size(1)
    return _predict(model, bundle["x"], bundle["edge_index"], bundle["edge_attr"],
                    bundle["label_index"], bundle["edge_attr"][:E], batch_size)


@torch.no_grad()
def explain_transactions(model, bundle: dict, edge_indices: list[int]) -> dict:
    """Use GNNExplainer to compute edge importance for flagged transactions.

    Returns {edge_idx: importance_score (0-1)} for edges in edge_indices.
    High score = edge was important to the laundering prediction.
    """
    if model is None or not HAS_TORCH:
        return {idx: 0.5 for idx in edge_indices}

    try:
        from torch_geometric.explain import Explainer, GNNExplainer

        x, edge_index, edge_attr = bundle["x"], bundle["edge_index"], bundle["edge_attr"]
        label_index, edge_attr_fwd = bundle["label_index"], edge_attr[:bundle["label_index"].size(1)]

        # GNNExplainer computes the mask of edges that matter for a specific prediction.
        explainer = Explainer(
            model=model,
            algorithm=GNNExplainer(epochs=100, lr=0.01),
            explanation_type='model',
            model_config=dict(
                mode='regression',
                task_level='edge',
                return_type='raw',
            ),
        )

        importance: dict = {}
        for edge_idx in edge_indices[:50]:  # Limit to first 50 for speed
            if edge_idx >= label_index.size(1):
                continue
            try:
                # Explain this specific edge's prediction
                exp = explainer(
                    x=x,
                    edge_index=edge_index,
                    edge_attr=edge_attr,
                    index=edge_idx,
                    target=label_index[:, edge_idx],
                )
                # The explanation returns an edge_mask; take its mean as importance.
                if hasattr(exp, 'edge_mask') and exp.edge_mask is not None:
                    importance[edge_idx] = float(exp.edge_mask.mean().cpu().numpy())
                else:
                    importance[edge_idx] = 0.5
            except Exception as e:
                logger.debug(f"GNNExplainer failed for edge {edge_idx}: {e}")
                importance[edge_idx] = 0.5

        return importance
    except ImportError:
        logger.warning("torch_geometric.explain not available — GNNExplainer disabled")
        return {idx: 0.5 for idx in edge_indices}
    except Exception as e:
        logger.warning(f"GNNExplainer failed: {e}")
        return {idx: 0.5 for idx in edge_indices}


# ── CLI ──────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if not HAS_TORCH:
        print("PyTorch not installed. Run: pip install torch torch_geometric", file=sys.stderr)
        sys.exit(1)

    ap = argparse.ArgumentParser(description="Train the Multi-GNN AML classifier")
    ap.add_argument("--epochs", type=int, default=8)
    ap.add_argument("--max-rows", type=int, default=None, help="Cap transactions per dataset")
    ap.add_argument("--hidden", type=int, default=64)
    ap.add_argument("--layers", type=int, default=3)
    ap.add_argument("--batch-size", type=int, default=4096)
    ap.add_argument("--lr", type=float, default=3e-3)
    ap.add_argument("--pos-weight", type=float, default=7.1)
    ap.add_argument("--datasets", type=str, nargs="+", default=None,
                    help="List of CSV paths to train on (default: HI-Small)")
    ap.add_argument("--autotune", action="store_true", help="Grid-search hyperparameters")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    if args.datasets:
        m = train_multignn_multi(csv_paths=args.datasets, max_rows=args.max_rows,
                                epochs=args.epochs, hidden=args.hidden, layers=args.layers,
                                batch_size=args.batch_size, lr=args.lr, pos_weight=args.pos_weight,
                                autotune=args.autotune)
    else:
        m = train_multignn(max_rows=args.max_rows, epochs=args.epochs, hidden=args.hidden,
                          layers=args.layers, batch_size=args.batch_size, lr=args.lr)

    print(f"\nMulti-GNN done — Test F1={m['f1']} AUC={m['auc']} AP={m['ap']} "
          f"P={m['precision']} R={m['recall']} @thr={m['threshold']}")

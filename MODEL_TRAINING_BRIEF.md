# Argus Multi-GNN — Complete Modeling Brief & Improvement Mandate

> **Paste this whole file into a fresh Claude session.** It is self-contained.
> Your job: get the transaction-level money-laundering classifier to
> **F1 ≥ 0.75 and AUC ≥ 0.90 on an honest (non-leaked) test split**, and produce a
> `multignn_model.pt` + `multignn_meta.json` that loads with the existing inference code **unchanged in shape**.

---

## 0. TL;DR for the receiving Claude

- This is an **edge-level binary classification** problem on a **transaction multigraph**. Each transaction (edge between two bank accounts) is laundering (1) or not (0).
- Class imbalance is **extreme: ~0.1% positive**. This is the central difficulty. Everything below revolves around it.
- The architecture already exists and is sound (it's the IBM Multi-GNN paper). **Do not rewrite it from scratch.** Improve the *training*, *data*, *loss*, and *evaluation*.
- The five things currently sabotaging results are: **(1) training on the wrong dataset, (2) a `pos_weight` that collapses precision, (3) threshold tuning leaking from the test set, (4) full-batch OOM forcing tiny row caps, (5) row caps starving the model of the already-rare positives.** Fix those.
- Realistic expectation: AUC 0.90+ is easy. **F1 0.75 is at/above published SOTA for this dataset** — reachable with full data + the fixes, not guaranteed. Report honest numbers.

---

## 1. What the system is

**Argus** is an anti-money-laundering (AML) detection platform. The **Multi-GNN is the sole detector**: it scores every transaction edge for laundering probability. Flagged edges are clustered into connected components, each component becomes one "alert", the alert's topology is classified into an AML pattern (fan-out, fan-in, cycle, layering chain, etc.), and alerts render on a dashboard.

Pipeline: `CSV → build multigraph → MultiGNN scores every edge → keep edges ≥ threshold → cluster connected flagged edges → classify topology → serialize alerts → dashboard`.

**The model quality directly determines whether the dashboard shows real laundering rings or noise.**

---

## 2. The task, precisely

- **Input:** transaction CSV in IBM AML format. Canonical columns:
  `Timestamp, From Bank, Account, To Bank, Account.1, Amount Received, Receiving Currency, Amount Paid, Payment Currency, Payment Format, Is Laundering`
- **Node identity:** `f"{Bank}:{Account}"` (accounts repeat across banks, so bank must be part of the key).
- **Edge:** one transaction, directed source→dest.
- **Label:** `Is Laundering` ∈ {0,1}, per edge.
- **Self-loops** (same src and dst key, "reinvestment" rows) are dropped.
- **Split MUST be temporal**, never random. Sort by timestamp, take earliest 75% train / next 15% val / last 10% test. Laundering detection that shuffles time leaks the future into the past and inflates everything.

---

## 3. Current architecture (improve, don't replace)

File: `src/backend/models/multignn.py`. Class `MultiGNN`.

**Backbone:** PyG `PNAConv` (Principal Neighbourhood Aggregation).
- Aggregators: `["mean", "max", "min", "std"]`
- Scalers: `["identity", "amplification", "attenuation"]`
- `layers=3`, `hidden=64` (default) or `128` (better), `dropout=0.2`, `BatchNorm1d` after each conv.
- ⚠️ PNA multiplies message memory by `len(aggregators) × len(scalers) = 12`. **This is why it OOMs.** A lighter alternative is `GINEConv` (sum-only) if you stay memory-bound.

**Multi-GNN adaptations already implemented (from Egressy et al., "Provably Powerful GNNs for Directed Multigraphs"):**
- **Reverse message passing:** every edge mirrored with a reverse edge carrying an `is_reverse` flag, so a node sees both inflow and outflow.
- **Port numbering:** each edge records its ordinal position among the source's out-edges and the dest's in-edges (lets the GNN distinguish parallel multigraph edges).
- **Edge features in message passing:** an edge encoder consumes per-edge features during convolution.
- **Edge-level head:** MLP over `[h_src, h_dst, h_src*h_dst, edge_emb]` → 1 logit.

**Edge feature vector (14 dims):**
`[log_amount(z-scored), t_norm, out_port_norm, in_port_norm, is_reverse, hour_sin, hour_cos, dow_sin, dow_cos, is_cross_bank, cross_bank×high_risk_currency, cross_bank×high_risk_format, currency_code, format_code]`
The last two are integer codes fed to `nn.Embedding`. The first 12 are continuous (`edge_cont_dim=12`).

**Node features (4 dims):** `[log(in_degree), log(out_degree), log(total_received), log(total_sent)]`, z-scored.

**Inference contract (CRITICAL — do not break):**
The saved `multignn_model.pt` is a dict with keys:
```python
{
  "state_dict": <model weights>,
  "config": {"node_dim", "edge_cont_dim", "n_currencies", "n_formats", "hidden", "layers"},
  "deg": <degree histogram tensor for PNA scalers>,
  "metrics": {... including "threshold" ...},
}
```
`multignn_meta.json` is `{"metrics": {...}, "encoders": {"currencies": [...], "formats": [...]}}`.
`load_multignn()` reconstructs `MultiGNN(**config, deg=deg)` and calls `load_state_dict`.
**If you change the architecture (layer count, hidden size, feature count, conv type), you MUST mirror the identical change in `src/backend/models/multignn.py` or production inference will fail to load the weights.** The encoder vocabularies (`currencies`, `formats`) and feature order must match between training and `build_graph()` in production.

---

## 4. What's been tried, and the results

| Run | Dataset | Rows | Epochs | hidden | pos_weight | Test F1 | AUC | Notes |
|-----|---------|------|--------|--------|-----------|---------|-----|-------|
| Deployed (bad) | HI-Small | 268K (capped) | 8 | 64 | 7.1 | **0.023** | 0.597 | Only 305 positives. Threshold floored to 0.10. Basically noise. |
| Best so far | TransXion (tx.csv) | 200K | 50 (early-stopped ~20) | 128 | auto→200 | **0.44** | **0.94** | Best val F1 0.466 @ epoch 8, then collapsed. P=0.44 R=0.44 thr=0.525. |

**Observed pathology (important):** with `pos_weight` auto-set to 200, val F1 peaks around epoch 8 then **recall → 1.0 while precision → 0.003**, F1 collapses to ~0.006. The model learns to flag everything. Early stopping rescued the epoch-8 checkpoint. This is a **loss-weighting problem**, not a capacity problem.

---

## 5. Known failure modes — FIX THESE

1. **Distribution mismatch (biggest correctness bug).** Production scores **`HI-Small_Trans.csv`** (see `_resolve_csv()` in `multignn.py`). The best run trained on **TransXion**. Train and deploy on the **same** dataset → train on **HI-Small**.

2. **`pos_weight` collapse.** `auto_pw = min(n_neg/n_pos, 200)` hits the 200 cap because positives are ~0.1%. 200 over-weights positives so hard that precision dies. **Fix:** cap pos_weight in the **5–20** range, OR switch to **focal loss** (γ=2, α≈0.25) which handles extreme imbalance without blowing up precision. Sweep pos_weight ∈ {3, 5, 8, 12} as a small grid.

3. **Test-set threshold leakage.** `_evaluate(..., sweep=True)` picks the F1-max threshold **on the test set**, then reports F1 at that threshold — that is leakage and inflates the reported number. **Fix:** sweep the threshold on the **validation** set, freeze it, then report test metrics at that frozen threshold. AUC/AP are threshold-free and honest already.

4. **Full-batch OOM.** `encode_nodes()` runs message passing over the entire graph every step. With PNA's 12× blowup, anything past ~1M edges OOMs a 15 GB GPU. **Fix options, in order of payoff:** (a) **neighbor sampling** with `LinkNeighborLoader` (bounded memory, unlocks the full dataset — this is how large-graph GNNs are actually trained); (b) lighter conv (GINEConv); (c) `PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True`; (d) train on CPU with 30 GB RAM (Kaggle) for the full graph, slow but works.

5. **Row caps starve positives.** At 0.1% positive, `max_rows=200000` ≈ only ~115 positives in the train split. The model can't learn a rare pattern from ~100 examples. **More rows = more positives = the single biggest lever on F1.** Use the **full** dataset (requires fix #4).

---

## 6. Improvement levers, ranked by expected payoff

1. **Use the full HI-Small dataset** (needs neighbor sampling). Goes from ~hundreds to ~thousands of positives. **Highest impact.**
2. **Fix the loss** (focal loss or sane pos_weight). Stops the precision collapse → directly raises F1.
3. **Honest val-based threshold selection.** Makes the number trustworthy and usually *more* robust on test.
4. **Neighbor sampling with class-balanced batches** — oversample positive edges per batch so each gradient step sees a workable positive ratio (e.g. 1:10 instead of 1:1000).
5. **More epochs + LR schedule.** Cosine annealing is already in the notebook; with sampling you can run 30–100 effective epochs.
6. **Architecture: keep PNA if memory allows** (it's more expressive); add **residual connections** between conv layers; consider **edge updates** (the full Multi-GNN "EU" variant updates edge embeddings each layer — this is what pushes the paper's F1 into the high 60s/70s).
7. **Feature engineering** (the features are already good): consider account-level velocity (txns per hour), repeated-exact-amount flags, round-number flags, time-since-last-txn per account, fan-in/fan-out counts in a rolling window.
8. **Calibrate, then pick an operating point** that matches the dashboard's needs (precision-leaning so analysts aren't drowned). Report F1 but also precision@k.

---

## 7. Recommended plan to actually hit the target

1. Upload **`HI-Small_Trans.csv`** to the GPU environment (Kaggle T4 ×2, 30 GB RAM; NOT P100 — too old for current PyTorch).
2. Implement **`LinkNeighborLoader`** mini-batch training over the full graph (num_neighbors e.g. `[15, 10, 5]` for 3 layers, batch of edges e.g. 2048, with positive oversampling).
3. Swap weighted BCE → **focal loss** (γ=2). If keeping BCE, set `pos_weight` ≈ 8 and remove the 200 cap.
4. **Threshold = argmax F1 on validation**, frozen before touching test.
5. Train to convergence with early stopping on **val F1** (patience ~10). Cosine LR.
6. Small grid if time: `hidden ∈ {64,128}`, `layers ∈ {2,3}`, `pos_weight/γ`.
7. Save artifacts in the exact inference contract (§3). **Mirror any architecture change into `src/backend/models/multignn.py`.**
8. Validate locally: drop `multignn_model.pt` + `multignn_meta.json` into `data/`, delete `data/pipeline_cache.json`, restart server, confirm alerts render.

---

## 8. Datasets available (in repo, gitignored — do NOT commit them)

| Dataset | Path | Rows | Format | Use |
|---------|------|------|--------|-----|
| **HI-Small** | `data/active/HI-Small_Trans.csv` | ~5M | IBM (canonical) | **PRODUCTION TARGET — train on this** |
| TransXion | `data/TransXion/data/tx.csv` | ~3M | IBM-compatible (`From Account`/`To Account`) | Optional augmentation |
| SAML-D | `data/SAML-D/SAML-D.csv` | ~9.5M | Different schema (`Sender_account`, etc.) | Needs column remap (notebook handles it) |
| Elliptic | `data/Elliptic/*` | ~204K | Node-level, no IBM columns | ❌ Incompatible (different task) |
| HI/LI Medium/Large | `data/archive/datasets/IBM/*` | up to ~180M | IBM | Too big for now |

Column remap for cross-dataset training is in `train_multignn.ipynb` → `normalize_columns()`.

---

## 9. Key file map

- `src/backend/models/multignn.py` — model, `build_graph()`, `train_multignn()`, `train_multignn_multi()`, `_evaluate()` (has the threshold-leak), `load_multignn()`, `score_transactions()`, `explain_transactions()` (GNNExplainer), CLI `main()`.
- `src/backend/pipeline/detection.py` — consumes scores. `ALERT_THRESHOLD_FLOOR = 0.10`, `MAX_ALERTS = 200`. Clusters flagged edges, classifies topology.
- `src/config.py` — `DATA_DIR`, `MODEL_PATH = data/multignn_model.pt`, `META_PATH = data/multignn_meta.json`, `CACHE_PATH = data/pipeline_cache.json`.
- `train_multignn.ipynb` — the Colab/Kaggle training notebook (self-contained copy of model + graph build + train loop). **This is where to prototype the fixes**, then port the winning architecture back into `multignn.py`.
- `data/multignn_meta.json` — current (bad) model metrics.

---

## 10. CLI for in-repo training (alternative to the notebook)

```bash
# single dataset
python src/backend/models/multignn.py --epochs 50 --hidden 128 --layers 3

# multi-dataset with hyperparameter grid search
python src/backend/models/multignn.py --datasets data/active/HI-Small_Trans.csv data/TransXion/data/tx.csv --epochs 50 --autotune
```
`train_multignn_multi()` already supports concatenating datasets and an autotune grid (`hidden ∈ {64,128}`, `layers ∈ {2,3}`, `pos_weight ∈ {5,7.1,10}`) — but it inherits the same threshold-leak and pos_weight issues; fix those.

---

## 11. Hard constraints (do not violate)

- **Never commit datasets or large model files to git.** They're gitignored. The user pushes to GitHub manually.
- **Demo safety:** if any change risks breaking the running demo, log it in `KNOWN_ISSUES.md` instead of shipping it.
- **Don't `git push`** — the user controls what goes to the remote.
- **`config/deployment.yaml` is documentation only** — the live service (Render) uses dashboard settings, not that file. Render needs `PYTHONPATH=src` set in its Environment tab.
- Keep the **inference contract** (§3) intact or update `multignn.py` in lockstep.

---

## 12. Definition of done

- [ ] Trained on **HI-Small** (the production dataset).
- [ ] **Honest** test metrics: threshold chosen on val, reported on test, no leakage.
- [ ] **F1 ≥ 0.75** and **AUC ≥ 0.90** on the temporal test split (target; report whatever is honestly achieved).
- [ ] No precision collapse — precision and recall both meaningfully > 0 at the chosen threshold.
- [ ] `multignn_model.pt` + `multignn_meta.json` load via `load_multignn()` without shape errors.
- [ ] Any architecture change mirrored in `src/backend/models/multignn.py`.
- [ ] Local smoke test: artifacts in `data/`, `pipeline_cache.json` deleted, server restarts, dashboard shows alerts.
```

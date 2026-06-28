# Block 1 — Val→Test Collapse Diagnosis

## Symptom
On LI-Medium (chronological 75/15/15 at subgraph level), validation F1 is high but test F1
collapses:

| Model      | Val F1 | Test F1 | Gap   |
|------------|--------|---------|-------|
| ExtraTrees | 0.91   | 0.40    | 0.51  |
| XGBoost    | ~0.95  | ~0.52   | ~0.43 |
| LightGBM   | ~0.97  | ~0.52   | ~0.45 |

A gap this large is not normal generalization error — it points to a distribution shift
between the val window and the test window plus high model variance.

## Split audit (confirmed correct)
- Components are ordered by **min edge timestamp** (`_comp_min_ts`) before slicing at
  `i_train=0.75n`, `i_val=0.90n`. Chronological ordering is respected.
- **No subgraph-ID leakage across splits**: each weakly-connected component is assigned to
  exactly one split; features are computed per-subgraph, so a test component's
  betweenness/clustering/degree stats never see train-side nodes.
- **Noise injection was NOT in `benchmark.py`** (only in `ml_model.py._train()`). The
  benchmark trains clean — so noise was never the lever here. Raised σ 0.02→0.05 in
  `ml_model.py` only; benchmark stays clean so the model comparison is unbiased.

## Root causes
**(a) Synthetic IBM distribution homogeneity.** The generator produces laundering subgraphs
from a small set of canonical templates. Tree ensembles memorize template-exact feature
values (amounts, degree counts) that recur in train/val but not in the later test window,
so deep trees overfit the template fingerprints rather than learning topology.

**(b) Negative-sampling bias (3× positives).** Negatives were drawn with a flat
`random.sample`, which — under a time-ordered split — tends to over-represent whichever time
window has more clean components. That makes the val negatives easy and the test negatives
out-of-distribution. **Fix:** `_temporal_stratified_sample()` spreads negatives evenly
across 10 time buckets.

**(c) Graph-level feature leakage risk.** Checked: features are extracted on each
component's own subgraph (`G.subgraph(comp)`), not on the full graph, so there is no
cross-component contamination. The only global quantity is `max_node_count` used for
confidence in the detector — not used in the benchmark feature matrix. No leakage found.

**(d) 75/15/15 boundary = distributional cliff.** Even after the post-date-range cutoff,
the IBM time series is non-stationary: laundering density and component sizes drift over the
window. The last 15% (test) sits in a region the model never trained on, so the cliff is
real. **Mitigations applied:** temporal-stratified negatives, `max_features="sqrt"` on
RF/ExtraTrees to cut variance, and 5-fold stratified CV reported alongside val/test F1 so a
stable model is distinguishable from a lucky-val one. The ranked table now also prints the
val→test gap explicitly.

## Fixes implemented (Block 1)
- `ml_model.py`: noise σ 0.02→0.05; `max_features="sqrt"` on RF fallback.
- `benchmark.py`: `_temporal_stratified_sample()`, `_distribution_check()` (flags features
  with |mean_train−mean_test| > 2·std_train), `max_features="sqrt"` on RF & ExtraTrees,
  5-fold stratified CV column, val→test gap column in the ranked table.

## How to read the new output
- **CV F1 ≫ Test F1** with a large gap → the model is variance-bound / overfit; prefer a
  model whose CV F1 and Test F1 agree.
- **DISTRIBUTION CHECK flags** → those features are the cliff drivers; expect them to be the
  high-importance features in the overfit models.

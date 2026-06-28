# Multi-GNN Migration — Orphaned Files

The detection stack is now a single **Multi-GNN** edge-level classifier
([backend/multignn_model.py](../backend/multignn_model.py)) wired through
[backend/multignn_pipeline.py](../backend/multignn_pipeline.py). The rule-based
detector and the Random-Forest/XGBoost scorer are **no longer called**.

Nothing below has been deleted — per your instruction, deletion is your call.
This is the inventory of what is now dormant.

## New files (the active model)
| File | Role |
|---|---|
| `backend/multignn_model.py` | Multi-GNN: graph builder, GINE backbone (reverse MP + port numbering), training, inference. |
| `backend/multignn_pipeline.py` | Turns Multi-GNN edge predictions into the alert clusters the frontend renders. |
| `data/multignn_model.pt` | Trained weights + config + metrics. |
| `data/multignn_meta.json` | Encoders + metrics (human-readable). |

## Now-orphaned CODE (safe to delete once you're happy with Multi-GNN)
| File | Was |
|---|---|
| `backend/ml_model.py` | RandomForest/XGBoost subgraph scorer. |
| `backend/gnn_model.py` | Old GraphSAGE second layer (superseded by Multi-GNN). |
| `backend/detector.py` | Rule-based pattern detector (fan-in/out, cycle, …). |
| `backend/pattern_classifier.py` | ML classifier for pattern *type*. |
| `backend/benchmark.py` | Classical-ML bake-off (13 algos). |
| `backend/retrainer.py` | Retrained the RF from analyst feedback. |
| `backend/validator.py` | Validated rule-detector alerts vs ground truth. |
| `backend/audit_saml.py` | SAML-D dataset audit. |

> ⚠️ `main.py` still *imports* `ml_model`, `detector`, `retrainer`, `gnn_model`
> (used only by the now-dormant `/retrain` and pattern endpoints). If you delete
> those modules, also remove their imports at the top of `main.py` and the
> `/retrain` + benchmark endpoints, or those routes will error when called.
> The main detection path does **not** use them.

## Now-orphaned ARTIFACTS
| File | From |
|---|---|
| `data/fraud_model.pkl` | RF/XGBoost model. |
| `data/gnn_model.pkl` | Old GraphSAGE weights. |
| `data/pattern_classifier.pkl` | Pattern-type classifier. |
| `data/threshold_curve.json` | RF threshold sweep. |
| `data/model_selection_report.txt` | Benchmark winner report (if present). |
| `data/benchmark_results_*.txt` | Benchmark outputs (if present). |
| `data/saml_audit_report.txt` | SAML-D audit output. |
| `data/validation_results.json` | Rule-detector validation. |
| `data/pipeline_cache.json` | Cached alerts — **delete this** so the app rebuilds with Multi-GNN. |

## Already deleted but uncommitted (from your git status)
`Bootup.bat`, `README.md`, `run_benchmarks.ps1` — unrelated to this migration.

## Alternate datasets under `data/` (unused at runtime — only IBM HI-Small is used)
`Elliptic/`, `EllipticPlusPlus/`, `SAML-D/`, `TransXion/`

## Retraining the Multi-GNN
```bash
# quick CPU run (subset)
python backend/multignn_model.py --epochs 30 --max-rows 1200000

# full HI-Small (heavier; needs more RAM)
python backend/multignn_model.py --epochs 8
```
Then delete `data/pipeline_cache.json` and restart the backend.

# Architecture — AML Intelligence Platform

## System Overview

The AML Intelligence Platform runs two parallel detection pipelines on IBM's HI-Small synthetic transaction dataset, classifies graph topology on both outputs, merges them via account-set overlap deduplication, applies a whitelist filter to suppress known false positives, then serves the results through a single FastAPI backend and a 6-view light-theme investigator dashboard.

---

## Pipeline Flow

```
                    HI-Small_Trans.csv (454 MB)
                           │
                    load_and_build()
                    ├── Parse timestamps (%Y/%m/%d %H:%M)
                    ├── Filter 48-hr window: 2022-09-01 – 2022-09-02 23:59
                    ├── Remove self-loops (Account == Account.1)
                    ├── df_full  (all ~1.8M windowed rows)
                    └── df_suspicious (Is Laundering == 1, ~729 rows)

        ┌──────────────────────────┐    ┌──────────────────────────────────────┐
        │  LABELLED PIPELINE       │    │  UNLABELLED PIPELINE                 │
        │                          │    │                                      │
        │  G_suspicious            │    │  find_suspicious_unlabelled(df_full) │
        │  detect_all_patterns()   │    │                                      │
        │  source="labelled"       │    │  7 Behavioural Signals (see below)   │
        │  → 46 labelled alerts    │    │  Score ≥ 2 → suspicious accounts     │
        │                          │    │  G_unlabelled (flagged edges only)   │
        │                          │    │  detect_all_patterns()               │
        │                          │    │  source="unlabelled"                 │
        │                          │    │  id_prefix="u_"                      │
        └──────────────────────────┘    └──────────────────────────────────────┘
                         │                              │
                         └──────────┬───────────────────┘
                                    │
                         _merge_raw_alerts()
                         >80% account overlap → source="both"
                                    │
                         filter_alerts()  ←── data/whitelist.json
                         ┌──────────┴───────────┐
                      KEPT alerts         SUPPRESSED alerts
                      ALERTS dict         SUPPRESSED dict
                                    │
                         serialize_alerts()
                                    │
                   ┌────────────────▼──────────────────┐
                   │           FastAPI (port 8000)      │
                   │  /health  /status  /alerts         │
                   │  /alerts/{id}  /alerts/suppressed  │
                   │  /whitelist  /validation           │
                   └────────────────┬──────────────────┘
                                    │
                        frontend/index.html
                   ┌────────────────▼──────────────────┐
                   │  Dashboard  |  Investigate          │
                   │  Case Manager  |  Search            │
                   │  Validation  |  Whitelist           │
                   └───────────────────────────────────┘
```

---

## Unlabelled Detection — 7 Behavioural Signals

### Signal 1 — Rapid Fan-Out

**Detects:** A distributor account sending to many distinct recipients quickly — analogous to smurfing or bulk cash-out.

**Implementation:** Group by `(Account, 2-hour bucket)`. Count distinct `Account.1`. Flag accounts where any bucket has ≥ 3 distinct recipients.

**Why 2 hours?** Legitimate bulk payroll spans hours-to-days in defined batches. Laundering distributions are compressed to avoid detection.

---

### Signal 2 — Round-Trip (A→B→A within 24 hours)

**Detects:** Money leaving an account and returning through direct reversal — circular flow to obscure origin.

**Implementation:** Aggregate `(Account, Account.1)` pairs to min/max timestamps. Merge forward pairs against reversed pairs; filter `|ts_rev - ts_fwd| ≤ 86400s`.

**Why aggregated?** Row-level join on 1.8M rows produces a cartesian product for heavy traders. Aggregation reduces to unique account-pair combinations first.

---

### Signal 3 — Structuring

**Detects:** Multiple transactions clustered just below reporting thresholds — intentionally staying under $10k or $50k per transaction.

**Implementation:** Filter `Amount Paid in [9,000, 9,999] or [49,000, 49,999]`. Group by `(Account, 1-hour bucket)`. Flag accounts with ≥ 3 such transactions in any bucket.

---

### Signal 4 — Layering Velocity

**Detects:** Pure pass-through accounts that receive funds and immediately forward nearly all of it — the layering phase of placement→layering→integration.

**Implementation:** Group received amounts by `(Account.1, 6-hour bucket)` and sent by `(Account, 6-hour bucket)`. Join on account+bucket; flag where `sent / received > 0.9`.

---

### Signal 5 — Dormant Account Activation

**Detects:** Accounts that are silent in the first 24 hours of the window, then suddenly burst into activity — consistent with a dormant mule account being activated on command.

**Implementation:** Split df at `WINDOW_START + 24h`. Compute `active_before` set. Compute `all_after` set. `dormant_set = all_after - active_before`. Among dormant accounts, flag those with ≥ 3 transactions in any 2-hour bucket after the midpoint.

**Why split at hour 24?** A 48-hour window gives a clear before/after reference. Truly dormant accounts appear only in the second half.

---

### Signal 6 — Currency Mismatch Layering

**Detects:** Accounts that receive in one currency set and forward in a different currency set — the classic FX-layering indicator where funds are converted at each hop to obscure the money trail.

**Implementation:** Group `Receiving Currency` by receiving account; group `Payment Currency` by sending account. Merge on account ID; flag where `received_currencies ⊄ sent_currencies`. A set-membership check (not edge-level join) keeps this O(accounts) not O(edges).

---

### Signal 7 — Smurfing (coordinated small deposits)

**Detects:** 5 or more different accounts each sending amounts in the $1k–$10k range to the same destination in a 4-hour window — the classic smurfing pattern where many couriers deposit just below the reporting threshold.

**Implementation:** Filter `Amount Paid in [1,000, 10,000]`. Group by `(Account.1, 4-hour bucket)` counting distinct senders. Flag destinations with ≥ 5 distinct senders. Also flag the coordinated senders themselves (5+ in a qualifying bucket).

---

## Scoring and Flagging

Each account scores 1 point per triggered signal. Accounts with **score ≥ 2** are flagged as suspicious.

`G_unlabelled` includes all edges where **either** endpoint is a flagged account. This intentionally over-includes edges to capture the full network context of suspicious actors.

---

## Whitelist / False Positive Reduction

### Why Whitelisting Matters

FAN_IN and FAN_OUT are structurally identical to payroll collection and bulk distribution accounts. A large employer receiving payroll contributions will trigger FAN_IN. A corporate treasury distributing dividends will trigger FAN_OUT. Without filtering, these generate high-volume alert noise that obscures genuine laundering.

### Design

```
data/whitelist.json
{
  "exempt_accounts": [],
  "exempt_banks": ["Federal Reserve", "Central Bank", "RBI", "ECB"],
  "business_account_patterns": ["CORP", "LTD", "INC", "PLC", "LLC", "BANK"],
  "exemption_rules": {
    "FAN_IN":    { "exempt_if": ["is_business", "is_exempt_bank"] },
    "FAN_OUT":   { "exempt_if": ["is_business", "is_exempt_bank"] },
    "BIPARTITE": { "exempt_if": ["is_exempt_bank"] }
  }
}
```

### Filter Logic

`filter_alerts()` in `whitelist.py` evaluates each alert:

1. **All nodes exempt** → alert moved to `SUPPRESSED` dict with `exemption_reason` field. Accessible at `GET /alerts/suppressed` for audit trail.
2. **Some nodes exempt** → alert kept in `ALERTS` dict with `partial_exemption: true` flag. Investigator sees a warning.
3. **No nodes exempt** → alert passes through unchanged.

### Persistence

`data/whitelist.json` is committed to the repo. Changes via `POST /whitelist/account` and `DELETE /whitelist/account/{id}` are written back to disk immediately. On Render, the `/data` directory lives on a persistent disk that survives redeploys.

---

## Deduplication / Overlap Logic

```
overlap_ratio(A, B) = |A ∩ B| / max(|A|, |B|)
```

For each unlabelled alert, if any labelled alert has `overlap_ratio > 0.8`:
- The labelled alert is upgraded to `source = "both"`
- The unlabelled alert is discarded (no duplicate IDs)

`source = "both"` is the system's internal cross-validation signal: the unsupervised method independently corroborates IBM's ground truth without seeing the `Is Laundering` flag.

---

## Topology Classifier

The same classifier runs on both `G_suspicious` and `G_unlabelled`. Priority order:

```
CYCLE → FAN_OUT → FAN_IN → SCATTER_GATHER → GATHER_SCATTER → BIPARTITE → STACK → RANDOM
```

Components with fewer than 3 nodes are excluded. The priority order ensures the most structurally distinctive patterns (CYCLE) are classified before generic ones (RANDOM).

---

## Confidence Score

```
confidence = 0.4 × severity_weight
           + 0.3 × (node_count / max_node_count_in_batch)
           + 0.3 × amount_concentration
```

Where `amount_concentration = max_edge_amount / total_edge_amount`.

---

## Background Thread Architecture

`/health` must respond immediately at startup while the pipeline (8+ minutes) loads:

```python
t = threading.Thread(target=_run_pipeline, daemon=True)
t.start()
# FastAPI starts serving immediately
# PIPELINE_READY.set() is called when both modes complete + whitelist applied
```

`/status` returns `"loading"` until `PIPELINE_READY.is_set()`. The frontend polls every 3 seconds and advances its 5-stage loading animation accordingly.

---

## Visual Design

The frontend uses a light theme (white background) with two Google Fonts:
- **Syne 700/800** — headings, numbers, pattern names
- **DM Mono** — body text, labels, data values

This matches the project's methodology diagram aesthetic. Card components use a 4px colored left accent bar rather than heavy colored backgrounds, keeping the interface readable at high information density. All labels are UPPERCASE with 0.08em letter-spacing.

Pattern names are always displayed fully formatted:
- `fanOut` → `FAN-OUT`
- `scatterGather` → `SCATTER-GATHER`
- etc.

This is enforced by the `formatPatternName()` helper called at every display site.

---

## Validation

`backend/validator.py` runs both alert sets against `HI-Small_Patterns.txt`. Matching uses >80% account-set overlap. Low recall is expected — the 48-hour window captures only a slice of multi-day schemes. CYCLE achieves 100% precision when fully captured in the window.

"""
Validates detected alerts (both labelled and unlabelled modes) against
the ground-truth HI-Small_Patterns.txt.
"""
import re, json
from pathlib import Path
from collections import defaultdict

from pipeline import load_and_build, find_suspicious_unlabelled
from detector import detect_all_patterns
from serializer import serialize_alerts

DATA_DIR      = Path(__file__).parent.parent / "data"
PATTERNS_PATH = DATA_DIR / "HI-Small_Patterns.txt"
RESULTS_PATH  = DATA_DIR / "validation_results.json"

TYPE_MAP = {
    "FAN-IN": "FAN_IN", "FAN-OUT": "FAN_OUT",
    "SCATTER-GATHER": "SCATTER_GATHER", "GATHER-SCATTER": "GATHER_SCATTER",
    "CYCLE": "CYCLE", "BIPARTITE": "BIPARTITE",
    "STACK": "STACK", "RANDOM": "RANDOM",
}

CAMEL_TO_UPPER = {
    "fanOut": "FAN_OUT", "fanIn": "FAN_IN", "cycle": "CYCLE",
    "scatterGather": "SCATTER_GATHER", "gatherScatter": "GATHER_SCATTER",
    "bipartite": "BIPARTITE", "stack": "STACK", "random": "RANDOM",
}


def _parse_patterns(path: Path) -> dict:
    """Returns {frozenset_of_account_ids: pattern_type_upper}."""
    ground_truth: dict = {}
    current_type = None
    current_accounts: set = set()
    in_block = False

    begin_re = re.compile(r"BEGIN LAUNDERING ATTEMPT\s*-\s*([\w-]+)", re.IGNORECASE)
    end_re   = re.compile(r"END LAUNDERING ATTEMPT", re.IGNORECASE)

    with open(path, encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            m = begin_re.search(line)
            if m:
                if in_block and current_accounts:
                    ground_truth[frozenset(current_accounts)] = current_type
                current_type = TYPE_MAP.get(m.group(1).upper(), m.group(1).upper())
                current_accounts = set()
                in_block = True
                continue
            if end_re.search(line):
                if in_block and current_accounts:
                    ground_truth[frozenset(current_accounts)] = current_type
                in_block = False
                current_type = None
                current_accounts = set()
                continue
            if in_block:
                parts = line.split(",")
                if len(parts) >= 5:
                    try:
                        current_accounts.add(parts[2].strip())
                        current_accounts.add(parts[4].strip())
                    except IndexError:
                        pass

    if in_block and current_accounts:
        ground_truth[frozenset(current_accounts)] = current_type

    return ground_truth


def _overlap_ratio(set_a: frozenset, set_b: frozenset) -> float:
    if not set_a or not set_b:
        return 0.0
    return len(set_a & set_b) / max(len(set_a), len(set_b))


def _validate_alert_set(serialized: list, ground_truth: dict) -> dict:
    """
    Validate a list of serialized alerts against the ground truth.
    Returns a metrics dict.
    """
    records = []
    matched_gt_keys: set = set()

    for alert in serialized:
        alert_accounts = frozenset(n["id"] for n in alert["nodes"])
        detected_type  = CAMEL_TO_UPPER.get(alert["patternType"], alert["patternType"])

        best_ratio   = 0.0
        best_gt_key  = None
        best_gt_type = None

        for gt_key, gt_type in ground_truth.items():
            ratio = _overlap_ratio(alert_accounts, gt_key)
            if ratio > best_ratio:
                best_ratio   = ratio
                best_gt_key  = gt_key
                best_gt_type = gt_type

        if best_ratio > 0.8:
            matched_gt_keys.add(best_gt_key)
            status = "correct" if detected_type == best_gt_type else "wrong_label"
        else:
            status       = "unmatched"
            best_gt_type = None

        records.append({
            "alert_id":      alert["id"],
            "detected_type": detected_type,
            "gt_type":       best_gt_type,
            "overlap":       round(best_ratio, 3),
            "status":        status,
        })

    matched = [r for r in records if r["status"] in ("correct", "wrong_label")]

    det_counts:     dict[str, int] = defaultdict(int)
    correct_counts: dict[str, int] = defaultdict(int)
    for r in records:
        det_counts[r["detected_type"]] += 1
        if r["status"] == "correct":
            correct_counts[r["detected_type"]] += 1

    precision: dict[str, float] = {
        pt: round(correct_counts[pt] / det_counts[pt], 3)
        for pt in det_counts
    }

    gt_counts: dict[str, int] = defaultdict(int)
    found_gt:  dict[str, int] = defaultdict(int)
    for gt_type in ground_truth.values():
        gt_counts[gt_type] += 1
    for r in records:
        if r["status"] in ("correct", "wrong_label") and r["gt_type"]:
            found_gt[r["gt_type"]] += 1

    recall: dict[str, float] = {
        pt: round(found_gt[pt] / gt_counts[pt], 3)
        for pt in gt_counts
    }

    accuracy = (
        round(sum(1 for r in matched if r["status"] == "correct") / len(matched), 3)
        if matched else 0.0
    )

    all_types = sorted(set(list(det_counts.keys()) + list(gt_counts.keys())))
    confusion: dict[str, dict] = {t: defaultdict(int) for t in all_types}
    for r in records:
        if r["status"] in ("correct", "wrong_label"):
            confusion[r["detected_type"]][r["gt_type"]] += 1

    overall_precision = round(len(matched) / len(serialized), 3) if serialized else 0.0
    overall_recall    = round(len(matched_gt_keys) / len(ground_truth), 3) if ground_truth else 0.0

    return {
        "total_alerts":          len(serialized),
        "matched":               len(matched),
        "unmatched":             len([r for r in records if r["status"] == "unmatched"]),
        "overall_accuracy":      accuracy,
        "overall_precision":     overall_precision,
        "overall_recall":        overall_recall,
        "matched_gt_count":      len(matched_gt_keys),
        "per_pattern_precision": precision,
        "per_pattern_recall":    recall,
        "confusion_table":       {k: dict(v) for k, v in confusion.items()},
        "records":               records,
    }


def validate_detections() -> dict:
    print("Loading pipeline...")
    df_suspicious, df_full, G_suspicious, G_full = load_and_build()

    # Labelled mode
    labelled_raw   = detect_all_patterns(G_suspicious, df_suspicious, source="labelled")
    labelled_ser   = serialize_alerts(labelled_raw)

    # Unlabelled mode
    print("Running unlabelled detection...")
    G_unlabelled, account_signals = find_suspicious_unlabelled(df_full)
    unlabelled_raw = detect_all_patterns(
        G_unlabelled, df_full,
        source="unlabelled", account_signals=account_signals, id_prefix="u_",
    )
    unlabelled_ser = serialize_alerts(unlabelled_raw)

    print(f"\nParsing {PATTERNS_PATH.name}...")
    ground_truth = _parse_patterns(PATTERNS_PATH)
    print(f"Ground truth blocks parsed: {len(ground_truth)}")

    lab_metrics   = _validate_alert_set(labelled_ser,   ground_truth)
    unlab_metrics = _validate_alert_set(unlabelled_ser, ground_truth)

    # Overlap between the two alert sets (>80% account overlap)
    lab_sets = [frozenset(n["id"] for n in a["nodes"]) for a in labelled_ser]
    overlap_count = 0
    for u in unlabelled_ser:
        u_set = frozenset(n["id"] for n in u["nodes"])
        for l_set in lab_sets:
            inter = len(u_set & l_set)
            denom = max(len(u_set), len(l_set))
            if denom and inter / denom > 0.8:
                overlap_count += 1
                break

    results = {
        "total_gt_blocks": len(ground_truth),
        "labelled":        lab_metrics,
        "unlabelled":      unlab_metrics,
        "overlap_count":   overlap_count,
        "comparison": {
            "labelled_alerts":     len(labelled_ser),
            "unlabelled_alerts":   len(unlabelled_ser),
            "overlap_count":       overlap_count,
            "labelled_precision":  lab_metrics["overall_precision"],
            "labelled_recall":     lab_metrics["overall_recall"],
            "unlabelled_precision": unlab_metrics["overall_precision"],
            "unlabelled_recall":   unlab_metrics["overall_recall"],
        },
    }

    RESULTS_PATH.write_text(json.dumps(results, indent=2))
    print(f"\nResults saved to {RESULTS_PATH}")

    # ── Comparison table ──────────────────────────────────────────────────────
    print("\n┌─────────────┬──────────────┬────────────┬───────────┬────────┐")
    print("│ Mode        │ Alerts Found │ Matched GT │ Precision │ Recall │")
    print("├─────────────┼──────────────┼────────────┼───────────┼────────┤")
    print(f"│ Labelled    │ {len(labelled_ser):>12} │ "
          f"{lab_metrics['matched']:>10} │ "
          f"{lab_metrics['overall_precision']:>8.1%}  │ "
          f"{lab_metrics['overall_recall']:>5.1%}  │")
    print(f"│ Unlabelled  │ {len(unlabelled_ser):>12} │ "
          f"{unlab_metrics['matched']:>10} │ "
          f"{unlab_metrics['overall_precision']:>8.1%}  │ "
          f"{unlab_metrics['overall_recall']:>5.1%}  │")
    print(f"│ Overlap     │ {overlap_count:>12} │ {'—':>10} │ {'—':>9} │ {'—':>6} │")
    print("└─────────────┴──────────────┴────────────┴───────────┴────────┘")

    return results


if __name__ == "__main__":
    validate_detections()

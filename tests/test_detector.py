import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import pytest
from pipeline import load_and_build, find_suspicious_unlabelled
from detector import detect_all_patterns
from serializer import serialize_alerts

VALID_PATTERN_TYPES = {
    "fanOut", "fanIn", "cycle", "scatterGather",
    "gatherScatter", "bipartite", "stack", "random",
}

REQUIRED_TOP_KEYS = {
    "id", "name", "sub", "severity", "confidence", "patternType",
    "timeSpan", "hops", "totalMoved", "routeNodes", "description",
    "nodes", "edges", "transactions", "source", "signalsTriggered",
}

REQUIRED_NODE_KEYS = {"id", "role", "sev", "bank", "vol", "txn"}


@pytest.fixture(scope="module")
def labelled_chain():
    df_suspicious, df_full, G_suspicious, G_full = load_and_build()
    raw = detect_all_patterns(G_suspicious, df_suspicious, source="labelled")
    return serialize_alerts(raw)


@pytest.fixture(scope="module")
def unlabelled_chain():
    _, df_full, _, _ = load_and_build()
    G_unlabelled, account_signals = find_suspicious_unlabelled(df_full)
    raw = detect_all_patterns(
        G_unlabelled, df_full,
        source="unlabelled", account_signals=account_signals, id_prefix="u_",
    )
    return serialize_alerts(raw)


# ── Labelled alerts ───────────────────────────────────────────────────────────

def test_at_least_one_labelled_alert(labelled_chain):
    assert len(labelled_chain) > 0, "No labelled alerts detected"


def test_labelled_source_field(labelled_chain):
    for a in labelled_chain:
        assert a["source"] == "labelled", f"Alert {a['id']} has wrong source: {a['source']}"


def test_labelled_signals_empty(labelled_chain):
    for a in labelled_chain:
        assert a["signalsTriggered"] == [], (
            f"Labelled alert {a['id']} should have no signalsTriggered"
        )


def test_all_required_keys(labelled_chain):
    for alert in labelled_chain:
        missing = REQUIRED_TOP_KEYS - set(alert.keys())
        assert not missing, f"Alert {alert.get('id')} missing keys: {missing}"


def test_edges_sorted_by_txidx(labelled_chain):
    for alert in labelled_chain:
        idxs = [e["txIdx"] for e in alert["edges"]]
        assert idxs == list(range(len(idxs))), f"Alert {alert['id']} edges not sorted"


def test_node_fields(labelled_chain):
    for alert in labelled_chain:
        for node in alert["nodes"]:
            missing = REQUIRED_NODE_KEYS - set(node.keys())
            assert not missing, f"Node {node.get('id')} missing: {missing}"


def test_valid_pattern_types(labelled_chain):
    for alert in labelled_chain:
        assert alert["patternType"] in VALID_PATTERN_TYPES, \
            f"Unknown patternType: {alert['patternType']}"


def test_confidence_range(labelled_chain):
    for alert in labelled_chain:
        c = alert["confidence"]
        assert 0.0 <= c <= 1.0, f"Confidence out of range: {c}"


# ── Unlabelled alerts ─────────────────────────────────────────────────────────

def test_at_least_one_unlabelled_alert(unlabelled_chain):
    assert len(unlabelled_chain) > 0, "No unlabelled alerts detected"


def test_unlabelled_source_field(unlabelled_chain):
    for a in unlabelled_chain:
        assert a["source"] == "unlabelled", f"Alert {a['id']} has wrong source: {a['source']}"


def test_unlabelled_ids_prefixed(unlabelled_chain):
    for a in unlabelled_chain:
        assert a["id"].startswith("u_"), f"Unlabelled alert id not prefixed: {a['id']}"


def test_unlabelled_required_keys(unlabelled_chain):
    for alert in unlabelled_chain:
        missing = REQUIRED_TOP_KEYS - set(alert.keys())
        assert not missing, f"Alert {alert.get('id')} missing keys: {missing}"


def test_unlabelled_valid_pattern_types(unlabelled_chain):
    for alert in unlabelled_chain:
        assert alert["patternType"] in VALID_PATTERN_TYPES, \
            f"Unknown patternType: {alert['patternType']}"


def test_pattern_breakdown(labelled_chain, unlabelled_chain):
    def _counts(chain):
        c: dict[str, int] = {}
        for a in chain:
            c[a["patternType"]] = c.get(a["patternType"], 0) + 1
        return c

    print("\n=== Labelled Pattern Breakdown ===")
    for pt, cnt in sorted(_counts(labelled_chain).items()):
        print(f"  {pt}: {cnt}")
    print(f"  TOTAL: {len(labelled_chain)}")

    print("\n=== Unlabelled Pattern Breakdown ===")
    for pt, cnt in sorted(_counts(unlabelled_chain).items()):
        print(f"  {pt}: {cnt}")
    print(f"  TOTAL: {len(unlabelled_chain)}")

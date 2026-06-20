"""
Core unit tests for the AML detection backend.
Runs on every push/PR to catch regressions before merging.
"""
import sys
from pathlib import Path

# Allow imports from backend/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import networkx as nx
import numpy as np
import pytest


# ── ml_model tests ────────────────────────────────────────────────────────────

from ml_model import _gini, extract_features, FEATURE_COLS


class TestGini:
    def test_equal_amounts(self):
        assert _gini([100, 100, 100]) == pytest.approx(0.0, abs=0.01)

    def test_single_amount(self):
        assert _gini([500]) == pytest.approx(0.0, abs=0.01)

    def test_empty(self):
        assert _gini([]) == 0.0

    def test_all_zeros(self):
        assert _gini([0, 0, 0]) == 0.0

    def test_unequal_distribution(self):
        result = _gini([0, 0, 0, 1000])
        assert result > 0.5

    def test_returns_float(self):
        assert isinstance(_gini([1, 2, 3]), float)


class TestExtractFeatures:
    def _make_graph(self):
        G = nx.DiGraph()
        G.add_edge("A", "B", amount_paid=1000, from_bank="Bank1", to_bank="Bank2")
        G.add_edge("B", "C", amount_paid=2000, from_bank="Bank2", to_bank="Bank3")
        G.add_edge("C", "A", amount_paid=500, from_bank="Bank3", to_bank="Bank1")
        return G

    def test_returns_all_feature_cols(self):
        feats = extract_features(self._make_graph())
        for col in FEATURE_COLS:
            assert col in feats, f"Missing feature: {col}"

    def test_empty_graph(self):
        feats = extract_features(nx.DiGraph())
        assert all(v == 0.0 for v in feats.values())

    def test_node_edge_counts(self):
        feats = extract_features(self._make_graph())
        assert feats["n_nodes"] == 3.0
        assert feats["n_edges"] == 3.0

    def test_cycle_detected(self):
        feats = extract_features(self._make_graph())
        assert feats["has_cycle"] == 1.0

    def test_no_cycle(self):
        G = nx.DiGraph()
        G.add_edge("A", "B", amount_paid=100)
        G.add_edge("B", "C", amount_paid=200)
        feats = extract_features(G)
        assert feats["has_cycle"] == 0.0

    def test_amounts(self):
        feats = extract_features(self._make_graph())
        assert feats["total_amount"] == 3500.0
        assert feats["max_amount"] == 2000.0

    def test_bank_count(self):
        feats = extract_features(self._make_graph())
        assert feats["n_banks"] == 3.0


# ── detector tests ────────────────────────────────────────────────────────────

from detector import _classify, _compute_hops, _assign_roles


class TestClassify:
    def test_cycle(self):
        G = nx.DiGraph()
        G.add_edges_from([("A", "B"), ("B", "C"), ("C", "A")])
        assert _classify(G) == "CYCLE"

    def test_fan_out(self):
        G = nx.DiGraph()
        G.add_edges_from([("H", "A"), ("H", "B"), ("H", "C")])
        assert _classify(G) == "FAN_OUT"

    def test_fan_in(self):
        G = nx.DiGraph()
        G.add_edges_from([("A", "H"), ("B", "H"), ("C", "H")])
        assert _classify(G) == "FAN_IN"

    def test_scatter_gather(self):
        G = nx.DiGraph()
        G.add_edges_from([("O", "M1"), ("M1", "D")])
        # Need n >= 3 and exactly 1 origin, 1 dest, rest middlemen
        G.add_edge("O", "M2")
        G.add_edge("M2", "D")
        # This is actually more complex; build exact structure
        G2 = nx.DiGraph()
        G2.add_edges_from([("O", "M1"), ("M1", "D"), ("O", "M2"), ("M2", "D")])
        # O has out_deg=2, in_deg=0; D has in_deg=2, out_deg=0; M1,M2 have in=1,out=1
        # n=4, origins=1, dests=1, middles=2 => n-2=2 ✓
        result = _classify(G2)
        assert result == "SCATTER_GATHER"

    def test_gather_scatter(self):
        G = nx.DiGraph()
        G.add_edges_from([("S1", "H"), ("S2", "H"), ("H", "D1"), ("H", "D2")])
        assert _classify(G) == "GATHER_SCATTER"

    def test_random_fallback(self):
        G = nx.DiGraph()
        G.add_edges_from([("A", "B"), ("C", "D"), ("B", "C"), ("D", "A"), ("A", "C")])
        result = _classify(G)
        assert result in ("CYCLE", "FAN_OUT", "FAN_IN", "SCATTER_GATHER",
                          "GATHER_SCATTER", "BIPARTITE", "STACK", "RANDOM")


class TestComputeHops:
    def test_cycle_hops(self):
        G = nx.DiGraph()
        G.add_edges_from([("A", "B"), ("B", "C"), ("C", "A")])
        assert _compute_hops(G, "CYCLE") == 3

    def test_linear_hops(self):
        G = nx.DiGraph()
        G.add_edges_from([("A", "B"), ("B", "C"), ("C", "D")])
        assert _compute_hops(G, "STACK") == 3


class TestAssignRoles:
    def test_fan_out_roles(self):
        G = nx.DiGraph()
        G.add_edges_from([("H", "A"), ("H", "B"), ("H", "C")])
        roles, sevs = _assign_roles(G, "FAN_OUT")
        assert roles["H"] == "Distributor"
        assert sevs["H"] == "high"
        assert roles["A"] == "Recipient"

    def test_cycle_roles(self):
        G = nx.DiGraph()
        G.add_edges_from([("A", "B"), ("B", "C"), ("C", "A")])
        roles, sevs = _assign_roles(G, "CYCLE")
        assert all(r == "Cycle Member" for r in roles.values())


# ── whitelist tests ───────────────────────────────────────────────────────────

from whitelist import is_exempt, filter_alerts, DEFAULT_WHITELIST


class TestIsExempt:
    def test_explicit_account(self):
        wl = {**DEFAULT_WHITELIST, "exempt_accounts": ["ACCT-001"]}
        assert is_exempt("ACCT-001", "SomeBank", "FAN_IN", wl) is True

    def test_non_exempt_account(self):
        assert is_exempt("ACCT-999", "Joe's Shop", "FAN_IN", DEFAULT_WHITELIST) is False

    def test_exempt_bank(self):
        assert is_exempt("X", "Federal Reserve", "FAN_IN", DEFAULT_WHITELIST) is True

    def test_business_pattern(self):
        assert is_exempt("X", "CORP Industries", "FAN_OUT", DEFAULT_WHITELIST) is True

    def test_unknown_pattern(self):
        assert is_exempt("X", "Federal Reserve", "NONEXISTENT", DEFAULT_WHITELIST) is False


class TestFilterAlerts:
    def _make_alert(self, pattern, nodes):
        return {
            "pattern_type": pattern,
            "nodes": [{"node_id": n, "bank": b} for n, b in nodes],
        }

    def test_all_exempt_suppressed(self):
        alert = self._make_alert("FAN_IN", [("A", "Federal Reserve"), ("B", "Federal Reserve")])
        kept, suppressed = filter_alerts([alert], DEFAULT_WHITELIST)
        assert len(suppressed) == 1
        assert len(kept) == 0

    def test_none_exempt_kept(self):
        alert = self._make_alert("FAN_IN", [("A", "Joe's Shop"), ("B", "Jane's Deli")])
        kept, suppressed = filter_alerts([alert], DEFAULT_WHITELIST)
        assert len(kept) == 1
        assert len(suppressed) == 0

    def test_partial_exemption(self):
        alert = self._make_alert("FAN_IN", [("A", "Federal Reserve"), ("B", "Joe's Shop")])
        kept, suppressed = filter_alerts([alert], DEFAULT_WHITELIST)
        assert len(kept) == 1
        assert kept[0].get("partial_exemption") is True

    def test_empty_alerts(self):
        kept, suppressed = filter_alerts([], DEFAULT_WHITELIST)
        assert kept == []
        assert suppressed == []


# ── main.py overlap ratio test ────────────────────────────────────────────────

from main import _overlap_ratio


class TestOverlapRatio:
    def test_identical_sets(self):
        s = frozenset(["A", "B", "C"])
        assert _overlap_ratio(s, s) == pytest.approx(1.0)

    def test_no_overlap(self):
        assert _overlap_ratio(frozenset(["A"]), frozenset(["B"])) == 0.0

    def test_partial_overlap(self):
        a = frozenset(["A", "B", "C"])
        b = frozenset(["B", "C", "D"])
        assert _overlap_ratio(a, b) == pytest.approx(2 / 3)

    def test_empty_set(self):
        assert _overlap_ratio(frozenset(), frozenset(["A"])) == 0.0

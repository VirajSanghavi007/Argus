"""
Core unit tests for the AML detection backend.
Runs on every push/PR to catch regressions before merging.
"""
import sys
from pathlib import Path

# Allow imports from src/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import networkx as nx
import numpy as np
import pytest

from backend.core.whitelist import is_exempt, filter_alerts, DEFAULT_WHITELIST


# ── Whitelist tests ───────────────────────────────────────────────────────────

class TestIsExempt:
    def test_exempt_account(self):
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

"""
End-to-end tests for the AML backend that run WITHOUT the heavy ML stack.

These cover the parts of the pipeline that don't need torch / torch-geometric /
the IBM dataset / a trained model, so they run fast and green in CI:

  * topology classifier   (pure networkx)
  * alert serialization    (raw cluster dict -> frontend JSON shape)
  * SQLite persistence      (alerts + append-only decision audit trail)
  * API surface             (FastAPI TestClient: health + decision persist loop)

The one test that needs torch + a trained model is guarded with importorskip and
a model-exists check, so it's exercised locally but never fails the CI build.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import networkx as nx
import pytest


# ── 1. Topology classifier (no torch) ───────────────────────────────────────

class TestTopologyClassifier:
    def _classify(self, edges):
        from backend.pipeline.detection import _classify_topology
        g = nx.DiGraph()
        g.add_edges_from(edges)
        return _classify_topology(g)

    def test_fan_out(self):
        # one hub -> many leaves
        assert self._classify([("H", "A"), ("H", "B"), ("H", "C")]) == "FAN_OUT"

    def test_fan_in(self):
        # many senders -> one collector
        assert self._classify([("A", "H"), ("B", "H"), ("C", "H")]) == "FAN_IN"

    def test_cycle(self):
        assert self._classify([("A", "B"), ("B", "C"), ("C", "A")]) == "CYCLE"

    def test_linear_chain_is_classified(self):
        # A linear layering chain A->B->C->D resolves to a single-origin/
        # single-dest pattern (SCATTER_GATHER under the current rules). We assert
        # it lands on a known label rather than RANDOM — the exact bucket is a
        # product decision, but it must classify deterministically.
        result = self._classify([("A", "B"), ("B", "C"), ("C", "D")])
        assert result in ("SCATTER_GATHER", "STACK", "BIPARTITE")

    def test_too_small(self):
        assert self._classify([]) == "RANDOM"


# ── 2. Serialization (no torch) ──────────────────────────────────────────────

def _raw_alert(pattern="FAN_OUT", alert_id="mgnn_0"):
    """Build a raw cluster dict in the exact shape serialize_alerts expects."""
    return {
        "pattern_type": pattern,
        "alert_id": alert_id,
        "nodes_list": [
            {"node_id": "A", "sev": "critical", "role": "source",
             "bank": "1", "vol": 1_200_000.0, "txn": 3},
            {"node_id": "B", "sev": "high", "role": "destination",
             "bank": "2", "vol": 400_000.0, "txn": 1},
        ],
        "edges_list": [
            {"txIdx": 0, "source": "A", "target": "B", "amount_paid": 400_000.0},
        ],
        "transactions_list": [
            {"Account": "A", "Account.1": "B", "Amount Paid": 400_000.0,
             "Amount Received": 400_000.0, "Payment Currency": "USD",
             "Receiving Currency": "USD", "From Bank": "1", "To Bank": "2",
             "Payment Format": "Wire", "Timestamp": None},
        ],
        "sub": "test cluster",
        "severity": "critical",
        "confidence": 0.95,
        "ml_score": 0.95,
        "time_span": "2.0h",
        "hops": 1,
        "total_moved": 400_000.0,
        "route_nodes": ["A", "B"],
        "description": "FAN_OUT test",
        "source": "labelled",
        "signals_triggered": ["Multi-GNN edge classification"],
    }


class TestSerializer:
    def test_returns_list(self):
        from backend.core.serializer import serialize_alerts
        out = serialize_alerts([_raw_alert()])
        assert isinstance(out, list)
        assert len(out) == 1

    def test_camel_case_shape(self):
        from backend.core.serializer import serialize_alerts
        a = serialize_alerts([_raw_alert()])[0]
        for key in ("id", "name", "patternType", "severity", "confidence",
                    "mlScore", "totalMoved", "nodes", "edges", "transactions"):
            assert key in a, f"missing key: {key}"

    def test_pattern_name_and_type(self):
        from backend.core.serializer import serialize_alerts
        a = serialize_alerts([_raw_alert("FAN_OUT")])[0]
        assert a["name"] == "Fan-Out"
        assert a["patternType"] == "fanOut"

    def test_amount_formatting(self):
        from backend.core.serializer import serialize_alerts
        a = serialize_alerts([_raw_alert()])[0]
        assert a["totalMoved"] == "$400,000"


# ── 3. SQLite persistence + append-only audit trail ──────────────────────────

@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    from database import service as db_svc
    import config
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "test.db")
    monkeypatch.setattr(db_svc, "_conn", None)
    db_svc.init_db()
    yield db_svc
    if db_svc._conn:
        db_svc._conn.close()


class TestPersistence:
    def test_alerts_round_trip(self, temp_db):
        from backend.core.serializer import serialize_alerts
        serialized = serialize_alerts([_raw_alert(alert_id="mgnn_7")])
        temp_db.replace_alerts(serialized, scan_id="s1")
        loaded = temp_db.load_alerts()
        assert "mgnn_7" in loaded
        assert loaded["mgnn_7"]["patternType"] == "fanOut"

    def test_replace_clears_old(self, temp_db):
        from backend.core.serializer import serialize_alerts
        temp_db.replace_alerts(serialize_alerts([_raw_alert(alert_id="old")]))
        temp_db.replace_alerts(serialize_alerts([_raw_alert(alert_id="new")]))
        loaded = temp_db.load_alerts()
        assert "old" not in loaded and "new" in loaded

    def test_decision_audit_is_append_only(self, temp_db):
        temp_db.record_decision("mgnn_0", "review", "suspicious", "analyst1")
        temp_db.record_decision("mgnn_0", "confirm", "confirmed", "analyst2")
        # current = latest
        current = temp_db.current_decisions()
        assert current["mgnn_0"]["decision"] == "confirm"
        # history = full immutable trail, oldest first
        history = temp_db.decision_history("mgnn_0")
        assert [h["decision"] for h in history] == ["review", "confirm"]

    def test_decision_counts(self, temp_db):
        temp_db.record_decision("a", "confirm")
        temp_db.record_decision("b", "dismiss")
        temp_db.record_decision("c", "confirm")
        counts = temp_db.decision_counts()
        assert counts["confirm"] == 2 and counts["dismiss"] == 1


# ── 4. API surface (FastAPI TestClient, no torch needed at import time) ───────

@pytest.fixture
def client(tmp_path, monkeypatch):
    from database import service as db_svc
    import config
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "api.db")
    monkeypatch.setattr(db_svc, "_conn", None)
    db_svc.init_db()

    from backend.api import main
    from fastapi.testclient import TestClient
    from backend.core.serializer import serialize_alerts
    alert = serialize_alerts([_raw_alert(alert_id="mgnn_api")])[0]
    monkeypatch.setattr(main, "ALERTS", {"mgnn_api": alert})
    monkeypatch.setattr(main, "DECISIONS", {})
    return TestClient(main.app)


class TestApi:
    def test_health(self, client):
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"

    def test_list_alerts(self, client):
        r = client.get("/alerts")
        assert r.status_code == 200
        assert any(a["id"] == "mgnn_api" for a in r.json())

    def test_decision_persists_and_has_history(self, client):
        r = client.post("/alerts/mgnn_api/decision",
                        json={"decision": "confirm", "reason": "test", "analyst": "qa"})
        assert r.status_code == 200
        assert r.json()["status"] == "saved"

        # The decision survives as the current state...
        assert client.get("/decisions").json()["mgnn_api"]["decision"] == "confirm"
        # ...and is recorded in the immutable audit trail.
        hist = client.get("/alerts/mgnn_api/decision/history").json()["history"]
        assert len(hist) == 1 and hist[0]["decision"] == "confirm"

    def test_decision_on_unknown_alert_404(self, client):
        r = client.post("/alerts/does_not_exist/decision", json={"decision": "confirm"})
        assert r.status_code == 404


# ── 5. Full ML pipeline (guarded — skips in CI without torch + model) ─────────

class TestFullPipeline:
    def test_pipeline_runs_if_model_present(self):
        pytest.importorskip("torch_geometric")
        from config import MODEL_PATH
        from backend.models.multignn import load_multignn
        if not MODEL_PATH.exists():
            pytest.skip("No trained model — run training first")
        if load_multignn()[0] is None:
            pytest.skip("Trained model incompatible with current architecture — retrain")

        from backend.pipeline.detection import run_multignn_pipeline
        serialized, metrics = run_multignn_pipeline(max_rows=20_000)
        assert isinstance(serialized, list)
        assert isinstance(metrics, dict)
        # Every serialized alert must carry the keys the frontend reads.
        for a in serialized:
            assert {"id", "patternType", "severity", "confidence"} <= a.keys()

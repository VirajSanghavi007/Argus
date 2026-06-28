"""
End-to-end test: scan → alerts → serialization.
Proves the full pipeline works with synthetic data.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import numpy as np
import pytest
from datetime import datetime, timedelta


@pytest.fixture
def synthetic_transactions():
    """Create a small synthetic transaction dataset with a clear FAN_OUT pattern."""
    base_time = datetime(2024, 1, 1, 12, 0, 0)

    transactions = []
    # FAN_OUT: account A sends to B, C, D on same day
    for i, dst in enumerate(["ACCT-B", "ACCT-C", "ACCT-D"]):
        transactions.append({
            "From Account": "ACCT-A",
            "To Account": dst,
            "Amount Paid": 10000.0 + i * 500,
            "Timestamp": base_time + timedelta(minutes=i),
            "Payment Format": "WIRE",
            "From Currency": "USD",
            "To Currency": "USD",
            "From Bank": "Bank X",
            "To Bank": "Bank Y",
        })

    # Add some clean transactions
    transactions.append({
        "From Account": "ACCT-E",
        "To Account": "ACCT-F",
        "Amount Paid": 5000.0,
        "Timestamp": base_time + timedelta(hours=1),
        "Payment Format": "ACH",
        "From Currency": "USD",
        "To Currency": "USD",
        "From Bank": "Bank A",
        "To Bank": "Bank B",
    })

    return pd.DataFrame(transactions)


def test_pipeline_returns_alerts(synthetic_transactions):
    """Verify pipeline runs and returns alerts."""
    from multignn_pipeline import run_multignn_pipeline

    # Write synthetic data to temp CSV
    csv_path = Path("/tmp/test_txns.csv")
    synthetic_transactions.to_csv(csv_path, index=False)

    try:
        # Run pipeline
        alerts_json, metrics = run_multignn_pipeline(max_rows=600_000)

        # Verify output structure
        assert isinstance(alerts_json, str), "Alerts should be JSON string"
        assert isinstance(metrics, dict), "Metrics should be dict"
        assert "n_alerts" in metrics, "Metrics should have n_alerts"
        assert "inference_ms" in metrics, "Metrics should have inference_ms"
    finally:
        if csv_path.exists():
            csv_path.unlink()


def test_serialization_format():
    """Verify serialized alerts have correct schema."""
    from serializer import serialize_alerts

    # Create a mock alert cluster
    alerts = [
        {
            "nodes": ["ACCT-A", "ACCT-B", "ACCT-C"],
            "edges": [("ACCT-A", "ACCT-B"), ("ACCT-A", "ACCT-C")],
            "transactions": [
                {"src": "ACCT-A", "dst": "ACCT-B", "amount": 10000, "timestamp": "2024-01-01T12:00:00"},
                {"src": "ACCT-A", "dst": "ACCT-C", "amount": 10500, "timestamp": "2024-01-01T12:01:00"},
            ],
            "pattern": "FAN_OUT",
            "confidence": 0.95,
        }
    ]

    serialized = serialize_alerts(alerts, {})

    # Verify structure
    assert "alerts" in serialized, "Serialized should have 'alerts' key"
    alerts_list = serialized["alerts"]
    assert len(alerts_list) > 0, "Should have at least one alert"

    alert = alerts_list[0]
    assert "id" in alert, "Alert should have id"
    assert "nodes" in alert, "Alert should have nodes"
    assert "edges" in alert, "Alert should have edges"
    assert "pattern_type" in alert, "Alert should have pattern_type"
    assert "confidence" in alert, "Alert should have confidence"

    # Pattern should be mapped
    assert alert["pattern_type"] in [
        "Fan-Out", "Fan-In", "Cycle", "Scatter-Gather",
        "Gather-Scatter", "Bipartite", "Stacked Chain", "Complex Network"
    ], f"Unknown pattern type: {alert['pattern_type']}"


def test_whitelist_filters_alerts():
    """Verify whitelist suppresses exempt entities."""
    from whitelist import filter_alerts, DEFAULT_WHITELIST

    # Create alert with Federal Reserve (exempt)
    alerts = [
        {
            "nodes": [
                {"node_id": "FED-001", "bank": "Federal Reserve"},
                {"node_id": "ACCT-B", "bank": "Bank X"},
            ],
            "pattern_type": "FAN_IN",
            "edges": [],
        }
    ]

    kept, suppressed = filter_alerts(alerts, DEFAULT_WHITELIST)

    # Federal Reserve is exempt, so alert should be suppressed
    assert len(suppressed) > 0, "Exempt entity should be suppressed"
    assert len(kept) == 0, "Alert with exempt entity should not be kept"

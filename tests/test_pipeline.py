import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import pytest
import pandas as pd
from pipeline import load_and_build, find_suspicious_unlabelled

REQUIRED_EDGE_ATTRS = {"amount_paid", "timestamp", "from_bank", "to_bank", "payment_format", "receiving_currency"}


@pytest.fixture(scope="module")
def pipeline_data():
    return load_and_build()


@pytest.fixture(scope="module")
def unlabelled_data(pipeline_data):
    _, df_full, _, _ = pipeline_data
    return find_suspicious_unlabelled(df_full)


# ── Labelled pipeline tests ──────────────────────────────────────────────────

def test_suspicious_only_laundering(pipeline_data):
    df_suspicious, *_ = pipeline_data
    assert (df_suspicious["Is Laundering"] == 1).all(), "df_suspicious contains non-laundering rows"


def test_no_self_loops(pipeline_data):
    _, _, G_suspicious, _ = pipeline_data
    for u, v in G_suspicious.edges():
        assert u != v, f"Self-loop detected: {u}"


def test_min_nodes(pipeline_data):
    _, _, G_suspicious, _ = pipeline_data
    assert G_suspicious.number_of_nodes() >= 50, f"Only {G_suspicious.number_of_nodes()} nodes"


def test_edge_attributes(pipeline_data):
    _, _, G_suspicious, _ = pipeline_data
    for u, v, data in G_suspicious.edges(data=True):
        missing = REQUIRED_EDGE_ATTRS - set(data.keys())
        assert not missing, f"Edge ({u},{v}) missing attrs: {missing}"


def test_timestamp_window(pipeline_data):
    df_suspicious, *_ = pipeline_data
    start = pd.Timestamp("2022-09-01 00:00")
    end   = pd.Timestamp("2022-09-02 23:59")
    assert (df_suspicious["Timestamp"] >= start).all(), "Timestamps before window start"
    assert (df_suspicious["Timestamp"] <= end).all(), "Timestamps after window end"


# ── Unlabelled pipeline tests ────────────────────────────────────────────────

def test_unlabelled_min_nodes(unlabelled_data):
    G_unlabelled, _ = unlabelled_data
    assert G_unlabelled.number_of_nodes() >= 10, (
        f"G_unlabelled has only {G_unlabelled.number_of_nodes()} nodes"
    )


def test_unlabelled_all_accounts_have_two_signals(unlabelled_data):
    _, account_signals = unlabelled_data
    assert len(account_signals) > 0, "No suspicious accounts found"
    for acc, sigs in account_signals.items():
        assert len(sigs) >= 2, (
            f"Account {acc} has only {len(sigs)} signal(s): {sigs}"
        )


def test_unlabelled_no_self_loops(unlabelled_data):
    G_unlabelled, _ = unlabelled_data
    for u, v in G_unlabelled.edges():
        assert u != v, f"Self-loop in G_unlabelled: {u}"


def test_unlabelled_signals_are_valid(unlabelled_data):
    _, account_signals = unlabelled_data
    valid_signals = {
        "Rapid Fan-Out", "Round-Trip", "Structuring", "Layering Velocity",
        "Dormant Activation", "Currency Mismatch", "Smurfing",
    }
    for acc, sigs in account_signals.items():
        for sig in sigs:
            assert sig in valid_signals, f"Unknown signal '{sig}' for account {acc}"


def test_unlabelled_edge_attributes(unlabelled_data):
    G_unlabelled, _ = unlabelled_data
    for u, v, data in G_unlabelled.edges(data=True):
        missing = REQUIRED_EDGE_ATTRS - set(data.keys())
        assert not missing, f"Edge ({u},{v}) missing attrs: {missing}"

from typing import Any

PATTERN_CAMEL = {
    "FAN_OUT": "fanOut", "FAN_IN": "fanIn",
    "CYCLE": "cycle", "SCATTER_GATHER": "scatterGather",
    "GATHER_SCATTER": "gatherScatter", "BIPARTITE": "bipartite",
    "STACK": "stack", "RANDOM": "random",
}

PATTERN_NAME = {
    "FAN_OUT": "Fan-Out", "FAN_IN": "Fan-In",
    "CYCLE": "Cycle", "SCATTER_GATHER": "Scatter-Gather",
    "GATHER_SCATTER": "Gather-Scatter", "BIPARTITE": "Bipartite",
    "STACK": "Stack", "RANDOM": "Random Chain",
}

FMT_MAP = {
    "Wire": "RTGS", "ACH": "NEFT", "Cheque": "Cheque",
    "Credit Card": "Credit Card", "RTGS": "RTGS", "NEFT": "NEFT",
}


def _fmt_amount(val: float) -> str:
    return f"${int(val):,}"


def _fmt_ts(ts) -> str:
    if ts is None:
        return ""
    try:
        return ts.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return str(ts)


def serialize_alerts(alert_dicts: list[dict]) -> list[dict]:
    serialized = []
    for a in alert_dicts:
        pattern  = a["pattern_type"]
        alert_id = a["alert_id"]

        nodes = []
        for n in a["nodes_list"]:
            nodes.append({
                "id":    n["node_id"],
                "label": n["node_id"],
                "sev":   n["sev"],
                "role":  n["role"],
                "bank":  f"Bank-{n['bank']}",
                "vol":   _fmt_amount(n["vol"]),
                "txn":   n["txn"],
            })

        edges = []
        for e in a["edges_list"]:
            edges.append({
                "id":     f"e{e['txIdx']}",
                "source": e["source"],
                "target": e["target"],
                "label":  _fmt_amount(e["amount_paid"]),
                "txIdx":  e["txIdx"],
            })

        transactions = []
        for row in a["transactions_list"]:
            # Handle both dict from df.to_dict("records") and raw rows
            def _get(key, fallbacks=()):
                val = row.get(key)
                if val is not None:
                    return val
                for fb in fallbacks:
                    v = row.get(fb)
                    if v is not None:
                        return v
                return ""

            fmt_raw = str(_get("Payment Format"))
            fmt_mapped = FMT_MAP.get(fmt_raw, fmt_raw)

            ts = _get("Timestamp")
            ts_str = _fmt_ts(ts)

            transactions.append({
                "from":     str(_get("Account")),
                "to":       str(_get("Account.1")),
                "paid":     _fmt_amount(float(_get("Amount Paid", ("amount_paid",)) or 0)),
                "recv":     _fmt_amount(float(_get("Amount Received", ("receiving_amount",)) or 0)),
                "pCur":     str(_get("Payment Currency", ("pay_currency",))),
                "rCur":     str(_get("Receiving Currency", ("receiving_currency",))),
                "fromBank": str(_get("From Bank", ("from_bank",))),
                "toBank":   str(_get("To Bank", ("to_bank",))),
                "fmt":      fmt_mapped,
                "ts":       ts_str,
            })

        serialized.append({
            "id":               alert_id,
            "name":             PATTERN_NAME.get(pattern, pattern),
            "sub":              a["sub"],
            "severity":         a["severity"],
            "confidence":       a["confidence"],
            "patternType":      PATTERN_CAMEL.get(pattern, pattern.lower()),
            "timeSpan":         a["time_span"],
            "hops":             a["hops"],
            "totalMoved":       _fmt_amount(a["total_moved"]),
            "routeNodes":       [str(v) for v in a["route_nodes"]],
            "description":      a["description"],
            "nodes":            nodes,
            "edges":            edges,
            "transactions":     transactions,
            "source":           a.get("source", "labelled"),
            "signalsTriggered": a.get("signals_triggered", []),
        })

    return serialized

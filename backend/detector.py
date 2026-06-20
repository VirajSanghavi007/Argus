import logging
import networkx as nx
import pandas as pd
from typing import Any

logger = logging.getLogger("uvicorn.error")

# Phase 3 — ML pattern classifier (optional; falls back to rules if not trained)
_PATTERN_MODEL = None
try:
    from pattern_classifier import load_pattern_classifier, classify_subgraph_ml
    _loaded = load_pattern_classifier()
    if _loaded is not None:
        _PATTERN_MODEL = _loaded
        logger.info("ML pattern classifier loaded.")
    else:
        logger.info("ML pattern classifier not trained yet — using rule-based fallback.")
except Exception as _e:
    logger.info(f"ML pattern classifier unavailable ({_e}) — using rule-based fallback.")


SEVERITY_WEIGHT = {
    "SCATTER_GATHER": 1.0, "GATHER_SCATTER": 1.0, "STACK": 1.0, "BIPARTITE": 1.0,
    "CYCLE": 0.6, "FAN_IN": 0.6,
    "FAN_OUT": 0.3, "RANDOM": 0.3,
}

SEV_LABEL = {
    "SCATTER_GATHER": "HIGH", "GATHER_SCATTER": "HIGH", "STACK": "HIGH",
    "BIPARTITE": "HIGH", "CYCLE": "MEDIUM", "FAN_IN": "MEDIUM",
    "FAN_OUT": "HIGH", "RANDOM": "LOW",
}


def _classify(sub: nx.DiGraph) -> str:
    nodes = list(sub.nodes())
    n = len(nodes)
    in_deg  = dict(sub.in_degree())
    out_deg = dict(sub.out_degree())

    # CYCLE
    all_one = all(in_deg[v] == 1 and out_deg[v] == 1 for v in nodes)
    if all_one:
        try:
            nx.find_cycle(sub)
            return "CYCLE"
        except nx.NetworkXNoCycle:
            pass

    # FAN_OUT
    hubs_out = [v for v in nodes if out_deg[v] >= 3 and in_deg[v] == 0]
    leaves_in = [v for v in nodes if out_deg[v] == 0]
    if len(hubs_out) == 1 and len(leaves_in) == n - 1:
        return "FAN_OUT"

    # FAN_IN
    hubs_in  = [v for v in nodes if in_deg[v] >= 3 and out_deg[v] == 0]
    senders  = [v for v in nodes if in_deg[v] == 0]
    if len(hubs_in) == 1 and len(senders) == n - 1:
        return "FAN_IN"

    # SCATTER_GATHER
    origins = [v for v in nodes if in_deg[v] == 0]
    dests   = [v for v in nodes if out_deg[v] == 0]
    middles = [v for v in nodes if in_deg[v] == 1 and out_deg[v] == 1]
    if (len(origins) == 1 and len(dests) == 1 and
            len(middles) == n - 2 and n >= 3):
        return "SCATTER_GATHER"

    # GATHER_SCATTER
    hubs_gs = [v for v in nodes if in_deg[v] >= 2 and out_deg[v] >= 2]
    sources_gs = [v for v in nodes if in_deg[v] == 0]
    dests_gs   = [v for v in nodes if out_deg[v] == 0]
    if len(hubs_gs) == 1 and len(sources_gs) >= 2 and len(dests_gs) >= 2:
        return "GATHER_SCATTER"

    # BIPARTITE
    undirected = sub.to_undirected()
    if nx.is_bipartite(undirected):
        return "BIPARTITE"

    # STACK
    if nx.is_directed_acyclic_graph(sub):
        try:
            gens = list(nx.topological_generations(sub))
            if len(gens) >= 3:
                return "STACK"
        except nx.NetworkXError as exc:
            logger.warning("topological_generations failed: %s", exc)

    return "RANDOM"


def _assign_roles(sub: nx.DiGraph, pattern: str):
    in_deg  = dict(sub.in_degree())
    out_deg = dict(sub.out_degree())
    roles = {}
    sevs  = {}

    if pattern == "CYCLE":
        for v in sub.nodes():
            roles[v] = "Cycle Member"
            sevs[v]  = "medium"

    elif pattern == "FAN_OUT":
        hub = next(v for v in sub.nodes() if out_deg[v] >= 3 and in_deg[v] == 0)
        for v in sub.nodes():
            if v == hub:
                roles[v] = "Distributor"; sevs[v] = "high"
            else:
                roles[v] = "Recipient";   sevs[v] = "low"

    elif pattern == "FAN_IN":
        hub = next(v for v in sub.nodes() if in_deg[v] >= 3 and out_deg[v] == 0)
        for v in sub.nodes():
            if v == hub:
                roles[v] = "Aggregator"; sevs[v] = "medium"
            else:
                roles[v] = "Sender";     sevs[v] = "low"

    elif pattern == "SCATTER_GATHER":
        origin = next(v for v in sub.nodes() if in_deg[v] == 0)
        dest   = next(v for v in sub.nodes() if out_deg[v] == 0)
        for v in sub.nodes():
            if v == origin:
                roles[v] = "Origin";      sevs[v] = "high"
            elif v == dest:
                roles[v] = "Destination"; sevs[v] = "high"
            else:
                roles[v] = "Middleman";   sevs[v] = "medium"

    elif pattern == "GATHER_SCATTER":
        hub = next(v for v in sub.nodes() if in_deg[v] >= 2 and out_deg[v] >= 2)
        for v in sub.nodes():
            if v == hub:
                roles[v] = "Hub";         sevs[v] = "high"
            elif in_deg[v] == 0:
                roles[v] = "Source";      sevs[v] = "low"
            elif out_deg[v] == 0:
                roles[v] = "Destination"; sevs[v] = "medium"
            else:
                roles[v] = "Transit";     sevs[v] = "medium"

    elif pattern == "BIPARTITE":
        undirected = sub.to_undirected()
        top, bottom = nx.bipartite.sets(undirected)
        for v in sub.nodes():
            if v in top:
                roles[v] = "Coordinator";   sevs[v] = "high"
            else:
                roles[v] = "Joint Target";  sevs[v] = "medium"

    elif pattern == "STACK":
        gens = list(nx.topological_generations(sub))
        for i, layer in enumerate(gens):
            for v in layer:
                if i == 0:
                    roles[v] = "Source Layer";  sevs[v] = "high"
                elif i == len(gens) - 1:
                    roles[v] = "Exit Layer";    sevs[v] = "medium"
                else:
                    roles[v] = "Transit Layer"; sevs[v] = "medium"

    else:  # RANDOM
        for v in sub.nodes():
            roles[v] = "Chain Member"; sevs[v] = "low"

    return roles, sevs


def _get_edge_timestamps(sub: nx.DiGraph):
    ts_list = []
    for u, v, d in sub.edges(data=True):
        ts = d.get("timestamp")
        if ts is not None:
            ts_list.append(ts)
    return ts_list


def _time_span(timestamps):
    if not timestamps:
        return "0h 0m"
    delta = max(timestamps) - min(timestamps)
    total_min = int(delta.total_seconds() // 60)
    h, m = divmod(total_min, 60)
    return f"{h}h {m}m"


def _compute_hops(sub: nx.DiGraph, pattern: str) -> int:
    if pattern == "CYCLE":
        try:
            return len(nx.find_cycle(sub))
        except nx.NetworkXNoCycle:
            return len(sub.nodes())
    if nx.is_directed_acyclic_graph(sub):
        try:
            return nx.dag_longest_path_length(sub)
        except nx.NetworkXError as exc:
            logger.warning("dag_longest_path_length failed: %s", exc)
    return len(sub.nodes()) - 1


def _total_moved(sub: nx.DiGraph, pattern: str, roles: dict) -> float:
    if pattern == "CYCLE":
        total = sum(d.get("amount_paid", 0) for _, _, d in sub.edges(data=True))
        return total / 2
    # Sum edges leaving origin node(s) — fall back to all edges if no origin
    origins = [v for v, r in roles.items() if r in ("Origin", "Source", "Distributor", "Source Layer")]
    if origins:
        total = sum(
            d.get("amount_paid", 0)
            for u, _, d in sub.edges(data=True)
            if u in origins
        )
        if total > 0:
            return total
    return sum(d.get("amount_paid", 0) for _, _, d in sub.edges(data=True))


def _confidence(pattern: str, node_count: int, max_node_count: int, sub: nx.DiGraph) -> float:
    sw = SEVERITY_WEIGHT.get(pattern, 0.3)
    norm_nc = node_count / max_node_count if max_node_count > 0 else 0
    amounts = [d.get("amount_paid", 0) for _, _, d in sub.edges(data=True)]
    total_amt = sum(amounts)
    max_amt   = max(amounts) if amounts else 0
    ac = max_amt / total_amt if total_amt > 0 else 0
    return round(0.4 * sw + 0.3 * norm_nc + 0.3 * ac, 4)


def _sub_description(pattern: str, sub: nx.DiGraph, roles: dict) -> str:
    in_deg  = dict(sub.in_degree())
    out_deg = dict(sub.out_degree())
    n = sub.number_of_nodes()

    if pattern == "CYCLE":
        return f"{n}-hop Cycle"
    if pattern == "FAN_OUT":
        hub = next((v for v, r in roles.items() if r == "Distributor"), None)
        deg = out_deg.get(hub, 0) if hub else 0
        return f"Max {deg}-degree Fan-Out"
    if pattern == "FAN_IN":
        hub = next((v for v, r in roles.items() if r == "Aggregator"), None)
        deg = in_deg.get(hub, 0) if hub else 0
        return f"{deg}-sender Fan-In"
    if pattern == "SCATTER_GATHER":
        mid = sum(1 for v, r in roles.items() if r == "Middleman")
        return f"{mid} intermediaries → 1 destination"
    if pattern == "GATHER_SCATTER":
        srcs = sum(1 for v, r in roles.items() if r == "Source")
        dsts = sum(1 for v, r in roles.items() if r == "Destination")
        return f"{srcs} sources → hub → {dsts} destinations"
    if pattern == "BIPARTITE":
        return f"{n}-node Bipartite Transfer"
    if pattern == "STACK":
        gens = list(nx.topological_generations(sub))
        return f"{len(gens)}-layer Stack"
    return f"{n}-node Random Chain"


def _description(pattern: str, sub: nx.DiGraph) -> str:
    descs = {
        "CYCLE": (
            "Funds are cycled through a closed loop of accounts, returning to the originator "
            "after passing through intermediaries. This circular flow is a classic layering technique "
            "designed to obscure the original source of illicit funds."
        ),
        "FAN_OUT": (
            "A single account rapidly distributes funds to multiple recipients simultaneously, "
            "a technique known as smurfing. This fragmentation is used to evade detection thresholds "
            "and obscure the aggregated transaction amount."
        ),
        "FAN_IN": (
            "Multiple source accounts funnel money into a single destination account in parallel. "
            "This aggregation pattern is used to pool illicit funds from many actors into one "
            "controlled account for extraction."
        ),
        "SCATTER_GATHER": (
            "Funds flow from one origin account through multiple intermediary accounts before "
            "converging at a single destination. This scatter-gather structure creates a layering "
            "fog that makes it difficult to trace the original source to the final recipient."
        ),
        "GATHER_SCATTER": (
            "A central hub account first aggregates funds from multiple source accounts, then "
            "redistributes them to multiple destination accounts. The hub acts as a mixer, "
            "breaking the direct link between sources and destinations."
        ),
        "BIPARTITE": (
            "Transactions form a clean two-group structure where one set of accounts exclusively "
            "sends to another set, with no intra-group transfers. This coordinated bipartite pattern "
            "suggests organised collusion between two distinct groups of actors."
        ),
        "STACK": (
            "Funds move through multiple distinct layers of accounts in a directed acyclic structure, "
            "creating a deep chain of transfers. Each layer adds separation between the origin and "
            "destination, making it harder to trace the money flow end-to-end."
        ),
        "RANDOM": (
            "The transaction pattern does not match any canonical laundering topology but still "
            "involves flagged accounts. The irregular structure may indicate an emerging or "
            "obfuscated scheme not covered by standard pattern libraries."
        ),
    }
    return descs.get(pattern, "Suspicious transaction cluster detected.")


def _route_nodes(sub: nx.DiGraph, roles: dict) -> list:
    if nx.is_directed_acyclic_graph(sub):
        try:
            return list(nx.dag_longest_path(sub))
        except nx.NetworkXError as exc:
            logger.warning("dag_longest_path failed: %s", exc)
    # For cycles and others, return nodes sorted by out_degree desc
    return sorted(sub.nodes(), key=lambda v: sub.out_degree(v), reverse=True)


def detect_all_patterns(
    G: nx.DiGraph,
    df: "pd.DataFrame",
    source: str = "labelled",
    account_signals: "dict | None" = None,
    id_prefix: str = "",
) -> list:
    """
    Classify each weakly-connected component of G into an AML pattern.

    Parameters
    ----------
    G               : Input graph (G_suspicious for labelled, G_unlabelled for unlabelled)
    df              : Transactions DataFrame (used to populate transactions_list per alert)
    source          : "labelled" | "unlabelled" — stored on each alert
    account_signals : {account_id: [signal_names]} from find_suspicious_unlabelled()
    id_prefix       : Prefix added to alert_id to avoid collisions when merging modes
    """
    components = [
        c for c in nx.weakly_connected_components(G)
        if len(c) >= 3
    ]

    alerts = []
    max_node_count = max((len(c) for c in components), default=1)
    counters: dict[str, int] = {}

    for comp in components:
        sub = G.subgraph(comp).copy()

        # Try ML classifier first; fall back to rules if unavailable or low confidence
        ml_pattern_conf = None
        if _PATTERN_MODEL is not None:
            try:
                ml_pat, ml_conf = classify_subgraph_ml(sub, _PATTERN_MODEL)
                if ml_conf >= 0.5:
                    pattern = ml_pat
                    ml_pattern_conf = ml_conf
                else:
                    pattern = _classify(sub)
            except Exception:
                pattern = _classify(sub)
        else:
            pattern = _classify(sub)

        roles, sevs = _assign_roles(sub, pattern)

        ts_list = _get_edge_timestamps(sub)
        time_span_str = _time_span(ts_list)
        hops = _compute_hops(sub, pattern)
        moved = _total_moved(sub, pattern, roles)
        conf  = _confidence(pattern, len(comp), max_node_count, sub)
        sub_str = _sub_description(pattern, sub, roles)
        desc = _description(pattern, sub)
        route = _route_nodes(sub, roles)

        # Aggregate signals triggered across all accounts in this component
        signals_in_comp: list[str] = []
        if account_signals:
            seen: set[str] = set()
            for v in comp:
                for sig in account_signals.get(str(v), []):
                    if sig not in seen:
                        seen.add(sig)
                        signals_in_comp.append(sig)

        # nodes_list
        nodes_list = []
        for v in sub.nodes():
            edges_touching = list(sub.in_edges(v, data=True)) + list(sub.out_edges(v, data=True))
            vol = sum(d.get("amount_paid", 0) for _, _, d in edges_touching)
            txn = len(edges_touching)
            bank_val = ""
            for u, w, d in sub.out_edges(v, data=True):
                bank_val = d.get("from_bank", "")
                break
            if not bank_val:
                for u, w, d in sub.in_edges(v, data=True):
                    bank_val = d.get("to_bank", "")
                    break
            nodes_list.append({
                "node_id": v,
                "role": roles.get(v, "Unknown"),
                "sev":  sevs.get(v, "low"),
                "vol":  vol,
                "txn":  txn,
                "bank": bank_val,
            })

        # edges_list sorted by timestamp
        raw_edges = []
        for u, v, d in sub.edges(data=True):
            raw_edges.append({
                "source": u,
                "target": v,
                "amount_paid": d.get("amount_paid", 0),
                "timestamp": d.get("timestamp"),
                "from_bank": d.get("from_bank", ""),
                "to_bank":   d.get("to_bank", ""),
                "payment_format": d.get("payment_format", ""),
                "receiving_currency": d.get("receiving_currency", ""),
            })
        raw_edges.sort(key=lambda e: (e["timestamp"] is None, e["timestamp"]))
        edges_list = [{ **e, "txIdx": idx } for idx, e in enumerate(raw_edges)]

        # transactions_list filtered to accounts in this component
        comp_set = set(comp)
        txn_rows = df[
            df["Account"].astype(str).isin(comp_set) |
            df["Account.1"].astype(str).isin(comp_set)
        ].copy()
        txn_rows = txn_rows.sort_values("Timestamp")
        transactions_list = txn_rows.to_dict("records")

        idx_key = counters.get(pattern, 0)
        counters[pattern] = idx_key + 1

        alerts.append({
            "alert_id":          f"{id_prefix}{pattern.lower()}_{idx_key}",
            "pattern_type":      pattern,
            "severity":          SEV_LABEL.get(pattern, "LOW"),
            "confidence":        conf,
            "pattern_ml_conf":   round(ml_pattern_conf, 4) if ml_pattern_conf is not None else None,
            "total_moved":       moved,
            "time_span":         time_span_str,
            "hops":              hops,
            "route_nodes":       route,
            "sub":               sub_str,
            "description":       desc,
            "nodes_list":        nodes_list,
            "edges_list":        edges_list,
            "transactions_list": transactions_list,
            "source":            source,
            "signals_triggered": signals_in_comp,
        })

    return alerts

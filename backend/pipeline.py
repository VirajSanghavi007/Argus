import logging
import pandas as pd
import networkx as nx
from pathlib import Path

logger   = logging.getLogger("uvicorn.error")
DATA_DIR = Path(__file__).parent.parent / "data"
CSV_PATH = DATA_DIR / "HI-Small_Trans.csv"

WINDOW_START = pd.Timestamp("2022-09-01 00:00")
WINDOW_END   = pd.Timestamp("2022-09-02 23:59")


def load_and_build():
    if not CSV_PATH.exists():
        raise FileNotFoundError(
            f"Dataset not found at {CSV_PATH}. "
            "Ensure HI-Small_Trans.csv is committed to the data/ directory."
        )
    df = pd.read_csv(CSV_PATH)
    logger.info(f"Loaded: {df.shape[0]} rows, {df.shape[1]} columns")

    df["Timestamp"] = pd.to_datetime(df["Timestamp"], format="%Y/%m/%d %H:%M")
    df.sort_values("Timestamp", inplace=True)
    df.reset_index(drop=True, inplace=True)

    df = df[(df["Timestamp"] >= WINDOW_START) & (df["Timestamp"] <= WINDOW_END)]
    logger.info(f"48-hr window: {len(df)} rows")

    # Remove self-loops (Reinvestment rows)
    df = df[df["Account"] != df["Account.1"]].copy()

    df_suspicious = df[df["Is Laundering"] == 1].copy()
    df_full = df.copy()

    logger.info(f"Suspicious rows: {len(df_suspicious)}")

    G_suspicious = _build_graph(df_suspicious)
    G_full       = _build_graph(df_full)

    logger.info(f"G_suspicious: {G_suspicious.number_of_nodes()} nodes, {G_suspicious.number_of_edges()} edges")
    return df_suspicious, df_full, G_suspicious, G_full


def find_suspicious_unlabelled(df_full: pd.DataFrame):
    """
    Detects suspicious accounts from unlabelled transaction data using 7 behavioural signals.

    Signals:
      1. Rapid Fan-Out   – sends to 3+ different recipients within any 2-hour bucket
      2. Round-Trip      – money returns to the originator within 24 hours (A→B→A)
      3. Structuring     – 3+ transactions in 1 hour, amounts in $9k-$9.999k or $49k-$49.999k
      4. Layering Vel.   – receives then re-sends ≥90% of the amount within any 6-hour bucket

    Accounts scoring ≥2 signals are flagged as suspicious.

    Returns:
        (G_unlabelled, account_signals)
        G_unlabelled     – DiGraph of edges touching flagged accounts
        account_signals  – {account_id: [signal_names_triggered]}
    """
    flagged: dict[str, list] = {}

    def _flag(accounts, signal_name: str):
        for acc in accounts:
            acc = str(acc)
            if acc not in flagged:
                flagged[acc] = []
            if signal_name not in flagged[acc]:
                flagged[acc].append(signal_name)

    logger.info("Unlabelled detection — running 7 signals...")

    # ── Signal 1: Rapid Fan-Out ──────────────────────────────────────────────
    # Account sends to 3+ distinct recipients within any fixed 2-hour bucket.
    s1 = (
        df_full[["Account", "Account.1", "Timestamp"]]
        .assign(bucket=lambda d: d["Timestamp"].dt.floor("2h"))
        .groupby(["Account", "bucket"])["Account.1"]
        .nunique()
    )
    s1_accs = s1[s1 >= 3].reset_index()["Account"].unique()
    _flag(s1_accs, "Rapid Fan-Out")
    logger.info(f"  Signal 1 (Rapid Fan-Out):    {len(s1_accs):6,} accounts")

    # ── Signal 2: Round-Trip within 24 hours ────────────────────────────────
    # For each unique (A→B) pair, check if (B→A) also exists with timestamps
    # within 24 hours.  Uses aggregated pairs to avoid O(n²) row-level merge.
    pairs = (
        df_full[["Account", "Account.1", "Timestamp"]]
        .groupby(["Account", "Account.1"])["Timestamp"]
        .agg(ts_min="min", ts_max="max")
        .reset_index()
    )
    pairs.columns = ["src", "dst", "ts_min", "ts_max"]
    rev = pairs.rename(columns={"src": "dst2", "dst": "src2",
                                "ts_min": "ts_min_r", "ts_max": "ts_max_r"})
    rt = pairs.merge(rev, left_on=["src", "dst"], right_on=["src2", "dst2"])
    rt["diff_sec"] = (rt["ts_min_r"] - rt["ts_max"]).dt.total_seconds().abs()
    rt24 = rt[rt["diff_sec"] <= 86400]
    rt_accs = pd.unique(pd.concat([rt24["src"], rt24["dst"]]))
    _flag(rt_accs, "Round-Trip")
    logger.info(f"  Signal 2 (Round-Trip):       {len(rt_accs):6,} accounts")

    # ── Signal 3: Structuring ────────────────────────────────────────────────
    # 3+ transactions within 1 hour where amounts cluster just below $10k or $50k.
    struct_mask = (
        ((df_full["Amount Paid"] >= 9_000) & (df_full["Amount Paid"] <= 9_999)) |
        ((df_full["Amount Paid"] >= 49_000) & (df_full["Amount Paid"] <= 49_999))
    )
    s3 = (
        df_full[struct_mask][["Account", "Timestamp"]]
        .assign(bucket=lambda d: d["Timestamp"].dt.floor("1h"))
        .groupby(["Account", "bucket"])
        .size()
    )
    s3_accs = s3[s3 >= 3].reset_index()["Account"].unique()
    _flag(s3_accs, "Structuring")
    logger.info(f"  Signal 3 (Structuring):      {len(s3_accs):6,} accounts")

    # ── Signal 4: Layering Velocity ──────────────────────────────────────────
    # Account receives funds then forwards ≥90% of the total within 6 hours.
    df_s4 = df_full[["Account", "Account.1", "Amount Paid", "Timestamp"]].copy()
    df_s4["bucket"] = df_s4["Timestamp"].dt.floor("6h")
    received = (
        df_s4.groupby(["Account.1", "bucket"])["Amount Paid"]
        .sum().reset_index()
        .rename(columns={"Account.1": "Account", "Amount Paid": "received"})
    )
    sent = (
        df_s4.groupby(["Account", "bucket"])["Amount Paid"]
        .sum().reset_index()
        .rename(columns={"Amount Paid": "sent"})
    )
    layer = received.merge(sent, on=["Account", "bucket"])
    layer = layer[layer["received"] > 0].copy()
    layer["ratio"] = layer["sent"] / layer["received"]
    s4_accs = layer[layer["ratio"] > 0.9]["Account"].unique()
    _flag(s4_accs, "Layering Velocity")
    logger.info(f"  Signal 4 (Layering Velocity):{len(s4_accs):6,} accounts")

    # ── Signal 5: Dormant Account Activation ────────────────────────────────
    # Account is silent in the first 24 hours of the window, then suddenly
    # sends or receives 3+ transactions within any 2-hour bucket in hours 24-48.
    MIDPOINT = WINDOW_START + pd.Timedelta(hours=24)
    df_before = df_full[df_full["Timestamp"] < MIDPOINT]
    df_after  = df_full[df_full["Timestamp"] >= MIDPOINT]

    active_before = (
        set(df_before["Account"].astype(str)) |
        set(df_before["Account.1"].astype(str))
    )
    # All accounts that appear after MIDPOINT but NOT before
    all_after = (
        set(df_after["Account"].astype(str)) |
        set(df_after["Account.1"].astype(str))
    )
    dormant_set = all_after - active_before

    if dormant_set:
        df_dormant = df_after[
            df_after["Account"].astype(str).isin(dormant_set)
        ][["Account", "Timestamp"]].copy()
        df_dormant["bucket"] = df_dormant["Timestamp"].dt.floor("2h")
        s5 = df_dormant.groupby(["Account", "bucket"]).size()
        s5_accs = s5[s5 >= 3].reset_index()["Account"].unique()
    else:
        s5_accs = []
    _flag(s5_accs, "Dormant Activation")
    logger.info(f"  Signal 5 (Dormant Activation): {len(s5_accs):5,} accounts")

    # ── Signal 6: Currency Mismatch Layering ─────────────────────────────────
    # Accounts that receive funds in one currency set and forward in a different
    # currency set — the classic FX-layering indicator.
    s6_df = df_full[["Account", "Account.1", "Payment Currency", "Receiving Currency"]].copy()
    recv_cur = (
        s6_df.groupby("Account.1")["Receiving Currency"]
        .apply(set).reset_index()
        .rename(columns={"Account.1": "Account", "Receiving Currency": "recv_curs"})
    )
    sent_cur = (
        s6_df.groupby("Account")["Payment Currency"]
        .apply(set).reset_index()
        .rename(columns={"Payment Currency": "sent_curs"})
    )
    cur_merge = recv_cur.merge(sent_cur, on="Account", how="inner")
    cur_merge["mismatch"] = cur_merge.apply(
        lambda r: not r["recv_curs"].issubset(r["sent_curs"]), axis=1
    )
    s6_accs = cur_merge[cur_merge["mismatch"]]["Account"].unique()
    _flag(s6_accs, "Currency Mismatch")
    logger.info(f"  Signal 6 (Currency Mismatch):  {len(s6_accs):5,} accounts")

    # ── Signal 7: Smurfing ───────────────────────────────────────────────────
    # 5+ different accounts each send amounts between $1,000 and $10,000 to the
    # same destination within any fixed 4-hour bucket.  Flag both the destination
    # (recipient of coordinated deposits) and the coordinated senders.
    smurf_mask = (
        (df_full["Amount Paid"] >= 1_000) & (df_full["Amount Paid"] <= 10_000)
    )
    df_smurf = df_full[smurf_mask][["Account", "Account.1", "Timestamp"]].copy()
    df_smurf["bucket"] = df_smurf["Timestamp"].dt.floor("4h")
    # Count distinct senders per (destination, 4h bucket)
    s7_counts = df_smurf.groupby(["Account.1", "bucket"])["Account"].nunique()
    s7_dests  = s7_counts[s7_counts >= 5].reset_index()["Account.1"].unique()
    _flag(s7_dests, "Smurfing")
    # Also flag the coordinated senders into those destinations
    s7_dest_set = set(str(d) for d in s7_dests)
    if s7_dest_set:
        df_senders = df_smurf[df_smurf["Account.1"].astype(str).isin(s7_dest_set)]
        s7_senders = (
            df_senders.groupby(["Account.1", "bucket"])["Account"]
            .apply(lambda x: set(str(v) for v in x))
            .reset_index()
        )
        all_senders: set = set()
        for _, row in s7_senders.iterrows():
            if len(row["Account"]) >= 5:
                all_senders |= row["Account"]
        _flag(list(all_senders), "Smurfing")
    s7_total = len(s7_dests) + len(all_senders if s7_dest_set else set())
    logger.info(f"  Signal 7 (Smurfing):           {s7_total:5,} accounts")

    # ── Score: keep accounts with ≥2 signals ────────────────────────────────
    account_signals = {acc: sigs for acc, sigs in flagged.items() if len(sigs) >= 2}
    logger.info(f"  Suspicious (≥2 signals):     {len(account_signals):6,} accounts")

    # ── Build G_unlabelled ───────────────────────────────────────────────────
    acc_set = set(account_signals.keys())
    mask = (
        df_full["Account"].astype(str).isin(acc_set) |
        df_full["Account.1"].astype(str).isin(acc_set)
    )
    df_unlab = df_full[mask].copy()
    G_unlabelled = _build_graph(df_unlab)
    logger.info(f"  G_unlabelled: {G_unlabelled.number_of_nodes()} nodes, "
               f"{G_unlabelled.number_of_edges()} edges")

    return G_unlabelled, account_signals


def _build_graph(df: pd.DataFrame) -> nx.DiGraph:
    G = nx.DiGraph()
    if df.empty:
        return G
    cols = ["Account", "Account.1", "Amount Paid", "Timestamp",
            "From Bank", "To Bank", "Payment Format", "Receiving Currency"]
    for row in df[cols].to_dict("records"):
        G.add_edge(
            str(row["Account"]), str(row["Account.1"]),
            amount_paid=float(row["Amount Paid"]),
            timestamp=row["Timestamp"],
            from_bank=str(row["From Bank"]),
            to_bank=str(row["To Bank"]),
            payment_format=str(row["Payment Format"]),
            receiving_currency=str(row["Receiving Currency"]),
        )
    return G

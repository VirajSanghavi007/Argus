"""
Dataset Analysis — profiles every AML dataset in data/ and writes a
consolidated report to docs/dataset_analysis_report.md.

Run:  python backend/dataset_analysis.py
"""

from __future__ import annotations
import json
import sys
from pathlib import Path
from collections import Counter
from datetime import datetime

import numpy as np
import pandas as pd

DATA = Path(__file__).parent.parent / "data"
OUT  = Path(__file__).parent.parent / "docs" / "dataset_analysis_report.md"

# ── helpers ──────────────────────────────────────────────────────────────────

def _pct(n, total):
    return f"{n/total*100:.4f}%" if total else "N/A"

def _fmt(n):
    return f"{n:,.0f}" if isinstance(n, (int, float, np.integer, np.floating)) else str(n)

def _section(title, lines):
    return [f"\n## {title}\n"] + lines + [""]


# ── IBM AMLWorld ─────────────────────────────────────────────────────────────

def analyse_ibm():
    lines = ["The IBM AMLWorld suite contains 6 transaction files (HI/LI × Small/Medium/Large) "
             "plus matching account files.\n"]
    summary_rows = []

    for prefix in ("HI", "LI"):
        for size in ("Small", "Medium", "Large"):
            tpath = DATA / "IBM" / f"{prefix}-{size}_Trans.csv"
            apath = DATA / "IBM" / f"{prefix}-{size}_accounts.csv"
            if not tpath.exists():
                continue

            # sample to keep memory sane on Large files
            n_lines = sum(1 for _ in open(tpath, encoding="utf-8")) - 1
            use_sample = n_lines > 2_000_000
            if use_sample:
                df = pd.read_csv(tpath, nrows=500_000)
                sample_note = f" (sampled first 500K of {n_lines:,})"
            else:
                df = pd.read_csv(tpath)
                sample_note = ""

            n_total = n_lines
            n_pos = int(df["Is Laundering"].sum())
            pos_rate = n_pos / len(df) if len(df) else 0

            accts = set()
            accts.update(df["Account"].astype(str).unique())
            accts.update(df["Account.1"].astype(str).unique())
            banks = set(df["From Bank"].astype(str).unique()) | set(df["To Bank"].astype(str).unique())

            amt = df["Amount Paid"].astype(float)
            currencies = df["Payment Currency"].nunique() if "Payment Currency" in df.columns else 0
            formats = df["Payment Format"].nunique() if "Payment Format" in df.columns else 0

            has_ts = "Timestamp" in df.columns
            if has_ts:
                ts = pd.to_datetime(df["Timestamp"], format="%Y/%m/%d %H:%M", errors="coerce")
                span = f"{ts.min()} → {ts.max()}"
            else:
                span = "N/A"

            # self-loops (reinvestments)
            self_loops = int((df["Account"].astype(str) == df["Account.1"].astype(str)).sum())

            tag = f"{prefix}-{size}"
            summary_rows.append({
                "variant": tag, "rows": n_total, "positives": n_pos,
                "pos_rate": f"{pos_rate*100:.4f}%", "accounts": len(accts),
                "banks": len(banks), "currencies": currencies, "formats": formats,
                "self_loops": self_loops, "amount_mean": f"${amt.mean():,.2f}",
                "amount_median": f"${amt.median():,.2f}", "amount_max": f"${amt.max():,.2f}",
                "time_span": span, "note": sample_note,
            })

    lines.append("| Variant | Rows | Positives | Pos Rate | Accounts | Banks | Currencies | Formats | Self-Loops | Amt Mean | Amt Median | Amt Max | Time Span |")
    lines.append("|---------|------|-----------|----------|----------|-------|------------|---------|------------|----------|------------|---------|-----------|")
    for r in summary_rows:
        lines.append(f"| {r['variant']}{r['note']} | {_fmt(r['rows'])} | {_fmt(r['positives'])} | {r['pos_rate']} | {_fmt(r['accounts'])} | {r['banks']} | {r['currencies']} | {r['formats']} | {_fmt(r['self_loops'])} | {r['amount_mean']} | {r['amount_median']} | {r['amount_max']} | {r['time_span']} |")

    # Deep dive on HI-Small (our training set)
    hi = pd.read_csv(DATA / "IBM" / "HI-Small_Trans.csv")
    hi["Timestamp"] = pd.to_datetime(hi["Timestamp"], format="%Y/%m/%d %H:%M")

    lines += ["", "### HI-Small Deep Dive (our training set)\n"]

    # laundering by payment format
    fmt_launder = hi.groupby("Payment Format")["Is Laundering"].agg(["sum", "count", "mean"])
    fmt_launder.columns = ["positives", "total", "rate"]
    fmt_launder = fmt_launder.sort_values("rate", ascending=False)
    lines.append("**Laundering rate by Payment Format:**\n")
    lines.append("| Format | Positives | Total | Rate |")
    lines.append("|--------|-----------|-------|------|")
    for fmt, row in fmt_launder.iterrows():
        lines.append(f"| {fmt} | {int(row['positives']):,} | {int(row['total']):,} | {row['rate']*100:.4f}% |")

    # laundering by currency
    cur_launder = hi.groupby("Payment Currency")["Is Laundering"].agg(["sum", "count", "mean"])
    cur_launder.columns = ["positives", "total", "rate"]
    cur_launder = cur_launder.sort_values("rate", ascending=False)
    lines.append("\n**Laundering rate by Currency:**\n")
    lines.append("| Currency | Positives | Total | Rate |")
    lines.append("|----------|-----------|-------|------|")
    for cur, row in cur_launder.iterrows():
        lines.append(f"| {cur} | {int(row['positives']):,} | {int(row['total']):,} | {row['rate']*100:.4f}% |")

    # amount distribution: laundering vs legit
    legit_amt = hi.loc[hi["Is Laundering"] == 0, "Amount Paid"]
    fraud_amt = hi.loc[hi["Is Laundering"] == 1, "Amount Paid"]
    lines.append("\n**Amount distribution (Laundering vs Legitimate):**\n")
    lines.append("| Stat | Legitimate | Laundering |")
    lines.append("|------|-----------|------------|")
    for stat in ["mean", "median", "std", "min", "max"]:
        lv = getattr(legit_amt, stat)()
        fv = getattr(fraud_amt, stat)()
        lines.append(f"| {stat} | ${lv:,.2f} | ${fv:,.2f} |")

    # temporal patterns
    hi["hour"] = hi["Timestamp"].dt.hour
    hour_rate = hi.groupby("hour")["Is Laundering"].mean()
    peak_hour = hour_rate.idxmax()
    lines.append(f"\n**Temporal insight:** Peak laundering hour = {peak_hour}:00 "
                 f"(rate {hour_rate[peak_hour]*100:.4f}%). "
                 f"Lowest = {hour_rate.idxmin()}:00 ({hour_rate.min()*100:.4f}%).")

    hi["dow"] = hi["Timestamp"].dt.dayofweek
    dow_rate = hi.groupby("dow")["Is Laundering"].mean()
    days = ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"]
    lines.append(f"Peak day = {days[dow_rate.idxmax()]} ({dow_rate.max()*100:.4f}%), "
                 f"lowest = {days[dow_rate.idxmin()]} ({dow_rate.min()*100:.4f}%).\n")

    # cross-border vs domestic
    hi["cross_border"] = hi["From Bank"] != hi["To Bank"]
    cb = hi.groupby("cross_border")["Is Laundering"].agg(["sum","count","mean"])
    lines.append("**Cross-bank vs Same-bank:**\n")
    lines.append("| Type | Positives | Total | Rate |")
    lines.append("|------|-----------|-------|------|")
    for is_cb, row in cb.iterrows():
        label = "Cross-bank" if is_cb else "Same-bank"
        lines.append(f"| {label} | {int(row['sum']):,} | {int(row['count']):,} | {row['mean']*100:.4f}% |")

    # top 10 accounts by laundering involvement
    src_fraud = hi.loc[hi["Is Laundering"]==1, "Account"].value_counts().head(10)
    lines.append("\n**Top 10 accounts by laundering transactions (as sender):**\n")
    lines.append("| Account | Laundering Txns |")
    lines.append("|---------|----------------|")
    for acct, cnt in src_fraud.items():
        lines.append(f"| {acct} | {cnt} |")

    return _section("1. IBM AMLWorld", lines)


# ── SAML-D ───────────────────────────────────────────────────────────────────

def analyse_saml():
    path = DATA / "SAML-D" / "SAML-D.csv"
    if not path.exists():
        return _section("2. SAML-D", ["Dataset not found."])

    n_lines = sum(1 for _ in open(path, encoding="utf-8")) - 1
    df = pd.read_csv(path, nrows=500_000)

    n_pos = int(df["Is_laundering"].sum())
    pos_rate = n_pos / len(df)

    types = df["Laundering_type"].value_counts()
    accts = set(df["Sender_account"].astype(str).unique()) | set(df["Receiver_account"].astype(str).unique())
    currencies = df["Payment_currency"].nunique()
    locations = set(df["Sender_bank_location"].unique()) | set(df["Receiver_bank_location"].unique())

    amt = df["Amount"].astype(float)

    lines = [
        f"- **Total rows:** {n_lines:,} (analysed first 500K)",
        f"- **Positives:** {n_pos:,} ({pos_rate*100:.4f}% in sample)",
        f"- **Unique accounts:** {len(accts):,}",
        f"- **Currencies:** {currencies}",
        f"- **Bank locations:** {len(locations)} countries",
        f"- **Amount:** mean=${amt.mean():,.2f}, median=${amt.median():,.2f}, max=${amt.max():,.2f}",
        "",
        "**Laundering type breakdown (first 500K):**\n",
        "| Type | Count | % of Sample |",
        "|------|-------|-------------|",
    ]
    for lt, cnt in types.items():
        lines.append(f"| {lt} | {cnt:,} | {cnt/len(df)*100:.3f}% |")

    # cross-border
    df["cross_border"] = df["Sender_bank_location"] != df["Receiver_bank_location"]
    cb = df.groupby("cross_border")["Is_laundering"].agg(["sum","count","mean"])
    lines += ["", "**Cross-border vs Domestic:**\n",
              "| Type | Positives | Total | Rate |",
              "|------|-----------|-------|------|"]
    for is_cb, row in cb.iterrows():
        label = "Cross-border" if is_cb else "Domestic"
        lines.append(f"| {label} | {int(row['sum']):,} | {int(row['count']):,} | {row['mean']*100:.4f}% |")

    # laundering rate by payment type
    pt = df.groupby("Payment_type")["Is_laundering"].agg(["sum","count","mean"]).sort_values("mean", ascending=False)
    lines += ["", "**Laundering rate by Payment Type:**\n",
              "| Payment Type | Positives | Total | Rate |",
              "|-------------|-----------|-------|------|"]
    for ptype, row in pt.iterrows():
        lines.append(f"| {ptype} | {int(row['sum']):,} | {int(row['count']):,} | {row['mean']*100:.4f}% |")

    return _section("2. SAML-D", lines)


# ── Elliptic ─────────────────────────────────────────────────────────────────

def analyse_elliptic():
    classes_path = DATA / "Elliptic" / "elliptic_txs_classes.csv"
    feat_path    = DATA / "Elliptic" / "elliptic_txs_features.csv"
    edge_path    = DATA / "Elliptic" / "elliptic_txs_edgelist.csv"

    if not all(p.exists() for p in (classes_path, feat_path, edge_path)):
        return _section("3. Elliptic Bitcoin", ["Dataset not found."])

    classes = pd.read_csv(classes_path)
    edges   = pd.read_csv(edge_path)
    feats   = pd.read_csv(feat_path, header=None)

    n_nodes = len(classes)
    n_edges = len(edges)
    n_features = feats.shape[1] - 1  # first col is txId

    illicit  = int((classes["class"] == "1").sum())
    licit    = int((classes["class"] == "2").sum())
    unknown  = int((classes["class"] == "unknown").sum())

    lines = [
        f"- **Nodes (transactions):** {n_nodes:,}",
        f"- **Edges (payment flows):** {n_edges:,}",
        f"- **Features per node:** {n_features}",
        f"- **Illicit:** {illicit:,} ({illicit/n_nodes*100:.2f}%)",
        f"- **Licit:** {licit:,} ({licit/n_nodes*100:.2f}%)",
        f"- **Unknown:** {unknown:,} ({unknown/n_nodes*100:.2f}%)",
        f"- **Imbalance (illicit / labelled):** {illicit/(illicit+licit)*100:.2f}%",
        f"- **Graph density:** {n_edges / (n_nodes * (n_nodes-1)):.8f}",
        "",
        "**Key characteristics:**",
        "- Bitcoin blockchain transactions across 49 time steps",
        "- Node features: 94 local + 72 aggregate (166 total), anonymized",
        "- No edge features — purely node-level classification",
        "- Temporal: nodes belong to distinct time steps, enabling temporal splits",
        "- Labels come from known entities (exchanges, darknet markets, etc.)",
    ]

    # degree distribution
    all_nodes = pd.concat([edges["txId1"], edges["txId2"]])
    deg = all_nodes.value_counts()
    lines += [
        "",
        "**Degree distribution:**",
        f"- Mean: {deg.mean():.2f}",
        f"- Median: {deg.median():.0f}",
        f"- Max: {deg.max()}",
        f"- Nodes with degree 1: {(deg==1).sum():,} ({(deg==1).sum()/n_nodes*100:.1f}%)",
    ]

    return _section("3. Elliptic Bitcoin", lines)


# ── TransXion ────────────────────────────────────────────────────────────────

def analyse_transxion():
    tx_path = DATA / "TransXion" / "data" / "tx.csv"
    person_path = DATA / "TransXion" / "data" / "person.csv"
    merchant_path = DATA / "TransXion" / "data" / "merchant.csv"

    if not tx_path.exists():
        return _section("4. TransXion", ["Dataset not found."])

    df = pd.read_csv(tx_path, nrows=500_000)
    persons = pd.read_csv(person_path)
    merchants = pd.read_csv(merchant_path)

    n_lines = sum(1 for _ in open(tx_path, encoding="utf-8")) - 1
    n_pos = int(df["Is Laundering"].sum())
    pos_rate = n_pos / len(df)

    accts = set(df["From Account"].astype(str).unique()) | set(df["To Account"].astype(str).unique())
    banks = set(df["From Bank"].astype(str).unique()) | set(df["To Bank"].astype(str).unique())
    currencies = df["Payment Currency"].nunique()
    formats = df["Payment Format"].nunique()
    amt = df["Amount Paid"].astype(float)

    lines = [
        f"- **Total rows:** {n_lines:,} (analysed first 500K)",
        f"- **Positives:** {n_pos:,} ({pos_rate*100:.4f}% in sample)",
        f"- **Unique accounts:** {len(accts):,}",
        f"- **Unique banks:** {len(banks):,}",
        f"- **Currencies:** {currencies}",
        f"- **Payment formats:** {formats}",
        f"- **Person profiles:** {len(persons):,}",
        f"- **Merchant profiles:** {len(merchants):,}",
        f"- **Amount:** mean=${amt.mean():,.2f}, median=${amt.median():,.2f}, max=${amt.max():,.2f}",
        "",
        "**Unique features of TransXion:**",
        "- Rich entity profiles (age, education, gender, marital status, occupation)",
        "- Merchant metadata (industry, registered capital, operating status)",
        "- Adversarially synthesized anomalies (not template-driven)",
        "- Profile-conditioned normal behaviour backbone",
        "",
    ]

    # person demographics
    lines += ["**Person demographics:**\n"]
    for col in ["person_gender", "person_education", "person_occupation"]:
        if col in persons.columns:
            top5 = persons[col].value_counts().head(5)
            lines.append(f"*{col}:* " + ", ".join(f"{k} ({v})" for k, v in top5.items()))
    lines.append("")

    # merchant industries
    if "industry" in merchants.columns:
        lines.append("**Merchant industries:** " + ", ".join(merchants["industry"].value_counts().head(8).index.tolist()))
        lines.append("")

    return _section("4. TransXion", lines)


# ── Cross-dataset comparison ─────────────────────────────────────────────────

def cross_comparison():
    lines = [
        "| Property | IBM HI-Small | SAML-D | Elliptic | TransXion |",
        "|----------|-------------|--------|----------|-----------|",
        "| Domain | Synthetic banking | Synthetic banking | Bitcoin blockchain | Synthetic banking |",
        "| Graph type | Directed multigraph | Directed multigraph | Directed graph | Directed multigraph |",
        "| Node semantics | Account (bank:id) | Account | Transaction | Account (with profiles) |",
        "| Edge semantics | Transaction | Transaction | Payment flow | Transaction |",
        "| Rows | ~5M | ~9.5M | 203K nodes, 234K edges | ~3M |",
        "| Positive rate | ~0.11% | ~TBD% | ~9.8% (of labelled) | ~0.15% |",
        "| Edge features | ✅ (amount, currency, format, time) | ✅ (amount, currency, location, type) | ❌ (node features only) | ✅ (amount, currency, format, time) |",
        "| Node features | ❌ | ❌ | ✅ (166 anonymized) | ✅ (demographics, occupation) |",
        "| Temporal | ✅ timestamps | ✅ timestamps | ✅ 49 time steps | ✅ timestamps |",
        "| Pattern labels | ❌ | ✅ Laundering_type column | ❌ | ❌ |",
        "| Entity profiles | ❌ | ❌ | ❌ | ✅ person + merchant |",
        "| Multi-currency | ✅ 15 currencies | ✅ | ❌ (Bitcoin only) | ✅ |",
        "| Cross-border | ✅ multi-bank | ✅ multi-country | ❌ | ✅ multi-bank |",
        "",
        "### Strategic insights\n",
        "1. **SAML-D has explicit laundering type labels** — this is the only dataset that tells you *what kind* "
        "of laundering each transaction belongs to (fan-out, cycle, etc.). This is gold for validating "
        "the topology classifier.",
        "2. **TransXion has entity profiles** — demographics, occupation, merchant industry. No other dataset "
        "has this. Enables node-feature-enriched GNNs that can learn behavioural priors.",
        "3. **Elliptic is node-level, not edge-level** — different classification task. Most papers report on it "
        "so it's useful for benchmarking, but it doesn't map directly to your edge-level Multi-GNN.",
        "4. **IBM HI-Small is the standard benchmark** for edge-level AML GNNs (used by Grama 2025, the "
        "Multi-GNN paper). Keep this as primary training/eval set.",
        "5. **Class imbalance is extreme everywhere** except Elliptic (~9.8%). IBM (~0.11%) and TransXion "
        "(~0.15%) are the hardest — this is why weighted BCE matters more than focal loss.",
        "6. **SAML-D's multi-country dimension** enables cross-border pattern analysis that IBM lacks.",
    ]
    return _section("5. Cross-Dataset Comparison & Strategic Insights", lines)


# ── main ─────────────────────────────────────────────────────────────────────

def main():
    print("Analysing datasets...")

    report = [
        "# AML Dataset Analysis Report",
        f"*Generated {datetime.now().strftime('%Y-%m-%d %H:%M')}*\n",
        "This report profiles every AML dataset available in `data/` and surfaces "
        "hidden insights relevant to model training and hackathon strategy.",
    ]

    for fn in (analyse_ibm, analyse_saml, analyse_elliptic, analyse_transxion, cross_comparison):
        print(f"  > {fn.__name__}...")
        report.extend(fn())

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(report), encoding="utf-8")
    print(f"\nDone! Report written to {OUT}")


if __name__ == "__main__":
    main()

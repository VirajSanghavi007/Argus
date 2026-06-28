# AML Dataset Analysis Report
*Generated 2026-06-27 13:46*

This report profiles every AML dataset available in `data/` and surfaces hidden insights relevant to model training and hackathon strategy.

## 1. IBM AMLWorld

The IBM AMLWorld suite contains 6 transaction files (HI/LI × Small/Medium/Large) plus matching account files.

| Variant | Rows | Positives | Pos Rate | Accounts | Banks | Currencies | Formats | Self-Loops | Amt Mean | Amt Median | Amt Max | Time Span |
|---------|------|-----------|----------|----------|-------|------------|---------|------------|----------|------------|---------|-----------|
| HI-Small (sampled first 500K of 5,078,345) | 5,078,345 | 193 | 0.0386% | 326,815 | 16608 | 15 | 7 | 297,563 | $6,073,694.60 | $2,139.34 | $140,212,375,027.40 | 2022-09-01 00:00:00 → 2022-09-06 19:16:00 |
| HI-Medium (sampled first 500K of 31,898,238) | 31,898,238 | 35 | 0.0070% | 405,043 | 22719 | 15 | 7 | 368,370 | $893,018.46 | $2,029.51 | $7,737,418,739.91 | 2022-09-01 00:00:00 → 2022-09-06 13:24:00 |
| HI-Large (sampled first 500K of 179,702,229) | 179,702,229 | 35 | 0.0070% | 405,043 | 22719 | 15 | 7 | 368,370 | $893,018.46 | $2,029.51 | $7,737,418,739.91 | 2022-08-01 00:00:00 → 2022-08-30 11:54:00 |
| LI-Small (sampled first 500K of 6,924,049) | 6,924,049 | 30 | 0.0060% | 384,769 | 21449 | 15 | 7 | 344,496 | $9,440,404.80 | $2,266.30 | $322,407,541,886.58 | 2022-09-01 00:00:00 → 2022-09-01 01:59:00 |
| LI-Medium (sampled first 500K of 31,251,483) | 31,251,483 | 23 | 0.0046% | 404,532 | 22830 | 15 | 7 | 368,321 | $797,789.24 | $2,027.38 | $5,654,524,618.18 | 2022-09-01 00:00:00 → 2022-09-01 00:29:00 |
| LI-Large (sampled first 500K of 176,066,557) | 176,066,557 | 23 | 0.0046% | 404,532 | 22830 | 15 | 7 | 368,321 | $797,789.24 | $2,027.38 | $5,654,524,618.18 | 2022-08-01 00:00:00 → 2022-08-01 00:29:00 |

### HI-Small Deep Dive (our training set)

**Laundering rate by Payment Format:**

| Format | Positives | Total | Rate |
|--------|-----------|-------|------|
| ACH | 4,483 | 600,797 | 0.7462% |
| Bitcoin | 56 | 146,091 | 0.0383% |
| Cash | 108 | 490,891 | 0.0220% |
| Cheque | 324 | 1,864,331 | 0.0174% |
| Credit Card | 206 | 1,323,324 | 0.0156% |
| Reinvestment | 0 | 481,056 | 0.0000% |
| Wire | 0 | 171,855 | 0.0000% |

**Laundering rate by Currency:**

| Currency | Positives | Total | Rate |
|----------|-----------|-------|------|
| Saudi Riyal | 374 | 89,014 | 0.4202% |
| Euro | 1,372 | 1,168,297 | 0.1174% |
| US Dollar | 1,912 | 1,895,172 | 0.1009% |
| Yen | 155 | 155,209 | 0.0999% |
| Australian Dollar | 127 | 136,769 | 0.0929% |
| Canadian Dollar | 128 | 140,042 | 0.0914% |
| Rupee | 167 | 190,202 | 0.0878% |
| Yuan | 184 | 213,752 | 0.0861% |
| Ruble | 133 | 155,178 | 0.0857% |
| Mexican Peso | 92 | 110,159 | 0.0835% |
| Swiss Franc | 193 | 234,860 | 0.0822% |
| Brazil Real | 57 | 70,703 | 0.0806% |
| UK Pound | 132 | 180,738 | 0.0730% |
| Shekel | 95 | 192,184 | 0.0494% |
| Bitcoin | 56 | 146,066 | 0.0383% |

**Amount distribution (Laundering vs Legitimate):**

| Stat | Legitimate | Laundering |
|------|-----------|------------|
| mean | $4,477,000.04 | $36,135,310.41 |
| median | $1,410.99 | $8,667.21 |
| std | $868,846,296.80 | $1,527,918,669.80 |
| min | $0.00 | $0.00 |
| max | $1,046,302,363,293.48 | $84,853,144,179.58 |

**Temporal insight:** Peak laundering hour = 12:00 (rate 0.1741%). Lowest = 0:00 (0.0277%).
Peak day = Sun (0.3113%), lowest = Thu (0.0556%).

**Cross-bank vs Same-bank:**

| Type | Positives | Total | Rate |
|------|-----------|-------|------|
| Same-bank | 103 | 691,332 | 0.0149% |
| Cross-bank | 5,074 | 4,387,013 | 0.1157% |

**Top 10 accounts by laundering transactions (as sender):**

| Account | Laundering Txns |
|---------|----------------|
| 100428660 | 243 |
| 1004286A8 | 158 |
| 100428978 | 29 |
| 80266F880 | 29 |
| 100428810 | 26 |
| 812D22980 | 25 |
| 100428738 | 23 |
| 811C597B0 | 21 |
| 811C599A0 | 21 |
| 100428780 | 21 |


## 2. SAML-D

- **Total rows:** 9,504,852 (analysed first 500K)
- **Positives:** 556 (0.1112% in sample)
- **Unique accounts:** 206,772
- **Currencies:** 13
- **Bank locations:** 18 countries
- **Amount:** mean=$8,710.73, median=$6,110.18, max=$6,213,931.56

**Laundering type breakdown (first 500K):**

| Type | Count | % of Sample |
|------|-------|-------------|
| Normal_Small_Fan_Out | 185,221 | 37.044% |
| Normal_Fan_Out | 123,188 | 24.638% |
| Normal_Fan_In | 113,444 | 22.689% |
| Normal_Group | 28,206 | 5.641% |
| Normal_Cash_Withdrawal | 16,171 | 3.234% |
| Normal_Cash_Deposits | 11,065 | 2.213% |
| Normal_Periodical | 10,676 | 2.135% |
| Normal_Mutual | 5,604 | 1.121% |
| Normal_Plus_Mutual | 2,593 | 0.519% |
| Normal_Foward | 2,198 | 0.440% |
| Normal_single_large | 1,078 | 0.216% |
| Structuring | 166 | 0.033% |
| Cash_Withdrawal | 74 | 0.015% |
| Smurfing | 59 | 0.012% |
| Stacked Bipartite | 40 | 0.008% |
| Layered_Fan_Out | 39 | 0.008% |
| Behavioural_Change_1 | 38 | 0.008% |
| Deposit-Send | 30 | 0.006% |
| Fan_In | 17 | 0.003% |
| Behavioural_Change_2 | 13 | 0.003% |
| Gather-Scatter | 13 | 0.003% |
| Layered_Fan_In | 12 | 0.002% |
| Cycle | 12 | 0.002% |
| Single_large | 12 | 0.002% |
| Scatter-Gather | 11 | 0.002% |
| Bipartite | 11 | 0.002% |
| Fan_Out | 7 | 0.001% |
| Over-Invoicing | 2 | 0.000% |

**Cross-border vs Domestic:**

| Type | Positives | Total | Rate |
|------|-----------|-------|------|
| Domestic | 404 | 451,970 | 0.0894% |
| Cross-border | 152 | 48,030 | 0.3165% |

**Laundering rate by Payment Type:**

| Payment Type | Positives | Total | Rate |
|-------------|-----------|-------|------|
| Cash Deposit | 75 | 11,140 | 0.6732% |
| Cash Withdrawal | 74 | 15,883 | 0.4659% |
| Cross-border | 126 | 48,004 | 0.2625% |
| Credit card | 78 | 106,333 | 0.0734% |
| ACH | 71 | 106,714 | 0.0665% |
| Cheque | 70 | 105,675 | 0.0662% |
| Debit card | 62 | 106,251 | 0.0584% |


## 3. Elliptic Bitcoin

- **Nodes (transactions):** 203,769
- **Edges (payment flows):** 234,355
- **Features per node:** 166
- **Illicit:** 4,545 (2.23%)
- **Licit:** 42,019 (20.62%)
- **Unknown:** 157,205 (77.15%)
- **Imbalance (illicit / labelled):** 9.76%
- **Graph density:** 0.00000564

**Key characteristics:**
- Bitcoin blockchain transactions across 49 time steps
- Node features: 94 local + 72 aggregate (166 total), anonymized
- No edge features — purely node-level classification
- Temporal: nodes belong to distinct time steps, enabling temporal splits
- Labels come from known entities (exchanges, darknet markets, etc.)

**Degree distribution:**
- Mean: 2.30
- Median: 2
- Max: 473
- Nodes with degree 1: 70,341 (34.5%)


## 4. TransXion

- **Total rows:** 3,029,170 (analysed first 500K)
- **Positives:** 617 (0.1234% in sample)
- **Unique accounts:** 16,389
- **Unique banks:** 30
- **Currencies:** 8
- **Payment formats:** 4
- **Person profiles:** 46,400
- **Merchant profiles:** 1,330
- **Amount:** mean=$1,543.08, median=$66.77, max=$2,864,231.35

**Unique features of TransXion:**
- Rich entity profiles (age, education, gender, marital status, occupation)
- Merchant metadata (industry, registered capital, operating status)
- Adversarially synthesized anomalies (not template-driven)
- Profile-conditioned normal behaviour backbone

**Person demographics:**

*person_gender:* male (26597), female (19803)
*person_education:* associate degree (15100), bachelor's degree (14130), high school (7372), below high school (5582), graduate degree or higher (4216)
*person_occupation:* retired (9901), blue-collar worker (4895), business owner (4683), unemployed (4447), student (3874)

**Merchant industries:** Food & Beverage, Retail, E-commerce, Manufacturing, Entertainment, Utilities, Telecommunications, Financial Services



## 5. Cross-Dataset Comparison & Strategic Insights

| Property | IBM HI-Small | SAML-D | Elliptic | TransXion |
|----------|-------------|--------|----------|-----------|
| Domain | Synthetic banking | Synthetic banking | Bitcoin blockchain | Synthetic banking |
| Graph type | Directed multigraph | Directed multigraph | Directed graph | Directed multigraph |
| Node semantics | Account (bank:id) | Account | Transaction | Account (with profiles) |
| Edge semantics | Transaction | Transaction | Payment flow | Transaction |
| Rows | ~5M | ~9.5M | 203K nodes, 234K edges | ~3M |
| Positive rate | ~0.11% | ~TBD% | ~9.8% (of labelled) | ~0.15% |
| Edge features | ✅ (amount, currency, format, time) | ✅ (amount, currency, location, type) | ❌ (node features only) | ✅ (amount, currency, format, time) |
| Node features | ❌ | ❌ | ✅ (166 anonymized) | ✅ (demographics, occupation) |
| Temporal | ✅ timestamps | ✅ timestamps | ✅ 49 time steps | ✅ timestamps |
| Pattern labels | ❌ | ✅ Laundering_type column | ❌ | ❌ |
| Entity profiles | ❌ | ❌ | ❌ | ✅ person + merchant |
| Multi-currency | ✅ 15 currencies | ✅ | ❌ (Bitcoin only) | ✅ |
| Cross-border | ✅ multi-bank | ✅ multi-country | ❌ | ✅ multi-bank |

### Strategic insights

1. **SAML-D has explicit laundering type labels** — this is the only dataset that tells you *what kind* of laundering each transaction belongs to (fan-out, cycle, etc.). This is gold for validating the topology classifier.
2. **TransXion has entity profiles** — demographics, occupation, merchant industry. No other dataset has this. Enables node-feature-enriched GNNs that can learn behavioural priors.
3. **Elliptic is node-level, not edge-level** — different classification task. Most papers report on it so it's useful for benchmarking, but it doesn't map directly to your edge-level Multi-GNN.
4. **IBM HI-Small is the standard benchmark** for edge-level AML GNNs (used by Grama 2025, the Multi-GNN paper). Keep this as primary training/eval set.
5. **Class imbalance is extreme everywhere** except Elliptic (~9.8%). IBM (~0.11%) and TransXion (~0.15%) are the hardest — this is why weighted BCE matters more than focal loss.
6. **SAML-D's multi-country dimension** enables cross-border pattern analysis that IBM lacks.

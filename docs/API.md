# API Reference — AML Intelligence Platform

## Base URL

```
http://localhost:8000          (local)
https://aml-backend.onrender.com  (production)
```

All endpoints return JSON. CORS is open (`*`).

---

## GET /health

Always returns 200, regardless of pipeline state. Used by `Bootup.bat` to determine when the server is accepting connections.

```json
{"status": "ok"}
```

---

## GET /status

Returns the current pipeline state and alert counts.

```json
{
  "status": "ready",
  "alert_count": 312,
  "labelled_count": 46,
  "unlabelled_count": 280,
  "overlap_count": 14,
  "suppressed_count": 8,
  "patterns": {
    "fanOut": 23,
    "bipartite": 18,
    "scatterGather": 9,
    "fanIn": 7,
    "cycle": 1
  }
}
```

| Field | Description |
|-------|-------------|
| `status` | `"loading"` while pipeline runs, `"ready"` when complete |
| `labelled_count` | Alerts with `source in ("labelled", "both")` |
| `unlabelled_count` | Alerts with `source in ("unlabelled", "both")` |
| `overlap_count` | Alerts found by both modes (cross-validated) |
| `suppressed_count` | Alerts suppressed by whitelist rules |

---

## GET /alerts

Returns the summary list of all active (non-suppressed) alerts.

**Query Parameters:**

| Parameter | Example | Description |
|-----------|---------|-------------|
| `severity` | `?severity=HIGH` | Filter: `HIGH`, `MEDIUM`, `LOW` |
| `pattern_type` | `?pattern_type=fanOut` | Filter by camelCase pattern type |
| `source` | `?source=unlabelled` | Filter: `labelled`, `unlabelled`, `both` |

**Example response item:**

```json
{
  "id": "u_fanout_3",
  "name": "Fan-Out",
  "sub": "Max 5-degree Fan-Out",
  "severity": "HIGH",
  "confidence": 0.72,
  "patternType": "fanOut",
  "totalMoved": "$48,200",
  "timeSpan": "1h 22m",
  "hops": 1,
  "node_count": 6,
  "txn_count": 5,
  "source": "unlabelled",
  "partialExemption": false
}
```

| Field | Description |
|-------|-------------|
| `source` | `"labelled"`, `"unlabelled"`, or `"both"` |
| `partialExemption` | `true` if some (not all) nodes in this cluster are whitelisted |

IDs prefixed with `u_` are unlabelled-mode alerts. Labelled alert IDs have no prefix.

---

## GET /alerts/suppressed

Returns alerts that were fully suppressed by whitelist rules. These are separated from the main alert list but preserved for audit purposes.

**Note:** This route is defined before `/alerts/{alert_id}` in the server to prevent the literal string `"suppressed"` from being captured as an alert ID parameter.

```json
[
  {
    "id": "fanin_2",
    "name": "Fan-In",
    "patternType": "fanIn",
    "severity": "MEDIUM",
    "exemption_reason": "All nodes exempt: FAN_IN — is_business",
    "exempt_accounts": ["80045678", "80012300"],
    ...
  }
]
```

| Field | Description |
|-------|-------------|
| `exemption_reason` | Human-readable reason why this alert was suppressed |
| `exempt_accounts` | Account IDs that triggered the exemption |

---

## GET /alerts/{alert_id}

Returns the full alert detail.

```json
{
  "id": "u_fanout_3",
  "name": "Fan-Out",
  "sub": "Max 5-degree Fan-Out",
  "severity": "HIGH",
  "confidence": 0.72,
  "patternType": "fanOut",
  "totalMoved": "$48,200",
  "timeSpan": "1h 22m",
  "hops": 1,
  "routeNodes": ["80012345", "80098765", "80011111"],
  "description": "A single account rapidly distributes funds...",
  "source": "unlabelled",
  "signalsTriggered": ["Rapid Fan-Out", "Layering Velocity"],
  "partial_exemption": false,
  "nodes": [
    {
      "id": "80012345",
      "label": "80012345",
      "sev": "high",
      "role": "Distributor",
      "bank": "Bank-11",
      "vol": "$52,100",
      "txn": 5
    }
  ],
  "edges": [
    {
      "id": "e0",
      "source": "80012345",
      "target": "80098765",
      "label": "$9,800",
      "txIdx": 0
    }
  ],
  "transactions": [
    {
      "from": "80012345",
      "to": "80098765",
      "paid": "$9,800",
      "recv": "$9,800",
      "pCur": "US Dollar",
      "rCur": "US Dollar",
      "fromBank": "11",
      "toBank": "22",
      "fmt": "RTGS",
      "ts": "2022-09-01 14:32"
    }
  ]
}
```

### Fields

| Field | Type | Description |
|-------|------|-------------|
| `source` | string | `"labelled"`, `"unlabelled"`, or `"both"` |
| `signalsTriggered` | array | Behavioural signals that flagged accounts in this cluster. All 7 possible values: `"Rapid Fan-Out"`, `"Round-Trip"`, `"Structuring"`, `"Layering Velocity"`, `"Dormant Activation"`, `"Currency Mismatch"`, `"Smurfing"` |
| `partial_exemption` | bool | `true` if some (not all) nodes are whitelisted |

Returns **404** if `alert_id` does not exist:
```json
{"detail": {"error": "not found"}}
```

---

## POST /alerts/{alert_id}/decision

Records an investigator decision. Decisions are held in memory (not persisted to disk).

**Request body:**
```json
{
  "decision": "confirm",
  "reason": "Clear Fan-Out pattern, matches known mule account"
}
```

`decision` must be one of: `confirm`, `review`, `dismiss`.

**Response:**
```json
{"status": "saved", "alert_id": "fanout_0", "decision": "confirm"}
```

---

## GET /whitelist

Returns the current whitelist configuration.

```json
{
  "exempt_accounts": ["80012345"],
  "exempt_banks": ["Federal Reserve", "Central Bank", "RBI", "ECB"],
  "business_account_patterns": ["CORP", "LTD", "INC", "PLC", "LLC", "BANK"],
  "exemption_rules": {
    "FAN_IN": {
      "reason": "High-volume collection accounts (payroll, tax, utility)",
      "exempt_if": ["is_business", "is_exempt_bank"]
    },
    "FAN_OUT": {
      "reason": "High-volume distribution accounts (payroll, dividends)",
      "exempt_if": ["is_business", "is_exempt_bank"]
    },
    "BIPARTITE": {
      "reason": "Correspondent banking relationships",
      "exempt_if": ["is_exempt_bank"]
    }
  }
}
```

---

## POST /whitelist/account

Adds an account ID to the `exempt_accounts` list and saves to `data/whitelist.json`.

**Request body:**
```json
{
  "account_id": "80012345",
  "reason": "Verified payroll account — Finance dept confirmed"
}
```

**Response:**
```json
{
  "status": "added",
  "account_id": "80012345",
  "whitelist": { ... }
}
```

Note: Adding an account to the whitelist does not immediately re-run the pipeline. The filter applies on the next server restart. To suppress an alert immediately, use the frontend Whitelist tab which calls this endpoint and updates the UI.

---

## DELETE /whitelist/account/{account_id}

Removes an account ID from the `exempt_accounts` list and saves to `data/whitelist.json`.

**Response:**
```json
{
  "status": "removed",
  "account_id": "80012345"
}
```

Returns **200** even if the account was not in the list (idempotent).

---

## GET /validation

Returns the ground-truth validation results comparing both detection modes against `HI-Small_Patterns.txt`.

Returns **404** if `validator.py` has not been run yet:
```json
{"detail": {"error": "validation not run yet"}}
```

**Response structure:**
```json
{
  "total_gt_blocks": 270,
  "labelled": {
    "total_alerts": 46,
    "matched": 4,
    "overall_precision": 0.087,
    "overall_recall": 0.015,
    "per_pattern_precision": {"CYCLE": 1.0, "FAN_OUT": 0.0},
    "per_pattern_recall": {"CYCLE": 0.033, "FAN_OUT": 0.0},
    "records": [...]
  },
  "unlabelled": {
    "total_alerts": 280,
    "matched": 12,
    "overall_precision": 0.043,
    "overall_recall": 0.044,
    "per_pattern_precision": {...},
    "per_pattern_recall": {...},
    "records": [...]
  },
  "overlap_count": 14,
  "comparison": {
    "labelled_alerts": 46,
    "unlabelled_alerts": 280,
    "overlap_count": 14,
    "labelled_precision": 0.087,
    "labelled_recall": 0.015,
    "unlabelled_precision": 0.043,
    "unlabelled_recall": 0.044
  }
}
```

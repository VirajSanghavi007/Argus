"""
Whitelist / Exemption System

Reads data/whitelist.json and provides helpers to:
  - Check if an account/bank is exempt from a pattern
  - Filter alerts (suppressing fully-exempt clusters, tagging partial)
  - Add / remove accounts from the explicit exempt list
"""
import json
from pathlib import Path

DATA_DIR       = Path(__file__).parent.parent.parent.parent / "data"
WHITELIST_PATH = DATA_DIR / "whitelist.json"

DEFAULT_WHITELIST: dict = {
    "exempt_accounts": [],
    "exempt_banks": ["Federal Reserve", "Central Bank", "RBI", "ECB"],
    "business_account_patterns": ["CORP", "LTD", "INC", "PLC", "LLC", "BANK"],
    "exemption_rules": {
        "FAN_IN": {
            "reason": "High-volume collection accounts (payroll, tax, utility)",
            "exempt_if": ["is_business", "is_exempt_bank"],
        },
        "FAN_OUT": {
            "reason": "High-volume distribution accounts (payroll, dividends)",
            "exempt_if": ["is_business", "is_exempt_bank"],
        },
        "BIPARTITE": {
            "reason": "Correspondent banking relationships",
            "exempt_if": ["is_exempt_bank"],
        },
        "CYCLE": {
            "reason": "Internal treasury recycling between affiliated entities",
            "exempt_if": ["is_business", "is_exempt_bank"],
        },
        "SCATTER_GATHER": {
            "reason": "Legitimate payment aggregation and redistribution",
            "exempt_if": ["is_business", "is_exempt_bank"],
        },
        "GATHER_SCATTER": {
            "reason": "Clearing house or settlement hub operations",
            "exempt_if": ["is_exempt_bank"],
        },
        "STACK": {
            "reason": "Multi-tier corporate fund routing (holding structures)",
            "exempt_if": ["is_business", "is_exempt_bank"],
        },
        "RANDOM": {
            "reason": "Unstructured activity from known low-risk entities",
            "exempt_if": ["is_exempt_bank"],
        },
    },
}


def load_whitelist() -> dict:
    if not WHITELIST_PATH.exists():
        save_whitelist(DEFAULT_WHITELIST)
        return dict(DEFAULT_WHITELIST)
    return json.loads(WHITELIST_PATH.read_text(encoding="utf-8"))


def save_whitelist(wl: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    WHITELIST_PATH.write_text(json.dumps(wl, indent=2), encoding="utf-8")


def _is_business(bank_name: str, patterns: list[str]) -> bool:
    upper = bank_name.upper()
    return any(p.upper() in upper for p in patterns)


def _is_exempt_bank(bank_name: str, exempt_banks: list[str]) -> bool:
    return bank_name in exempt_banks


def is_exempt(
    account_id: str,
    bank_name: str,
    pattern_type: str,
    whitelist: dict | None = None,
) -> bool:
    """
    Return True if this account should be exempt from alerts of pattern_type.

    Exemption hierarchy:
    1. Explicit account ID in exempt_accounts list
    2. Bank-name matches an exemption rule condition (is_business / is_exempt_bank)
       for the given pattern_type
    """
    if whitelist is None:
        whitelist = load_whitelist()

    if account_id in whitelist.get("exempt_accounts", []):
        return True

    rules = whitelist.get("exemption_rules", {})
    rule  = rules.get(pattern_type.upper().replace("-", "_"))
    if not rule:
        return False

    exempt_if    = rule.get("exempt_if", [])
    biz_patterns = whitelist.get("business_account_patterns", [])
    exempt_banks = whitelist.get("exempt_banks", [])

    clean_bank = bank_name.replace("Bank-", "").strip()
    for cond in exempt_if:
        if cond == "is_business"   and _is_business(clean_bank, biz_patterns):
            return True
        if cond == "is_exempt_bank" and _is_exempt_bank(clean_bank, exempt_banks):
            return True

    return False


def filter_alerts(
    alerts: list[dict],
    whitelist: dict | None = None,
) -> tuple[list[dict], list[dict]]:
    """
    Split alerts into (kept, suppressed).

    - ALL nodes exempt → suppressed (added to audit dict with exemption_reason)
    - SOME nodes exempt → kept, with partial_exemption=True + exempt_accounts list
    - No nodes exempt → kept unchanged
    """
    if whitelist is None:
        whitelist = load_whitelist()

    rules = whitelist.get("exemption_rules", {})
    kept: list[dict]       = []
    suppressed: list[dict] = []

    for alert in alerts:
        # Normalise pattern key to UPPER_SNAKE
        pattern = (
            alert.get("pattern_type") or alert.get("patternType", "")
        ).upper().replace("-", "_")

        if pattern not in rules:
            kept.append(alert)
            continue

        nodes = alert.get("nodes_list") or alert.get("nodes", [])
        if not nodes:
            kept.append(alert)
            continue

        exempt_node_ids: list[str] = []
        for node in nodes:
            nid  = node.get("node_id") or node.get("id", "")
            bank = node.get("bank", "")
            if is_exempt(nid, bank, pattern, whitelist):
                exempt_node_ids.append(nid)

        all_exempt  = len(exempt_node_ids) == len(nodes)
        some_exempt = 0 < len(exempt_node_ids) < len(nodes)

        rule_reason = rules[pattern].get("reason", "Whitelist rule")

        if all_exempt:
            suppressed.append({
                **alert,
                "suppressed":       True,
                "exemption_reason": rule_reason,
                "exempt_accounts":  exempt_node_ids,
            })
        else:
            modified = dict(alert)
            if some_exempt:
                modified["partial_exemption"] = True
                modified["exempt_accounts"]   = exempt_node_ids
            kept.append(modified)

    return kept, suppressed


def add_to_whitelist(account_id: str) -> dict:
    wl = load_whitelist()
    if account_id not in wl["exempt_accounts"]:
        wl["exempt_accounts"].append(account_id)
        save_whitelist(wl)
    return wl


def remove_from_whitelist(account_id: str) -> dict:
    wl = load_whitelist()
    wl["exempt_accounts"] = [a for a in wl["exempt_accounts"] if a != account_id]
    save_whitelist(wl)
    return wl

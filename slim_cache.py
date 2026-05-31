"""
Slims pipeline_cache.json to under 100MB by capping transactions per alert.
Run from repo root: python slim_cache.py
"""
import json
from pathlib import Path

MAX_TXN = 150   # transactions kept per alert — enough for timeline demo

cache_path = Path("data/pipeline_cache.json")
if not cache_path.exists():
    print("ERROR: data/pipeline_cache.json not found. Run the backend first.")
    raise SystemExit(1)

original_mb = cache_path.stat().st_size / 1024 / 1024
print(f"Original size: {original_mb:.1f} MB")

with open(cache_path, encoding="utf-8") as f:
    cache = json.load(f)

total_before = sum(len(a.get("transactions", [])) for a in cache.get("alerts", []))
total_before += sum(len(a.get("transactions", [])) for a in cache.get("suppressed", []))

for alert in cache.get("alerts", []):
    if len(alert.get("transactions", [])) > MAX_TXN:
        alert["transactions"] = alert["transactions"][:MAX_TXN]

for alert in cache.get("suppressed", []):
    if len(alert.get("transactions", [])) > MAX_TXN:
        alert["transactions"] = alert["transactions"][:MAX_TXN]

total_after = sum(len(a.get("transactions", [])) for a in cache.get("alerts", []))
total_after += sum(len(a.get("transactions", [])) for a in cache.get("suppressed", []))

slim_content = json.dumps(cache)
cache_path.write_text(slim_content, encoding="utf-8")

slim_mb = cache_path.stat().st_size / 1024 / 1024
print(f"Slim size:     {slim_mb:.1f} MB  ({(1-slim_mb/original_mb)*100:.0f}% reduction)")
print(f"Transactions:  {total_before:,} -> {total_after:,}")

if slim_mb < 95:
    print(f"\nSUCCESS — under 95MB, safe to commit.")
    print("\nNext steps:")
    print("  git reset HEAD~1          # undo the failed commit")
    print("  git add data/pipeline_cache.json data/fraud_model.pkl .gitignore render.yaml frontend/index.html backend/")
    print('  git commit -m "Add slim pipeline cache and fixes"')
    print("  git push origin main")
else:
    print(f"\nStill {slim_mb:.1f}MB — reduce MAX_TXN to 50 and rerun.")

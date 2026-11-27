import json
from pathlib import Path

def main():
    rows = json.loads(Path("inventory.json").read_text(encoding="utf-8"))
    totals = {}
    for row in rows:
        if row["active"]:
            sku = row["sku"]
            totals[sku] = totals.get(sku, 0) + row["quantity"]
    output = [{"sku": sku, "quantity": totals[sku]} for sku in sorted(totals)]
    Path("totals.json").write_text(json.dumps(output), encoding="utf-8")

if __name__ == "__main__":
    main()

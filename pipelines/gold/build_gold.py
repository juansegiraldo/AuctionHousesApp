#!/usr/bin/env python3
"""Build Gold analytics artifacts from Silver layer."""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SILVER_ROOT = ROOT / "data" / "silver"
GOLD_ROOT = ROOT / "data" / "gold"


def main() -> None:
    GOLD_ROOT.mkdir(parents=True, exist_ok=True)
    lots_path = SILVER_ROOT / "lots.jsonl"
    if not lots_path.exists():
        raise FileNotFoundError(f"Silver lots not found: {lots_path}")

    per_house = defaultdict(lambda: {"lots_offered": 0, "lots_sold": 0, "revenue": 0})
    with open(lots_path, encoding="utf-8") as handle:
        for line in handle:
            row = json.loads(line)
            house = row.get("house_slug", "unknown")
            per_house[house]["lots_offered"] += 1
            sold = row.get("price_sold")
            if sold is not None:
                per_house[house]["lots_sold"] += 1
                per_house[house]["revenue"] += sold

    out_path = GOLD_ROOT / "agg_house_metrics.jsonl"
    with open(out_path, "w", encoding="utf-8") as output:
        for house, metrics in sorted(per_house.items()):
            lots_sold = metrics["lots_sold"]
            lots_offered = metrics["lots_offered"] or 1
            avg_sold_price = metrics["revenue"] / lots_sold if lots_sold else None
            payload = {
                "house_slug": house,
                "lots_offered": metrics["lots_offered"],
                "lots_sold": lots_sold,
                "sell_through_rate": lots_sold / lots_offered,
                "revenue": metrics["revenue"],
                "avg_sold_price": avg_sold_price,
            }
            output.write(json.dumps(payload, ensure_ascii=False) + "\n")

    print(f"[gold] wrote: {out_path}")


if __name__ == "__main__":
    main()

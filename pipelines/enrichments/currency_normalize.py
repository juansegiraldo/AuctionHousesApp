#!/usr/bin/env python3
"""Example enrichment: normalize prices into USD using a fixed rate."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SILVER_LOTS = ROOT / "data" / "silver" / "lots.jsonl"
OUTPUT = ROOT / "data" / "enrichments" / "currency_normalized.jsonl"

COP_TO_USD = 1 / 4000


def to_usd(value):
    if value is None:
        return None
    return round(value * COP_TO_USD, 2)


def main() -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with open(SILVER_LOTS, encoding="utf-8") as source, open(OUTPUT, "w", encoding="utf-8") as target:
        for line in source:
            row = json.loads(line)
            payload = {
                "dedupe_key": row.get("dedupe_key"),
                "price_sold_usd": to_usd(row.get("price_sold")),
                "price_estimate_min_usd": to_usd(row.get("price_estimate_min")),
                "price_estimate_max_usd": to_usd(row.get("price_estimate_max")),
                "fx_source": "static_cop_usd_4000",
            }
            target.write(json.dumps(payload, ensure_ascii=False) + "\n")
    print(f"[enrichment] wrote: {OUTPUT}")


if __name__ == "__main__":
    main()

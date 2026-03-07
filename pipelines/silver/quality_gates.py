#!/usr/bin/env python3
"""Data quality gates for Silver layer, focused by house/category."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SILVER_LOTS = ROOT / "data" / "silver" / "lots.jsonl"
CATEGORY_TAGS = ROOT / "data" / "enrichments" / "category_tags.jsonl"


def load_category_map(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    mapping: dict[str, str] = {}
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            row = json.loads(line)
            key = row.get("dedupe_key")
            category = row.get("category")
            if key and category:
                mapping[key] = category
    return mapping


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate Silver quality gates.")
    parser.add_argument("--house-slug", required=True)
    parser.add_argument("--allowed-categories", default="obra_grafica,pintura")
    parser.add_argument("--min-lot-url", type=float, default=0.99)
    parser.add_argument("--min-lot-title", type=float, default=0.95)
    parser.add_argument("--min-price-coverage", type=float, default=0.70)
    args = parser.parse_args()

    allowed = {v.strip() for v in args.allowed_categories.split(",") if v.strip()}
    cat_map = load_category_map(CATEGORY_TAGS)
    rows = []
    with open(SILVER_LOTS, encoding="utf-8") as handle:
        for line in handle:
            row = json.loads(line)
            if row.get("house_slug") == args.house_slug:
                rows.append(row)

    if not rows:
        raise SystemExit(f"No rows found for house {args.house_slug}")

    total = len(rows)
    with_url = sum(1 for r in rows if r.get("lot_url"))
    with_title = sum(1 for r in rows if r.get("lot_title"))
    with_price = sum(1 for r in rows if (r.get("price_estimate_min") is not None or r.get("price_sold") is not None))
    out_of_scope = 0
    for row in rows:
        category = cat_map.get(row.get("dedupe_key", ""))
        if category and category not in allowed:
            out_of_scope += 1

    pct_url = with_url / total
    pct_title = with_title / total
    pct_price = with_price / total
    print(f"house={args.house_slug} total={total}")
    print(f"lot_url_coverage={pct_url:.4f}")
    print(f"lot_title_coverage={pct_title:.4f}")
    print(f"price_coverage={pct_price:.4f}")
    print(f"out_of_scope_count={out_of_scope}")

    failures = []
    if pct_url < args.min_lot_url:
        failures.append("lot_url")
    if pct_title < args.min_lot_title:
        failures.append("lot_title")
    if pct_price < args.min_price_coverage:
        failures.append("price")
    if out_of_scope > 0:
        failures.append("category_scope")

    if failures:
        raise SystemExit(f"failed_quality_gate: {','.join(failures)}")


if __name__ == "__main__":
    main()


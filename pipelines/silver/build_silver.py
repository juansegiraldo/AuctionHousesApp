#!/usr/bin/env python3
"""Build Silver datasets from Bronze JSONL files."""

from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipelines.shared.schema import normalize_lot

BRONZE_ROOT = ROOT / "data" / "bronze"
SILVER_ROOT = ROOT / "data" / "silver"
NON_LOT_FILES = {"auction_index.jsonl"}


def iter_bronze_rows():
    for house_dir in BRONZE_ROOT.iterdir():
        if not house_dir.is_dir():
            continue
        house_slug = house_dir.name
        for partition_dir in house_dir.iterdir():
            if not partition_dir.is_dir():
                continue
            for file_path in partition_dir.glob("*.jsonl"):
                if file_path.name in NON_LOT_FILES:
                    continue
                with open(file_path, encoding="utf-8") as handle:
                    for line in handle:
                        line = line.strip()
                        if not line:
                            continue
                        record = json.loads(line)
                        if not record.get("lot_url"):
                            continue
                        yield normalize_lot(record, house_slug, str(file_path.relative_to(ROOT)))


def main() -> None:
    SILVER_ROOT.mkdir(parents=True, exist_ok=True)
    lots_path = SILVER_ROOT / "lots.jsonl"
    auctions_path = SILVER_ROOT / "auctions.jsonl"

    dedupe_keys: set[str] = set()
    seen_auctions: set[str] = set()

    with open(lots_path, "w", encoding="utf-8") as lots_out, open(auctions_path, "w", encoding="utf-8") as auctions_out:
        for row in iter_bronze_rows():
            dedupe_key = row["dedupe_key"]
            if dedupe_key in dedupe_keys:
                continue
            dedupe_keys.add(dedupe_key)
            lots_out.write(json.dumps(row, ensure_ascii=False) + "\n")

            auction_key = f"{row.get('house_slug')}|{row.get('auction_id')}"
            if auction_key not in seen_auctions:
                seen_auctions.add(auction_key)
                auctions_out.write(
                    json.dumps(
                        {
                            "house_slug": row.get("house_slug"),
                            "auction_id": row.get("auction_id"),
                            "auction_title": row.get("auction_title"),
                            "auction_start_date": row.get("auction_start_date"),
                            "auction_end_date": row.get("auction_end_date"),
                            "auction_url": row.get("auction_url"),
                            "auction_info_url": row.get("auction_info_url"),
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )

    print(f"[silver] wrote: {lots_path}")
    print(f"[silver] wrote: {auctions_path}")


if __name__ == "__main__":
    main()

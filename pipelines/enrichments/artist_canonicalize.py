#!/usr/bin/env python3
"""Example enrichment: canonicalize artist names to stable IDs."""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SILVER_LOTS = ROOT / "data" / "silver" / "lots.jsonl"
OUTPUT = ROOT / "data" / "enrichments" / "artist_canonicalized.jsonl"


def artist_key(name: str | None) -> str | None:
    if not name:
        return None
    cleaned = re.sub(r"\s+", " ", name).strip().lower()
    cleaned = re.sub(r"[^a-z0-9\s]", "", cleaned)
    return cleaned.replace(" ", "_")


def main() -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with open(SILVER_LOTS, encoding="utf-8") as source, open(OUTPUT, "w", encoding="utf-8") as target:
        for line in source:
            row = json.loads(line)
            key = artist_key(row.get("artist_name"))
            payload = {
                "dedupe_key": row.get("dedupe_key"),
                "artist_name": row.get("artist_name"),
                "artist_id": f"artist_{key}" if key else None,
            }
            target.write(json.dumps(payload, ensure_ascii=False) + "\n")
    print(f"[enrichment] wrote: {OUTPUT}")


if __name__ == "__main__":
    main()

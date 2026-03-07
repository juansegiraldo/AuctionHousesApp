#!/usr/bin/env python3
"""Placeholder embedding enrichment scaffold.

Integrate your embedding provider here and emit vectors keyed by dedupe_key.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SILVER_LOTS = ROOT / "data" / "silver" / "lots.jsonl"
OUTPUT = ROOT / "data" / "enrichments" / "embeddings_stub.jsonl"


def fake_embedding(text: str) -> list[float]:
    # Deterministic lightweight placeholder vector.
    length = len(text)
    return [float((length % 97) / 97), float((length % 53) / 53), float((length % 31) / 31)]


def main() -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with open(SILVER_LOTS, encoding="utf-8") as source, open(OUTPUT, "w", encoding="utf-8") as target:
        for line in source:
            row = json.loads(line)
            text = " ".join(filter(None, [row.get("lot_title"), row.get("description")]))
            payload = {
                "dedupe_key": row.get("dedupe_key"),
                "embedding_model": "stub-v1",
                "vector": fake_embedding(text),
            }
            target.write(json.dumps(payload, ensure_ascii=False) + "\n")
    print(f"[enrichment] wrote: {OUTPUT}")


if __name__ == "__main__":
    main()

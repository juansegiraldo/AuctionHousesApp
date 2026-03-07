#!/usr/bin/env python3
"""Example enrichment: assign simple category tags from text rules."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SILVER_LOTS = ROOT / "data" / "silver" / "lots.jsonl"
OUTPUT = ROOT / "data" / "enrichments" / "category_tags.jsonl"


RULES = {
    "painting": ["oleo", "óleo", "acrilico", "acrílico", "acuarela", "gouache"],
    "prints": ["grabado", "litografia", "litografía", "serigrafia", "serigrafía"],
    "books_documents": ["libro", "documento", "postales"],
    "decorative_arts": ["bronce", "madera", "ceramica", "cerámica", "design", "decorativas"],
}


def classify(text: str) -> str:
    lower = text.lower()
    for category, keywords in RULES.items():
        if any(keyword in lower for keyword in keywords):
            return category
    return "other"


def main() -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with open(SILVER_LOTS, encoding="utf-8") as source, open(OUTPUT, "w", encoding="utf-8") as target:
        for line in source:
            row = json.loads(line)
            text = " ".join(filter(None, [row.get("lot_title"), row.get("description"), row.get("medium")]))
            payload = {
                "dedupe_key": row.get("dedupe_key"),
                "category": classify(text),
            }
            target.write(json.dumps(payload, ensure_ascii=False) + "\n")
    print(f"[enrichment] wrote: {OUTPUT}")


if __name__ == "__main__":
    main()

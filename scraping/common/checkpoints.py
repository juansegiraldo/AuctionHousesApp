"""Historic-run persistence helpers, lifted verbatim from Duran's run_historic.

Shared so every house gets resume + per-auction checkpoints + merged output for free.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

import orjson

from scraping.common.models import AuctionMeta


def save_auction_index(auctions: list[AuctionMeta], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as handle:
        for auction in auctions:
            handle.write(orjson.dumps(auction.model_dump(), option=orjson.OPT_APPEND_NEWLINE))


def write_checkpoint(checkpoint_dir: Path, auction_id: str, payload: dict) -> None:
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    with open(checkpoint_dir / f"{auction_id}.json", "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)


def merge_outputs(
    auctions: list[AuctionMeta],
    output_path_for: Callable[[AuctionMeta], Path],
    merged_path: Path,
) -> int:
    """Concatenate each auction's individual JSONL into one merged file. Returns line count."""
    merged_path.parent.mkdir(parents=True, exist_ok=True)
    merged_lots = 0
    with open(merged_path, "wb") as merged:
        for auction in auctions:
            individual_path = output_path_for(auction)
            if not individual_path.exists():
                continue
            with open(individual_path, "rb") as input_handle:
                payload = input_handle.read()
                merged.write(payload)
            merged_lots += payload.count(b"\n")
    return merged_lots

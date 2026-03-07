#!/usr/bin/env python3
"""Phase 3: scrape Duran historic auctions with resume/checkpoints."""

from __future__ import annotations

import argparse
import json
import logging
import time
from pathlib import Path

import orjson

from scraping.common.models import AuctionMeta
from scraping.houses.duran_subastas.parsers import _auction_id_from_url, parse_historic_page
from scraping.houses.duran_subastas.run_one_auction import (
    DEFAULT_OUTPUT_DIR,
    fetch_with_retry,
    log_event,
    scrape_auction,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

DEFAULT_HISTORIC_URL = "https://www.duran-subastas.com/es/subastas-historicas/"


def fetch_historic(url: str, max_retries: int, timeout_seconds: float) -> list[AuctionMeta]:
    page = fetch_with_retry(url, max_retries=max_retries, timeout_seconds=timeout_seconds)
    auctions = parse_historic_page(page)
    log_event("historic_discovered", count=len(auctions), url=url)
    return auctions


def save_auction_index(auctions: list[AuctionMeta], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as handle:
        for auction in auctions:
            handle.write(orjson.dumps(auction.model_dump(), option=orjson.OPT_APPEND_NEWLINE))


def write_checkpoint(checkpoint_dir: Path, auction_id: str, payload: dict) -> None:
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    with open(checkpoint_dir / f"{auction_id}.json", "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)


def main() -> None:
    parser = argparse.ArgumentParser(description="Scrape Duran historic auctions.")
    parser.add_argument("--url", default=DEFAULT_HISTORIC_URL)
    parser.add_argument("-o", "--output", default=None, help="Merged output")
    parser.add_argument("-d", "--delay", type=float, default=1.5)
    parser.add_argument("--list-only", action="store_true")
    parser.add_argument("--start-from", default=None)
    parser.add_argument("--quick", action="store_true")
    parser.add_argument("--max-auctions", type=int, default=None)
    parser.add_argument("--max-lots-per-auction", type=int, default=None)
    parser.add_argument("--max-retries", type=int, default=2)
    parser.add_argument("--timeout", type=float, default=20.0)
    args = parser.parse_args()

    DEFAULT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    checkpoint_dir = DEFAULT_OUTPUT_DIR / "checkpoints"
    merged_path = Path(args.output) if args.output else (DEFAULT_OUTPUT_DIR / "historic_all_lots.jsonl")

    auctions = fetch_historic(args.url, max_retries=args.max_retries, timeout_seconds=args.timeout)
    save_auction_index(auctions, DEFAULT_OUTPUT_DIR / "auction_index.jsonl")

    if args.start_from:
        for idx, auction in enumerate(auctions):
            if args.start_from in auction.auction_id or args.start_from in auction.auction_url:
                auctions = auctions[idx:]
                break

    if args.max_auctions is not None:
        auctions = auctions[: args.max_auctions]

    if args.list_only:
        for auction in auctions:
            print(f"{auction.auction_id} -> {auction.auction_url}")
        return

    merged_path.parent.mkdir(parents=True, exist_ok=True)
    total_lots = 0
    with open(merged_path, "ab") as merged:
        for auction in auctions:
            auction_id = _auction_id_from_url(auction.auction_url)
            individual_path = DEFAULT_OUTPUT_DIR / f"{auction_id}.jsonl"
            if individual_path.exists():
                write_checkpoint(
                    checkpoint_dir,
                    auction_id,
                    {"status": "skipped_existing", "auction_id": auction_id, "output": str(individual_path)},
                )
            else:
                try:
                    lots = scrape_auction(
                        auction.auction_url,
                        individual_path,
                        delay=args.delay,
                        skip_lot_detail=args.quick,
                        auction_meta=auction,
                        max_lots_per_auction=args.max_lots_per_auction,
                        max_retries=args.max_retries,
                        timeout_seconds=args.timeout,
                    )
                    total_lots += len(lots)
                    write_checkpoint(
                        checkpoint_dir,
                        auction_id,
                        {"status": "done", "auction_id": auction_id, "accepted_lots": len(lots)},
                    )
                except Exception as exc:  # pragma: no cover - network dependent
                    write_checkpoint(
                        checkpoint_dir,
                        auction_id,
                        {"status": "failed", "auction_id": auction_id, "error_type": type(exc).__name__, "error": str(exc)},
                    )
                    log_event("auction_failed", auction_id=auction_id, error_type=type(exc).__name__, message=str(exc))
                    continue
                time.sleep(args.delay * 2)

            if individual_path.exists():
                with open(individual_path, "rb") as input_handle:
                    merged.write(input_handle.read())

    log_event("historic_done", total_lots=total_lots, merged_output=str(merged_path))


if __name__ == "__main__":
    main()


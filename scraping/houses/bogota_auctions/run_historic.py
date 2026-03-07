#!/usr/bin/env python3
"""Phase 3: scrape Bogota Auctions historic index and then each auction."""

from __future__ import annotations

import argparse
import logging
import time
from pathlib import Path

import orjson
from scrapling import Fetcher

from scraping.common.models import AuctionMeta
from scraping.houses.bogota_auctions.parsers import _auction_id_from_url, parse_historic_page
from scraping.houses.bogota_auctions.run_one_auction import DEFAULT_OUTPUT_DIR, scrape_auction

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

DEFAULT_HISTORIC_URL = "https://www.bogotaauctions.com/es/subastas-historicas"


def fetch_historic(url: str) -> list[AuctionMeta]:
    page = Fetcher.get(url)
    auctions = parse_historic_page(page)
    log.info("Found %d auctions in historic listing", len(auctions))
    return auctions


def save_auction_index(auctions: list[AuctionMeta], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as output_file:
        for auction in auctions:
            output_file.write(orjson.dumps(auction.model_dump(), option=orjson.OPT_APPEND_NEWLINE))


def main() -> None:
    parser = argparse.ArgumentParser(description="Scrape full historic from Bogota Auctions.")
    parser.add_argument("--url", default=DEFAULT_HISTORIC_URL, help="URL of the historic page")
    parser.add_argument("-o", "--output", default=None, help="Merged JSONL output file")
    parser.add_argument("-d", "--delay", type=float, default=1.5, help="Delay between requests")
    parser.add_argument("--list-only", action="store_true", help="Only list auctions found")
    parser.add_argument("--start-from", default=None, help="Start from auction id fragment")
    parser.add_argument("--quick", action="store_true", help="Skip lot detail pages")
    args = parser.parse_args()

    DEFAULT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    merged_path = Path(args.output) if args.output else (DEFAULT_OUTPUT_DIR / "historic_all_lots.jsonl")
    auctions = fetch_historic(args.url)
    save_auction_index(auctions, DEFAULT_OUTPUT_DIR / "auction_index.jsonl")

    if args.list_only:
        for auction in auctions:
            print(f"{auction.auction_start_date or '?'} - {auction.auction_title}")
            print(f"  {auction.auction_url}")
        return

    start_idx = 0
    if args.start_from:
        for index, auction in enumerate(auctions):
            if args.start_from in auction.auction_id or args.start_from in auction.auction_url:
                start_idx = index
                break

    merged_path.parent.mkdir(parents=True, exist_ok=True)
    total_lots = 0
    with open(merged_path, "ab") as merged_handle:
        for auction in auctions[start_idx:]:
            auction_id = _auction_id_from_url(auction.auction_url)
            individual_path = DEFAULT_OUTPUT_DIR / f"{auction_id}.jsonl"

            if not individual_path.exists():
                lots = scrape_auction(
                    auction.auction_url,
                    individual_path,
                    delay=args.delay,
                    skip_lot_detail=args.quick,
                    auction_meta=auction,
                )
                total_lots += len(lots)
                time.sleep(args.delay * 2)

            with open(individual_path, "rb") as input_handle:
                merged_handle.write(input_handle.read())

    log.info("Done. %d lots scraped to %s", total_lots, merged_path)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Phase 2: scrape multiple Duran auctions from URLs/file."""

from __future__ import annotations

import argparse
import logging
import shutil
import time
from pathlib import Path

from scraping.houses.duran_subastas.parsers import _auction_id_from_url
from scraping.houses.duran_subastas.run_one_auction import DEFAULT_OUTPUT_DIR, scrape_auction

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(description="Scrape multiple Duran auctions.")
    parser.add_argument("urls", nargs="*", help="Auction URLs")
    parser.add_argument("-f", "--file", default=None, help="One URL per line")
    parser.add_argument("-o", "--output", default=None, help="Merged output file")
    parser.add_argument("-d", "--delay", type=float, default=1.0)
    parser.add_argument("--quick", action="store_true")
    parser.add_argument("--max-lots-per-auction", type=int, default=None)
    parser.add_argument("--max-retries", type=int, default=2)
    parser.add_argument("--timeout", type=float, default=20.0)
    args = parser.parse_args()

    urls = list(args.urls)
    if args.file:
        with open(args.file, encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if line and not line.startswith("#"):
                    urls.append(line)

    if not urls:
        parser.error("No auction URLs provided.")

    DEFAULT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    merged_path = Path(args.output) if args.output else None
    total_lots = 0

    for index, auction_url in enumerate(urls, 1):
        auction_id = _auction_id_from_url(auction_url)
        out = DEFAULT_OUTPUT_DIR / f"{auction_id}.jsonl"
        lots = scrape_auction(
            auction_url,
            out,
            delay=args.delay,
            skip_lot_detail=args.quick,
            max_lots_per_auction=args.max_lots_per_auction,
            max_retries=args.max_retries,
            timeout_seconds=args.timeout,
        )
        total_lots += len(lots)
        if index < len(urls):
            time.sleep(args.delay * 2)

    if merged_path and len(urls) > 1:
        merged_path.parent.mkdir(parents=True, exist_ok=True)
        with open(merged_path, "wb") as out_handle:
            for auction_url in urls:
                auction_id = _auction_id_from_url(auction_url)
                src = DEFAULT_OUTPUT_DIR / f"{auction_id}.jsonl"
                if src.exists():
                    with open(src, "rb") as in_handle:
                        shutil.copyfileobj(in_handle, out_handle)
    log.info("Done. %d lots scraped in %d auctions.", total_lots, len(urls))


if __name__ == "__main__":
    main()


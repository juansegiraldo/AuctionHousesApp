#!/usr/bin/env python3
"""Phase 2: scrape multiple Bogota Auctions auctions from a list of URLs."""

from __future__ import annotations

import argparse
import logging
import shutil
import time
from pathlib import Path

from scraping.houses.bogota_auctions.parsers import _auction_id_from_url
from scraping.houses.bogota_auctions.run_one_auction import DEFAULT_OUTPUT_DIR, scrape_auction

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(description="Scrape multiple Bogota Auctions auctions.")
    parser.add_argument("urls", nargs="*", help="Auction URLs to scrape")
    parser.add_argument("-f", "--file", default=None, help="Text file with one auction URL per line")
    parser.add_argument("-o", "--output", default=None, help="Single merged JSONL output file")
    parser.add_argument("-d", "--delay", type=float, default=1.0, help="Delay between requests")
    parser.add_argument("--quick", action="store_true", help="Skip lot detail pages")
    args = parser.parse_args()

    urls = list(args.urls)
    if args.file:
        with open(args.file, encoding="utf-8") as file_handle:
            for line in file_handle:
                stripped = line.strip()
                if stripped and not stripped.startswith("#"):
                    urls.append(stripped)

    if not urls:
        parser.error("No auction URLs provided. Pass URLs as arguments or via --file.")

    DEFAULT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    merged_path = Path(args.output) if args.output else None
    total_lots = 0

    for i, auction_url in enumerate(urls, 1):
        log.info("\n========== Auction %d/%d ==========", i, len(urls))
        auction_id = _auction_id_from_url(auction_url)
        individual_path = DEFAULT_OUTPUT_DIR / f"{auction_id}.jsonl"
        lots = scrape_auction(
            auction_url,
            individual_path,
            delay=args.delay,
            skip_lot_detail=args.quick,
        )
        total_lots += len(lots)
        if i < len(urls):
            time.sleep(args.delay * 2)

    if merged_path and len(urls) > 1:
        merged_path.parent.mkdir(parents=True, exist_ok=True)
        with open(merged_path, "wb") as merged:
            for auction_url in urls:
                src = DEFAULT_OUTPUT_DIR / f"{_auction_id_from_url(auction_url)}.jsonl"
                if src.exists():
                    with open(src, "rb") as source_handle:
                        shutil.copyfileobj(source_handle, merged)

    log.info("\nDone. %d lots scraped across %d auctions.", total_lots, len(urls))


if __name__ == "__main__":
    main()

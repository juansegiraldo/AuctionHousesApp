#!/usr/bin/env python3
"""
Phase 1: Scrape a single Bogota Auctions auction and all its lots.
"""

from __future__ import annotations

import argparse
import logging
import time
from pathlib import Path

import orjson
from scrapling import Fetcher

from scraping.common.models import AuctionMeta, LotItem
from scraping.houses.bogota_auctions.parsers import (
    _auction_id_from_url,
    _info_url_from_auction_url,
    get_auction_page_urls,
    get_auction_title_from_page,
    parse_auction_page,
    parse_historic_page,
    parse_lot_page,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

HOUSE_DIR = Path(__file__).resolve().parent
DEFAULT_OUTPUT_DIR = HOUSE_DIR / "output"


def fetch_page(url: str):
    return Fetcher.get(url)


def _meta_from_historic(auction_url: str) -> AuctionMeta | None:
    try:
        historic_url = "https://www.bogotaauctions.com/es/subastas-historicas"
        page = fetch_page(historic_url)
        auctions = parse_historic_page(page)
        norm = auction_url.split("?")[0].rstrip("/")
        for auction in auctions:
            if (auction.auction_url or "").split("?")[0].rstrip("/") == norm:
                return auction
    except Exception as exc:
        log.warning("Could not load historic index for dates: %s", exc)
    return None


def scrape_auction(
    auction_url: str,
    output_path: Path,
    delay: float = 1.0,
    skip_lot_detail: bool = False,
    auction_meta: AuctionMeta | None = None,
) -> list[LotItem]:
    log.info("Fetching auction page: %s", auction_url)
    first_page = fetch_page(auction_url)
    auction_title = get_auction_title_from_page(first_page)
    auction_id = _auction_id_from_url(auction_url)

    if auction_meta:
        meta = auction_meta.model_copy(
            update={
                "auction_id": auction_id,
                "auction_title": auction_title or auction_meta.auction_title,
                "auction_url": auction_url,
            }
        )
    else:
        meta = _meta_from_historic(auction_url)
        if meta:
            meta = meta.model_copy(
                update={
                    "auction_id": auction_id,
                    "auction_title": auction_title or meta.auction_title,
                    "auction_url": auction_url,
                }
            )
        else:
            meta = AuctionMeta(
                auction_id=auction_id,
                auction_title=auction_title,
                auction_url=auction_url,
                auction_info_url=_info_url_from_auction_url(auction_url),
            )

    all_page_urls = get_auction_page_urls(first_page, auction_url)
    lot_previews: list[dict] = parse_auction_page(first_page, meta)
    for page_url in all_page_urls:
        if page_url in {auction_url, auction_url.split("?")[0]}:
            continue
        time.sleep(delay)
        lot_previews.extend(parse_auction_page(fetch_page(page_url), meta))

    seen: set[str] = set()
    unique_previews: list[dict] = []
    for preview in lot_previews:
        if preview["lot_url"] not in seen:
            seen.add(preview["lot_url"])
            unique_previews.append(preview)

    results: list[LotItem] = []
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "wb") as output_file:
        for index, preview in enumerate(unique_previews, 1):
            lot_url = preview["lot_url"]
            if skip_lot_detail:
                lot_data = _lot_from_preview(preview, meta)
            else:
                log.info("  [%d/%d] Scraping lot: %s", index, len(unique_previews), lot_url)
                time.sleep(delay)
                try:
                    detail = parse_lot_page(fetch_page(lot_url), meta)
                except Exception as exc:
                    log.warning("  Failed to fetch lot %s: %s", lot_url, exc)
                    detail = {}
                lot_data = _merge_lot(preview, detail, meta, lot_url)

            results.append(lot_data)
            output_file.write(orjson.dumps(lot_data.model_dump(), option=orjson.OPT_APPEND_NEWLINE))

    log.info("Wrote %d lots to %s", len(results), output_path)
    return results


def _lot_from_preview(preview: dict, meta: AuctionMeta) -> LotItem:
    return LotItem(
        auction_id=meta.auction_id,
        auction_title=meta.auction_title,
        auction_start_date=meta.auction_start_date,
        auction_end_date=meta.auction_end_date,
        auction_house_name=meta.auction_house_name,
        auction_url=meta.auction_url,
        auction_info_url=meta.auction_info_url,
        lot_number=preview.get("lot_number"),
        lot_url=preview["lot_url"],
        lot_title=preview.get("lot_title"),
        lot_year=preview.get("lot_year"),
        image_url=preview.get("thumbnail_url"),
        price_estimate_min=preview.get("price_estimate_min"),
        price_estimate_max=preview.get("price_estimate_max"),
        price_sold=preview.get("price_sold"),
        status=preview.get("status"),
    )


def _merge_lot(preview: dict, detail: dict, meta: AuctionMeta, lot_url: str) -> LotItem:
    return LotItem(
        auction_id=detail.get("auction_id", meta.auction_id),
        auction_title=detail.get("auction_title", meta.auction_title),
        auction_start_date=detail.get("auction_start_date", meta.auction_start_date),
        auction_end_date=detail.get("auction_end_date", meta.auction_end_date),
        auction_house_name=detail.get("auction_house_name", meta.auction_house_name),
        auction_url=detail.get("auction_url", meta.auction_url),
        auction_info_url=detail.get("auction_info_url", meta.auction_info_url),
        lot_number=detail.get("lot_number") or preview.get("lot_number"),
        lot_url=lot_url,
        lot_title=detail.get("lot_title") or preview.get("lot_title"),
        lot_year=detail.get("lot_year") or preview.get("lot_year"),
        image_url=detail.get("image_url") or preview.get("thumbnail_url"),
        price_estimate_min=detail.get("price_estimate_min") or preview.get("price_estimate_min"),
        price_estimate_max=detail.get("price_estimate_max") or preview.get("price_estimate_max"),
        price_sold=detail.get("price_sold") or preview.get("price_sold"),
        currency=detail.get("currency", "COP"),
        artist_name=detail.get("artist_name"),
        artist_birth_year=detail.get("artist_birth_year"),
        artist_death_year=detail.get("artist_death_year"),
        artist_country=detail.get("artist_country"),
        artist_raw=detail.get("artist_raw"),
        description=detail.get("description"),
        medium=detail.get("medium"),
        dimensions=detail.get("dimensions"),
        provenance=detail.get("provenance"),
        status=detail.get("status") or preview.get("status"),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Scrape a single Bogota Auctions auction.")
    parser.add_argument("auction_url", help="URL of the auction page")
    parser.add_argument("-o", "--output", default=None, help="Custom output path")
    parser.add_argument("-d", "--delay", type=float, default=1.0, help="Delay between requests in seconds")
    parser.add_argument("--quick", action="store_true", help="Skip lot detail pages")
    args = parser.parse_args()

    if args.output:
        output_path = Path(args.output)
    else:
        output_path = DEFAULT_OUTPUT_DIR / f"{_auction_id_from_url(args.auction_url)}.jsonl"

    lots = scrape_auction(
        args.auction_url,
        output_path,
        delay=args.delay,
        skip_lot_detail=args.quick,
    )
    print(f"\nDone. {len(lots)} lots scraped -> {output_path}")


if __name__ == "__main__":
    main()

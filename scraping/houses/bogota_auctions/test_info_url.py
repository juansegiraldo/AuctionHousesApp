#!/usr/bin/env python3
"""Quick checks for auction_info_url extraction."""

from __future__ import annotations

import json
import sys

from pathlib import Path

from scrapling import Fetcher

from scraping.houses.bogota_auctions.parsers import _info_url_from_auction_url, parse_historic_page
from scraping.houses.bogota_auctions.run_one_auction import DEFAULT_OUTPUT_DIR, scrape_auction


def test_historic_index() -> bool:
    page = Fetcher.get("https://www.bogotaauctions.com/es/subastas-historicas")
    auctions = parse_historic_page(page)
    return bool(auctions and auctions[0].auction_info_url)


def test_derived_url() -> bool:
    url = "https://www.bogotaauctions.com/es/subasta/libros-documentos-y-grabados-antiguos-virtual_2685B-001"
    expected = "https://www.bogotaauctions.com/es/info-subasta/2685B-libros-documentos-y-grabados-antiguos-virtual"
    return _info_url_from_auction_url(url) == expected


def test_scrape_has_info_url() -> bool:
    out = DEFAULT_OUTPUT_DIR / "test_info_url.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    url = "https://www.bogotaauctions.com/es/subasta/libros-documentos-y-grabados-antiguos-virtual_2685B-001"
    scrape_auction(url, out, delay=0.5, skip_lot_detail=True)
    with open(out, encoding="utf-8") as file_handle:
        row = json.loads(file_handle.readline())
    return bool(row.get("auction_info_url"))


if __name__ == "__main__":
    checks = [test_historic_index(), test_derived_url(), test_scrape_has_info_url()]
    sys.exit(0 if all(checks) else 1)

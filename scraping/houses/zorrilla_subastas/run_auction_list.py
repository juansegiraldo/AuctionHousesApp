#!/usr/bin/env python3
"""Fase 2: scrapear varios catalogos de Zorrilla (LiveAuctioneers)."""

from __future__ import annotations

import logging

from scraping.common import runner
from scraping.houses.zorrilla_subastas.house import DEFAULT_OUTPUT_DIR, HOUSE
from scraping.houses.zorrilla_subastas.run_one_auction import scrape_auction

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

__all__ = ["HOUSE", "DEFAULT_OUTPUT_DIR", "scrape_auction"]


if __name__ == "__main__":
    runner.run_auction_list_cli(globals())

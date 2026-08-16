#!/usr/bin/env python3
"""Fase 1: scrapear un catalogo de Zorrilla (LiveAuctioneers).

Shim sobre el engine compartido: la logica vive en scraping/common/runner.py.
"""

from __future__ import annotations

import functools
import logging

from scraping.common import runner
from scraping.houses.zorrilla_subastas.house import DEFAULT_OUTPUT_DIR, HOUSE

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

# el CLI resuelve estos nombres desde globals() de este modulo
scrape_auction = functools.partial(runner.scrape_auction, HOUSE)

__all__ = ["HOUSE", "DEFAULT_OUTPUT_DIR", "scrape_auction"]


if __name__ == "__main__":
    runner.run_one_auction_cli(globals())

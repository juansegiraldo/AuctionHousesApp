#!/usr/bin/env python3
"""Fase 1: scrapear una subasta de Lefebre.

    python -m scraping.houses.lefebre_subastas.run_one_auction \
        https://auction.lefebresubastas.com/auctions/4-GS38GR/subasta-34 --quick

Usar siempre --quick: el catalogo ya trae precio, estado, titulo, numero de lote
e imagen, y /ajax/lot/<id> no devuelve nada util (ver parse_lot_page).
"""

from __future__ import annotations

import functools
import logging

from scraping.common import runner
from scraping.houses.lefebre_subastas.house import DEFAULT_OUTPUT_DIR, HOUSE

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

# el CLI resuelve estos nombres desde globals() de este modulo
scrape_auction = functools.partial(runner.scrape_auction, HOUSE)

__all__ = ["HOUSE", "DEFAULT_OUTPUT_DIR", "scrape_auction"]


if __name__ == "__main__":
    runner.run_one_auction_cli(globals())

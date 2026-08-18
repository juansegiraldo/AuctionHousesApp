#!/usr/bin/env python3
"""Fase 2: scrapear una lista de subastas de Lefebre.

    python -m scraping.houses.lefebre_subastas.run_auction_list -f urls.txt --quick

OJO: a diferencia de run_historic, aqui NO hay resume ni exclusion de las
subastas del Excel. Lo que se le pase se baja y se sobreescribe. Para el uso
normal (bajar lo que falta) usa run_historic.
"""

from __future__ import annotations

import logging

from scraping.common import runner
from scraping.houses.lefebre_subastas.house import DEFAULT_OUTPUT_DIR, HOUSE
from scraping.houses.lefebre_subastas.run_one_auction import scrape_auction

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

__all__ = ["HOUSE", "DEFAULT_OUTPUT_DIR", "scrape_auction"]


if __name__ == "__main__":
    runner.run_auction_list_cli(globals())

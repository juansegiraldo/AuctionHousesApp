#!/usr/bin/env python3
"""Fase 3: scrapear todo el historico de Zorrilla en LiveAuctioneers.

45 catalogos (2019-05 -> 2023-08), ~12.500 lotes. Resume y checkpoints los pone
el engine compartido.
"""

from __future__ import annotations

import logging

from scraping.common import net, runner
from scraping.common.models import AuctionMeta
from scraping.houses.zorrilla_subastas.house import DEFAULT_OUTPUT_DIR, HOUSE
from scraping.houses.zorrilla_subastas.parsers import parse_historic_page
from scraping.houses.zorrilla_subastas.run_one_auction import scrape_auction

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


MAX_HOUSE_PAGES = 10


def fetch_historic(url: str, max_retries: int, timeout_seconds: float) -> list[AuctionMeta]:
    """Lista los catalogos historicos paginando la pagina de la casa.

    OJO: la pagina 1 solo trae 24 catalogos de los 45 reales. Sin paginar aqui se
    perderian ~21 catalogos (~6.000 lotes, todo el periodo 2019-2020). Se para
    cuando una pagina no aporta ningun catalogo nuevo.
    """
    found: dict[str, AuctionMeta] = {}
    for page_number in range(1, MAX_HOUSE_PAGES + 1):
        page_url = url if page_number == 1 else f"{url.rstrip('/')}/?page={page_number}"
        page = net.fetch_with_retry(
            page_url,
            max_retries,
            timeout_seconds,
            fetcher=HOUSE.fetcher,
            house_slug=HOUSE.slug,
        )
        nuevos = [a for a in parse_historic_page(page) if a.auction_id not in found]
        for auction in nuevos:
            found[auction.auction_id] = auction
        net.log_event(
            "historic_page",
            house_slug=HOUSE.slug,
            page=page_number,
            new=len(nuevos),
            total=len(found),
        )
        if not nuevos:
            break

    auctions = sorted(found.values(), key=lambda a: a.auction_start_date or "")
    net.log_event("historic_discovered", house_slug=HOUSE.slug, count=len(auctions), url=url)
    return auctions


__all__ = ["HOUSE", "DEFAULT_OUTPUT_DIR", "scrape_auction", "fetch_historic"]


if __name__ == "__main__":
    runner.run_historic_cli(globals())

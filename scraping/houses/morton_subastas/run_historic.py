#!/usr/bin/env python3
"""Fase 3: scrapear todo el historico de ARTE de Morton Subastas.

803 subastas pasadas (2020-03 -> hoy), de las que 57 son de arte (2021-2026).
Resume y checkpoints los pone el engine compartido.
"""

from __future__ import annotations

import logging

from scraping.common import net, runner
from scraping.common.models import AuctionMeta
from scraping.houses.morton_subastas.house import DEFAULT_OUTPUT_DIR, HOUSE
from scraping.houses.morton_subastas.parsers import is_art_auction, parse_historic_page
from scraping.houses.morton_subastas.run_one_auction import scrape_auction

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


# 34 paginas de 24 subastas en 2026-10; margen para que crezca.
MAX_HOUSE_PAGES = 80


def fetch_historic(url: str, max_retries: int, timeout_seconds: float) -> list[AuctionMeta]:
    """Lista las subastas pasadas paginando y se queda con las de arte.

    OJO: una pagina fuera de rango NO viene vacia, repite la ultima. Se para
    cuando una pagina no aporta ninguna subasta nueva.
    """
    found: dict[str, AuctionMeta] = {}
    for page_number in range(1, MAX_HOUSE_PAGES + 1):
        page_url = url if page_number == 1 else f"{url}?page={page_number}"
        page = net.fetch_with_retry(
            page_url, max_retries, timeout_seconds, fetcher=HOUSE.fetcher, house_slug=HOUSE.slug
        )
        nuevas = [a for a in parse_historic_page(page) if a.auction_id not in found]
        for auction in nuevas:
            found[auction.auction_id] = auction
        net.log_event("historic_page", house_slug=HOUSE.slug, page=page_number, new=len(nuevas), total=len(found))
        if not nuevas:
            break

    arte = [a for a in found.values() if is_art_auction(a.auction_title)]
    auctions = sorted(arte, key=lambda a: a.auction_start_date or "")
    net.log_event(
        "historic_discovered", house_slug=HOUSE.slug, url=url,
        listed=len(found), art=len(auctions), skipped_not_art=len(found) - len(auctions),
    )
    return auctions


__all__ = ["HOUSE", "DEFAULT_OUTPUT_DIR", "scrape_auction", "fetch_historic"]


if __name__ == "__main__":
    runner.run_historic_cli(globals())

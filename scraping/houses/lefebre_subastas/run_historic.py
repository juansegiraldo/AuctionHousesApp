#!/usr/bin/env python3
"""Fase 3: bajar todo el historico pendiente de Lefebre.

    python -m scraping.houses.lefebre_subastas.run_historic --list-only
    python -m scraping.houses.lefebre_subastas.run_historic --quick

Que baja y que no:

  - Las 11 subastas cuyo dato viene del Excel curado se EXCLUYEN siempre, en
    parsers.EXCEL_ONLY_AUCTIONS. No es solo por no duplicar: sus 890 lotes extra
    en la web son mobiliario y joyeria que el curador descarto a proposito.
  - El resto se baja, y el resume del engine salta las que ya tengan .jsonj.
  - Las 4 que vinieron del Excel con URLs reales (27/28/29/30) se re-scrapean
    borrando antes su fichero: ver --refresh-scraped.

TRAMPA DEL RESUME (heredada, documentada en el README de Zorrilla): una subasta
que expira deja un .jsonl PARCIAL, y al relanzar el resume lo da por completo y
esos lotes se pierden en silencio. Tras un auction_timeout hay que borrar el
.jsonl y el checkpoint de esa subasta antes de relanzar.
"""

from __future__ import annotations

import logging

from scraping.common import net, runner
from scraping.common.models import AuctionMeta
from scraping.houses.lefebre_subastas.house import DEFAULT_OUTPUT_DIR, HOUSE
from scraping.houses.lefebre_subastas.parsers import parse_historic_page, raw_auction_count
from scraping.houses.lefebre_subastas.run_one_auction import scrape_auction

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

MAX_HISTORIC_PAGES = 10


def fetch_historic(url: str, max_retries: int, timeout_seconds: float) -> list[AuctionMeta]:
    """Lista las subastas paginando /auctions/past.

    OJO: la pagina 1 solo trae 20 de las 29 subastas pasadas. Sin paginar aqui
    se perderian 9, todas las de 2021-2022 — la misma trampa que Zorrilla.

    La parada NO puede mirar las subastas ya filtradas: la pagina 2 son casi
    todas del Excel y devuelve 0 utiles, pero detras podria haber una pagina 3
    con dato bueno. Se para cuando la pagina no trae ninguna subasta EN CRUDO
    (agotada de verdad), no cuando no trae ninguna util.
    """
    found: dict[str, AuctionMeta] = {}
    for page_number in range(1, MAX_HISTORIC_PAGES + 1):
        page_url = url if page_number == 1 else f"{url}?page={page_number}"
        page = net.fetch_with_retry(
            page_url,
            max_retries,
            timeout_seconds,
            fetcher=HOUSE.fetcher,
            house_slug=HOUSE.slug,
        )
        en_crudo = raw_auction_count(page)
        nuevas = [a for a in parse_historic_page(page) if a.auction_id not in found]
        for auction in nuevas:
            found[auction.auction_id] = auction
        net.log_event(
            "historic_page",
            house_slug=HOUSE.slug,
            page=page_number,
            raw=en_crudo,
            new=len(nuevas),
            total=len(found),
        )
        if not en_crudo:
            break

    auctions = sorted(found.values(), key=lambda a: a.auction_start_date or "")
    net.log_event("historic_discovered", house_slug=HOUSE.slug, count=len(auctions), url=url)
    return auctions


__all__ = ["HOUSE", "DEFAULT_OUTPUT_DIR", "scrape_auction", "fetch_historic"]


if __name__ == "__main__":
    runner.run_historic_cli(globals())

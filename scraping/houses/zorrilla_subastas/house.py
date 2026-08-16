"""Configuracion de la casa Zorrilla Subastas (via LiveAuctioneers).

Primer consumidor real del framework `scraping/common/`: aqui no hay orquestacion,
retry, resume ni escritura JSONL — todo eso lo pone el engine compartido.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from scrapling import StealthyFetcher

from scraping.common.discovery import html_pagination_discovery
from scraping.common.house import House
from scraping.houses.zorrilla_subastas import parsers

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_OUTPUT_DIR = ROOT / "scraping" / "houses" / "zorrilla_subastas" / "output"

HISTORIC_URL = "https://www.liveauctioneers.com/auctioneer/6727/zorrilla-subastas/"


def liveauctioneers_fetcher(url: str, timeout_seconds: float) -> Any:
    """Fetcher propio: LiveAuctioneers es React y `window.__data` se rellena en cliente.

    Difiere de common.net.stealthy_fetcher en `network_idle=True` + `wait`: sin esperar
    a que la red se calme, el payload llega incompleto o directamente ausente.
    `solve_cloudflare` se deja activo aunque LA no lo exija hoy (Zorrilla propio si).
    """
    return StealthyFetcher.fetch(
        url,
        headless=True,
        timeout=int(timeout_seconds * 1000),
        solve_cloudflare=True,
        load_dom=True,
        network_idle=True,
        wait=5000,
    )


HOUSE = House(
    slug="zorrilla_subastas",
    name=parsers.HOUSE_NAME,
    # LiveAuctioneers normaliza a USD en origen; el importe original en UYU no
    # existe en esta fuente (ver docstring de parsers.py y el quality_flag en gold).
    currency="USD",
    base_url=parsers.BASE_URL,
    historic_url=HISTORIC_URL,
    output_dir=DEFAULT_OUTPUT_DIR,
    parsers=parsers,
    discover=html_pagination_discovery(
        get_page_urls=parsers.get_page_urls,
        parse_auction_page=parsers.parse_auction_page,
    ),
    fetcher=liveauctioneers_fetcher,
    # el navegador headless tarda ~10-40s por pagina: no hace falta anadir mas espera
    default_delay=0.5,
    historic_delay=1.0,
    default_retries=2,
    # timeout generoso: una pagina de catalogo con network_idle puede irse a 90s
    default_timeout=120.0,
)

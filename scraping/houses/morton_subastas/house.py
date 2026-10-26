"""Configuracion de la casa Morton Subastas (Ciudad de Mexico).

Segunda casa sobre el framework `scraping/common/`, copiada de Zorrilla: aqui no
hay orquestacion, retry, resume ni escritura JSONL — todo eso lo pone el engine.
"""

from __future__ import annotations

from pathlib import Path

from scraping.common.discovery import html_pagination_discovery
from scraping.common.house import House
from scraping.houses.morton_subastas import parsers

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_OUTPUT_DIR = ROOT / "scraping" / "houses" / "morton_subastas" / "output"


HOUSE = House(
    slug="morton_subastas",
    name=parsers.HOUSE_NAME,
    # Pesos mexicanos: la casa cotiza en MXN (JSON-LD priceCurrency) y la
    # conversion a USD que pinta la web es suya, con una tasa fija de 18.78.
    currency="MXN",
    base_url=parsers.BASE_URL,
    historic_url=parsers.HISTORIC_URL,
    output_dir=DEFAULT_OUTPUT_DIR,
    parsers=parsers,
    discover=html_pagination_discovery(
        get_page_urls=parsers.get_page_urls,
        parse_auction_page=parsers.parse_auction_page,
    ),
    # HTML servido por el servidor: basta el fetcher plano (sin navegador).
    # Se corre SIN --quick: la ficha de cada lote es la unica fuente de precio
    # antes de 2024 (ver parsers.py), ~12.500 fichas en total.
    default_delay=0.5,
    historic_delay=0.5,
    default_retries=3,
    default_timeout=30.0,
)

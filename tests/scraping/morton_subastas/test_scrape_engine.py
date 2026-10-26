"""Morton de punta a punta por el engine compartido, con descargas falsas.

Prueba lo que los tests de parsers no ven: que un catalogo detras de login
("Login for Price") sale con precio porque el engine pide la ficha del lote, y
que el catalogo paginado no duplica lotes.
"""
import dataclasses
from pathlib import Path

import orjson

from scraping.common import runner
from scraping.houses.morton_subastas.house import HOUSE

FIXTURES = Path(__file__).parent / "fixtures"
EVENT_2021 = "https://live.mortonsubastas.com/en/auctions/morton-subastas/arte-moderno-y-contempor-neo-modern-and-contemporary-art-7312"


def _fake_fetcher(lot_pages: dict[str, str], catalog: str):
    seen: list[str] = []

    def fetch(url: str, timeout_seconds: float) -> str:
        seen.append(url)
        if "/online-auctions/" in url:
            for suffix, fixture in lot_pages.items():
                if url.endswith(suffix):
                    return (FIXTURES / fixture).read_text(encoding="utf-8")
            raise RuntimeError("ficha no disponible")  # el engine es lenient
        # la subasta y todas sus paginas de catalogo devuelven el mismo HTML
        return (FIXTURES / catalog).read_text(encoding="utf-8")

    return fetch, seen


def test_login_catalog_gets_price_status_and_biography_from_the_lot_page(tmp_path):
    fetch, seen = _fake_fetcher({"-2349617": "lot_2021_sold_bilingual.html"}, "catalog_2021_bilingual.html")
    house = dataclasses.replace(HOUSE, fetcher=fetch, default_delay=0, default_retries=0)
    out = tmp_path / "7312.jsonl"

    lots = runner.scrape_auction(house, EVENT_2021, out, max_lots_per_auction=3)

    # 312 resultados -> 3 paginas a 120; repiten lotes y el engine los deduplica
    assert sum("/catalog?limit=120&page=" in u for u in seen) == 3
    assert [lot.lot_number for lot in lots] == [1, 2, 3]

    alzaga = lots[2]
    assert (alzaga.status, alzaga.price_sold, alzaga.currency) == ("VENDIDO", 48000, "MXN")
    assert alzaga.artist_name == "Jorge Alzaga"
    assert (alzaga.artist_birth_year, alzaga.artist_death_year) == (1938, 2010)
    assert alzaga.artist_country == "México"
    assert alzaga.auction_start_date == "2021-08-26T17:00:00-05:00"
    assert alzaga.auction_house_name == "Morton Subastas"

    # Sin ficha: no hay precio que leer y no se inventa "no vendido", pero el
    # autor leido del titulo del catalogo se conserva.
    osorio = lots[0]
    assert (osorio.status, osorio.price_sold) == (None, None)
    assert osorio.artist_name == "Trinidad Osorio"

    rows = [orjson.loads(line) for line in out.read_bytes().splitlines()]
    assert len(rows) == 3

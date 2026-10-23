from pathlib import Path

from scrapling import Selector

from scraping.houses.bogota_auctions.parsers import parse_lot_page

FIXTURES = Path(__file__).parent / "fixtures"


def _page(name: str) -> Selector:
    return Selector((FIXTURES / name).read_text(encoding="utf-8"))


def test_title_from_legacy_description_span():
    detail = parse_lot_page(_page("lot_page_2685_description.html"))
    assert detail["lot_title"].startswith("Sellos españoles del 2ndo centenario")


def test_title_from_object_title_span_2026_template():
    # Desde la subasta 2687 la ficha no trae span.description: 1.158 lotes
    # de 2026 entraron con lot_title vacio.
    detail = parse_lot_page(_page("lot_page_2026_object_title.html"))
    assert detail["lot_title"] == "Sin título, 1977"
    assert detail["lot_year"] == "1977"
    assert detail["artist_name"] == "Sara Dávila de Trujillo"

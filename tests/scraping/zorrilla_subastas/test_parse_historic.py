"""Tests del listado historico: pagina de la casa en LiveAuctioneers -> AuctionMeta."""
from pathlib import Path

from scraping.houses.zorrilla_subastas.parsers import parse_historic_page

FIXTURES = Path(__file__).parent / "fixtures"


def _house_html() -> str:
    return (FIXTURES / "la_house.html").read_text(encoding="utf-8")


def test_parse_historic_page_returns_auctions():
    auctions = parse_historic_page(_house_html())
    assert len(auctions) >= 20

    a = auctions[0]
    assert a.auction_id
    assert a.auction_url.startswith("https://www.liveauctioneers.com/catalog/")
    assert a.auction_title
    assert a.auction_house_name == "Zorrilla Subastas"


def test_historic_auctions_have_start_date():
    auctions = parse_historic_page(_house_html())
    con_fecha = [a for a in auctions if a.auction_start_date]
    assert con_fecha, "saleStartTs deberia dar fecha a casi todas las subastas"
    # epoch -> ISO, el anio debe ser plausible para el historico de Zorrilla
    anios = {a.auction_start_date[:4] for a in con_fecha}
    assert anios <= {str(y) for y in range(2018, 2027)}


def test_historic_auction_ids_are_unique():
    auctions = parse_historic_page(_house_html())
    ids = [a.auction_id for a in auctions]
    assert len(ids) == len(set(ids))


def test_historic_urls_are_catalog_urls():
    """El engine deriva el auction_id de la URL, asi que deben ser /catalog/<id>/."""
    from scraping.houses.zorrilla_subastas.parsers import _auction_id_from_url

    for a in parse_historic_page(_house_html()):
        assert _auction_id_from_url(a.auction_url) == a.auction_id

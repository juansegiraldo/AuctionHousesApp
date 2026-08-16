"""Tests del parser de catalogo (pagina de subasta) de Zorrilla via LiveAuctioneers.

Los datos NO se leen del DOM sino del JSON embebido en `window.__data`, que es mas
estable que el HTML de React y trae el precio de remate sin necesidad de login.
"""
from pathlib import Path

from scraping.common.models import AuctionMeta
from scraping.houses.zorrilla_subastas.parsers import (
    _auction_id_from_url,
    extract_page_data,
    get_auction_start_date_from_page,
    get_auction_title_from_page,
    get_page_urls,
    parse_auction_page,
)

FIXTURES = Path(__file__).parent / "fixtures"


def _catalog_html() -> str:
    return (FIXTURES / "la_catalog.html").read_text(encoding="utf-8")


def _meta() -> AuctionMeta:
    return AuctionMeta(
        auction_id="214514",
        auction_title="Uruguayan Art",
        auction_url="https://www.liveauctioneers.com/catalog/214514/",
        auction_house_name="Zorrilla Subastas",
    )


def test_auction_id_from_url_uses_catalog_id():
    assert _auction_id_from_url("https://www.liveauctioneers.com/catalog/214514/") == "214514"
    assert _auction_id_from_url("https://www.liveauctioneers.com/catalog/214514/?page=3") == "214514"


def test_extract_page_data_parses_embedded_json():
    data = extract_page_data(_catalog_html())
    assert isinstance(data, dict)
    # raw_decode debe cortar en el objeto correcto pese a las llaves anidadas
    assert "itemSummary" in data


def test_get_auction_title_from_page():
    assert get_auction_title_from_page(_catalog_html()) == "Uruguayan Art"


def test_get_auction_start_date_is_iso_from_epoch():
    # saleStartTs es epoch UTC -> ISO, evitando el parseo de texto espanol de Duran
    start = get_auction_start_date_from_page(_catalog_html())
    assert start is not None
    assert start.startswith("2021-09")


def test_parse_auction_page_extracts_lots_with_sold_price():
    previews = parse_auction_page(_catalog_html(), _meta())
    assert len(previews) >= 20

    first = previews[0]
    assert first["lot_url"].startswith("https://www.liveauctioneers.com/item/")
    assert isinstance(first["lot_number"], int)
    assert first["lot_title"]

    # el valor que justifica toda esta fuente: precio de remate real
    sold = [p for p in previews if p.get("price_sold")]
    assert sold, "se esperaba al menos un lote con precio de remate"
    assert all(isinstance(p["price_sold"], int) for p in sold)


def test_parse_auction_page_marks_status_from_is_sold():
    previews = parse_auction_page(_catalog_html(), _meta())
    estados = {p.get("status") for p in previews}
    # is_sold es explicito en el payload -> no inferimos por "tiene precio"
    assert estados <= {"VENDIDO", "NO VENDIDO"}
    assert "VENDIDO" in estados


def test_parse_auction_page_sets_estimates():
    previews = parse_auction_page(_catalog_html(), _meta())
    con_est = [p for p in previews if p.get("price_estimate_min")]
    assert con_est
    p = con_est[0]
    assert p["price_estimate_min"] <= p["price_estimate_max"]


def test_pagination_yields_new_lots():
    """page=2 debe aportar lotes nuevos, no repetir la pagina 1.

    No se exige solapamiento CERO: LiveAuctioneers repite unos pocos lotes
    promocionados en todas las paginas (3 de 27 en esta fixture). El engine
    deduplica por lot_url, asi que lo que importa es que la mayoria sea nueva.
    """
    p1 = parse_auction_page(_catalog_html(), _meta())
    p2_html = (FIXTURES / "la_catalog_p2.html").read_text(encoding="utf-8")
    p2 = parse_auction_page(p2_html, _meta())
    urls1 = {p["lot_url"] for p in p1}
    urls2 = {p["lot_url"] for p in p2}
    assert urls1 and urls2

    nuevos = urls2 - urls1
    assert len(nuevos) >= len(urls2) * 0.7, (
        f"page=2 solo aporto {len(nuevos)}/{len(urls2)} lotes nuevos"
    )
    # y deben ser lotes posteriores: p1 arranca en el lote 1, p2 mas adelante
    assert min(p["lot_number"] for p in p2) > min(p["lot_number"] for p in p1)


def test_parse_auction_page_keeps_description():
    """La descripcion viaja en el listado; perderla obligaria a re-scrapear."""
    previews = parse_auction_page(_catalog_html(), _meta())
    con_desc = [p for p in previews if p.get("description")]
    assert con_desc, "ningun lote trajo description"
    assert len(con_desc) >= len(previews) * 0.5


def test_parse_auction_page_builds_image_url():
    """image_url se monta desde photos+ids; el payload no la trae hecha."""
    previews = parse_auction_page(_catalog_html(), _meta())
    con_img = [p for p in previews if p.get("image_url")]
    assert con_img, "ningun lote trajo image_url"
    url = con_img[0]["image_url"]
    # formato verificado contra el HTML real, no deducido
    assert url.startswith("https://p1.liveauctioneers.com/6727/214514/")
    assert url.endswith("_x.jpg")


def test_quick_mode_preserves_description_and_image():
    """El engine con skip_lot_detail no debe descartar los campos del preview.

    Regresion: _lot_from_preview no copiaba description, asi que los 11.166
    lotes de Zorrilla llegaban a Silver sin descripcion pese a haberla
    descargado.
    """
    from scraping.common.runner import _lot_from_preview

    previews = parse_auction_page(_catalog_html(), _meta())
    preview = next(p for p in previews if p.get("description") and p.get("image_url"))
    lot = _lot_from_preview(preview, _meta(), "USD")
    assert lot.description == preview["description"]
    assert lot.image_url == preview["image_url"]


def test_get_page_urls_covers_all_lots():
    """lotsListed=149 con 28 por pagina -> hay que pedir varias paginas."""
    base = "https://www.liveauctioneers.com/catalog/214514/"
    urls = get_page_urls(_catalog_html(), base)
    assert len(urls) >= 5
    assert all(u.startswith(base) for u in urls)
    assert any("page=2" in u for u in urls)

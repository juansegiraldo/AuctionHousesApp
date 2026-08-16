"""Descubrimiento de subastas y exclusion de las que ya cubre el Excel."""
from pathlib import Path

from scraping.houses.lefebre_subastas.parsers import (
    EXCEL_ONLY_AUCTIONS,
    _auction_id_from_url,
    parse_historic_page,
)

FIXTURES = Path(__file__).parent / "fixtures"


def _historic() -> str:
    return (FIXTURES / "past_auctions.html").read_text(encoding="utf-8")


def test_lee_viewvars_del_html_renderizado_en_servidor():
    """La pagina es una SPA de Angular y parece vacia, pero el listado viene
    dentro del blob viewVars del propio HTML. Sin esto haria falta navegador."""
    auctions = parse_historic_page(_historic())
    assert auctions, "no se extrajo ninguna subasta de viewVars"
    ids = {a.auction_id for a in auctions}
    assert "subasta-38" in ids


def test_incluye_las_proximas_ademas_de_las_pasadas():
    ids = {a.auction_id for a in parse_historic_page(_historic())}
    assert "subasta-barranquilla-2026" in ids


def test_excluye_las_subastas_que_solo_estan_en_el_excel():
    """subasta-25 esta en la web (4-8Z5HCN) y en el Excel.

    No se scrapea por DOS motivos, y el segundo pesa mas:

    1. Sus lot_url del Excel son 'excel://' sinteticas: no colisionan con las
       https:// del scraper, asi que Silver contaria cada lote dos veces.
    2. La web trae 890 lotes mas en esas 11 subastas, y son mobiliario, joyeria
       y obra anonima que el curador descarto A PROPOSITO (93,4% de lo guardado
       tiene artista fechado, frente al 0,9% de lo descartado). Traerlos
       convertiria una base de arte en un catalogo generalista.
    """
    ids = {a.auction_id for a in parse_historic_page(_historic())}
    assert "subasta-25" not in ids
    assert "4-8Z5HCN" in EXCEL_ONLY_AUCTIONS


def test_las_ya_scrapeadas_si_se_devuelven():
    """27/28/29/30 vinieron del Excel pero sus URLs coinciden con las del API,
    asi que re-scrapearlas las sustituye sin duplicar (y anade imagenes)."""
    ids = {a.auction_id for a in parse_historic_page(_historic())}
    assert "subasta-30" in ids


def test_metadatos_de_la_subasta():
    por_id = {a.auction_id: a for a in parse_historic_page(_historic())}
    subasta = por_id["subasta-38"]
    assert subasta.auction_title == "SUBASTA 38"
    assert subasta.auction_start_date == "2026-05-20"
    assert subasta.auction_url == "https://auction.lefebresubastas.com/auctions/4-L2X0QX/subasta-38"


def test_raw_auction_count_cuenta_antes_de_excluir():
    """La paginacion para con este contador, no con el resultado filtrado.

    La pagina 2 de /auctions/past son casi todas subastas del Excel: devuelve 0
    utiles pero SI trae subastas. Parar ahi por "0 nuevas" podria saltarse una
    pagina 3 con dato bueno.
    """
    from scraping.houses.lefebre_subastas.parsers import raw_auction_count

    # la fixture trae 3 pasadas (una del Excel) + 1 proxima
    assert raw_auction_count(_historic()) == 4
    assert len(parse_historic_page(_historic())) == 3


def test_pagina_vacia_da_cero():
    from scraping.houses.lefebre_subastas.parsers import raw_auction_count

    assert raw_auction_count("<html><body>sin viewVars</body></html>") == 0


def test_auction_id_es_el_slug_no_el_codigo():
    """El fichero de salida se nombra con esto. Tiene que ser el slug para
    sobreescribir el subasta-30.jsonl que dejo el Excel, y no crear un
    4-DLG0WK.jsonl que conviviria con el (mismo dato, dos ficheros)."""
    assert _auction_id_from_url(
        "https://auction.lefebresubastas.com/auctions/4-DLG0WK/subasta-30"
    ) == "subasta-30"

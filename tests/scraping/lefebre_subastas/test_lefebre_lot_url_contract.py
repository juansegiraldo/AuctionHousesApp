"""El contrato del lot_url: Silver deduplica por 'house_slug|lot_url'.

Este es el test que impide duplicar 674 lotes. Las 4 subastas que ya estaban en
el Excel (27/28/29/30) guardaron el lot_url con DOBLE BARRA, que es lo que sale
de concatenar BASE + '/' + _detail_url (el _detail_url del API ya empieza por
'/'). Un urljoin() "bien hecho" produciria barra simple, no casaria con nada de
lo guardado y Silver contaria cada lote dos veces.

Verificado el 2026-08-16 contra los 89 lotes de subasta-30: 89/89 coinciden.
"""
from pathlib import Path

from scraping.houses.lefebre_subastas.parsers import BASE_URL, parse_auction_page

FIXTURES = Path(__file__).parent / "fixtures"

# Lote 2 de subasta-30, tal y como esta hoy en output/subasta-30.jsonl.
URL_YA_GUARDADA = (
    "https://auction.lefebresubastas.com//lots/view/4-DNKN05/"
    "ignacio-gomez-jaramillo-1910-1970st-sftinta-sobre-papelmedidas-49-x32-cm"
)


def test_lot_url_reproduce_exactamente_la_url_del_excel():
    previews = parse_auction_page((FIXTURES / "ajax_lots_page1.json").read_text(encoding="utf-8"))
    by_num = {p["lot_number"]: p for p in previews}
    assert by_num[2]["lot_url"] == URL_YA_GUARDADA


def test_la_doble_barra_es_intencionada():
    """Si alguien "arregla" la doble barra, este test lo caza antes de duplicar."""
    previews = parse_auction_page((FIXTURES / "ajax_lots_page1.json").read_text(encoding="utf-8"))
    for preview in previews:
        assert preview["lot_url"].startswith(BASE_URL + "//lots/view/"), (
            "El lot_url perdio la doble barra: dejaria de casar con los lotes ya "
            "ingeridos y Silver los duplicaria."
        )

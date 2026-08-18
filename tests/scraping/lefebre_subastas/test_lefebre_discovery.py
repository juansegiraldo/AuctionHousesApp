"""Paginacion del catalogo: se sigue query_info.next_page, reescrito al proxy."""
import json
from pathlib import Path

from scraping.houses.lefebre_subastas.house import HOUSE
from scraping.houses.lefebre_subastas.parsers import next_page_url

FIXTURES = Path(__file__).parent / "fixtures"


def test_next_page_se_reescribe_al_proxy_del_sitio():
    """El next_page apunta al backend de Auction Mobility, que devuelve 401 con
    cualquier cabecera. Hay que reescribirlo al /ajax/lots del propio sitio."""
    crudo = "https://production4-server.auctionmobility.com/v1/auction/4-DLG0WK/lots?n=4&o=4"
    assert next_page_url(crudo, "4-DLG0WK") == (
        "https://auction.lefebresubastas.com/ajax/lots/4-DLG0WK?n=4&o=4"
    )


def test_sin_next_page_se_para():
    assert next_page_url(None, "4-DLG0WK") is None


def test_discover_concatena_las_paginas_y_deduplica():
    """La fixture de la pagina 2 repite un lote de la 1 a proposito."""
    paginas = [
        (FIXTURES / "ajax_lots_page1.json").read_text(encoding="utf-8"),
        (FIXTURES / "ajax_lots_page2.json").read_text(encoding="utf-8"),
    ]
    pedidas = []

    def fake_fetch(url):
        # Firma IDENTICA a la del engine: fetch(url) y nada mas. Un fake que
        # aceptase timeout_seconds dejaria pasar un TypeError que solo se ve en
        # subastas de mas de una pagina.
        # La pagina 1 llega como first_page sin pasar por fetch, asi que la
        # primera peticion que se ve aqui ya es la 2.
        pedidas.append(url)
        return paginas[len(pedidas)]

    meta = type("Meta", (), {"auction_id": "subasta-30",
                             "auction_url": "https://auction.lefebresubastas.com/auctions/4-DLG0WK/subasta-30"})()
    previews = HOUSE.discover(
        paginas[0], meta,
        fetch=fake_fetch, post=None, get_session=None,
        delay=0, max_lots=None, max_retries=0, timeout_seconds=5, log=lambda *a, **k: None,
    )

    urls = [p["lot_url"] for p in previews]
    assert len(urls) == len(set(urls)), "hay lot_url repetidos: falta el dedupe"
    # 4 lotes de la pagina 1 + 2 nuevos de la 2 (el tercero es repetido)
    assert len(previews) == 6
    # la segunda peticion ya va contra el proxy, no contra el backend con 401
    assert pedidas[-1].startswith("https://auction.lefebresubastas.com/ajax/lots/")


def test_el_fetcher_traduce_la_url_de_subasta_al_catalogo(monkeypatch):
    """El engine arranca con fetch(auction_url), y esa URL es la SPA de Angular.

    Si no se reescribe al catalogo JSON, parse_auction_page recibe HTML y
    revienta. Este test fija la traduccion.
    """
    from scraping.houses.lefebre_subastas import house as house_mod

    pedidas = []

    class FakeResponse:
        headers = {"Content-Type": "application/json"}

        def raise_for_status(self):
            return None

        def json(self):
            return {"result_page": [], "query_info": {}}

    def fake_get(url, **kwargs):
        pedidas.append(url)
        return FakeResponse()

    monkeypatch.setattr(house_mod.requests, "get", fake_get)

    house_mod.lefebre_fetcher(
        "https://auction.lefebresubastas.com/auctions/4-DLG0WK/subasta-30", 30.0
    )
    assert pedidas == ["https://auction.lefebresubastas.com/ajax/lots/4-DLG0WK?limit=100"]

    # una URL que ya es del proxy se deja como esta
    pedidas.clear()
    ya_ajax = "https://auction.lefebresubastas.com/ajax/lots/4-DLG0WK?n=100&o=100"
    house_mod.lefebre_fetcher(ya_ajax, 30.0)
    assert pedidas == [ya_ajax]


def test_el_historico_no_se_reescribe(monkeypatch):
    """/auctions/past no lleva codigo de subasta: debe pedirse tal cual."""
    from scraping.houses.lefebre_subastas import house as house_mod

    pedidas = []

    class FakeResponse:
        headers = {"Content-Type": "text/html"}
        text = "<html></html>"

        def raise_for_status(self):
            return None

    monkeypatch.setattr(house_mod.requests, "get",
                        lambda url, **kw: (pedidas.append(url), FakeResponse())[1])
    house_mod.lefebre_fetcher("https://auction.lefebresubastas.com/auctions/past", 30.0)
    assert pedidas == ["https://auction.lefebresubastas.com/auctions/past"]


def test_respeta_max_lots():
    paginas = [(FIXTURES / "ajax_lots_page1.json").read_text(encoding="utf-8")]

    def fake_fetch(url):
        return paginas[0]

    meta = type("Meta", (), {"auction_id": "subasta-30",
                             "auction_url": "https://auction.lefebresubastas.com/auctions/4-DLG0WK/subasta-30"})()
    previews = HOUSE.discover(
        paginas[0], meta,
        fetch=fake_fetch, post=None, get_session=None,
        delay=0, max_lots=2, max_retries=0, timeout_seconds=5, log=lambda *a, **k: None,
    )
    assert len(previews) == 2

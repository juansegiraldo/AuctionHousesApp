"""Parseo del catalogo JSON de Lefebre (proxy AJAX de Auction Mobility).

Las fixtures son recortes reales de /ajax/lots/<code>, no HTML: esta casa no
expone el dato en el DOM (Angular lo rellena en cliente), asi que el parser lee
JSON. Los tests pasan dict o str, nunca una pagina viva.
"""
import json
from pathlib import Path

from scraping.houses.lefebre_subastas.parsers import parse_auction_page

FIXTURES = Path(__file__).parent / "fixtures"


def _page1() -> str:
    return (FIXTURES / "ajax_lots_page1.json").read_text(encoding="utf-8")


def test_parse_auction_page_extrae_los_lotes():
    previews = parse_auction_page(_page1())
    assert len(previews) == 4
    assert all(p["lot_url"] for p in previews)


def test_acepta_dict_ya_parseado_y_str():
    """El fetcher devuelve dict; los tests pasan str. Los dos tienen que valer."""
    desde_str = parse_auction_page(_page1())
    desde_dict = parse_auction_page(json.loads(_page1()))
    assert [p["lot_url"] for p in desde_str] == [p["lot_url"] for p in desde_dict]


def test_precio_y_estado():
    by_num = {p["lot_number"]: p for p in parse_auction_page(_page1())}

    # 'sold' -> VENDIDO, con precio entero (el JSON trae '1500000.00')
    vendido = by_num[2]
    assert vendido["status"] == "VENDIDO"
    assert vendido["price_sold"] == 1_500_000

    # 'expired' -> NO VENDIDO y sin precio
    assert by_num[3]["status"] == "NO VENDIDO"
    assert by_num[3]["price_sold"] is None


def test_active_es_no_vendido():
    """'active' en una subasta cerrada es un lote que no se remato, no uno en curso.

    Mapearlo a EN CURSO inflaria la tasa de venta de la casa.
    """
    by_num = {p["lot_number"]: p for p in parse_auction_page(_page1())}
    assert by_num[1]["status"] == "NO VENDIDO"
    assert by_num[1]["price_sold"] is None


def test_starting_price_es_la_estimacion():
    """La casa no publica estimate_low/high (vienen siempre null): el precio de
    salida es lo unico que hay, igual que en el Excel."""
    by_num = {p["lot_number"]: p for p in parse_auction_page(_page1())}
    assert by_num[2]["price_estimate_min"] == 1_500_000


def test_imagen_y_numero_de_lote():
    """Dos campos que el Excel no tenia y el API si: por eso se re-scrapean 27-30."""
    previews = parse_auction_page(_page1())
    assert all(p["lot_number"] is not None for p in previews)
    assert all((p["image_url"] or "").startswith("https://") for p in previews)


def test_titulo_tecnica_y_medidas_se_separan():
    """Reutiliza split_title() de from_excel.py: el bloque es el mismo formato."""
    by_num = {p["lot_number"]: p for p in parse_auction_page(_page1())}
    lote = by_num[2]
    assert lote["lot_title"] == "S/T, sf."
    assert lote["medium"] == "Tinta sobre papel"
    # el bloque crudo se conserva entero
    assert "IGNACIO GOMEZ JARAMILLO" in lote["description"]

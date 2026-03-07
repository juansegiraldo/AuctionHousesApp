from pathlib import Path

from scraping.houses.duran_subastas.parsers import extract_infinite_scroll_config, parse_auction_page


def test_parse_auction_page_extracts_lot_links():
    html = Path(__file__).parent / "fixtures" / "auction_page.html"
    previews = parse_auction_page(html.read_text(encoding="utf-8"))
    urls = {item["lot_url"] for item in previews}
    assert "https://www.duran-subastas.com/es/articulo/lote-100-pintura" in urls
    assert "https://www.duran-subastas.com/es/articulo/lote-101-obra-grafica" in urls
    assert len(previews) == 3


def test_parse_auction_page_extracts_subasta_lote_cards():
    html = """
    <html><body>
    <div class="square">
      <a title="Joan Miro" href="https://www.duran-subastas.com/es/subasta-lote/joan-miro/653-1"></a>
      <span class="ref">Lote : 1</span>
      <img src="https://www.duran-subastas.com/img/thumbs/260/001/183/001-183-1.jpg" />
    </div></div>
    <div class="square">
      <a title="Max Mahlmann" href="https://www.duran-subastas.com/es/subasta-lote/max-mahlmann/653-281"></a>
      <span class="ref">Lote : 281</span>
      <img src="https://www.duran-subastas.com/img/thumbs/260/001/183/001-183-281.jpg" />
    </div></div>
    </body></html>
    """
    previews = parse_auction_page(html)
    urls = {item["lot_url"] for item in previews}
    assert "https://www.duran-subastas.com/es/subasta-lote/joan-miro/653-1" in urls
    assert "https://www.duran-subastas.com/es/subasta-lote/max-mahlmann/653-281" in urls
    by_url = {item["lot_url"]: item for item in previews}
    assert by_url["https://www.duran-subastas.com/es/subasta-lote/joan-miro/653-1"]["lot_number"] == 1
    assert by_url["https://www.duran-subastas.com/es/subasta-lote/max-mahlmann/653-281"]["lot_number"] == 281


def test_extract_infinite_scroll_config():
    html = """
    <html><body>
      <script>var url_lots ="https://www.duran-subastas.com/es/GetAjaxLots";</script>
      <form id="infiniteScrollForm">
        <input type="hidden" name="_token" value="abc123"/>
        <input type="hidden" name="category" value="614"/>
        <input type="hidden" name="page" value="1"/>
      </form>
    </body></html>
    """
    ajax_url, payload = extract_infinite_scroll_config(html)
    assert ajax_url == "https://www.duran-subastas.com/es/GetAjaxLots"
    assert payload["_token"] == "abc123"
    assert payload["category"] == "614"
    assert payload["page"] == "1"


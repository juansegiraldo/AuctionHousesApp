from pathlib import Path

from scraping.houses.duran_subastas.parsers import parse_historic_page


def test_parse_historic_page_extracts_auctions():
    html = Path(__file__).parent / "fixtures" / "historic.html"
    auctions = parse_historic_page(html.read_text(encoding="utf-8"))
    assert len(auctions) == 2
    assert auctions[0].auction_url.startswith("https://www.duran-subastas.com/es/subasta/")
    ids = {a.auction_id for a in auctions}
    assert "subasta-652-enero-2026_652-001" in ids


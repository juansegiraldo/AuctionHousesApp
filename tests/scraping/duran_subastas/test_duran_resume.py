from scraping.common.models import AuctionMeta
from scraping.houses.duran_subastas import run_historic


def test_resume_skips_existing_auction_file(tmp_path, monkeypatch):
    output_dir = tmp_path / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    existing_file = output_dir / "subasta-652-enero-2026_652-001.jsonl"
    existing_file.write_text('{"existing":true}\n', encoding="utf-8")

    auction = AuctionMeta(
        auction_id="subasta-652-enero-2026_652-001",
        auction_title="Subasta 652 Enero 2026",
        auction_url="https://www.duran-subastas.com/es/subasta/subasta-652-enero-2026_652-001",
        auction_house_name="Duran Arte y Subastas",
    )
    called = {"scrape": 0}

    def fake_fetch_historic(*args, **kwargs):
        return [auction]

    def fake_scrape_auction(*args, **kwargs):
        called["scrape"] += 1
        return []

    monkeypatch.setattr(run_historic, "DEFAULT_OUTPUT_DIR", output_dir)
    monkeypatch.setattr(run_historic, "fetch_historic", fake_fetch_historic)
    monkeypatch.setattr(run_historic, "scrape_auction", fake_scrape_auction)
    monkeypatch.setattr("sys.argv", ["run_historic.py", "--max-auctions", "1"])
    run_historic.main()

    assert called["scrape"] == 0


from pathlib import Path

from scraping.common.models import AuctionMeta
from scraping.houses.duran_subastas import run_historic


def test_historic_smoke_creates_output(tmp_path, monkeypatch):
    output_dir = tmp_path / "output"
    merged_file = tmp_path / "merged.jsonl"

    auction = AuctionMeta(
        auction_id="subasta-652-enero-2026_652-001",
        auction_title="Subasta 652 Enero 2026",
        auction_url="https://www.duran-subastas.com/es/subasta/subasta-652-enero-2026_652-001",
        auction_house_name="Duran Arte y Subastas",
    )

    def fake_fetch_historic(*args, **kwargs):
        return [auction]

    def fake_scrape_auction(*args, **kwargs):
        out = args[1]
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text('{"auction_id":"subasta-652-enero-2026_652-001","lot_url":"x"}\n', encoding="utf-8")
        return []

    monkeypatch.setattr(run_historic, "DEFAULT_OUTPUT_DIR", output_dir)
    monkeypatch.setattr(run_historic, "fetch_historic", fake_fetch_historic)
    monkeypatch.setattr(run_historic, "scrape_auction", fake_scrape_auction)
    monkeypatch.setattr(
        "sys.argv",
        [
            "run_historic.py",
            "--max-auctions",
            "1",
            "--output",
            str(merged_file),
        ],
    )
    run_historic.main()

    assert (output_dir / "subasta-652-enero-2026_652-001.jsonl").exists()
    assert merged_file.exists()


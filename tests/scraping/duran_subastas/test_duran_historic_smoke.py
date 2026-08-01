import json
import time

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


def test_historic_parallel_workers_merge_outputs(tmp_path, monkeypatch):
    output_dir = tmp_path / "output"
    merged_file = tmp_path / "merged.jsonl"
    auctions = [
        AuctionMeta(
            auction_id="subasta-652-enero-2026_652-001",
            auction_title="Subasta 652 Enero 2026",
            auction_url="https://www.duran-subastas.com/es/subasta/subasta-652-enero-2026_652-001",
            auction_house_name="Duran Arte y Subastas",
        ),
        AuctionMeta(
            auction_id="subasta-653-febrero-2026_653-001",
            auction_title="Subasta 653 Febrero 2026",
            auction_url="https://www.duran-subastas.com/es/subasta/subasta-653-febrero-2026_653-001",
            auction_house_name="Duran Arte y Subastas",
        ),
    ]

    def fake_fetch_historic(*args, **kwargs):
        return auctions

    def fake_scrape_auction(*args, **kwargs):
        out = args[1]
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(f'{{"auction_id":"{out.stem}","lot_url":"x"}}\n', encoding="utf-8")
        return [{"lot_url": "x"}]

    monkeypatch.setattr(run_historic, "DEFAULT_OUTPUT_DIR", output_dir)
    monkeypatch.setattr(run_historic, "fetch_historic", fake_fetch_historic)
    monkeypatch.setattr(run_historic, "scrape_auction", fake_scrape_auction)
    monkeypatch.setattr(
        "sys.argv",
        [
            "run_historic.py",
            "--workers",
            "2",
            "--output",
            str(merged_file),
        ],
    )
    run_historic.main()

    merged_lines = [line for line in merged_file.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(merged_lines) == 2
    assert (output_dir / "subasta-652-enero-2026_652-001.jsonl").exists()
    assert (output_dir / "subasta-653-febrero-2026_653-001.jsonl").exists()


def test_historic_parallel_auction_timeout_marks_checkpoint(tmp_path, monkeypatch):
    output_dir = tmp_path / "output"
    auction = AuctionMeta(
        auction_id="subasta-652-enero-2026_652-001",
        auction_title="Subasta 652 Enero 2026",
        auction_url="https://www.duran-subastas.com/es/subasta/subasta-652-enero-2026_652-001",
        auction_house_name="Duran Arte y Subastas",
    )

    def fake_fetch_historic(*args, **kwargs):
        return [auction]

    def slow_scrape(*args, **kwargs):
        time.sleep(0.05)
        return []

    monkeypatch.setattr(run_historic, "DEFAULT_OUTPUT_DIR", output_dir)
    monkeypatch.setattr(run_historic, "fetch_historic", fake_fetch_historic)
    monkeypatch.setattr(run_historic, "scrape_auction", slow_scrape)
    monkeypatch.setattr(
        "sys.argv",
        [
            "run_historic.py",
            "--workers",
            "2",
            "--auction-timeout",
            "0.001",
        ],
    )
    run_historic.main()

    checkpoint_path = output_dir / "checkpoints" / "subasta-652-enero-2026_652-001.json"
    payload = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    assert payload["status"] == "failed"
    assert payload["error"] == "auction_timeout"

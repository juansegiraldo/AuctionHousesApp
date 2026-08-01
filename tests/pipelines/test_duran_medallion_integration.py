import json
from pathlib import Path

from pipelines.bronze import ingest
from pipelines.silver import build_silver


def test_bronze_ingest_detects_duran(tmp_path, monkeypatch):
    root = tmp_path
    scraping_houses = root / "scraping" / "houses"
    output_dir = root / "scraping" / "houses" / "duran_subastas" / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "sample.jsonl").write_text('{"lot_url":"u","auction_id":"a"}\n', encoding="utf-8")
    registry = {
        "houses": [
            {
                "slug": "duran_subastas",
                "name": "Duran Arte y Subastas",
                "module": "scraping.houses.duran_subastas",
                "output_dir": "scraping/houses/duran_subastas/output",
            }
        ]
    }
    scraping_houses.mkdir(parents=True, exist_ok=True)
    (scraping_houses / "registry.json").write_text(json.dumps(registry), encoding="utf-8")

    monkeypatch.setattr(ingest, "ROOT", root)
    monkeypatch.setattr(ingest, "SCRAPING_HOUSES", scraping_houses)
    monkeypatch.setattr(ingest, "BRONZE_ROOT", root / "data" / "bronze")
    ingest.main()

    assert any((root / "data" / "bronze" / "duran_subastas").glob("**/sample.jsonl"))


def test_silver_build_dedupes_rows(tmp_path, monkeypatch):
    root = tmp_path
    bronze = root / "data" / "bronze" / "duran_subastas" / "ingestion_date=2026-03-07"
    bronze.mkdir(parents=True, exist_ok=True)
    bronze_file = bronze / "sample.jsonl"
    bronze_file.write_text(
        "\n".join(
            [
                '{"lot_url":"u1","auction_id":"a1","auction_title":"x","auction_url":"z"}',
                '{"lot_url":"u1","auction_id":"a1","auction_title":"x","auction_url":"z"}',
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(build_silver, "ROOT", root)
    monkeypatch.setattr(build_silver, "BRONZE_ROOT", root / "data" / "bronze")
    monkeypatch.setattr(build_silver, "SILVER_ROOT", root / "data" / "silver")
    build_silver.main()

    lots_file = root / "data" / "silver" / "lots.jsonl"
    lines = lots_file.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1


def test_silver_build_ignores_auction_index_and_non_lot_rows(tmp_path, monkeypatch):
    root = tmp_path
    bronze = root / "data" / "bronze" / "duran_subastas" / "ingestion_date=2026-03-07"
    bronze.mkdir(parents=True, exist_ok=True)
    (bronze / "sample.jsonl").write_text(
        "\n".join(
            [
                '{"lot_url":"u1","auction_id":"a1","auction_title":"x","auction_url":"z"}',
                '{"auction_id":"not-a-lot","auction_title":"index-like row","auction_url":"z"}',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (bronze / "auction_index.jsonl").write_text(
        '{"auction_id":"a2","auction_title":"index","auction_url":"z2"}\n',
        encoding="utf-8",
    )

    monkeypatch.setattr(build_silver, "ROOT", root)
    monkeypatch.setattr(build_silver, "BRONZE_ROOT", root / "data" / "bronze")
    monkeypatch.setattr(build_silver, "SILVER_ROOT", root / "data" / "silver")
    build_silver.main()

    lots_file = root / "data" / "silver" / "lots.jsonl"
    rows = [json.loads(line) for line in lots_file.read_text(encoding="utf-8").splitlines()]

    assert len(rows) == 1
    assert rows[0]["lot_url"] == "u1"
    assert rows[0]["dedupe_key"] == "duran_subastas|u1"
    assert all(row.get("dedupe_key") != "duran_subastas|" for row in rows)

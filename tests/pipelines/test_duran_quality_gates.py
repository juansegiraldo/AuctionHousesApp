import json

import pytest

from pipelines.silver import quality_gates


def test_quality_gates_fail_on_out_of_scope(tmp_path, monkeypatch):
    lots = tmp_path / "data" / "silver" / "lots.jsonl"
    tags = tmp_path / "data" / "enrichments" / "category_tags.jsonl"
    lots.parent.mkdir(parents=True, exist_ok=True)
    tags.parent.mkdir(parents=True, exist_ok=True)

    row = {
        "house_slug": "duran_subastas",
        "dedupe_key": "duran_subastas|u1",
        "lot_url": "u1",
        "lot_title": "Lote 1",
        "price_sold": 1000,
    }
    lots.write_text(json.dumps(row) + "\n", encoding="utf-8")
    tags.write_text(json.dumps({"dedupe_key": "duran_subastas|u1", "category": "joyas"}) + "\n", encoding="utf-8")

    monkeypatch.setattr(quality_gates, "SILVER_LOTS", lots)
    monkeypatch.setattr(quality_gates, "CATEGORY_TAGS", tags)
    monkeypatch.setattr("sys.argv", ["quality_gates.py", "--house-slug", "duran_subastas"])
    with pytest.raises(SystemExit):
        quality_gates.main()


"""Avisos por casa que build_gold escribe en quality_flags.jsonl.

Se corre main() sobre una Silver minima en tmp_path: los avisos de casa salen
de per_house, asi que basta con que la casa aparezca.
"""

import json

import orjson
import pytest

from pipelines.gold import build_gold


def _lot(house: str, n: int, **extra) -> dict:
    return {
        "house_slug": house, "auction_id": "a1", "auction_title": "Subasta",
        "auction_start_date": "2024-11-27T17:00:00-06:00", "lot_number": n,
        "status": "VENDIDO", "price_sold": 1000, "currency": "MXN",
        "dedupe_key": f"{house}|u{n}", "lot_url": f"u{n}", **extra,
    }


@pytest.fixture
def gold_flags(tmp_path, monkeypatch):
    silver = tmp_path / "silver"
    silver.mkdir()
    monkeypatch.setattr(build_gold, "SILVER_ROOT", silver)
    monkeypatch.setattr(build_gold, "GOLD_ROOT", tmp_path / "gold")

    def run(rows):
        (silver / "lots.jsonl").write_bytes(
            b"".join(orjson.dumps(r, option=orjson.OPT_APPEND_NEWLINE) for r in rows)
        )
        build_gold.main()
        path = tmp_path / "gold" / "quality_flags.jsonl"
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]

    return run


def test_morton_is_flagged_as_an_art_only_subset(gold_flags):
    # Morton vende tambien flotillas, coches, vinos, joyas y antiguedades; aqui
    # solo estan sus subastas de arte. Sin el aviso, su volumen se leeria como
    # el total de la casa.
    flags = gold_flags([_lot("morton_subastas", 1), _lot("morton_subastas", 2)])
    morton = [f for f in flags if f.get("code") == "source_is_art_subset"]
    assert len(morton) == 1
    assert morton[0]["house_slug"] == "morton_subastas"
    assert morton[0]["count"] == 2


def test_art_subset_flag_absent_without_morton(gold_flags):
    flags = gold_flags([_lot("duran_subastas", 1, currency="EUR")])
    assert not [f for f in flags if f.get("code") == "source_is_art_subset"]

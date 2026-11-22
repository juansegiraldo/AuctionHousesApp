"""Fallos que antes pasaban en silencio: Silver a medias y entradas que faltan."""
import json

import pytest

from pipelines.analytics import build_artifact
from pipelines.gold import build_insights
from pipelines.silver import build_silver


def _bronze(tmp_path, monkeypatch, files: dict[str, bytes]):
    monkeypatch.setattr(build_silver, "ROOT", tmp_path)
    monkeypatch.setattr(build_silver, "BRONZE_ROOT", tmp_path / "data" / "bronze")
    monkeypatch.setattr(build_silver, "SILVER_ROOT", tmp_path / "data" / "silver")
    part = tmp_path / "data" / "bronze" / "casa" / "ingestion_date=2026-11-09"
    part.mkdir(parents=True)
    for name, data in files.items():
        (part / name).write_bytes(data)
    return tmp_path / "data" / "silver" / "lots.jsonl"


def _lot(i: int) -> bytes:
    return json.dumps({"lot_url": f"u{i}", "auction_id": "a"}).encode() + b"\n"


def test_silver_salta_la_cola_truncada_de_un_scraper_matado(tmp_path, monkeypatch):
    good = b"".join(_lot(i) for i in range(2000))
    lots = _bronze(tmp_path, monkeypatch, {"a.jsonl": good + b'{"lot_url": "u2000", "auc'})
    build_silver.main()
    rows = [json.loads(line) for line in lots.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 2000
    # Fecha de la particion, no el reloj: dos corridas dan el mismo Silver.
    assert {r["ingested_at"] for r in rows} == {"2026-11-09T00:00:00+00:00"}


def test_silver_aborta_con_corrupcion_masiva_y_no_pisa_el_anterior(tmp_path, monkeypatch):
    lots = _bronze(tmp_path, monkeypatch, {"a.jsonl": _lot(1) + b"basura\n" * 5})
    lots.parent.mkdir(parents=True)
    lots.write_text("silver bueno de ayer\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="ABORTADO"):
        build_silver.main()
    assert lots.read_text(encoding="utf-8") == "silver bueno de ayer\n"


def test_insights_exige_category_tags(tmp_path, monkeypatch):
    # Sin el fichero, todos los lotes salian como categoria "other".
    monkeypatch.setattr(build_insights, "ENRICH_ROOT", tmp_path)
    with pytest.raises(SystemExit, match="category_tags.jsonl"):
        build_insights.load_categories()


def test_la_app_exige_lot_details(tmp_path, monkeypatch):
    # Sin el fichero se publicaba una app con 0 lotes.
    (tmp_path / "analytics_report.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(build_artifact, "GOLD_ROOT", tmp_path)
    monkeypatch.setattr("sys.argv", ["build_artifact", "--out", str(tmp_path / "app")])
    with pytest.raises(SystemExit, match="lot_details.jsonl"):
        build_artifact.main()

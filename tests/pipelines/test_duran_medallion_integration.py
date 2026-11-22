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


def _silver_from(tmp_path, monkeypatch, files: dict[str, list[dict]]) -> dict[str, dict]:
    """files: {"<casa>/<particion>/<fichero>": [filas]} -> Silver indexado por lot_url."""
    for rel, rows in files.items():
        path = tmp_path / "data" / "bronze" / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    monkeypatch.setattr(build_silver, "ROOT", tmp_path)
    monkeypatch.setattr(build_silver, "BRONZE_ROOT", tmp_path / "data" / "bronze")
    monkeypatch.setattr(build_silver, "SILVER_ROOT", tmp_path / "data" / "silver")
    build_silver.main()
    lots = tmp_path / "data" / "silver" / "lots.jsonl"
    return {r["lot_url"]: r for r in map(json.loads, lots.read_text(encoding="utf-8").splitlines())}


def test_silver_keeps_newest_partition(tmp_path, monkeypatch):
    """Un arreglo del scraper tiene que llegar a Silver.

    Regresion: ganaba la particion MAS ANTIGUA, asi que un re-scrape nunca pisaba un
    lote ya cargado (9.099 lotes de Bogota seguian saliendo de la copia de marzo). Un
    lote que solo existe en la particion vieja se conserva igual.
    """
    lot = {"lot_url": "u1", "auction_id": "a1"}
    silver = _silver_from(tmp_path, monkeypatch, {
        "bogota_auctions/ingestion_date=2026-03-07/2245.jsonl": [
            {**lot, "artist_name": "Fernando"},
            {"lot_url": "solo-vieja", "auction_id": "a1"},
        ],
        "bogota_auctions/ingestion_date=2026-10-25/2245.jsonl": [{**lot, "artist_name": "Fernando Botero"}],
    })
    assert silver["u1"]["artist_name"] == "Fernando Botero"
    assert "solo-vieja" in silver


def test_silver_prefers_auction_file_over_historic_all(tmp_path, monkeypatch):
    """Dentro de una particion, historic_all_lots.jsonl va el ULTIMO.

    Es una concatenacion de los ficheros por subasta hecha al final de la corrida, y
    no se regenera si luego se re-scrapea una subasta suelta. En Zorrilla 13 subastas
    se re-scrapearon despues, ya con descripcion: 1.018 lotes traen artista en su
    fichero y no en historic_all. Por orden alfabetico ganaba o perdia segun el nombre
    ("146347" < "historic" < "libros-..."), que es la trampa ya conocida de Duran.
    Los lotes que solo estan en historic_all se conservan.
    """
    part = "zorrilla_subastas/ingestion_date=2026-10-25"
    silver = _silver_from(tmp_path, monkeypatch, {
        f"{part}/historic_all_lots.jsonl": [
            {"lot_url": "mac-entyre", "auction_id": "146347", "artist_name": None},
            {"lot_url": "libro", "auction_id": "libros-2020", "lot_title": "viejo"},
            {"lot_url": "solo-historic", "auction_id": "146347"},
        ],
        f"{part}/146347.jsonl": [{"lot_url": "mac-entyre", "auction_id": "146347", "artist_name": "Eduardo Mac Entyre"}],
        f"{part}/libros-2020.jsonl": [{"lot_url": "libro", "auction_id": "libros-2020", "lot_title": "re-scrapeado"}],
    })
    assert silver["mac-entyre"]["artist_name"] == "Eduardo Mac Entyre"
    assert silver["libro"]["lot_title"] == "re-scrapeado"
    assert "solo-historic" in silver


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

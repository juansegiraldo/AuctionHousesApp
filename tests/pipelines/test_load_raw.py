from pipelines.bronze import load_raw


def test_content_hash_ignora_scraped_at_pero_no_los_datos():
    base = {"lot_url": "u", "price_sold": 100, "scraped_at": "2026-01-01T00:00:00Z"}
    rescrape = {**base, "scraped_at": "2026-11-09T00:00:00Z"}
    changed = {**base, "price_sold": 200}
    assert load_raw.content_hash(base) == load_raw.content_hash(rescrape)
    assert load_raw.content_hash(base) != load_raw.content_hash(changed)


def test_read_file_cuenta_la_linea_rota_y_sigue(tmp_path, monkeypatch):
    monkeypatch.setattr(load_raw, "ROOT", tmp_path)
    f = tmp_path / "subasta.jsonl"
    # La ultima linea cortada es lo que deja un scraper matado a medias.
    f.write_bytes(b'{"lot_url": "a", "lot_title": "x"}\n\n{"lot_title": "sin url"}\n{"lot_url": "b", "lot_t')
    rows, rejects = load_raw.read_file(f, "casa")
    assert [r["lot_url"] for r in rows] == ["a"]
    assert rows[0]["source_file"] == "subasta.jsonl"
    assert dict(rejects) == {"sin_lot_url": 1, "linea_rota": 1}

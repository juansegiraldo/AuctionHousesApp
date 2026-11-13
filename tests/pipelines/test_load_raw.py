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


def test_call_reintenta_un_corte_de_red_y_acaba_bien(monkeypatch):
    # Un "bad record mac" de TLS a mitad de carga tumbo una corrida entera.
    import io, ssl
    attempts = []

    def flaky(req, timeout):
        attempts.append(1)
        if len(attempts) < 3:
            raise ssl.SSLError("bad record mac")
        return io.BytesIO(b'{"inserted": 5}')

    monkeypatch.setattr(load_raw, "_urlopen", flaky)
    monkeypatch.setattr(load_raw, "_env", lambda name: "http://local.invalid")
    monkeypatch.setattr(load_raw.time, "sleep", lambda s: None)
    assert load_raw.call("auction", {"op": "raw", "rows": []}) == {"inserted": 5}
    assert len(attempts) == 3


def test_degradado_tolera_un_arreglo_de_parser_pero_no_un_scrape_roto():
    # Lefebre tiene 3.858 lotes: el 1 % son 38.
    assert not load_raw.degraded_exceeds(38, 3858)
    assert load_raw.degraded_exceeds(39, 3858)
    assert not load_raw.degraded_exceeds(0, 0)


def test_sin_red_y_con_best_effort_la_corrida_sigue(monkeypatch, capsys):
    # El pipeline tiene que poder correr sin conexion: avisa y sale sin error.
    def sin_red(req, timeout):
        raise OSError("getaddrinfo failed")

    monkeypatch.setattr(load_raw, "_urlopen", sin_red)
    monkeypatch.setattr(load_raw, "_env", lambda name: "http://local.invalid")
    monkeypatch.setattr(load_raw.time, "sleep", lambda s: None)
    monkeypatch.setattr("sys.argv", ["load_raw", "--best-effort"])
    load_raw.main()
    assert "queda pendiente" in capsys.readouterr().out


def test_sin_red_y_sin_best_effort_la_carga_falla(monkeypatch):
    import pytest

    def sin_red(req, timeout):
        raise OSError("getaddrinfo failed")

    monkeypatch.setattr(load_raw, "_urlopen", sin_red)
    monkeypatch.setattr(load_raw, "_env", lambda name: "http://local.invalid")
    monkeypatch.setattr(load_raw.time, "sleep", lambda s: None)
    monkeypatch.setattr("sys.argv", ["load_raw"])
    with pytest.raises(OSError):
        load_raw.main()

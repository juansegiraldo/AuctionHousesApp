"""Tests de pipelines/shared/attribution_jev.py, sin red: solo la cache.

Lo que se protege: Jev solo quita nombres del ranking (nunca anade ni da pais),
solo por encima del umbral, solo fuera del maestro, y sin red el pipeline sigue.
"""

import json

import orjson

from pipelines.shared import attribution_jev
from pipelines.silver import artist_resolve
from tests.pipelines.test_artist_resolve import _lot, _read, _seed_master, _write, silver  # noqa: F401


def _seed_cache(entries):
    attribution_jev.CACHE.write_bytes(b"".join(
        orjson.dumps({"model": "jev-test", "date": "2026-10-12", **e},
                     option=orjson.OPT_APPEND_NEWLINE)
        for e in entries
    ))


def test_cache_drives_silver_offline(silver):
    lots, master = silver
    _seed_master(master, [{"artist_id": "fernando_botero", "display_name": "Fernando Botero",
                           "aliases": ["Fernando Botero"], "country_birth": "CO"}])
    _seed_cache([
        {"fold": "collar de perlas", "label": "no_autor", "confidence": 0.99},
        {"fold": "dama con perro", "label": "no_autor", "confidence": 0.89},
        {"fold": "ana collar", "label": "autor", "confidence": 1.0},
        # El maestro gana siempre: aunque Jev dijese lo contrario, no se consulta.
        {"fold": "fernando botero", "label": "no_autor", "confidence": 1.0},
    ])
    _write(lots, [
        _lot(lot_url="1", dedupe_key="d|1", artist_name="Collar de perlas"),
        _lot(lot_url="2", dedupe_key="d|2", artist_name="Dama con perro"),
        _lot(lot_url="3", dedupe_key="d|3", artist_name="Ana Collar"),
        _lot(lot_url="4", dedupe_key="d|4", artist_name="Fernando Botero"),
        _lot(lot_url="5", dedupe_key="d|5", artist_name="Pintor Sin Cache"),
    ])

    artist_resolve.main()  # sin clave (conftest): solo reglas + cache
    rows = {r["lot_url"]: r for r in _read(lots)}

    assert rows["1"]["attribution_type"] == "no_autor"
    assert rows["1"]["artist_resolution"] == "not_an_author"
    assert rows["1"]["artist_id"] is None and rows["1"]["artist_country_birth"] is None
    # Por debajo del umbral se queda autor, y Gold lo marca como low_conf.
    assert rows["2"]["attribution_type"] == "autor"
    cache = attribution_jev.load_cache()
    assert attribution_jev.is_low_conf(rows["2"], cache)
    assert rows["3"]["attribution_type"] == "autor"
    assert rows["4"]["artist_resolution"] == "master"
    assert rows["4"]["artist_country_birth"] == "CO"
    assert rows["5"]["artist_resolution"] == "fold_only"  # sin cache: reglas


def test_network_error_keeps_cache_and_does_not_raise():
    from typesafe_sdk import TypeSafeAPIConnectionError

    class DownClient:
        def system_one(self, **kw):
            raise TypeSafeAPIConnectionError("sin red")

    cache = {"ya": {"fold": "ya", "label": "autor", "confidence": 1.0}}
    added = attribution_jev.fetch_missing({"nuevo": {"artist_name": "Nuevo"}}, cache,
                                          client=DownClient())
    assert added == 0
    assert set(cache) == {"ya"}


def test_no_key_is_a_noop():
    assert attribution_jev.fetch_missing({"nuevo": {"artist_name": "Nuevo"}}, {}) == 0
    assert not attribution_jev.CACHE.exists()


def test_committed_cache_is_well_formed():
    # La cache real (no la del conftest): cada linea con los campos que usa apply().
    path = attribution_jev.ROOT / "pipelines" / "config" / "attribution_jev.jsonl"
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        e = json.loads(line)
        assert set(e) == {"fold", "label", "confidence", "model", "date"}
        assert e["label"] in attribution_jev.CRITERIA
        assert 0.0 <= e["confidence"] <= 1.0

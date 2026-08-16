"""Tests de scripts/artist_master_propose.py.

Lo que se protege aqui es que el YAML que emite la herramienta se pueda pegar
en un shard sin corromper nada: es la puerta de entrada del maestro y lo que
salga de aqui lo revisa una persona, no una maquina.
"""

import importlib.util
from collections import Counter
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]

_spec = importlib.util.spec_from_file_location(
    "artist_master_propose", ROOT / "scripts" / "artist_master_propose.py"
)
propose = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(propose)


def _candidate(country, **kw):
    base = {
        "fold": "edvard munch",
        "artist_id": "edvard_munch",
        "display_name": "Edvard Munch",
        "lots": 12,
        "houses": ["duran_subastas"],
        "aliases": ["Edvard Munch"],
        "countries": Counter([country] if country else []),
        "birth": Counter(),
        "death": Counter(),
    }
    base.update(kw)
    return base


def test_emitted_country_codes_survive_a_yaml_roundtrip():
    """"NO" (Noruega) no puede volver como el booleano False.

    YAML 1.1 lee NO, ON, OFF e YES sin comillas como booleanos. Sin comillas,
    un artista noruego se pegaba en el shard con country_birth: False y perdia
    el pais en silencio, sin un solo error en toda la cadena.
    """
    text = propose.to_yaml([_candidate("NO")], show_inversions=False)
    entry = yaml.safe_load(text)["artists"][0]
    assert entry["country_birth"] == "NO"
    assert entry["nationalities"] == ["NO"]


def test_emitted_yaml_is_valid_for_every_country_code():
    """Ningun codigo de _countries.yaml se degrada al pasar por la herramienta."""
    from pipelines.shared.artist_master import load_countries

    codes = sorted(load_countries()["countries"])
    candidates = [
        _candidate(code, artist_id=f"artista_{i}", display_name=f"Artista {i}")
        for i, code in enumerate(codes)
    ]
    entries = yaml.safe_load(propose.to_yaml(candidates, show_inversions=False))["artists"]
    assert [e["country_birth"] for e in entries] == codes
    assert all(isinstance(e["country_birth"], str) for e in entries)


def test_unknown_country_is_left_null_not_guessed():
    """Sin pais en los datos, la herramienta no lo inventa."""
    text = propose.to_yaml([_candidate(None)], show_inversions=False)
    entry = yaml.safe_load(text)["artists"][0]
    assert entry["country_birth"] is None
    assert entry["nationalities"] == []
    assert entry["confidence"] == "low"


def test_conflicting_birth_years_are_flagged_for_review():
    """Dos fechas de nacimiento = puede que sean dos personas distintas.

    Es el caso "Francisco Toledo": el aviso tiene que llegar a quien revisa,
    porque fusionarlos en un solo artist_id seria irreparable.
    """
    cand = _candidate("ES", birth=Counter({1928: 4, 1940: 3}))
    text = propose.to_yaml([cand], show_inversions=False)
    entry = yaml.safe_load(text)["artists"][0]
    assert "CONFLICTO nacimiento" in entry["notes"]
    # Con anios en conflicto no se elige uno: se deja fuera.
    assert "birth_year" not in entry


def test_parse_biography_extracts_country_and_years():
    got = propose.parse_biography("Ever Astudillo (Colombia, 1948 - 2015)")
    assert got["country_birth"] == "CO"
    assert got["birth_year"] == 1948
    assert got["death_year"] == 2015


def test_parse_biography_ignores_unknown_country():
    """Un pais que _countries.yaml no conoce no se cuela como codigo."""
    assert "country_birth" not in propose.parse_biography("Alguien (Frobnia, 1900)")


def test_parse_biography_on_empty_input():
    assert propose.parse_biography(None) == {}
    assert propose.parse_biography("Fernando Botero") == {}

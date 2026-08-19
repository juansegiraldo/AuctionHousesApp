"""Pruebas del aplicador de complementos sobre los shards del maestro.

Es la unica pieza de todo el ciclo que ESCRIBE en pipelines/config/artists, asi
que aqui se fija que solo pueda rellenar huecos:

  - nunca sobrescribe un valor existente
  - solo toca los campos que se le piden
  - deja intactos comentarios, orden y el resto del shard
"""

import importlib.util
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location(
    "artist_master_apply",
    ROOT / "scripts" / "artist_master_apply.py",
)
apply_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(apply_mod)


SHARD = """artists:
  - artist_id: juan_perez
    display_name: "Juan Pérez"
    country_birth: "ES"
    nationalities: ["ES"]
    birth_year: 1954
    attribution_type: autor
    source: manual
    confidence: high
    aliases:
      - "Juan Pérez"
    notes: "3 lotes"

  - artist_id: maria_lopez
    display_name: "María López"
    country_birth: "CO"
    nationalities: ["CO"]
    birth_year: 1930
    death_year: 1999
    attribution_type: autor
    source: manual
    confidence: high
    aliases:
      - "María López"
"""


def _write(tmp_path):
    shard = tmp_path / "j.yaml"
    shard.write_text(SHARD, encoding="utf-8")
    return shard


def test_a_missing_field_is_filled(tmp_path):
    shard = _write(tmp_path)

    changed = apply_mod.apply_completions(
        [{"artist_id": "juan_perez", "fields": {"death_status": "living"}}],
        shard_dir=tmp_path,
    )

    assert changed == 1
    data = yaml.safe_load(shard.read_text(encoding="utf-8"))
    entry = next(a for a in data["artists"] if a["artist_id"] == "juan_perez")
    assert entry["death_status"] == "living"
    # Lo que ya estaba no se toca.
    assert entry["birth_year"] == 1954
    assert entry["country_birth"] == "ES"


def test_an_existing_value_is_never_overwritten(tmp_path):
    shard = _write(tmp_path)

    changed = apply_mod.apply_completions(
        [{"artist_id": "maria_lopez", "fields": {"death_year": 2020}}],
        shard_dir=tmp_path,
    )

    assert changed == 0
    data = yaml.safe_load(shard.read_text(encoding="utf-8"))
    entry = next(a for a in data["artists"] if a["artist_id"] == "maria_lopez")
    assert entry["death_year"] == 1999


def test_an_unknown_artist_is_ignored(tmp_path):
    _write(tmp_path)

    changed = apply_mod.apply_completions(
        [{"artist_id": "no_existe", "fields": {"death_status": "living"}}],
        shard_dir=tmp_path,
    )

    assert changed == 0


def test_other_entries_in_the_shard_survive(tmp_path):
    shard = _write(tmp_path)

    apply_mod.apply_completions(
        [{"artist_id": "juan_perez", "fields": {"death_status": "living"}}],
        shard_dir=tmp_path,
    )

    data = yaml.safe_load(shard.read_text(encoding="utf-8"))
    assert [a["artist_id"] for a in data["artists"]] == ["juan_perez", "maria_lopez"]
    otra = next(a for a in data["artists"] if a["artist_id"] == "maria_lopez")
    assert otra["aliases"] == ["María López"]


def test_country_codes_stay_quoted_so_norway_survives(tmp_path):
    """NO sin comillas parsea como booleano False y Noruega desaparecia."""
    shard = tmp_path / "o.yaml"
    shard.write_text(
        'artists:\n'
        '  - artist_id: ola_nordmann\n'
        '    display_name: "Ola Nordmann"\n'
        '    country_birth: "NO"\n'
        '    nationalities: ["NO"]\n'
        '    birth_year: 1950\n'
        '    attribution_type: autor\n'
        '    source: manual\n'
        '    confidence: high\n'
        '    aliases:\n'
        '      - "Ola Nordmann"\n',
        encoding="utf-8",
    )

    apply_mod.apply_completions(
        [{"artist_id": "ola_nordmann", "fields": {"death_status": "living"}}],
        shard_dir=tmp_path,
    )

    data = yaml.safe_load(shard.read_text(encoding="utf-8"))
    entry = data["artists"][0]
    assert entry["country_birth"] == "NO"
    assert entry["country_birth"] is not False


NEW_ENTRIES = [
    {
        "artist_id": "zoe_zapata",
        "display_name": "Zoe Zapata",
        "country_birth": "ES",
        "nationalities": ["ES"],
        "birth_year": 1950,
        "death_year": None,
        "attribution_type": "autor",
        "source": "wikidata",
        "confidence": "low",
        "aliases": ["Zoe Zapata"],
        "notes": "Fuente: https://www.wikidata.org/wiki/Q1",
    }
]


def test_new_entries_land_in_the_shard_of_their_initial(tmp_path):
    (tmp_path / "z.yaml").write_text("artists: []\n", encoding="utf-8")

    added = apply_mod.merge_new_entries(NEW_ENTRIES, shard_dir=tmp_path)

    assert added == 1
    data = yaml.safe_load((tmp_path / "z.yaml").read_text(encoding="utf-8"))
    assert data["artists"][0]["artist_id"] == "zoe_zapata"


def test_a_new_entry_never_replaces_an_existing_one(tmp_path):
    (tmp_path / "z.yaml").write_text(
        'artists:\n'
        '  - artist_id: zoe_zapata\n'
        '    display_name: "Zoe Zapata"\n'
        '    country_birth: "CO"\n'
        '    nationalities: ["CO"]\n'
        '    attribution_type: autor\n'
        '    source: manual\n'
        '    confidence: high\n'
        '    aliases:\n'
        '      - "Zoe Zapata"\n',
        encoding="utf-8",
    )

    added = apply_mod.merge_new_entries(NEW_ENTRIES, shard_dir=tmp_path)

    assert added == 0
    data = yaml.safe_load((tmp_path / "z.yaml").read_text(encoding="utf-8"))
    assert len(data["artists"]) == 1
    # Gana lo curado a mano.
    assert data["artists"][0]["country_birth"] == "CO"
    assert data["artists"][0]["source"] == "manual"


def test_an_entry_whose_alias_is_already_claimed_is_skipped(tmp_path):
    """Regla 3: un alias solo puede pertenecer a un artista."""
    (tmp_path / "z.yaml").write_text(
        'artists:\n'
        '  - artist_id: zoe_zapata_pintora\n'
        '    display_name: "Zoe Zapata"\n'
        '    country_birth: "CO"\n'
        '    nationalities: ["CO"]\n'
        '    attribution_type: autor\n'
        '    source: manual\n'
        '    confidence: high\n'
        '    aliases:\n'
        '      - "Zoe Zapata"\n',
        encoding="utf-8",
    )

    added = apply_mod.merge_new_entries(NEW_ENTRIES, shard_dir=tmp_path)

    assert added == 0


def test_a_null_death_year_is_not_written_as_a_key(tmp_path):
    """death_year: null ensucia el YAML y no aporta nada."""
    (tmp_path / "z.yaml").write_text("artists: []\n", encoding="utf-8")

    apply_mod.merge_new_entries(NEW_ENTRIES, shard_dir=tmp_path)

    data = yaml.safe_load((tmp_path / "z.yaml").read_text(encoding="utf-8"))
    assert "death_year" not in data["artists"][0]

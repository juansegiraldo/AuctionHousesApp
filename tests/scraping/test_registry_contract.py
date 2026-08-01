"""Contract test: every house that opts into the framework (has a house.py with HOUSE)
must satisfy the House contract and agree with its registry.json entry.

Legacy houses (bogota_auctions, duran_subastas) have no house.py yet and are simply
skipped — they keep their own runners. This is the cheap, offline guard that replaces a
second registry layer.
"""

import importlib
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = ROOT / "scraping" / "houses" / "registry.json"

REQUIRED_PARSER_FUNCS = (
    "_auction_id_from_url",
    "parse_historic_page",
    "parse_auction_page",
    "parse_lot_page",
    "get_auction_title_from_page",
)


def _registry_houses():
    data = json.loads(REGISTRY.read_text(encoding="utf-8"))
    return data["houses"]


def _framework_houses():
    """Registry houses that ship a house.py exposing HOUSE."""
    out = []
    for entry in _registry_houses():
        slug = entry["slug"]
        house_py = ROOT / "scraping" / "houses" / slug / "house.py"
        if house_py.exists():
            out.append(entry)
    return out


def test_registry_is_valid_json_with_required_keys():
    for entry in _registry_houses():
        assert {"slug", "name", "module", "output_dir"} <= set(entry)


@pytest.mark.parametrize("entry", _framework_houses(), ids=lambda e: e["slug"])
def test_framework_house_matches_registry(entry):
    slug = entry["slug"]
    module = importlib.import_module(f"scraping.houses.{slug}.house")
    house = module.HOUSE

    assert house.slug == slug, f"{slug}: HOUSE.slug mismatch"

    expected_output = (ROOT / entry["output_dir"]).resolve()
    assert house.output_dir.resolve() == expected_output, f"{slug}: output_dir mismatch"

    for func in REQUIRED_PARSER_FUNCS:
        assert hasattr(house.parsers, func), f"{slug}: parsers missing {func}"

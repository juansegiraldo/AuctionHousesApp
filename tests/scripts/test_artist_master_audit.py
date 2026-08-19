"""Pruebas del auditor previo al pegado de fichas.

Existe por lo que paso al pegar el shard A: la comprobacion manual dijo "0
colisiones" y habia DOS, porque comparaba alias contra alias y el loader
tambien indexa el display_name. Una de ellas (Antonio Reyna Manescau) habria
metido al pintor como italiano cuando nacio en Coin, Malaga.

El auditor no decide: senala. Lo que encuentra se revisa a mano.
"""

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location(
    "artist_master_audit", ROOT / "scripts" / "artist_master_audit.py"
)
audit = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(audit)


def _entry(artist_id, display_name, aliases=None, **extra):
    e = {
        "artist_id": artist_id,
        "display_name": display_name,
        "aliases": aliases if aliases is not None else [display_name],
        "country_birth": "ES",
        "birth_year": 1900,
        "confidence": "high",
    }
    e.update(extra)
    return e


def test_detects_a_clash_against_an_existing_display_name():
    # El caso Reyna Manescau: el alias nuevo choca con el DISPLAY_NAME de una
    # ficha curada, no con sus aliases. Mirar solo aliases lo dejaba pasar.
    master = {"antonio_reyna_manescau": {
        "display_name": "Antonio Reyna Manescau", "aliases": []}}
    found = audit.find_clashes(
        [_entry("antonio_reyna", "Antonio Reyna Manescau", ["Antonio Reyna"])],
        master,
    )
    assert len(found) == 1
    assert found[0]["owner"] == "antonio_reyna_manescau"


def test_detects_a_clash_between_two_new_entries():
    found = audit.find_clashes(
        [_entry("a_uno", "Mismo Pintor"), _entry("a_dos", "Mismo Pintor")], {}
    )
    assert len(found) == 1


def test_no_clash_when_names_are_genuinely_different():
    master = {"otro": {"display_name": "Otro Pintor", "aliases": []}}
    assert audit.find_clashes([_entry("nuevo", "Pintor Nuevo")], master) == []


def test_flags_a_country_that_contradicts_the_curated_one():
    # Wikidata da IT por el lugar de MUERTE (Roma) cuando nacio en Malaga.
    master = {"antonio_reyna_manescau": {
        "display_name": "Antonio Reyna Manescau", "aliases": [], "country_birth": "ES"}}
    found = audit.find_country_conflicts(
        [_entry("antonio_reyna", "Antonio Reyna Manescau", country_birth="IT")],
        master,
    )
    assert len(found) == 1
    assert found[0]["curated"] == "ES"
    assert found[0]["proposed"] == "IT"


def test_a_matching_country_is_not_a_conflict():
    master = {"x": {"display_name": "Pintor", "aliases": [], "country_birth": "ES"}}
    assert audit.find_country_conflicts([_entry("x", "Pintor", country_birth="ES")], master) == []


def test_flags_single_word_names_for_manual_review():
    # El caso Jano/Marola/Serny del README: una palabra suele ser ruido, pero a
    # veces es un pseudonimo real (Castelao, Alvar). Se senala, no se descarta.
    found = audit.flag_suspicious([_entry("castelao", "Castelao"),
                                   _entry("juan_perez", "Juan Pérez")])
    names = [f["display_name"] for f in found if f["reason"] == "nombre_de_una_palabra"]
    assert names == ["Castelao"]


def test_flags_entries_without_a_country():
    found = audit.flag_suspicious([_entry("sin_pais", "Sin País", country_birth=None)])
    assert any(f["reason"] == "sin_pais" for f in found)


def test_clean_batch_reports_nothing():
    assert audit.flag_suspicious([_entry("juan_perez", "Juan Pérez")]) == []

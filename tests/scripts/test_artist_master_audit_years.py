"""Deteccion de fichas cuyo anio contradice al catalogo de la casa.

Un hueco es un resultado correcto; un anio EQUIVOCADO se publica en el informe
y nadie lo detecta leyendolo. La carga del Excel curado dejo 40 fichas donde el
catalogo insiste en otra fecha: Nirma Zarate figura como n.1969 cuando sus 13
lotes dicen 1936-1999.
"""

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location(
    "artist_master_promote", ROOT / "scripts" / "artist_master_promote.py"
)
promote = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(promote)


def _row(birth_evidence, count=5):
    return {
        "artist_id": "nirma_zarate",
        "evidence": {"birth_year": [{"value": birth_evidence, "count": count}]},
    }


def test_a_far_off_catalog_year_is_reported():
    """13 lotes diciendo 1936 frente a un maestro que dice 1969."""
    conflicts = promote.catalog_year_conflicts(
        {"nirma_zarate": {"birth_year": 1969, "display_name": "Nirma Zárate"}},
        [_row(1936, count=13)],
    )

    assert len(conflicts) == 1
    assert conflicts[0]["artist_id"] == "nirma_zarate"
    assert conflicts[0]["master_birth_year"] == 1969
    assert conflicts[0]["catalog_birth_year"] == 1936


def test_a_small_discrepancy_is_not_a_conflict():
    """Antonio Palacios: 1874 en Wikipedia, 1876 en la ficha de la casa."""
    conflicts = promote.catalog_year_conflicts(
        {"nirma_zarate": {"birth_year": 1876, "display_name": "x"}},
        [_row(1874, count=13)],
    )

    assert conflicts == []


def test_a_single_lot_does_not_outweigh_the_master():
    """Un lote suelto puede llevar una errata; hace falta insistencia."""
    conflicts = promote.catalog_year_conflicts(
        {"nirma_zarate": {"birth_year": 1969, "display_name": "x"}},
        [_row(1936, count=1)],
    )

    assert conflicts == []


def test_an_entry_without_a_master_year_is_not_a_conflict():
    """Sin anio en el maestro no hay contradiccion, hay hueco."""
    conflicts = promote.catalog_year_conflicts(
        {"nirma_zarate": {"birth_year": None, "display_name": "x"}},
        [_row(1936, count=13)],
    )

    assert conflicts == []


def test_a_minority_year_does_not_challenge_a_confirmed_master():
    """Antonio Barrera: 62 lotes dicen 1948 (como el maestro) y 7 dicen 1889.

    El valor DOMINANTE del catalogo confirma al maestro, asi que no hay
    conflicto: la minoria es ruido de otra ficha o de un homonimo. Elegir el
    discrepante mas votado ignorando la mayoria era un falso positivo.
    """
    row = {
        "artist_id": "antonio_barrera",
        "evidence": {
            "birth_year": [
                {"value": 1948, "count": 62},
                {"value": 1889, "count": 7},
            ]
        },
    }

    conflicts = promote.catalog_year_conflicts(
        {"antonio_barrera": {"birth_year": 1948, "display_name": "Antonio Barrera"}},
        [row],
    )

    assert conflicts == []


def test_the_dominant_catalog_year_still_wins_when_it_disagrees():
    """Nirma Zarate: el valor mayoritario del catalogo SI contradice."""
    row = {
        "artist_id": "nirma_zarate",
        "evidence": {
            "birth_year": [
                {"value": 1936, "count": 13},
                {"value": 1969, "count": 1},
            ]
        },
    }

    conflicts = promote.catalog_year_conflicts(
        {"nirma_zarate": {"birth_year": 1969, "display_name": "Nirma Zárate"}},
        [row],
    )

    assert len(conflicts) == 1
    assert conflicts[0]["catalog_birth_year"] == 1936

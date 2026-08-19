"""Pruebas del maestro operativo exhaustivo de artistas."""

from __future__ import annotations

import json
import textwrap
from pathlib import Path

import pytest
import yaml

from pipelines.gold import build_artist_master
from pipelines.shared import artist_master


COUNTRIES = textwrap.dedent(
    """
    countries:
      CO: {es: Colombia, demonym_es: colombiano}
      ES: {es: España, demonym_es: español}
    aliases:
      colombia: CO
      espana: ES
      españa: ES
    """
)


@pytest.fixture
def curated_master(tmp_path, monkeypatch):
    directory = tmp_path / "artists"
    directory.mkdir()
    (directory / "_countries.yaml").write_text(COUNTRIES, encoding="utf-8")
    (directory / "a.yaml").write_text(
        yaml.safe_dump(
            {
                "artists": [
                    {
                        "artist_id": "artista_curada",
                        "display_name": "Artista Curada",
                        "country_birth": "CO",
                        "nationalities": ["CO"],
                        "birth_year": 1900,
                        "death_year": 1980,
                        "attribution_type": "autor",
                        "source": "manual",
                        "confidence": "high",
                        "aliases": ["Artista Curada"],
                        "notes": "Fuente: https://example.org/artista",
                    }
                ]
            },
            allow_unicode=True,
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(artist_master, "ARTISTS_DIR", directory)
    artist_master.reset_caches()
    yield directory
    artist_master.reset_caches()


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


def _row(name: str | None, **overrides) -> dict:
    base = {
        "artist_name": name,
        "artist_raw": name,
        "artist_fold": None,
        "artist_id": None,
        "artist_resolution": "fold_only",
        "attribution_type": "autor",
        "artist_country": None,
        "artist_birth_year": None,
        "artist_death_year": None,
        "house_slug": "casa_prueba",
        "source_file": "data/bronze/prueba.jsonl",
        "lot_url": f"https://example.org/{name}",
    }
    base.update(overrides)
    return base


def test_every_author_fold_is_accounted_without_promoting_candidates(
    tmp_path, curated_master
):
    lots = tmp_path / "lots.jsonl"
    _write_jsonl(
        lots,
        [
            _row(
                "Artista Curada",
                artist_fold="artista curada",
                artist_id="artista_curada",
                artist_resolution="master",
            ),
            _row(
                "Candidata Nueva (Colombia, 1980-2020)",
                artist_fold="candidata nueva colombia 1980 2020",
                artist_country="Colombia",
                artist_birth_year=1980,
                artist_death_year=2020,
            ),
            _row(
                "Mesa auxiliar",
                artist_fold="mesa auxiliar",
                artist_resolution="not_an_author",
                attribution_type="no_autor",
            ),
            _row(
                None,
                artist_resolution="unresolved",
                attribution_type="desconocido",
            ),
        ],
    )

    groups, raw_dispositions, latent, stats = build_artist_master.collect_silver(lots)
    dimension = build_artist_master.build_dimension(groups)
    dispositions = build_artist_master.build_dispositions(raw_dispositions, dimension)
    summary = build_artist_master.coverage_summary(
        dimension, dispositions, latent, stats, lots
    )

    assert summary["author_folds"] == 2
    assert summary["author_folds_accounted"] == 2
    assert summary["author_fold_coverage_rate"] == 1.0

    candidate = next(row for row in dimension if row["artist_id"] is None)
    assert candidate["curation_status"] == "needs_web"
    assert candidate["entity_type"] == "unknown"
    # La evidencia disponible se conserva, pero no se convierte en canon.
    assert candidate["country_birth"] is None
    assert candidate["birth_year"] is None
    assert candidate["death_year"] is None
    assert candidate["candidate_country_birth"] == "CO"
    assert candidate["candidate_birth_year"] == 1980
    assert candidate["candidate_death_year"] == 2020
    assert candidate["missing_fields"] == [
        "country_birth",
        "birth_year",
        "death_year",
    ]
    assert candidate["needs_web_research"] is True

    rejected = next(
        row for row in dispositions if row["artist_fold"] == "mesa auxiliar"
    )
    assert rejected["disposition"] == "rejected_non_artist"


def test_conflicting_biographies_are_ambiguous(tmp_path, curated_master):
    lots = tmp_path / "lots.jsonl"
    _write_jsonl(
        lots,
        [
            _row(
                "Nombre Ambiguo (Colombia, 1900-1980)",
                artist_fold="nombre ambiguo",
                artist_birth_year=1900,
                artist_death_year=1980,
            ),
            _row(
                "Nombre Ambiguo (Colombia, 1950-2020)",
                artist_fold="nombre ambiguo",
                artist_birth_year=1950,
                artist_death_year=2020,
            ),
        ],
    )
    groups, _, _, _ = build_artist_master.collect_silver(lots)
    row = next(
        item
        for item in build_artist_master.build_dimension(groups)
        if item["artist_id"] is None
    )
    assert row["curation_status"] == "ambiguous"
    assert "biographical_evidence_conflict" in row["quality_flags"]
    assert row["candidate_birth_year"] is None
    assert row["field_status"]["birth_year"] == "conflict"


def test_curated_complete_entry_with_url_is_verified(tmp_path, curated_master):
    lots = tmp_path / "lots.jsonl"
    _write_jsonl(
        lots,
        [
            _row(
                "Artista Curada",
                artist_fold="artista curada",
                artist_id="artista_curada",
                artist_resolution="master",
                artist_birth_year=1900,
                artist_death_year=1980,
                artist_country="Colombia",
            )
        ],
    )
    groups, _, _, _ = build_artist_master.collect_silver(lots)
    row = next(
        item
        for item in build_artist_master.build_dimension(groups)
        if item["artist_id"] == "artista_curada"
    )
    assert row["curation_status"] == "verified"
    assert row["missing_fields"] == []
    assert row["needs_web_research"] is False
    assert row["evidence_urls"] == ["https://example.org/artista"]


def test_possible_comma_alias_is_flagged_not_merged(tmp_path, curated_master):
    lots = tmp_path / "lots.jsonl"
    _write_jsonl(
        lots,
        [
            _row(
                "Curada, Artista",
                artist_fold="curada artista",
                artist_resolution="fold_only",
            )
        ],
    )
    groups, _, _, _ = build_artist_master.collect_silver(lots)
    candidate = next(
        item
        for item in build_artist_master.build_dimension(groups)
        if item["artist_id"] is None
    )
    assert candidate["curation_status"] == "ambiguous"
    assert candidate["possible_master_matches"] == [
        {
            "artist_id": "artista_curada",
            "method": "comma_inversion",
            "source_name": "Curada, Artista",
        }
    ]
    assert candidate["artist_id"] is None


def test_build_writes_atomic_outputs_and_versioned_review_queue(
    tmp_path, monkeypatch, curated_master
):
    silver = tmp_path / "lots.jsonl"
    _write_jsonl(
        silver,
        [_row("Pendiente Uno", artist_fold="pendiente uno")],
    )
    gold = tmp_path / "gold"
    monkeypatch.setattr(build_artist_master, "DIM_ARTISTS", gold / "dim.jsonl")
    monkeypatch.setattr(build_artist_master, "DISPOSITIONS", gold / "disp.jsonl")
    monkeypatch.setattr(build_artist_master, "COVERAGE", gold / "coverage.json")
    review_dir = tmp_path / "review"
    monkeypatch.setattr(build_artist_master, "REVIEW_DIR", review_dir)
    monkeypatch.setattr(build_artist_master, "REVIEW_MANIFEST", review_dir / "manifest.json")

    summary = build_artist_master.build(
        lots_path=silver, legacy_excel=None, write_queue=True
    )
    assert summary["author_fold_coverage_rate"] == 1.0
    assert (gold / "dim.jsonl").exists()
    queued = [
        json.loads(line)
        for line in (review_dir / "p.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert len(queued) == 1
    assert queued[0]["display_name"] == "Pendiente Uno"
    assert queued[0]["needs_web_research"] is True

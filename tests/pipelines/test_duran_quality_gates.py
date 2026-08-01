import json

import pytest

from pipelines.silver import quality_gates


def _setup(tmp_path, monkeypatch, category="joyas"):
    """Prepara un Silver minimo con un unico lote de la categoria indicada."""
    lots = tmp_path / "data" / "silver" / "lots.jsonl"
    tags = tmp_path / "data" / "enrichments" / "category_tags.jsonl"
    lots.parent.mkdir(parents=True, exist_ok=True)
    tags.parent.mkdir(parents=True, exist_ok=True)

    row = {
        "house_slug": "duran_subastas",
        "dedupe_key": "duran_subastas|u1",
        "lot_url": "u1",
        "lot_title": "Lote 1",
        "price_sold": 1000,
    }
    lots.write_text(json.dumps(row) + "\n", encoding="utf-8")
    tags.write_text(
        json.dumps({"dedupe_key": "duran_subastas|u1", "category": category}) + "\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(quality_gates, "SILVER_LOTS", lots)
    monkeypatch.setattr(quality_gates, "CATEGORY_TAGS", tags)


def _argv(monkeypatch, *extra):
    monkeypatch.setattr(
        "sys.argv",
        ["quality_gates.py", "--house-slug", "duran_subastas", *extra],
    )


def test_out_of_scope_aborts_with_fail_on_violation(tmp_path, monkeypatch):
    """Con --fail-on-violation y umbral estricto, una categoria ajena aborta."""
    _setup(tmp_path, monkeypatch, category="joyas")
    _argv(
        monkeypatch,
        "--allowed-categories",
        "painting,prints",
        "--max-out-of-scope-pct",
        "0.0",
        "--fail-on-violation",
    )
    with pytest.raises(SystemExit):
        quality_gates.main()


def test_reports_without_aborting_by_default(tmp_path, monkeypatch):
    """Sin --fail-on-violation la puerta informa pero no rompe el pipeline.

    Es lo que permite usarla como diagnostico en casas generalistas, donde
    siempre habra lotes fuera del foco.
    """
    _setup(tmp_path, monkeypatch, category="joyas")
    _argv(
        monkeypatch,
        "--allowed-categories",
        "painting,prints",
        "--max-out-of-scope-pct",
        "0.0",
    )
    quality_gates.main()  # no debe lanzar


def test_allowed_category_passes(tmp_path, monkeypatch):
    """Las categorias por defecto son las que emite category_tag.py (ingles).

    El bug original: el default era "obra_grafica,pintura" (espaniol), asi que
    ninguna fila coincidia y la puerta marcaba el 100% fuera de alcance.
    """
    _setup(tmp_path, monkeypatch, category="painting")
    _argv(monkeypatch, "--fail-on-violation")
    quality_gates.main()  # no debe lanzar

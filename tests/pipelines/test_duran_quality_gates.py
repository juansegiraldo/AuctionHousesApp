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


# --------------------------------------------------------------------------
# Puertas de artista y pais
# --------------------------------------------------------------------------

def _setup_artists(tmp_path, monkeypatch, rows, house="duran_subastas"):
    lots = tmp_path / "data" / "silver" / "lots.jsonl"
    tags = tmp_path / "data" / "enrichments" / "category_tags.jsonl"
    lots.parent.mkdir(parents=True, exist_ok=True)
    tags.parent.mkdir(parents=True, exist_ok=True)
    with open(lots, "w", encoding="utf-8") as f:
        for i, row in enumerate(rows):
            base = {
                "house_slug": house,
                "dedupe_key": f"{house}|u{i}",
                "lot_url": f"u{i}",
                "lot_title": f"Lote {i}",
                "price_sold": 1000,
            }
            base.update(row)
            f.write(json.dumps(base, ensure_ascii=False) + "\n")
    tags.write_text("", encoding="utf-8")
    monkeypatch.setattr(quality_gates, "SILVER_LOTS", lots)
    monkeypatch.setattr(quality_gates, "CATEGORY_TAGS", tags)


def test_artist_gates_report_coverage(tmp_path, monkeypatch, capsys):
    """Informa de resolucion y cobertura de pais sin bloquear por defecto."""
    _setup_artists(
        tmp_path,
        monkeypatch,
        [
            {"attribution_type": "autor", "artist_resolution": "master",
             "artist_country_birth": "ES"},
            {"attribution_type": "autor", "artist_resolution": "fold_only",
             "artist_country_birth": None},
            {"attribution_type": "escuela", "artist_resolution": "not_an_author"},
            {"attribution_type": "escuela", "artist_resolution": "not_an_author"},
        ],
    )
    _argv(monkeypatch)
    quality_gates.main()
    out = capsys.readouterr().out
    assert "attribution_autor_pct=0.5000" in out
    assert "artist_resolution_rate=0.5000" in out
    assert "artist_country_coverage=0.5000" in out


def test_unmapped_country_values_are_surfaced(tmp_path, monkeypatch, capsys):
    """Un pais que _countries.yaml no conoce se cuenta y se muestra.

    Es el bucle de realimentacion que evita que la tabla de paises envejezca en
    silencio, que es como houses.yaml quedo obsoleto.
    """
    _setup_artists(
        tmp_path,
        monkeypatch,
        [
            {"attribution_type": "autor", "artist_country": "Colombia"},
            {"attribution_type": "autor", "artist_country": "Frobnia"},
        ],
    )
    _argv(monkeypatch)
    quality_gates.main()
    out = capsys.readouterr().out
    assert "unmapped_country_values=1" in out
    assert "Frobnia" in out


def test_artist_gates_can_fail_the_build(tmp_path, monkeypatch):
    """Con umbral y --fail-on-violation, la puerta si aborta."""
    _setup_artists(
        tmp_path,
        monkeypatch,
        [{"attribution_type": "autor", "artist_resolution": "fold_only"}],
    )
    _argv(monkeypatch, "--min-artist-resolution-rate", "0.5", "--fail-on-violation")
    with pytest.raises(SystemExit, match="artist_resolution"):
        quality_gates.main()


def test_houses_without_artists_are_exempt(tmp_path, monkeypatch):
    """Zorrilla es joyeria: 0% de artistas para siempre, no es un fallo.

    Sin la excepcion la puerta gritaria lobo en cada ejecucion.
    """
    _setup_artists(
        tmp_path,
        monkeypatch,
        [{"attribution_type": "desconocido", "artist_resolution": "unresolved"}],
        house="zorrilla_subastas",
    )
    monkeypatch.setattr(
        "sys.argv",
        ["quality_gates.py", "--house-slug", "zorrilla_subastas",
         "--min-artist-resolution-rate", "0.9",
         "--min-country-coverage", "0.9",
         "--fail-on-violation"],
    )
    quality_gates.main()  # no debe lanzar


def test_silver_without_artist_resolve_does_not_crash(tmp_path, monkeypatch, capsys):
    """Un Silver anterior a artist_resolve.py informa 0, no rompe."""
    _setup_artists(tmp_path, monkeypatch, [{}, {}])
    _argv(monkeypatch)
    quality_gates.main()
    out = capsys.readouterr().out
    assert "artist_resolution_rate=0.0000" in out

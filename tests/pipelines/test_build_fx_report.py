"""Tests del informe FX. No tocan data/: prueban el render puro.

El grafico es SVG generado aqui (sin libreria de cliente) porque un Artifact de
Claude bloquea todo host externo, asi que la geometria se testea como codigo.
"""

from pipelines.analytics.build_fx_report import (
    TEMPLATE,
    _area,
    _hero,
    _path,
    _rows,
    _spark,
)


def test_path_has_one_point_per_month():
    assert _path([1.0, 1.2, 0.9]).count(",") == 3


def test_area_closes_on_the_baseline():
    # El area se cierra contra el 1,00x, no contra el borde: lo que se lee es
    # la desviacion respecto a la tasa estatica.
    assert _area([1.2, 1.4]).endswith("Z")


def test_hero_marks_max_and_min():
    months = [f"2014-{m:02d}" for m in range(1, 13)]
    cop = [1.0 + i / 100 for i in range(12)]
    svg = _hero(months, cop, cop)
    assert svg.count("<circle") == 2          # maximo y minimo
    assert "1.11&#215;" in svg                # el maximo etiquetado


def test_spark_ends_with_a_dot():
    assert _spark([1.0, 2.0, 3.0], "cop").count("<circle") == 1


def test_rows_marks_eur_house_as_not_converted():
    # Duran es EUR: no debe pintarse una serie de tasa, porque no hay ninguna.
    html = _rows(
        [{"house_slug": "duran_subastas", "currency": "EUR", "revenue_native": 10,
          "revenue_eur": 10, "lots_sold": 3, "fx_method_counts": {"monthly": 3},
          "fx_fallback_lots": 0}],
        {"COP": [1.0, 2.0]},
    )
    assert "sin conversi" in html
    assert "todo mensual" in html


def test_rows_flags_a_house_with_fallback():
    html = _rows(
        [{"house_slug": "bogota_auctions", "currency": "COP", "revenue_native": 10,
          "revenue_eur": 5, "lots_sold": 9, "fx_method_counts": {"monthly": 8},
          "fx_fallback_lots": 52}],
        {"COP": [1.0, 2.0]},
    )
    assert "52 est" in html
    assert "pill warn" in html


def test_template_defines_all_three_theme_states():
    # El visor tiene tres estados: sin marcar (system), light y dark. Si un
    # color solo existe dentro de [data-theme], la pagina se renderiza con el
    # texto de un tema sobre el fondo del otro.
    css = TEMPLATE.read_text(encoding="utf-8")
    assert "prefers-color-scheme:dark" in css
    assert '[data-theme="dark"]' in css
    assert "background:var(--bg)" in css

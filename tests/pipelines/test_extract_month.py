"""Tests de extract_month: cada casa guarda la fecha en un formato distinto."""

from pipelines.shared.schema import extract_month


def test_iso_date_bogota():
    # Bogota y Zorrilla guardan ISO con dia exacto.
    assert extract_month("2022-03-03T20:00") == ("2022-03", "iso")


def test_iso_date_with_timezone_zorrilla():
    assert extract_month("2019-05-10T20:00:00+00:00") == ("2019-05", "iso")


def test_spanish_text_duran():
    # Duran solo publica mes y anio, en texto libre y en espaniol.
    assert extract_month("Enero 2014") == ("2014-01", "text")
    assert extract_month("Julio 2014") == ("2014-07", "text")
    assert extract_month("Diciembre 2020") == ("2020-12", "text")


def test_spanish_text_is_accent_and_case_insensitive():
    # "Marzo", "marzo" y "MARZO" son la misma cosa.
    assert extract_month("marzo 2015") == ("2015-03", "text")
    assert extract_month("MARZO 2015") == ("2015-03", "text")


def test_falls_back_to_auction_id():
    # Ultimo recurso: el slug lleva mes y anio.
    assert extract_month(None, "subasta-504-enero-2014_504-001") == ("2014-01", "auction_id")


def test_auction_id_only_used_when_date_unusable():
    # Si la fecha sirve, el slug no se mira.
    assert extract_month("2021-06-01T19:00", "subasta-504-enero-2014_504-001") == (
        "2021-06",
        "iso",
    )


def test_typo_year_2107_is_not_accepted():
    # subasta-541-marzo-2107 es un typo de la propia web de Duran (2107 por
    # 2017). extract_year solo acepta 19xx/20xx; extract_month hace lo mismo,
    # para no fabricar un mes que no existe.
    assert extract_month(None, "subasta-541-marzo-2107") == (None, "unknown")


def test_no_date_no_id():
    assert extract_month(None) == (None, "unknown")
    assert extract_month("") == (None, "unknown")


def test_unparseable_text():
    assert extract_month("tienda-online") == (None, "unknown")


def test_month_without_year_is_unknown():
    # Un mes suelto no basta: sin anio no hay clave "YYYY-MM".
    assert extract_month("Enero") == (None, "unknown")

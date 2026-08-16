"""Tests de conversion de moneda.

El error que motivo este modulo: sumar COP con EUR inflaba los ingresos
totales unas 3500 veces.
"""

from pipelines.shared.fx import fx_as_of, fx_note, rate_for, to_eur


def test_eur_is_identity():
    assert to_eur(1000, "EUR") == 1000.0


def test_cop_converts_down():
    # 31.215.260.000 COP son ~7,2M EUR, no 31.215 millones de euros.
    result = to_eur(31_215_260_000, "COP")
    assert result is not None
    assert 7_000_000 < result < 7_500_000


def test_unknown_currency_returns_none_not_one():
    # Regla clave: una moneda sin tasa NO debe pasar por euros.
    assert to_eur(100, "XYZ") is None
    assert rate_for("XYZ") is None


def test_none_amount_returns_none():
    assert to_eur(None, "EUR") is None


def test_currency_is_case_insensitive():
    assert to_eur(100, "eur") == to_eur(100, "EUR")


def test_none_currency_returns_none():
    assert to_eur(100, None) is None


def test_note_describes_monthly_conversion():
    # La nota ya no habla de una tasa estatica unica: desde fx_history.yaml la
    # conversion usa la tasa del MES de cada subasta.
    note = fx_note()
    assert "MES" in note or "mes" in note


def test_note_mentions_fallback_count_when_given():
    # El fallback existe, pero queda contado en la nota, no invisible.
    assert "1,234" in fx_note(1234)
    assert fx_as_of() in fx_note(1234)

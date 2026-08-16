"""Tests de la conversion con tasa historica mensual.

Fijan el bug que arregla esta feature: aplicar la tasa de hoy a un lote de
2014 infravalora ~62% las ventas en COP.
"""

from pipelines.shared.fx import (
    fx_as_of,
    fx_history_range,
    fx_note,
    rate_for_month,
    to_eur,
    to_eur_at,
)


def test_monthly_rate_differs_from_static():
    # El test de regresion del bug. En 2014 el COP valia mucho mas frente al
    # EUR que hoy, asi que el mismo importe convierte a bastante mas.
    historico, method = to_eur_at(10_000_000, "COP", "2014-01")
    estatico = to_eur(10_000_000, "COP")
    assert method == "monthly"
    assert historico > estatico * 1.4


def test_eur_never_converts():
    # Duran ya viene en EUR: tasa 1.0 en cualquier mes, sin mirar el historico.
    for month in ("2014-01", "2026-07", None):
        assert to_eur_at(1000, "EUR", month) == (1000.0, "monthly")


def test_eur_without_month_is_not_counted_as_fallback():
    # Regresion: EUR sin fecha usable devolvia "fallback_static". Como EUR vale
    # 1.0 en cualquier mes, ese lote NO es aproximado, y contarlo engordaba el
    # recuento de fallback del informe con los 40.442 lotes de Duran.
    assert to_eur_at(1000, "EUR", None) == (1000.0, "monthly")
    assert to_eur_at(None, "EUR", None)[0] is None


def test_missing_month_falls_back_to_static():
    # Decision del propietario: todo lote convierte siempre. El fallback queda
    # contado en quality_flags, no invisible.
    importe, method = to_eur_at(10_000_000, "COP", None)
    assert method == "fallback_static"
    assert importe == to_eur(10_000_000, "COP")


def test_unknown_currency_returns_none_not_fallback():
    # El fallback es por FECHA ausente, no por MONEDA ausente. Una moneda sin
    # tasa sigue devolviendo None, nunca 1.0 ni la tasa estatica.
    assert to_eur_at(100, "XYZ", "2014-01") == (None, "unavailable")
    assert to_eur_at(100, "XYZ", None) == (None, "unavailable")
    assert to_eur_at(100, None, "2014-01") == (None, "unavailable")


def test_none_amount_returns_none():
    assert to_eur_at(None, "COP", "2014-01")[0] is None


def test_month_before_range_clamps_to_earliest():
    # Un mes fuera de rango cae al mes mas cercano DENTRO del historico, no a
    # la tasa estatica: sigue siendo un dato real.
    first, _ = fx_history_range()
    importe, method = to_eur_at(1_000_000, "COP", "1990-01")
    assert method == "monthly"
    assert importe == to_eur_at(1_000_000, "COP", first)[0]


def test_month_after_range_clamps_to_latest():
    _, last = fx_history_range()
    importe, method = to_eur_at(1_000_000, "COP", "2099-12")
    assert method == "monthly"
    assert importe == to_eur_at(1_000_000, "COP", last)[0]


def test_rate_for_month_usd():
    rate = rate_for_month("USD", "2014-01")
    assert rate is not None
    # 1 EUR valia ~1,36 USD en enero de 2014 -> 1 USD ~ 0,73 EUR.
    assert 0.70 < rate < 0.78


def test_rate_for_month_is_case_insensitive():
    assert rate_for_month("cop", "2014-01") == rate_for_month("COP", "2014-01")


def test_history_range_covers_data():
    first, last = fx_history_range()
    assert first <= "2014-01"   # el primer lote es de enero de 2014
    assert last >= "2026-01"


def test_legacy_to_eur_unchanged():
    # No se rompe lo existente: to_eur sigue siendo el camino del fallback.
    assert to_eur(1000, "EUR") == 1000.0
    assert to_eur(100, "XYZ") is None


def test_note_describes_monthly_conversion():
    note = fx_note()
    assert "MES" in note or "mes" in note


def test_note_mentions_fallback_count_when_given():
    assert "1,234" in fx_note(1234)
    assert fx_as_of() in fx_note(1234)

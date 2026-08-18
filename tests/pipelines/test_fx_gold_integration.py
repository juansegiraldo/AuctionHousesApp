"""Invariantes de la conversion FX tal y como la aplica Gold.

No reconstruyen Gold (necesitaria data/): fijan las reglas que build_gold da
por buenas al llamar a to_eur_at() con el mes de extract_month().
"""

from pipelines.shared.fx import to_eur, to_eur_at
from pipelines.shared.schema import extract_month


def test_duran_eur_lot_never_moves_with_the_month():
    # La comprobacion de aceptacion del plan: Duran cotiza en EUR y su
    # revenue_eur NO debe cambiar al pasar a tasa mensual. Si esto se rompe,
    # es que EUR esta pasando por el historico.
    for date in ("Enero 2014", "Julio 2020", None):
        month, _ = extract_month(date, "subasta-504-enero-2014_504-001")
        assert to_eur_at(120_000, "EUR", month) == (120_000.0, "monthly")


def test_cop_lot_uses_its_own_month_not_todays_rate():
    # El mismo importe en dos meses distintos NO puede dar el mismo EUR: si
    # diera igual, se estaria aplicando una tasa unica.
    a, _ = to_eur_at(100_000_000, "COP", "2014-01")
    b, _ = to_eur_at(100_000_000, "COP", "2023-06")
    assert a != b
    # 2014 fue el peso mas fuerte del periodo cubierto.
    assert a > b


def test_lot_without_usable_date_still_converts():
    # Decision del propietario: todo lote convierte siempre. Sin fecha usable
    # cae a la tasa estatica, pero se contabiliza como fallback_static para que
    # el informe pueda publicarlo.
    month, method = extract_month(None, "tienda-online")
    assert (month, method) == (None, "unknown")
    importe, fx_method = to_eur_at(1_000_000, "COP", month)
    assert fx_method == "fallback_static"
    assert importe == to_eur(1_000_000, "COP")


def test_unknown_currency_is_not_rescued_by_the_fallback():
    # El fallback es por fecha, nunca por moneda: un lote en moneda sin tasa
    # queda fuera de los agregados en EUR en vez de colarse como euros.
    assert to_eur_at(1_000, "XYZ", "2023-06") == (None, "unavailable")


def test_duran_typo_month_2107_falls_back_instead_of_inventing():
    # subasta-541-marzo-2107 es un typo de la web de Duran. Preferimos el
    # fallback contado a fabricar un mes de 2107.
    month, _ = extract_month(None, "subasta-541-marzo-2107")
    assert month is None

"""Tests del parseo de fx_fetch_history. NUNCA tocan la red: usan fixtures.

El script se ejecuta a mano y rara vez; lo que hay que blindar es que lo
descargado se interprete bien, no que la API responda.
"""

from pathlib import Path

from scripts.fx_fetch_history import (
    build_rates,
    monthly_average,
    parse_ecb_csv,
    parse_trm_json,
)

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_ecb_csv():
    text = (FIXTURES / "ecb_sample.csv").read_text(encoding="utf-8")
    daily = parse_ecb_csv(text)
    assert daily["2014-01-02"] == 1.3670
    assert daily["2014-01-03"] == 1.3592
    assert len(daily) == 3


def test_parse_ecb_csv_skips_header():
    text = (FIXTURES / "ecb_sample.csv").read_text(encoding="utf-8")
    assert "TIME_PERIOD" not in parse_ecb_csv(text)


def test_parse_trm_json():
    text = (FIXTURES / "trm_sample.json").read_text(encoding="utf-8")
    daily = parse_trm_json(text)
    assert daily["2014-01-02"] == 1938.89
    assert daily["2014-02-03"] == 1970.00
    assert len(daily) == 3


def test_monthly_average():
    daily = {"2014-01-02": 1.0, "2014-01-03": 2.0, "2014-02-03": 5.0}
    monthly = monthly_average(daily)
    assert monthly["2014-01"] == 1.5
    assert monthly["2014-02"] == 5.0


def test_monthly_average_empty():
    assert monthly_average({}) == {}


def test_build_rates_usd_is_inverse_of_eurusd():
    # El BCE publica EUR->USD (cuantos USD vale 1 EUR). Nosotros guardamos
    # USD->EUR, que es el inverso.
    rates = build_rates({"2014-01": 1.36}, {})
    assert rates["USD"]["2014-01"] == round(1 / 1.36, 8)


def test_build_rates_cop_bridges_through_usd():
    # COP->EUR = (1/TRM) x (1/EURUSD). El BCE no publica COP, de ahi el puente.
    rates = build_rates({"2014-01": 1.36}, {"2014-01": 1938.0})
    expected = round((1 / 1938.0) * (1 / 1.36), 10)
    assert rates["COP"]["2014-01"] == expected


def test_build_rates_skips_month_missing_from_either_source():
    # Sin las dos series no se puede componer COP: mejor omitir el mes que
    # inventarlo. Es la misma disciplina que to_eur() devolviendo None.
    rates = build_rates({"2014-01": 1.36}, {"2014-02": 1938.0})
    assert "2014-02" not in rates["COP"]
    assert "2014-01" not in rates["COP"]

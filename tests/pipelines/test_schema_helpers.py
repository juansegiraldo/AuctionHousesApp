"""Tests de extract_year() e is_sold(): la logica que sostiene las cifras Gold.

Cada caso viene de datos reales que rompieron el pipeline en su momento.
"""

import pytest

from pipelines.shared.schema import UNKNOWN_YEAR, extract_year, is_sold


class TestExtractYear:
    def test_iso_date_bogota(self):
        # Formato de Bogota: el unico que funcionaba antes.
        assert extract_year("2024-06-07T19:00") == ("2024", "iso")

    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("Julio 2014", "2014"),
            ("Enero 2014", "2014"),
            ("Junio 2015", "2015"),
            ("Septiembre 2014", "2014"),
        ],
    )
    def test_spanish_month_text_duran(self, raw, expected):
        # Formato de Duran: caia entero en "unknown" y borraba la casa de los
        # graficos temporales.
        year, method = extract_year(raw)
        assert (year, method) == (expected, "text")

    def test_falls_back_to_auction_id(self):
        year, method = extract_year(None, "subasta-504-enero-2014_504-001")
        assert (year, method) == ("2014", "auction_id")

    def test_iso_wins_over_auction_id(self):
        # Si hay fecha real, no se usa el identificador.
        assert extract_year("2024-06-07T19:00", "subasta-504-enero-2014")[1] == "iso"

    def test_unknown_when_no_year_anywhere(self):
        # Caso real: subasta de El Paular, sin anio en fecha ni en el slug.
        # Debe quedarse en unknown, no inventarse un anio.
        assert extract_year(None, "subasta-510-de-el-paular_510-001") == (
            UNKNOWN_YEAR,
            "unknown",
        )

    def test_unknown_on_empty_input(self):
        assert extract_year(None, None)[0] == UNKNOWN_YEAR
        assert extract_year("", "")[0] == UNKNOWN_YEAR

    def test_ignores_non_year_numbers(self):
        # "504" no es un anio valido; no debe colarse como tal.
        assert extract_year("subasta 504")[0] == UNKNOWN_YEAR


class TestIsSold:
    def test_explicit_sold(self):
        assert is_sold("VENDIDO", None) is True

    def test_explicit_unsold_beats_price(self):
        # Un lote NO VENDIDO con precio de salida no es una venta.
        assert is_sold("NO VENDIDO", 500) is False

    def test_falls_back_to_price_when_no_status(self):
        # Bogota no publica estado en 1133 lotes: ahi si vale la aproximacion.
        assert is_sold(None, 500) is True
        assert is_sold(None, None) is False

    def test_case_and_whitespace_insensitive(self):
        assert is_sold(" vendido ", None) is True

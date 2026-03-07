from scraping.houses.duran_subastas.parsers import normalize_category
from scraping.houses.duran_subastas.run_one_auction import is_target_category


def test_category_normalization_variants():
    assert normalize_category("OBRA GRÁFICA") == "obra_grafica"
    assert normalize_category("obra grafica") == "obra_grafica"
    assert normalize_category("PINTURA") == "pintura"
    assert normalize_category("Joyas") is None


def test_target_category_filter():
    assert is_target_category("obra_grafica") is True
    assert is_target_category("pintura") is True
    assert is_target_category("joyas") is False
    assert is_target_category(None, fallback_text="Lote de pintura contemporánea") is True


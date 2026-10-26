"""La tabla REAL de paises (_countries.yaml) contra los valores que trajo Morton.

Morton escribe el lugar de nacimiento, no el pais, y con grafias propias: la
puerta de calidad los listo en unmapped_country_values (557 lotes en la primera
corrida). Esta es la tabla atendiendo ese aviso, como pide su cabecera.
"""
import pytest

from pipelines.shared.artist_master import country_es, normalize_country


@pytest.mark.parametrize("text, iso", [
    # Variantes de EE. UU. con puntos y espacios ("E.E. U.U." pliega a "e e u u")
    ("E.E. U.U.", "US"),
    ("E.E.U.U.", "US"),
    ("E.E. U.U", "US"),
    # Estados de EE. UU. escritos donde iria el pais, como ya se hace con ciudades
    ("Utah", "US"),
    ("California", "US"),
    ("Texas", "US"),
    ("Nuevo México", "US"),  # el estado de EE. UU., no Mexico
    # Capital pegada al pais
    ("Santiago de Chile", "CL"),
    ("San José de Costa Rica", "CR"),
    ("República de Panamá", "PA"),
    # Region de un pais, como 'catalan' -> ES, que ya estaba
    ("Cataluña", "ES"),
    # Paises que faltaban
    ("India", "IN"),
    ("Chipre", "CY"),
    ("Letonia", "LV"),
    ("Latvia", "LV"),
    ("Finlandia", "FI"),
    ("Baréin", "BH"),
])
def test_morton_country_values_resolve(text, iso):
    assert normalize_country(text) == iso


@pytest.mark.parametrize("iso", ["IN", "CY", "LV", "FI", "BH"])
def test_new_countries_have_a_spanish_label(iso):
    # La app pinta country_es(); un codigo sin etiqueta saldria en blanco.
    assert country_es(iso)


def test_house_typos_stay_unmapped():
    # Erratas de la casa: no se adivinan.
    assert normalize_country("Guerrrero") is None
    assert normalize_country("Siglo XX") is None

"""Autor desde el texto alternativo de la imagen de Bogota ("Nombre País, año - año : Título").

El fallo que motivo estos tests: el grupo del pais admitia varias palabras en
mayuscula, asi que en "Fernando Botero Colombia, 1932" se comia el apellido y el
autor quedaba en "Fernando" (unos 150 lotes: La plegaria de Botero, Luis
Caballero, Juan Antonio Roda...). La regla se escribio para el formato pegado
("Fernando BoteroColombia"); Bogota publica tambien el formato con espacio.
"""
import pytest

from scraping.parsers import _parse_artist_from_alt


def _parse(alt: str) -> dict:
    result: dict = {}
    _parse_artist_from_alt(alt, result)
    return result


@pytest.mark.parametrize("alt, name, birth, death", [
    # Con espacio entre nombre y pais: el caso que estaba roto
    ("Fernando Botero Colombia, 1932 - Mónaco, 2023 : La plegaria", "Fernando Botero", 1932, 2023),
    ("Luis Caballero Colombia, 1943 - 1995 : Sin título", "Luis Caballero", 1943, 1995),
    ("Juan Antonio Roda España, 1921 - Colombia, 2003 : Sin título", "Juan Antonio Roda", 1921, 2003),
    ("Guillermo Wiedemann Alemania, 1905 - EE.UU., 1969 : Sin título", "Guillermo Wiedemann", 1905, 1969),
    # Pegado: el formato para el que se escribio la regla, que debe seguir funcionando
    ("Manuel HernándezColombia, 1928 - 2014 : Sin título", "Manuel Hernández", 1928, 2014),
    ("Juan Antonio RodaEspaña, 1921 - Colombia 2003 : Sin título", "Juan Antonio Roda", 1921, 2003),
    # Pais de dos palabras: aqui SI son dos, y no forman parte del nombre
    ("Domingo Izquierdo Puerto Rico, 1931 : Sin título", "Domingo Izquierdo", 1931, None),
    # Variantes de puntuacion reales
    ("Alejandro Obregón España 1920 - Colombia, 1992 : Boceto", "Alejandro Obregón", 1920, 1992),
    ("Nirma Zárate Colombia,1936-1999 : Sin título", "Nirma Zárate", 1936, 1999),
    ("José María Espinosa Colombia, 1796 -1883 : Retrato", "José María Espinosa", 1796, 1883),
    ("Jim Amaral EE.UU., 1933 : Esfera en sitio", "Jim Amaral", 1933, None),
    # Artista vivo: sin guion detras del nacimiento
    ("Fernando Botero Colombia, 1932 : Sin título", "Fernando Botero", 1932, None),
    # Biografia entre parentesis
    ("Manuel Hernández (Colombia, 1928 - 2014) : Sin título", "Manuel Hernández", 1928, 2014),
    # "EE. UU." con espacio: dos palabras de pais, no "Robert Motherwell EE."
    ("Robert Motherwell EE. UU., 1915 - 1991 : No 5 de la serie", "Robert Motherwell", 1915, 1991),
    # Coma en vez de guion entre nacimiento y muerte: el nacimiento es el PRIMER anio
    ("Pablo Picasso España, 1881, Francia, 1973 : Taureau", "Pablo Picasso", 1881, 1973),
    # Guion delante del pais
    ("John Castles - Colombia, 1946 - 2023 : Sin título", "John Castles", 1946, 2023),
])
def test_alt_artist_keeps_the_full_name(alt, name, birth, death):
    out = _parse(alt)
    assert out["artist_name"] == name
    assert out.get("artist_birth_year") == birth
    assert out.get("artist_death_year") == death


@pytest.mark.parametrize("alt", [
    "Argemiro Vélez Colombia, 19 - 1972 : Picasso, marca registrada",    # anio incompleto
    "Ricardo Acevedo Bernal Colombia, 19867 - Italia, 1930 : Puerto",     # errata de 5 cifras
])
def test_broken_years_set_nothing_rather_than_a_wrong_name(alt):
    # Con digitos sueltos delante del primer anio no hay frontera fiable entre
    # nombre y pais: mejor no tocar que dejar "Argemiro Vélez Colombia, 19".
    assert _parse(alt) == {}


def test_alt_without_years_sets_nothing():
    # Fichas de libro ("[Primera edición] Icaza, Jorge"): no hay pais ni anio que separar.
    assert _parse("[Primera edición] Icaza, Jorge : Huasipungo") == {}
    assert _parse("Fernando Botero sin separador de titulo") == {}


def test_alt_never_overrides_a_name_from_the_lot_page():
    result = {"artist_name": "Fernando Botero Angulo"}
    _parse_artist_from_alt("Fernando Botero Colombia, 1932 : Sin título", result)
    assert result["artist_name"] == "Fernando Botero Angulo"

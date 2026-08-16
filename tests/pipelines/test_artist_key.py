"""Tests de pipelines/shared/artist_key.py.

Cubren el bug que motivo el modulo (acentos borrados en vez de plegados) y las
reglas de clasificacion que, si se rompen, o parten un artista en varias filas
del ranking o cuelan escuelas y muebles como si fueran autores.
"""

import pytest

from pipelines.shared.artist_key import (
    ATTRIBUTION_TYPES,
    artist_fold,
    attribution_type,
    propose_inversion,
    strip_biography,
)


# --------------------------------------------------------------------------
# artist_fold: el bug de los acentos
# --------------------------------------------------------------------------

@pytest.mark.parametrize(
    "name,expected",
    [
        ("Joan Miró", "joan miro"),
        ("Álvaro Barrios", "alvaro barrios"),
        ("Antoni Tàpies", "antoni tapies"),
        ("Manuel Hernández", "manuel hernandez"),
        ("Agustín Úbeda", "agustin ubeda"),
    ],
)
def test_accents_are_folded_not_deleted(name, expected):
    """El acento pliega a su letra base; no se borra la letra entera.

    artist_canonicalize.py aplicaba re.sub(r"[^a-z0-9\\s]", "") despues de
    .lower() sin NFKD, asi que "Joan Miró" daba "joan mir" y "Álvaro Barrios"
    daba "lvaro barrios". Cada variante acentuada quedaba como un artista
    distinto del mismo nombre sin acentuar.
    """
    assert artist_fold(name) == expected


def test_case_and_punctuation_variants_collapse():
    """Las 4 grafias reales de Agustin Ubeda son un solo artista (368 lotes)."""
    variants = ["Agustín Úbeda", "Agustin Úbeda", "Agustín Ubeda", "Agustin Ubeda"]
    assert len({artist_fold(v) for v in variants}) == 1


@pytest.mark.parametrize(
    "variants",
    [
        ["Antoni Tàpies", "Antoni Tapies", "Antoni Tápies"],
        ["Luis García Ochoa", "Luis Garcia Ochoa", "Luis García-Ochoa", "Luis García ochoa"],
        ["Rafael Canogar", "Rafael canogar", "RAFAEL CANOGAR"],
        ["Álvaro Barrios", "Álvaro  Barrios"],  # doble espacio interno
    ],
)
def test_real_world_variant_groups_collapse_to_one_fold(variants):
    assert len({artist_fold(v) for v in variants}) == 1


def test_fold_is_idempotent():
    """Plegar un fold no lo cambia: garantiza que re-ejecutar no derive."""
    for name in ["Joan Miró", "GARCIA OCHOA, LUIS", "Escuela Española S. XVII"]:
        once = artist_fold(name)
        assert artist_fold(once) == once


@pytest.mark.parametrize("name", [None, "", "   ", "J", "*A", "s.a", "S."])
def test_fold_returns_none_when_there_is_no_usable_key(name):
    """Nunca devuelve cadena vacia: o hay clave o hay None."""
    assert artist_fold(name) is None


# --------------------------------------------------------------------------
# attribution_type
# --------------------------------------------------------------------------

@pytest.mark.parametrize(
    "name,expected",
    [
        # Escuelas: 504 nombres, 6.214 lotes. Con y sin acento, mayusculas y
        # minusculas: is_noise_artist necesitaba una entrada por variante.
        ("Escuela Española S. XVII", "escuela"),
        ("escuela flamenca", "escuela"),
        ("Escuela española, S", "escuela"),
        ("Taller de Pieter Coecke van Aelst", "taller"),
        ("Círculo de Rubens", "circulo"),
        ("Circulo de Rubens", "circulo"),  # sin acento: mismo resultado
        ("Seguidor de Murillo", "seguidor"),
        ("Maestro de las medias figuras", "seguidor"),
        ("Copia de Velázquez", "copia"),
        ("Atribuido a Goya", "atribuido"),
        ("Atrib. a Goya", "atribuido"),
        ("Anónimo", "anonimo"),
        ("ANONIMO", "anonimo"),
        ("VV.AA.", "anonimo"),
        ("Varios autores", "anonimo"),
        # Autores de verdad
        ("Fernando Botero", "autor"),
        ("Antoni Tàpies", "autor"),
        ("Olga de Amaral", "autor"),
        ("Julio Romero de Torres", "autor"),
        # Sin nombre utilizable
        ("", "desconocido"),
        ("   ", "desconocido"),
        (None, "desconocido"),
        # Basura que el scraper metio en artist_name
        ("J", "no_autor"),
        ("s.a", "no_autor"),
        ("Colonia: 10 obras", "no_autor"),
        ("11 Postales Transporte y Hoteles", "no_autor"),
    ],
)
def test_attribution_types(name, expected):
    assert attribution_type(name) == expected


def test_every_result_is_a_declared_type():
    """Nunca inventa una etiqueta fuera de ATTRIBUTION_TYPES."""
    samples = ["Fernando Botero", "Escuela Española", None, "", "J", "Anónimo"]
    assert all(attribution_type(s) in ATTRIBUTION_TYPES for s in samples)


@pytest.mark.parametrize(
    "name",
    [
        "Ever Astudillo (Colombia, 1948 - 2015)",
        "Jorge Ortiz (Colombia, 1948.)",
        "Edgar Negret - Colombia, 1920-2012.",
        "Eduardo Ramírez Villamizar (Colombia, 1922 - 2004)",
    ],
)
def test_inline_biography_is_not_no_autor(name):
    """Un autor con la biografia pegada al nombre sigue siendo autor.

    Protege el orden de las reglas: la biografia se recorta ANTES de mirar si
    hay digitos. Si se invirtiera, estos 552 nombres caerian en no_autor y
    perderiamos justo los que llevan el pais dentro del propio nombre.
    """
    assert attribution_type(name) == "autor"


def test_biography_is_stripped_from_the_name():
    assert strip_biography("Ever Astudillo (Colombia, 1948 - 2015)") == "Ever Astudillo"
    assert strip_biography("Edgar Negret - Colombia, 1920-2012.") == "Edgar Negret"
    assert strip_biography("Fernando Botero") == "Fernando Botero"


def test_long_paragraphs_are_not_authors():
    """430 nombres son parrafos enteros (titulos de libro, textos de cartel)."""
    parrafo = (
        "[Arquitecture] Zodiac international magazine of contemporary "
        "architecture, numeros varios encuadernados"
    )
    assert attribution_type(parrafo) == "no_autor"


# --------------------------------------------------------------------------
# propose_inversion: sugerencia, nunca regla automatica
# --------------------------------------------------------------------------

def test_inversion_matches_the_direct_form():
    """"GARCIA OCHOA, LUIS" propone el mismo fold que "Luis García Ochoa"."""
    assert propose_inversion("GARCIA OCHOA, LUIS") == artist_fold("Luis García Ochoa")


def test_inversion_is_not_applied_by_artist_fold():
    """El fold NO invierte por su cuenta.

    "García Márquez, Gabriel" (51 lotes) es un escritor en lotes de libros, no
    un pintor: fusionarlo automaticamente con un "Gabriel García Márquez"
    pintor seria un error irreparable. La inversion se propone y la revisa una
    persona.
    """
    assert artist_fold("García Márquez, Gabriel") != artist_fold("Gabriel García Márquez")


@pytest.mark.parametrize("name", [None, "", "Fernando Botero", "Quiroz, Fernando; Aguilar, José"])
def test_inversion_returns_none_when_not_applicable(name):
    assert propose_inversion(name) is None


# --------------------------------------------------------------------------
# Nombres que son el objeto o el titulo, no el autor
# --------------------------------------------------------------------------

@pytest.mark.parametrize(
    "name",
    [
        "Collar", "Cinturón", "Vestido", "Aretes", "Alfombra persa",
        "Mesa de centro", "Consola", "Florero",
        "Cartel", '"Paisaje"', '"Bodegón"', '"Composición"', "Sin título",
        '"Desnudo"', '"Marina"', "Fotografía",
    ],
)
def test_object_names_are_not_authors(name):
    """El scraper metio el tipo de objeto en artist_name: 467 lotes.

    Entraban en el ranking de artistas como autores, con "Cartel" (85 lotes)
    por delante de artistas reales.
    """
    assert attribution_type(name) == "no_autor"


@pytest.mark.parametrize(
    "name",
    [
        # Sus lotes son proclamas impresas, mapas y primeras ediciones: firman
        # el TEXTO, no una obra plastica. Bolivar salia en el ranking de
        # artistas con 19 lotes y "sin pais informado".
        "Bolívar, Simón",
        "[Bolívar, Simón]",
        "Santander, Francisco de Paula",
        "Restrepo, José Manuel",
        "Humboldt, Alexander von",
        "Bellin, Jacques Nicolas",
        "Acosta de Samper, Soledad",
    ],
)
def test_text_authors_are_not_visual_artists(name):
    assert attribution_type(name) == "no_autor"


@pytest.mark.parametrize(
    "name",
    [
        # Cumplen el MISMO patron "Autor : Titulo" en artist_raw y SI son
        # pintores. Son la razon de que el filtro sea una lista cerrada y no
        # una regla sobre el patron: una heuristica los borraria en silencio.
        "Antonio Caro",
        "Beatriz González",
        "Ana Mercedes Hoyos",
        "García Márquez, Gabriel",   # escritor, pero se deja entrar a proposito
    ],
)
def test_book_pattern_painters_survive(name):
    assert attribution_type(name) == "autor"


@pytest.mark.parametrize(
    "name",
    [
        "Manuel Rivera",          # apellido Rivera, no el objeto
        "Ana Marina Gómez",       # Marina como nombre propio
        "Carlos Prado",
        "Paisajes de Castilla, Juan Ruiz",
        "Mesa Bolívar, Carlos",   # Mesa como apellido
        "Simón Bolívar Restrepo",  # apellido Bolivar: NO es el Libertador
    ],
)
def test_real_names_containing_object_words_survive(name):
    """La comparacion es por igualdad con el fold entero, no por 'contiene'.

    Un 'in' aqui borraria a artistas reales apellidados Rivera, Marina o Mesa,
    que es exactamente el tipo de fallo silencioso que no se ve en el informe.
    """
    assert attribution_type(name) == "autor"


# --------------------------------------------------------------------------
# Campo "Ciudad" de la ficha bibliografica
# --------------------------------------------------------------------------

@pytest.mark.parametrize(
    "name",
    [
        "Ciudad Bogotá",
        "Ciudad Paris",
        "Ciudad Madrid",
        "Ciudad Nueva York",
        "Ciudad Santafé de Bogotá",
        # A veces arrastra la ficha entera detras.
        "Ciudad Bogotá Editorial Imprenta de la Luz Piezas 1 Tamaño Octavo",
        # Y a veces lleva el pais detras de una coma, como una persona.
        "Ciudad Bogotá, Colombia",
        "Ciudad Cádiz, España",
        "Ciudad Lausana, Suiza",
        "Ciudad España, París",
    ],
)
def test_city_field_is_not_an_author(name):
    """Bogota vende libros y el scraper metio el campo "Ciudad" en artist_name.

    Son 144 lotes en 28 variantes, y "Ciudad Bogotá" llegaba a ser el segundo
    "artista" con mas lotes de todo el dataset.
    """
    assert attribution_type(name) == "no_autor"


@pytest.mark.parametrize(
    "name",
    ["Ciudad Real, Antonio", "Ciudad Real, Manuel", "Juan Ciudad", "Ciudadano Kane"],
)
def test_city_rule_does_not_eat_real_names(name):
    """Ciudad Real es un apellido espaniol legitimo.

    Por eso la regla exige que no haya coma: la forma "Apellido, Nombre" delata
    a una persona. Un simple startswith("ciudad ") habria borrado a este autor.
    """
    assert attribution_type(name) == "autor"

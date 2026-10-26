"""Tests de los parsers de Morton Subastas (Ciudad de Mexico) via su web de pujas.

Las fixtures son paginas reales de live.mortonsubastas.com (plataforma Bidsquare),
recortadas: sin <script> salvo el JSON-LD, y los catalogos con 25 de sus lotes.
"""
import json
from pathlib import Path

import pytest

from scraping.common.models import AuctionMeta
from scraping.houses.morton_subastas.parsers import (
    _auction_id_from_url,
    artist_for_lot,
    artist_from_text,
    fix_mojibake,
    get_auction_start_date_from_page,
    get_auction_title_from_page,
    get_page_urls,
    is_art_auction,
    lot_title_for,
    mexico_city_iso,
    parse_auction_page,
    parse_historic_page,
    parse_lot_page,
)

FIXTURES = Path(__file__).parent / "fixtures"
EVENT_2024 = "https://live.mortonsubastas.com/en/auctions/morton-subastas/subasta-de-arte-latinoamericano-17078"
EVENT_2022 = "https://live.mortonsubastas.com/en/auctions/morton-subastas/subasta-de-obra-gr-fica-y-fotograf-a-9740"
EVENT_2021 = "https://live.mortonsubastas.com/en/auctions/morton-subastas/arte-moderno-y-contempor-neo-modern-and-contemporary-art-7312"


def _html(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def _meta(url: str, auction_id: str) -> AuctionMeta:
    return AuctionMeta(
        auction_id=auction_id,
        auction_title="x",
        auction_url=url,
        auction_house_name="Morton Subastas",
    )


# ---------------------------------------------------------------------------
# Identificadores y fechas
# ---------------------------------------------------------------------------

def test_auction_id_is_the_numeric_suffix():
    assert _auction_id_from_url(EVENT_2024) == "17078"
    assert _auction_id_from_url(EVENT_2024 + "/catalog?limit=120&page=2") == "17078"


def test_listing_date_is_converted_to_mexico_city_not_the_viewer_zone():
    # El listado pinta la hora en la zona de quien mira (aqui BST). La subasta de
    # Arte Mexicano fue el 24 de septiembre a las 18:00 en CDMX; leida tal cual
    # caeria el 25, y en un dia 31 cambiaria de MES (y de tasa de cambio).
    assert mexico_city_iso("Sep 25, 2026 01:00AM BST") == "2026-09-24T18:00:00-06:00"


def test_jsonld_dates_with_us_zone_abbreviations():
    # El JSON-LD de Bidsquare usa zonas de EE. UU.; CDMX tenia horario de verano
    # hasta 2022, asi que en 2021 su offset era -05:00.
    assert mexico_city_iso("2021-08-26 17:00:00 CDT") == "2021-08-26T17:00:00-05:00"
    assert mexico_city_iso("2026-08-27T20:00:00-04:00 EDT") == "2026-08-27T18:00:00-06:00"
    assert mexico_city_iso("2023-05-25 16:00:00 CST") == "2023-05-25T16:00:00-06:00"


def test_unknown_zone_returns_none_instead_of_guessing():
    assert mexico_city_iso("2026-08-27 20:00:00 XYZ") is None
    assert mexico_city_iso(None) is None


# ---------------------------------------------------------------------------
# Que subastas son de arte
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("title", [
    "Subasta de Arte Mexicano",
    "Subasta de Arte Moderno y Contemporáneo",
    "Subasta de Artistas Mexicanos",
    "Arte Latinoamericano | Latin American Art",
    "Subasta de Obra Gráfica y Fotografía",
    "Prints & Multiples Auction.",
    "Graphic Work and Photography Auction.",
    "Subasta Navideña de Pintura, Escultura y Obra Gráfica",
    "DISCRETAS OBRAS DE GRANDES MAESTROS | SOLO EN LÍNEA",
    "Subasta de Verano Ecos de la Ruptura | Summer Auction Echoes of Rupture",
])
def test_art_auctions_are_kept(title):
    assert is_art_auction(title)


@pytest.mark.parametrize("title", [
    "Subasta de los Sábados 1357",
    "Subasta de Flotilla Vehicular Bimbo Irapuato",
    "Subasta de Vinos y Destilados",
    "Subasta de Antigüedades y Libros",
    "Subasta de Joyería y Relojes",
    # "Arte" en el titulo no basta: son artes decorativas, vino, una venta a
    # precio fijo y libros.
    "Subasta de Artes Decorativas | Explora el Arte Pop",
    "Arte y Vid: encuentro de dos pasiones",
    "Venta directa | Rufino Tamayo",
    "Subasta de Fotografía y Libros",
    "Subasta de Antigüedades y Libros. Grandes pinceles del viejo y nuevo mundo.",
])
def test_non_art_auctions_are_skipped(title):
    assert not is_art_auction(title)


def test_art_rule_over_every_past_auction():
    # Los 803 titulos reales del historico (2020-03 -> 2026-10). Si este numero
    # cambia, alguien toco la regla: revisar que entra y que sale.
    titles = json.loads(_html("past_titles.json"))
    assert len(titles) == 803
    assert sum(is_art_auction(t) for t in titles) == 57


def test_parse_historic_page_reads_every_auction_with_its_mexico_date():
    auctions = parse_historic_page(_html("past_auctions_p1.html"))
    assert len(auctions) == 24
    arte = next(a for a in auctions if a.auction_id == "24790")
    assert arte.auction_title == "Subasta de Arte Mexicano"
    assert arte.auction_url.endswith("/subasta-de-arte-mexicano-24790")
    assert arte.auction_start_date.startswith("2026-09-24")
    assert arte.auction_house_name == "Morton Subastas"


# ---------------------------------------------------------------------------
# Pagina de subasta (catalogo)
# ---------------------------------------------------------------------------

def test_title_and_start_date_come_from_the_event_jsonld():
    html = _html("catalog_2024_visible_prices.html")
    assert get_auction_title_from_page(html) == "Subasta de Arte Latinoamericano"
    assert get_auction_start_date_from_page(html) == "2024-11-27T17:00:00-06:00"


def test_page_urls_cover_every_lot_at_120_per_page():
    # Una pagina fuera de rango devuelve la ultima otra vez (no una vacia), asi
    # que el numero de paginas sale del total, no de "hasta que no haya lotes".
    urls = get_page_urls(_html("catalog_2024_visible_prices.html"), EVENT_2024)
    assert urls == [f"{EVENT_2024}/catalog?limit=120&page={n}" for n in (1, 2)]
    assert len(get_page_urls(_html("catalog_2022_login_mojibake.html"), EVENT_2022)) == 3


def test_catalog_with_visible_prices():
    previews = parse_auction_page(_html("catalog_2024_visible_prices.html"), _meta(EVENT_2024, "17078"))
    assert len(previews) == 25
    first = previews[0]
    assert first["lot_number"] == 1
    assert first["lot_url"].endswith("-6769914")
    assert first["lot_title"].startswith("FRANCISCO TOLEDO. Torete rayado")
    assert first["artist_name"] == "Francisco Toledo"
    assert (first["price_estimate_min"], first["price_estimate_max"]) == (180000, 250000)
    assert (first["status"], first["price_sold"]) == ("VENDIDO", 210000)
    assert first["image_url"].startswith("https://s1.img.bidsquare.com/item/l/2821/28217982.jpeg")
    third = previews[2]
    assert (third["status"], third["price_sold"]) == ("NO VENDIDO", None)


def test_catalog_behind_login_leaves_price_and_status_to_the_lot_page():
    # Antes de 2024 la tarjeta dice "Login for Price": no hay precio ni estado
    # que leer, y NO se debe inferir "no vendido" de esa ausencia.
    previews = parse_auction_page(_html("catalog_2022_login_mojibake.html"), _meta(EVENT_2022, "9740"))
    assert len(previews) == 25
    assert all(p["price_sold"] is None and p["status"] is None for p in previews)
    assert previews[0]["price_estimate_min"] == 55000


def test_catalog_mojibake_is_repaired():
    previews = parse_auction_page(_html("catalog_2022_login_mojibake.html"), _meta(EVENT_2022, "9740"))
    assert previews[0]["lot_title"].startswith("SERGIO HERNÁNDEZ, Sin título, Firmado, Grabado")
    assert previews[0]["artist_name"] == "Sergio Hernández"


def test_bilingual_titles_keep_only_the_spanish_half():
    previews = parse_auction_page(_html("catalog_2021_bilingual.html"), _meta(EVENT_2021, "7312"))
    assert previews[0]["lot_title"] == (
        "TRINIDAD OSORIO, Sin título, Firmado, Lápices de color sobre papel, 42 x 32 cm"
    )
    assert previews[0]["artist_name"] == "Trinidad Osorio"


# ---------------------------------------------------------------------------
# Ficha del lote (JSON-LD Product)
# ---------------------------------------------------------------------------

def test_sold_lot_page():
    detail = parse_lot_page(_html("lot_2026_sold.html"))
    assert (detail["status"], detail["price_sold"]) == ("VENDIDO", 18000)
    assert detail["lot_number"] == 2
    assert detail["artist_name"] == "Julio Le Parc"
    assert (detail["artist_birth_year"], detail["artist_death_year"]) == (1928, 2026)
    assert detail["artist_country"] == "Argentina"
    assert "Denise René" in detail["description"]


def test_unsold_lot_price_is_the_opening_bid_and_is_never_a_sale():
    # TRAMPA: el JSON-LD de un lote no vendido ("Discontinued") TAMBIEN trae
    # precio: 120.000 con estimacion 130.000-250.000. Es la salida, siempre por
    # debajo de la estimacion baja (20 de 20 lotes comparados con su etiqueta
    # visible). Contarlo como venta inflaria la recaudacion.
    detail = parse_lot_page(_html("lot_2023_unsold_with_price.html"))
    assert detail["status"] == "NO VENDIDO"
    assert detail["price_sold"] is None


def test_lot_page_behind_login_still_has_the_hammer_price_in_jsonld():
    detail = parse_lot_page(_html("lot_2021_sold_bilingual.html"))
    assert (detail["status"], detail["price_sold"]) == ("VENDIDO", 48000)
    assert detail["lot_title"] == (
        "JORGE ALZAGA, Frutero, Firmado y fechado 91, Óleo y arena sobre tela, 80 x 100 cm"
    )


def test_mexican_birthplace_is_city_and_state_so_country_is_mexico():
    # Morton escribe "(Ciudad, Estado, anio - ...)" para los mexicanos y pone el
    # pais solo a los extranjeros.
    alzaga = parse_lot_page(_html("lot_2021_sold_bilingual.html"))
    assert alzaga["artist_name"] == "Jorge Alzaga"
    assert (alzaga["artist_birth_year"], alzaga["artist_death_year"]) == (1938, 2010)
    assert alzaga["artist_country"] == "México"
    coronel = parse_lot_page(_html("lot_2023_unsold_with_price.html"))
    assert coronel["artist_name"] == "Pedro Coronel"
    assert coronel["artist_country"] == "México"


def test_foreign_artist_keeps_the_house_country_text():
    warhol = parse_lot_page(_html("lot_2023_foreign_artist.html"))
    assert warhol["artist_name"] == "Andy Warhol"
    assert (warhol["artist_birth_year"], warhol["artist_death_year"]) == (1928, 1987)
    assert warhol["artist_country"] == "EE. UU."


# ---------------------------------------------------------------------------
# Artista desde el texto del lote
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("text, name", [
    ("FRANCISCO TOLEDO. Aves, de la serie Zoología fantástica.", "Francisco Toledo"),
    ("PEDRO FRIEDEBERG . Memento mori. Firmado.", "Pedro Friedeberg"),
    ("MATHIAS GOERITZ , Estrella, ca.1973", "Mathias Goeritz"),
    ("JOSÉ BRIBIESCA JR. Abanderada en desfile. Firmado.", "José Bribiesca Jr."),
    ("M. C. ESCHER. Relatividad. Litografía.", "M. C. Escher"),
    ("FERNANDO DE SZYSZLO. Sin título. Firmada.", "Fernando de Szyszlo"),
    ("PABLO O'HIGGINS, Sin título, Firmada y fechada 64", "Pablo O'Higgins"),
    ("ALBERTO DURERO. Saint Simon, 1523.", "Alberto Durero"),
])
def test_artist_is_the_uppercase_lead(text, name):
    assert artist_from_text(text)["artist_name"] == name


def test_lowercase_lead_is_not_an_artist():
    # La convencion de la casa es el autor en MAYUSCULAS; una descripcion que
    # empieza en minusculas es un objeto o un lote sin autor.
    assert artist_from_text("Lote de tres grabados. Sin firma.") == {}
    assert artist_from_text("") == {}


def test_inline_biography_gives_years_and_country():
    out = artist_from_text(
        "ANA MERCEDES HOYOS (Bogotá, Colombia, 1942 - Bogotá, Colombia, 2014), Sandía, 1991"
    )
    assert out["artist_name"] == "Ana Mercedes Hoyos"
    assert (out["artist_birth_year"], out["artist_death_year"]) == (1942, 2014)
    assert out["artist_country"] == "Colombia"


@pytest.mark.parametrize("bio", [
    "(Chilpancingo Guerrero, 1950 - )",     # sin coma antes del estado
    "(Chilapa, Guerrero., 1950 - )",        # punto suelto tras el estado
    "(Victoria de Durango, 1920 - 1990)",   # capital escrita sola, acaba en el estado
    "(Oaxaca de Juárez, 1950 - )",          # capital escrita sola
])
def test_mexican_birthplaces_written_loosely(bio):
    assert artist_from_text(f"JUAN PÉREZ {bio}, Sin título")["artist_country"] == "México"


def test_new_mexico_is_not_mexico():
    out = artist_from_text("JOHN DOE (Santa Fe, Nuevo México, 1940 - ), Sin título")
    assert out["artist_country"] == "Nuevo México"  # la tabla de paises lo lleva a US


def test_century_is_not_a_birthplace():
    out = artist_from_text("ESCUELA MEXICANA (Siglo XX), Sin título")
    assert "artist_country" not in out
    assert "artist_birth_year" not in out


def test_dash_glued_between_year_and_place():
    out = artist_from_text("JUAN PÉREZ (Ciudad de México, 1932-Ciudad de México, 2010), Sin título")
    assert (out["artist_birth_year"], out["artist_death_year"]) == (1932, 2010)
    assert out["artist_country"] == "México"


def test_html_entities_in_the_jsonld_are_decoded():
    # 251 descripciones de la primera corrida traian "M&eacute;xico" y
    # "&Oacute;leo": el JSON-LD a veces lleva entidades HTML escapadas dentro.
    html = (
        '<script type="application/ld+json">{"@type": "Product", '
        '"name": "RAFAEL CORONEL, Sin t&iacute;tulo, &Oacute;leo sobre tela", '
        '"description": "RAFAEL CORONEL\\n(Zacatecas, Zacatecas, 1932 - Ciudad de M&eacute;xico, 2019)'
        '\\nSin t&iacute;tulo\\n&Oacute;leo sobre tela", '
        '"offers": {"availability": "SoldOut", "price": 1000}}</script>'
    )
    detail = parse_lot_page(html)
    assert detail["lot_title"] == "RAFAEL CORONEL, Sin título, Óleo sobre tela"
    assert "Ciudad de México, 2019" in detail["description"]
    assert "Óleo sobre tela" in detail["description"]
    assert detail["artist_raw"] == "RAFAEL CORONEL (Zacatecas, Zacatecas, 1932 - Ciudad de México, 2019)"


@pytest.mark.parametrize("text, name", [
    # Seudonimos con tratamiento: el punto de "DR." no cierra el nombre
    ("DR. LAKRA, Sin título (llantas), 2004, Firmada", "Dr. Lakra"),
    ("DR. ATL. Popocatépetl. Sin firma.", "Dr. Atl"),
    ("MR. BRAINWASH, Art is not a crime - hard candy, Firmada", "Mr. Brainwash"),
    # Prefijos de la ficha delante del autor
    ("Diseñado por FRANCISCO TOLEDO (Juchitán, Oaxaca, 1940 - Oaxaca, Oaxaca, 2019), Papalote", "Francisco Toledo"),
    ("Firmada HERARI. Sin título. Firmada y fechada 1974.", "Herari"),
    (", LUIS NISHIZAWA, Sin título, Firmado y fechado 92", "Luis Nishizawa"),
    # Un apodo entre comillas no es parte del nombre
    ('GERARDO MURILLO "DR. ATL" (Guadalajara, Jalisco, 1875 - Ciudad de México, 1964)', "Gerardo Murillo"),
])
def test_artist_lead_variants(text, name):
    assert artist_from_text(text)["artist_name"] == name


@pytest.mark.parametrize("text, name", [
    # El apodo en MEDIO del nombre se salta y el nombre sigue: cortar en la
    # comilla dejaba "Georgina", "Ernesto" o "José" como artistas.
    ('GEORGINA "GOGY" FARÍAS (Ciudad de México, 1943 - ), Sin título', "Georgina Farías"),
    ('ERNESTO "EL CHANGO" GARCÍA CABRAL, Caricatura', "Ernesto García Cabral"),
    ('JOSÉ J. "SHALOM" ALMANZOR. Sin título.', "José J. Almanzor"),
    # Al final, se descarta y cierra el nombre
    ('ENRIQUE CARBAJAL "SEBASTIÁN", Escultura en acero', "Enrique Carbajal"),
])
def test_quoted_nickname_is_skipped_wherever_it_is(text, name):
    assert artist_from_text(text)["artist_name"] == name


def test_nickname_in_the_middle_keeps_the_biography():
    out = artist_from_text('GEORGINA "GOGY" FARÍAS (Ciudad de México, 1943 - ), Sin título')
    assert (out["artist_birth_year"], out["artist_country"]) == (1943, "México")


@pytest.mark.parametrize("text, name", [
    # Separador pegado a lo siguiente: el nombre se cortaba en "Javier" y
    # "Fernando", y "Javier" llego al puesto 105 del ranking como artista.
    ("JAVIER MARÍN,Torso de mujer,Firmada y fechada 04", "Javier Marín"),
    ("FERNANDO PENHOS,31/August/1939 Austria,Firmada frente y reverso", "Fernando Penhos"),
    ('ENRIQUE CARBAJAL "SEBASTIAN".Sin título. Firmada.', "Enrique Carbajal"),
    ("DE LAYSECA,Santa María,Sin firma", "De Layseca"),
])
def test_separator_glued_to_the_next_word(text, name):
    assert artist_from_text(text)["artist_name"] == name


def test_quoted_alias_does_not_hide_the_biography():
    out = artist_from_text('GERARDO MURILLO "DR. ATL" (Guadalajara, Jalisco, 1875 - Ciudad de México, 1964)')
    assert (out["artist_birth_year"], out["artist_death_year"]) == (1875, 1964)


def test_pseudonym_in_title_gets_the_biography_of_its_real_name():
    # Titulo "DR. ATL", descripcion 'GERARDO MURILLO "DR. ATL"': misma persona.
    out = artist_for_lot(
        "DR. ATL. Popocatépetl. Sin firma. Óleo sobre papel.",
        'GERARDO MURILLO "DR. ATL"\n(Guadalajara, Jalisco, 1875 - Ciudad de México, 1964)\nPopocatépetl',
    )
    assert out["artist_name"] == "Dr. Atl"
    assert (out["artist_birth_year"], out["artist_country"]) == (1875, "México")


def test_description_without_biography_does_not_erase_the_title_one():
    # 2021: titulo con biografia, descripcion en ingles sin ella. La descripcion
    # solo puede anadir anios, nunca borrar los que trae el titulo.
    out = artist_for_lot(
        "GABRIEL OROZCO (Jalapa, Veracruz, 1962 - ), Sin título, Firmado",
        "GABRIEL OROZCO, Untitled, Signed and dated 1990, Acrylic",
    )
    assert (out["artist_name"], out["artist_birth_year"], out["artist_country"]) == ("Gabriel Orozco", 1962, "México")


def test_collective_portfolio_is_not_given_to_its_first_artist():
    # La descripcion empieza por el primero de los cinco grabadores; atribuirle
    # la carpeta entera seria inventar autoria. "Varios autores" lo marca
    # attribution_type como anonimo.
    out = artist_for_lot(
        "Varios autores, Cinco Grabadores de San Carlos, Firmados, Grabados",
        "GILBERTO ACEVES NAVARRO\n(Ciudad de México, 1931 - Ciudad de México, 2019)\nCinco Grabadores",
    )
    assert out["artist_name"] == "Varios Autores"


def test_vehicle_title_from_a_recycled_record_is_rebuilt_from_the_description():
    # Subasta 20912 (Arte Latinoamericano, 2025-11): 51 lotes heredaron el
    # titulo de un lote de flotilla ("Camioneta Chevrolet Tornado 2009", hasta en
    # la URL), pero descripcion, precio y estimacion son de la obra.
    description = (
        "ANGELINA BELOFF\n(San Petersburgo, Rusia, 1883 - Ciudad de México, 1969)\nSin título\n"
        "Firmado y fechado 54\nÓleo sobre tela\nCon etiqueta del Instituto Nacional de Bellas Artes."
    )
    assert lot_title_for("Camioneta Chevrolet Tornado 2009", description) == (
        "ANGELINA BELOFF. Sin título. Firmado y fechado 54. Óleo sobre tela"
    )
    # Un titulo con autor se respeta tal cual.
    assert lot_title_for("DR. ATL. Popocatépetl.", description) == "DR. ATL. Popocatépetl."


def test_impossible_year_is_dropped_not_kept():
    # Errata real de la casa: "1055" por 1955. Mejor sin anio que con uno falso.
    out = artist_from_text("ELISEO GARZA AGUILAR (Ciudad de México, 1055 - ), Los tres")
    assert out["artist_name"] == "Eliseo Garza Aguilar"
    assert "artist_birth_year" not in out
    assert out["artist_country"] == "México"


# ---------------------------------------------------------------------------
# Mojibake
# ---------------------------------------------------------------------------

def test_fix_mojibake_single_and_double_encoding():
    assert fix_mojibake("Sin tÃ­tulo") == "Sin título"
    # "Á" doble-codificada lleva un \x81 invisible: 0x81 no existe en cp1252 y el
    # decode original lo dejo como caracter de control.
    assert fix_mojibake("SERGIO HERNÃƒÂ\x81NDEZ") == "SERGIO HERNÁNDEZ"
    assert fix_mojibake("Ãƒâ€œleo") == "Óleo"


def test_fix_mojibake_leaves_correct_text_alone():
    # En un mismo catalogo conviven titulos rotos y sanos: un texto bueno no se
    # toca, ni siquiera cuando trae "Ã" de verdad (portugues) o un espacio duro.
    assert fix_mojibake("JAVIER ARÉVALO, Mujer") == "JAVIER ARÉVALO, Mujer"
    assert fix_mojibake("SÃO PAULO") == "SÃO PAULO"
    assert fix_mojibake("Óleo\xa0sobre tela, 50°") == "Óleo\xa0sobre tela, 50°"
    assert fix_mojibake("JAVIER ARÉVALO, Sin tÃ­tulo") == "JAVIER ARÉVALO, Sin título"

"""Solo hay artista si hay parentesis biografico.

Lefebre es una casa GENERALISTA: vende arte, pero tambien joyeria, relojes,
mobiliario y vinilos. Con la heuristica "la primera linea es el artista" salen
artistas inventados ('Solitario de Diamante', 'DURA DURAN', 'Anillo Tiffany's
en oro blanco') exactamente igual que los 'Cartel'/'Collar'/'Florero' que
_OBJECT_NAMES filtra para Bogota.

La regla no es nueva: es la que el curador aplico a mano en el Excel de 2024.
Medido lote a lote sobre las 11 subastas antiguas: el 93,4% de lo que guardo
tiene parentesis biografico, frente al 0,9% de lo que descarto. Aqui el no-arte
si entra (para conservar la facturacion real de la casa), pero SIN artista.
"""
from pathlib import Path

from scraping.houses.lefebre_subastas.parsers import artist_from_title, parse_auction_page

FIXTURES = Path(__file__).parent / "fixtures"


def test_artista_con_fechas_completas():
    nombre, nacimiento, muerte = artist_from_title(
        "BERNARDO SALCEDO (1939-2007)\nCollage 66\nCollage sobre papel"
    )
    assert nombre == "BERNARDO SALCEDO"
    assert (nacimiento, muerte) == (1939, 2007)


def test_artista_vivo_sin_ano_de_muerte():
    nombre, nacimiento, muerte = artist_from_title("DAVID MANZUR (1929)\nS/T, 1957")
    assert nombre == "DAVID MANZUR"
    assert (nacimiento, muerte) == (1929, None)

    nombre, nacimiento, muerte = artist_from_title("LYDIA AZOUT (1942-)\nPunto de atraccion")
    assert nombre == "LYDIA AZOUT"
    assert (nacimiento, muerte) == (1942, None)


def test_joyeria_no_produce_artista():
    for titulo in [
        "Solitario de Diamante\nAnillo de diamante central redonde talla antigua",
        "Anillo Tiffany's en oro blanco\nOro amarillo de 18 ct.",
        "ANILLO EN PLATINUM STERLING CON ESMERALDAS",
        "Reloj Cartier de hombre Ronde\nSolo 3603",
    ]:
        assert artist_from_title(titulo) == (None, None, None), titulo


def test_vinilos_no_producen_artista():
    """Los discos llevan el nombre del grupo delante y colarian como pintores."""
    assert artist_from_title("DURA DURAN\nDuran Duran, 1983\nCapitol Records, USA") == (None, None, None)
    assert artist_from_title("MADONNA\nLike a prayer, 1989\nSire, Warner Bros, USA") == (None, None, None)


def test_mobiliario_no_produce_artista():
    assert artist_from_title("Espejo en madera tallada y dorada, S.XX\nMedidas: 208 x 90 cm") == (None, None, None)
    assert artist_from_title("Vajila Rosenthal Gianni Versace, S.XX\n72 piezas") == (None, None, None)


def test_el_lote_sin_artista_entra_igualmente():
    """No se descarta: solo se queda sin artista. Se conserva la facturacion."""
    previews = parse_auction_page((FIXTURES / "ajax_lots_page2.json").read_text(encoding="utf-8"))
    sin_artista = [p for p in previews if p["artist_name"] is None]
    assert sin_artista, "la fixture deberia traer algun lote sin parentesis biografico"
    for preview in sin_artista:
        assert preview["lot_url"]           # entra al pipeline
        assert preview["description"]       # y conserva el bloque crudo


def test_no_se_inventa_el_pais():
    """artist_country se queda a None: el pais lo fija el maestro de artistas,
    nunca el texto libre de la casa ni el pais de la sede."""
    previews = parse_auction_page((FIXTURES / "ajax_lots_page1.json").read_text(encoding="utf-8"))
    assert all(p["artist_country"] is None for p in previews)

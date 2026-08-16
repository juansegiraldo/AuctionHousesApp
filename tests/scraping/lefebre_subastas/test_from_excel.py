"""Tests del conversor Excel -> JSONL de Lefebre.

Cada caso corresponde a una trampa real de la hoja FINAL, no a un invento.
"""

from __future__ import annotations

import json

import pytest

from pipelines.shared.schema import extract_year, is_sold, normalize_lot
from scraping.common.models import LotItem
from scraping.houses.lefebre_subastas.from_excel import (
    _to_int,
    build_lot,
    main,
    normalize_date,
    read_rows,
    real_lot_numbers,
    slugify,
    split_title,
)


def _lots(excel_path):
    """Convierte el fixture y devuelve los LotItem ya construidos."""
    rows = read_rows(excel_path)
    by_auction = {}
    for row in rows:
        by_auction.setdefault(row["auction_name"], []).append(row)
    out = []
    for auction_name, auction_rows in by_auction.items():
        slug = slugify(auction_name)
        use_number = real_lot_numbers(auction_rows)
        out.extend(build_lot(r, slug, use_number) for r in auction_rows)
    return out


def test_solo_lefebre(excel_path):
    """Las filas de Bogota se descartan: ya entran por su propio scraper."""
    rows = read_rows(excel_path)
    assert len(rows) == 6
    assert all("Warhol" not in (r["title_raw"] or "") for r in rows)


def test_pasado_y_cero_son_lo_mismo(excel_path):
    """'Pasado' (subastas viejas) y 0 (nuevas) = NO vendido, las dos.

    Es la trampa que mas facil se rompe: son dos convenciones distintas para el
    mismo hecho, y confundirlas invertiria la tasa de venta de la casa.
    """
    lots = {lot.lot_url: lot for lot in _lots(excel_path)}

    cero = lots["https://auction.lefebresubastas.com//lots/view/3"]
    assert cero.price_sold is None
    assert cero.status == "NO VENDIDO"

    pasado = [lot for lot in lots.values() if lot.auction_id == "subasta-18"]
    assert all(lot.price_sold is None for lot in pasado)
    assert all(lot.status == "NO VENDIDO" for lot in pasado)

    # Y el estado explicito manda sobre 'tiene precio' en is_sold().
    assert is_sold(cero.status, cero.price_sold) is False
    vendido = lots["https://auction.lefebresubastas.com//lots/view/1"]
    assert vendido.price_sold == 2000000  # exacto: ni x10 ni redondeado
    assert vendido.price_estimate_min == 1000000
    assert is_sold(vendido.status, vendido.price_sold) is True


def test_lot_url_real_o_sintetica(excel_path):
    """Con URL se conserva la real; sin URL se fabrica una estable."""
    lots = _lots(excel_path)
    reales = [lot for lot in lots if lot.lot_url.startswith("https://")]
    sinteticas = [lot for lot in lots if lot.lot_url.startswith("excel://")]
    assert len(reales) == 3
    assert len(sinteticas) == 3
    assert "excel://lefebre_subastas/subasta-18/4968" in {lot.lot_url for lot in sinteticas}


def test_lot_url_unica_no_pierde_lotes(excel_path):
    """Silver deduplica por house|lot_url: una colision perderia lotes."""
    lots = _lots(excel_path)
    keys = [normalize_lot(lot.model_dump(), "lefebre_subastas", "x")["dedupe_key"] for lot in lots]
    assert len(keys) == len(set(keys)) == 6


def test_titulos_duplicados_son_lotes_distintos(excel_path):
    """Mismo artista y titulo, Order distinto: son dos obras, no un duplicado."""
    ruiz = [lot for lot in _lots(excel_path) if lot.artist_name == "PEDRO RUIZ"]
    assert len(ruiz) == 2
    assert ruiz[0].lot_url != ruiz[1].lot_url


def test_lot_number_solo_si_es_real(excel_path):
    """En las subastas viejas 'Order' es el nº de fila, no el nº de lote.

    Volcarlo fabricaria huecos de secuencia que build_gold.py leeria como lotes
    ausentes, disparando un aviso de sesgo de tasa de venta inventado.
    """
    lots = _lots(excel_path)
    nuevas = [lot for lot in lots if lot.auction_id == "subastas-29"]
    viejas = [lot for lot in lots if lot.auction_id == "subasta-18"]
    assert sorted(lot.lot_number for lot in nuevas) == [1, 2, 3]
    assert all(lot.lot_number is None for lot in viejas)


@pytest.mark.parametrize(
    "raw,expected",
    [
        # openpyxl devuelve las celdas numericas como float: si el punto decimal
        # se tratara como separador de millar, todo saldria multiplicado por 10
        # (1.0 -> 10, y 1250000.0 -> 12500000 en los precios).
        (1.0, 1),
        (194.0, 194),
        (1250000.0, 1250000),
        (4968, 4968),
        # En cadena, el punto y la coma SI son separadores de millar.
        ("1.200.000", 1200000),
        ("2,500,000", 2500000),
        ("COP$8,000,000", 8000000),
        ("Pasado", None),
        ("Pendiente", None),
        (None, None),
    ],
)
def test_to_int(raw, expected):
    assert _to_int(raw) == expected


def test_precios_no_se_multiplican_por_diez(excel_path):
    """Los importes salen exactos de la celda, sin x10.

    openpyxl devuelve las celdas numericas como float. Si el valor se convierte
    a texto antes de parsearlo ('2000000.0'), el punto decimal se lee como
    separador de millar y el importe queda multiplicado por 10. Este test fija
    la suma total, que es la cifra que acaba en el informe.
    """
    lots = _lots(excel_path)
    assert sum(lot.price_sold or 0 for lot in lots) == 4000000
    assert sum(lot.price_estimate_min or 0 for lot in lots) == 5500000


def test_real_lot_numbers_detecta_la_diferencia():
    assert real_lot_numbers([{"order": 1}, {"order": 2}, {"order": 3}]) is True
    assert real_lot_numbers([{"order": 4086}, {"order": 5034}]) is False
    assert real_lot_numbers([{"order": None}]) is False


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("13/03/2024", "2024-03-13"),          # texto dd/mm/YYYY
        ("2024-12-06 00:00:00", "2024-12-06"),  # ya ISO
        ("no es fecha", None),
        (None, None),
    ],
)
def test_normalize_date(raw, expected):
    assert normalize_date(raw) == expected


def test_fechas_dan_anio_leido_no_inferido(excel_path):
    """ISO hace que extract_year() diga 'iso' y no 'text'.

    Si el anio saliera inferido, el informe lo marcaria como tal sin motivo.
    """
    for lot in _lots(excel_path):
        year, method = extract_year(lot.auction_start_date, lot.auction_id)
        assert method == "iso"
        assert year in {"2024", "2021"}


def test_moneda_siempre_cop(excel_path):
    """Nunca sumar precios entre casas: el informe convierte via fx.yaml."""
    assert {lot.currency for lot in _lots(excel_path)} == {"COP"}


def test_pendiente_no_es_cero(excel_path):
    """'Pendiente' en el precio de salida es 'sin dato', no 0."""
    anon = [lot for lot in _lots(excel_path) if lot.artist_name is None][0]
    assert anon.price_estimate_min is None
    assert anon.price_sold is None


def test_centinelas_no_pasan_como_pais(excel_path):
    """'#N/D' es un error de formula de Excel, no un pais."""
    anon = [lot for lot in _lots(excel_path) if lot.artist_name is None][0]
    assert anon.artist_country is None


def test_pais_es_solo_diagnostico(excel_path):
    """El pais del Excel va a artist_country, nunca fija el pais del artista.

    La regla del repo: el pais sale solo del maestro. Aqui solo alimenta el
    contador de unmapped_country_values y el de conflictos.
    """
    lot = [lot for lot in _lots(excel_path) if lot.artist_name == "ARTISTA 1"][0]
    assert lot.artist_country == "Colombia"
    assert "artist_country_birth" not in lot.model_dump()


def test_vive_no_es_anio_de_muerte(excel_path):
    ruiz = [lot for lot in _lots(excel_path) if lot.artist_name == "PEDRO RUIZ"][0]
    assert ruiz.artist_birth_year == 1957
    assert ruiz.artist_death_year is None


def test_split_title():
    titulo, tecnica, medidas = split_title(
        "AARON BOHROD (1907-1992)\nAlrededores de Chicago, sf.\n"
        "Óleo sobre masonite\nMedidas: 70 x 120 cm"
    )
    assert titulo == "Alrededores de Chicago, sf."
    assert tecnica == "Óleo sobre masonite"
    assert medidas == "70 x 120 cm"


@pytest.mark.parametrize(
    "raw,titulo,tecnica",
    [
        # Las 4 subastas nuevas (678 lotes) traen el bloque con ESPACIOS en vez
        # de saltos de linea. Partir solo por lineas las dejaba sin titulo y
        # hundia la cobertura al 60%.
        (
            "SAUL ORDUZ (1922-2010) Vista aérea de Bogotá, sf. Fotografía  "
            "Medidas: 73.5 x 73.5 cm",
            "Vista aérea de Bogotá, sf.",
            "Fotografía",
        ),
        # Sin separacion ninguna entre titulo y tecnica.
        (
            "LUCIANO JARAMILLO (1955-1992)S/T, 1974Técnica mixta sobre papel"
            "Medidas: 47 x 49 cm",
            "S/T, 1974",
            "Técnica mixta sobre papel",
        ),
        # La edicion ('Ed. 44 /50') no debe colarse en las medidas.
        (
            "ANA MERCEDES HOYOS (1942-2014)  S/T , sf.  Obra gráfica  "
            "Medidas: 71 x 50 cm  Ed. 44 /50",
            "S/T , sf.",
            "Obra gráfica",
        ),
    ],
)
def test_split_title_formato_con_espacios(raw, titulo, tecnica):
    got_titulo, got_tecnica, _ = split_title(raw)
    assert got_titulo == titulo
    assert got_tecnica == tecnica


def test_split_title_no_corta_si_no_hay_marca():
    """Sin parentesis biografico no se adivina donde acaba el nombre.

    Se prefiere devolver el texto entero antes que cortar por donde no toca:
    el nombre limpio ya viene aparte en Artista_Clean.
    """
    titulo, tecnica, medidas = split_title(
        "ANA ROLDAN JARAMILLO Tránsito, 1999 Obra gráfica Medidas: 50 x 35 cm"
    )
    assert titulo == "ANA ROLDAN JARAMILLO Tránsito, 1999"
    assert tecnica == "Obra gráfica"
    assert medidas == "50 x 35 cm"


def test_slugify():
    assert slugify("Subasta Barranquilla") == "subasta-barranquilla"
    assert slugify("Subastas 29") == "subastas-29"


def test_main_escribe_jsonl_por_subasta(excel_path, tmp_path, monkeypatch, capsys):
    """El JSONL de salida tiene las 27 claves de LotItem que Gold lee con .get().

    Construir el lote con el modelo (y no con un dict a mano) es lo que garantiza
    que las claves sin dato salgan como null en vez de faltar.
    """
    out = tmp_path / "output"
    monkeypatch.setattr(
        "sys.argv",
        ["from_excel", "--excel", str(excel_path), "--output-dir", str(out)],
    )
    main()

    files = sorted(p.name for p in out.glob("*.jsonl"))
    assert files == ["subasta-18.jsonl", "subastas-29.jsonl"]

    records = [json.loads(line) for line in (out / "subastas-29.jsonl").read_text(
        encoding="utf-8").splitlines()]
    assert len(records) == 3
    assert len(records[0]) == len(LotItem.model_fields) == 27
    assert records[0]["auction_house_name"] == "Lefebre Subastas"
    assert records[0]["currency"] == "COP"

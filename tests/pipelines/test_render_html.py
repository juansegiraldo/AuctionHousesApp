"""Tests de la app del informe (build_artifact.py) y de sus piezas compartidas.

Habia dos renderers y vivian divergiendo: uno decia "las tres casas" con
cuatro, imprimia codigos ISO donde el otro escribia el pais, y los dos llevaban
el corte de lotes escrito a mano. Queda uno; estos tests guardan los mismos
invariantes sobre el, mas el contrato de la app ligera: los datos pesados van
en lots.json/cards.json y no inline.
"""

import json
import re

import pytest

from pipelines.analytics import build_artifact, narrative, render_html


# --------------------------------------------------------------------------
# Contrato del detalle de lotes
# --------------------------------------------------------------------------

def test_pack_lot_details_roundtrip_includes_artist_key():
    """Empaquetar y desempaquetar no puede perder la clave de cruce."""
    details = [
        {
            "artist_key": "fernando_botero", "artist_name": "Fernando Botero",
            "country": "CO", "house_slug": "bogota_auctions", "auction_id": "a1",
            "auction_start_date": "2024-05-10T18:00", "lot_number": 7,
            "lot_title": "Mujer", "status": "VENDIDO", "sold": True,
            "price_sold": 1000, "currency": "COP", "price_sold_eur": 232.0,
            "lot_url": "http://x/1",
        },
    ]
    packed = render_html.pack_lot_details(details)
    assert "artist_key" in packed["cols"]
    # artist_key es de baja cardinalidad: tiene que ir indexada, no repetida.
    assert "artist_key" in packed["dict"]

    cols = packed["cols"]
    row = packed["rows"][0]
    out = {
        c: (packed["dict"][c][row[i]] if c in packed["dict"] else row[i])
        for i, c in enumerate(cols)
    }
    assert out["artist_key"] == "fernando_botero"
    assert out["price_sold_eur"] == 232.0
    assert out["sold"] == 1


def test_pack_lot_details_handles_empty():
    packed = render_html.pack_lot_details([])
    assert packed["rows"] == []
    assert "artist_key" in packed["cols"]


def test_lot_detail_columns_match_the_lot_line_function():
    """LOT_DETAIL_COLUMNS y el LOT_HEAD del JS tienen que medir lo mismo: si
    alguien anade una columna y olvida la cabecera, el CSV sale desalineado
    sin que falle nada."""
    m = re.search(r"LOT_HEAD\s*=\s*\[(.*?)\]", build_artifact.JS, re.S)
    assert m, "no se encontro LOT_HEAD"
    head = [x for x in m.group(1).split(",") if x.strip()]
    assert len(head) == len(render_html.LOT_DETAIL_COLUMNS)


# --------------------------------------------------------------------------
# App completa
# --------------------------------------------------------------------------

def _report():
    """Informe minimo pero realista: dos artistas, cuatro casas, un pais."""
    artists = [
        {
            "artist_name": "Fernando Botero", "artist_key": "fernando_botero",
            "artist_id": "fernando_botero", "birth_year": 1932, "death_year": 2023,
            "life_years": "1932-2023", "country": "CO", "country_birth": "CO",
            "country_birth_es": "Colombia", "nationalities": ["CO"],
            "resolution": "master",
            "houses": ["bogota_auctions", "duran_subastas"],
            "lots_offered": 30, "lots_sold": 26, "sell_through_rate": 0.8667,
            "revenue_eur": 400000.0, "avg_sold_price_eur": 15384.6,
            "top_price_eur": 90000.0, "top_lot_title": "Mujer",
            "top_lot_url": "http://x/1",
            "first_year": "2015", "last_year": "2024", "years_active": 6,
        },
        {
            "artist_name": "Artista Sin Ficha", "artist_key": "artista sin ficha",
            "artist_id": None, "birth_year": None, "death_year": None,
            "life_years": None, "country": None, "country_birth": None,
            "country_birth_es": None, "nationalities": [], "resolution": "fold_only",
            "houses": ["duran_subastas"],
            "lots_offered": 10, "lots_sold": 5, "sell_through_rate": 0.5,
            "revenue_eur": 5000.0, "avg_sold_price_eur": 1000.0,
            "top_price_eur": 2000.0, "top_lot_title": None, "top_lot_url": None,
            "first_year": "2019", "last_year": "2021", "years_active": 2,
        },
    ]
    return {
        "summary": {
            "total_lots": 40, "total_sold": 31, "total_houses": 4,
            "sell_through_pct": 77.5, "total_revenue_eur": 405000.0,
            "avg_sold_price_eur": 13064.5,
        },
        "by_house": [
            {"house_slug": s, "lots_offered": 10, "lots_sold": 8,
             "sell_through_rate": 0.8, "currency": c, "revenue_native": 1000.0,
             "revenue_eur": 1000.0, "avg_sold_price_native": 125.0,
             "avg_sold_price_eur": 125.0}
            for s, c in [("bogota_auctions", "COP"), ("duran_subastas", "EUR"),
                         ("zorrilla_subastas", "USD"), ("lefebre_subastas", "COP")]
        ],
        "by_auction": [], "by_year": [], "by_year_by_house": [], "by_month": [],
        "by_artist": artists,
        "by_country": [
            {"country": "CO", "country_es": "Colombia", "artists": 1,
             "lots_offered": 30, "lots_sold": 26, "sell_through_rate": 0.8667,
             "revenue_eur": 400000.0, "avg_sold_price_eur": 15384.6,
             "top_artist": "Fernando Botero", "houses": ["bogota_auctions"]},
        ],
        "by_country_year": [
            {"country": "CO", "country_es": "Colombia", "year": "2020",
             "year_method": "iso", "lots_offered": 15, "lots_sold": 13,
             "revenue_eur": 200000.0, "houses": ["bogota_auctions"]},
            {"country": "CO", "country_es": "Colombia", "year": "2022",
             "year_method": "auction_id", "lots_offered": 15, "lots_sold": 13,
             "revenue_eur": 200000.0, "houses": ["bogota_auctions"]},
        ],
        "by_generation": [
            {"decade": 1930, "decade_label": "1930s", "artists": 1, "alive": 0,
             "lots_offered": 30, "lots_sold": 26, "revenue_eur": 400000.0,
             "avg_sold_price_eur": 15384.6, "top_artist": "Fernando Botero"},
            {"decade": None, "decade_label": "Sin fecha de nacimiento", "artists": 1,
             "alive": 0, "lots_offered": 10, "lots_sold": 5, "revenue_eur": 5000.0,
             "avg_sold_price_eur": 1000.0, "top_artist": "Artista Sin Ficha"},
        ],
        "country_lots_below_rank_cutoff": 1234,
        "by_category": [], "quality_flags": [],
        "price_distribution": {}, "estimate_accuracy": {},
        "artist_coverage": {
            "artists_ranked": 2, "artists_with_country": 1,
            "country_coverage_pct": 50.0, "countries": 1,
        },
        "lot_details": [
            {"artist_key": "fernando_botero", "artist_name": "Fernando Botero",
             "country": "CO", "house_slug": "bogota_auctions", "auction_id": "a1",
             "auction_start_date": "2024-05-10T18:00", "lot_number": 7,
             "lot_title": "Mujer", "status": "VENDIDO", "sold": True,
             "price_sold": 1000, "currency": "COP", "price_sold_eur": 232.0,
             "lot_url": "http://x/1"},
            # Un artista sin pais TIENE que traer detalle: es el caso mayoritario.
            {"artist_key": "artista sin ficha", "artist_name": "Artista Sin Ficha",
             "country": None, "house_slug": "duran_subastas", "auction_id": "a2",
             "auction_start_date": "Octubre 2019", "lot_number": 3,
             "lot_title": "Sin titulo", "status": "VENDIDO", "sold": True,
             "price_sold": 500, "currency": "EUR", "price_sold_eur": 500.0,
             "lot_url": "http://x/2"},
        ],
    }


@pytest.fixture
def app_html():
    return build_artifact.build(_report())


@pytest.fixture
def app_cards():
    rep = _report()
    return build_artifact.build_cards(rep, rep["lot_details"])


def test_every_artist_row_opens_an_existing_card(app_html, app_cards):
    """data-card de cada fila tiene que existir en cards.json, o tocar el
    nombre abre una hoja vacia. Las dos usan la misma seleccion."""
    keys = set(re.findall(r"data-card='([^']+)'", app_html))
    assert keys, "no se generaron filas de artista"
    assert keys == set(app_cards)
    assert "Fernando Botero" in app_cards["ficha-1"]


def test_cards_and_lot_details_are_not_inline(app_html):
    """Iban inline y eran 12 MB que el movil bajaba para pintar una cabecera."""
    assert "LOT_DETAILS" not in app_html
    assert "class='acard'" not in app_html
    assert "artist-card" not in app_html
    assert "cards.json" in app_html and "lots.json" in app_html


def test_write_app_writes_the_three_files(tmp_path):
    rep = _report()
    build_artifact.write_app(rep, rep["lot_details"], tmp_path)
    assert (tmp_path / "index.html").read_text(encoding="utf-8").startswith("<!doctype html>")
    lots = json.loads((tmp_path / "lots.json").read_text(encoding="utf-8"))
    assert len(lots["rows"]) == 2 and "artist_key" in lots["cols"]
    cards = json.loads((tmp_path / "cards.json").read_text(encoding="utf-8"))
    assert set(cards) == {"ficha-1", "ficha-2"}


def test_app_is_a_mobile_document(app_html):
    assert "<html lang='es'>" in app_html
    assert "viewport-fit=cover" in app_html
    # Una tabla con min-width obliga a desplazar de lado en el movil.
    assert "min-width:560px" not in build_artifact.CSS
    # Sin esto, .pager{display:flex} gana a hidden y sale con un solo resultado.
    assert "[hidden]{display:none!important}" in build_artifact.CSS


def test_artist_row_carries_the_join_key(app_html):
    """La fila lleva artist_key para cruzar con el detalle sin pasar por el fold."""
    assert "data-key='fernando_botero'" in app_html


def test_fold_only_artist_is_rendered_without_inventing_a_country(app_html, app_cards):
    """El caso mayoritario: la mayoria de artistas no tienen pais.

    No puede heredar el de su casa de subastas (Duran => Espania). Hay un test
    equivalente en el pipeline; este cubre la capa de presentacion.
    """
    row = re.search(
        r"<tr data-country='__none__'[^>]*data-key='artista sin ficha'[^>]*>.*?</tr>",
        app_html, re.S,
    )
    assert row, "no se encontro la fila del artista sin ficha"
    assert "Sin país informado" in row.group(0)
    assert "España" not in row.group(0)
    assert "no está en el maestro curado" in app_cards["ficha-2"]


def test_multi_house_filter_exists(app_html):
    """Los artistas que venden en varias casas tienen que poder aislarse."""
    assert "id='kind-filter'" in app_html
    for value in ("multi", "cross_market", "same_market", "single"):
        assert f"<option value='{value}'>" in app_html, value


def test_multi_house_filter_separates_markets_in_the_rows(app_html):
    """Botero (Bogota+Duran) es cross_market; el de una sola casa, single.

    Sin esa distincion, los artistas que solo repiten en Bogota+Lefebre (las
    dos colombianas) se contarian como internacionales.
    """
    botero = re.search(r"<tr[^>]*data-key='fernando_botero'[^>]*>", app_html)
    assert botero and "data-kind='cross_market'" in botero.group(0)
    solo = re.search(r"<tr[^>]*data-key='artista sin ficha'[^>]*>", app_html)
    assert solo and "data-kind='single'" in solo.group(0)


def test_house_count_is_derived_not_hardcoded(app_html):
    """Decia "Las tres casas" cuando ya eran cuatro."""
    assert "Las tres casas" not in app_html
    assert "Las cuatro casas" in app_html


def test_min_lots_text_is_not_hardcoded(app_html):
    assert narrative.CAVEAT_MIN_LOTS in app_html
    assert "Mínimo 3 lotes vendidos para entrar" not in app_html


def test_the_charts_are_drawn_and_readable_by_touch(app_html):
    """Pareto, scatter y mapa de calor, cada uno con marcas que llevan su lectura:
    en una pantalla tactil el <title> del SVG no aparece nunca."""
    assert "class='cum'" in app_html, "falta la linea del Pareto"
    assert "class='pt" in app_html, "falta el scatter"
    assert "class='hm" in app_html, "falta el mapa de calor"
    assert app_html.count("class='chart scrub") >= 4
    assert re.search(r"<circle class='pt[^>]*data-l='Fernando Botero'", app_html)
    assert "class='ro-v'" in app_html


def test_critical_flag_is_next_to_the_sell_through_it_qualifies():
    """La tasa de venta de Bogota no es comparable: el aviso tiene que estar en
    la pantalla de casas, donde se lee esa tasa, no solo en Resumen."""
    rep = _report()
    rep["quality_flags"] = [{"level": "critical", "house_slug": "bogota_auctions",
                             "message": "Tasa de venta de bogota_auctions NO comparable"}]
    casas = re.search(r"<section class='screen' id='casas'.*?</section>",
                      build_artifact.build(rep), re.S).group(0)
    assert "Tasa de venta de Bogotá Auctions NO comparable" in casas


def test_missing_birth_dates_are_coverage_not_a_fake_generation_bar(app_html):
    """La ausencia de dato sigue visible, pero queda fuera del eje temporal."""
    assert "class='generation-coverage'" in app_html
    assert "Cobertura de fechas del ranking completo" in app_html
    assert "<strong>Sin fecha</strong>" in app_html
    # Fixture: 400.000 EUR datados y 5.000 sin fecha.
    assert "style='width:98.8%'" in app_html
    assert "style='width:1.2%'" in app_html
    # El SVG no puede volver a dibujarlo como una barra normal.
    assert "<title>Sin fecha de nacimiento:" not in app_html


def test_narrative_caveats_reach_the_app(app_html):
    """Los avisos son parte del grafico, no un adorno opcional."""
    for caveat in (narrative.CAVEAT_PARETO_SCOPE, narrative.CAVEAT_SCATTER_LOWN,
                   narrative.CAVEAT_GENERATIONS_COVERAGE,
                   narrative.CAVEAT_FX_TIMESERIES, narrative.CAVEAT_COUNTRY_IS_HOUSE):
        assert caveat in app_html


def test_app_reports_the_artist_revenue(app_html):
    assert re.search(r"Fernando Botero.*?400[.,]000", app_html, re.S)


def test_short_money_matches_the_js_format():
    """La cabecera la escribe Python y la reanima el JS: mismo formato o salta."""
    assert build_artifact.money(41_839_851.72) == "41,84 M€"
    assert build_artifact.money(4_400_000) == "4,4 M€"
    assert build_artifact.money(934_000) == "934 k€"
    assert build_artifact.money(1_490) == "1.490 €"


def test_lot_date_does_not_truncate_spanish_text_dates():
    """Cortar a 10 caracteres convertia "Octubre 2020" en "Octubre 20"."""
    assert build_artifact.lot_date("Octubre 2020") == "Octubre 2020"
    assert build_artifact.lot_date("2024-05-10T18:00") == "2024-05-10"
    assert build_artifact.lot_date(None) == "—"


# --------------------------------------------------------------------------
# Alcance del ranking por pais
# --------------------------------------------------------------------------

def _artist(name, country, revenue):
    return {
        "artist_name": name, "artist_id": name.lower().replace(" ", "_"),
        "artist_key": name.lower().replace(" ", "_"),
        "country_birth": country, "country_birth_es": country,
        "lots_offered": 2, "lots_sold": 1, "revenue_eur": revenue,
        "sell_through_rate": 0.5, "avg_sold_price_eur": revenue,
        "houses": ["duran_subastas"], "resolution": "master",
    }


@pytest.fixture
def table(monkeypatch):
    def _table(artists, limit):
        monkeypatch.setattr(build_artifact, "ARTIST_LIMIT", limit)
        html = build_artifact.build_artist_table(artists, {})
        # Solo la lista y su paginador: los graficos de debajo (el scatter
        # etiqueta nombres) no son el ranking.
        return html[html.index("<table"):html.index("box-notes")]
    return _table


def test_country_ranking_reaches_beyond_the_global_top(table):
    """Filtrar Colombia mostraba 41 de 258 porque el corte era GLOBAL.

    Se renderiza el top global mas el top de cada pais, o el desplegable
    promete un filtro que no puede cumplir.
    """
    artists = [_artist(f"Espanol {i}", "ES", 10_000 - i) for i in range(5)]
    artists += [_artist(f"Colombiano {i}", "CO", 100 - i) for i in range(3)]
    html = table(artists, 5)
    for i in range(3):
        assert f"Colombiano {i}" in html


def test_country_ranking_still_caps_each_country(table):
    artists = [_artist(f"Espanol {i}", "ES", 10_000 - i) for i in range(9)]
    html = table(artists, 3)
    # 3 globales + 3 del tope por pais: el resto no se pinta.
    assert "Espanol 2" in html
    assert "Espanol 8" not in html


def test_a_single_country_batch_is_not_duplicated(table):
    """Un artista que esta en el top global Y en el de su pais sale una vez."""
    artists = [_artist(f"Espanol {i}", "ES", 10_000 - i) for i in range(3)]
    html = table(artists, 5)
    assert html.count(">Espanol 0<") == 1


def test_artist_table_ships_pagination_controls(table):
    """Mas de mil filas de golpe abruman. La lista pagina en cliente."""
    artists = [_artist(f"Pintor {i}", "ES", 1000 - i) for i in range(12)]
    html = table(artists, 12)
    assert "artist-pager" in html
    assert "artist-page-prev" in html
    assert "artist-page-next" in html


def test_pagination_logic_ships_in_the_document_script():
    js = build_artifact.JS
    assert "PAGE_SIZE" in js
    # Las descargas no pueden volver a leer !hidden: con paginacion, hidden
    # solo dice si la fila cae en la pagina actual.
    assert "dataset.match" in js


# --------------------------------------------------------------------------
# Mapa de paises
# --------------------------------------------------------------------------

def _world():
    return {
        "viewBox": [0, -10, 100, 20],
        "countries": {
            "CO": {"name": "Colombia", "d": "M0 0l1 1z", "c": [1, 1]},
            "PE": {"name": "Perú", "d": "M2 2l1 1z", "c": [2, 2]},
        },
    }


def test_map_paints_sales_blue_and_absence_gray():
    """Un pais sin ventas va gris, no con el tramo mas claro: se leeria como
    "vendio poco" cuando no hay ningun artista nacido alli en el ranking."""
    svg, missing = build_artifact.world_map(
        [{"country": "CO", "country_es": "Colombia", "revenue_eur": 6_000_000,
          "artists": 300, "lots_sold": 9000}], _world())
    co = re.search(r"<path class='geo q5'[^>]*data-l='Colombia'", svg)
    assert co, "Colombia (6 M€) tiene que ir en el tramo mas oscuro"
    assert re.search(r"<path class='geo' [^>]*data-l='Perú'[^>]*data-v='Sin ventas'", svg)
    assert missing == []


def test_map_declares_countries_it_cannot_draw():
    """Checoslovaquia no existe en el mapa de hoy. Se declara, no se reparte."""
    _, missing = build_artifact.world_map(
        [{"country": "CS", "country_es": "Checoslovaquia", "revenue_eur": 16_750}], _world())
    assert missing == ["Checoslovaquia"]


def test_map_bins_are_decades():
    assert build_artifact.map_bin(9_999) == "q1"
    assert build_artifact.map_bin(10_000) == "q2"
    assert build_artifact.map_bin(999_999) == "q3"
    assert build_artifact.map_bin(1_000_000) == "q4"
    assert build_artifact.map_bin(5_000_000) == "q5"


def test_versioned_world_has_france_and_norway():
    """En ISO_A2 de Natural Earth Francia y Noruega valen "-99": saldrian grises
    con ventas millonarias. El script usa ISO_A2_EH."""
    world = json.loads(build_artifact.WORLD_PATH.read_text(encoding="utf-8"))
    for code in ("FR", "NO", "ES", "CO", "UY"):
        assert code in world["countries"], code
    assert "AQ" not in world["countries"]

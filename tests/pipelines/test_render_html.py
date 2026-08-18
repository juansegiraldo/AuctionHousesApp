"""Tests de los dos renderizados del informe.

No habia ninguno, y es donde vivian las divergencias mas caras: el artifact
decia "las tres casas" con cuatro, imprimia codigos ISO donde el HTML local
escribia el nombre del pais, y los dos llevaban el corte de lotes escrito a mano.

Cubren tres cosas: el contrato posicional de LOT_DETAIL_COLUMNS (que acopla tres
sitios en dos ficheros), la accesibilidad de la ficha, y que las dos versiones
publiquen las mismas cifras.
"""

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


def test_lot_detail_columns_match_both_lot_line_functions():
    """LOT_DETAIL_COLUMNS acopla tres sitios en dos ficheros.

    La tupla, el LOT_HEAD del JS de render_html y el del JS del artifact tienen
    que tener la misma longitud: si alguien anade una columna y olvida una de
    las dos cabeceras, el CSV sale desalineado sin que falle nada.
    """
    n = len(render_html.LOT_DETAIL_COLUMNS)

    def _head_len(source: str) -> int:
        m = re.search(r"LOT_HEAD\s*=\s*\[(.*?)\]", source, re.S)
        assert m, "no se encontro LOT_HEAD"
        return len([x for x in m.group(1).split(",") if x.strip()])

    assert _head_len(render_html.JS_TEMPLATE) == n
    assert _head_len(build_artifact.JS) == n


# --------------------------------------------------------------------------
# Informe completo
# --------------------------------------------------------------------------

def _report():
    """Informe minimo pero realista: dos artistas, dos casas, dos paises."""
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
def local_html(tmp_path):
    out = tmp_path / "report.html"
    render_html.write_html(_report(), out)
    return out.read_text(encoding="utf-8")


@pytest.fixture
def artifact_html():
    rep = _report()
    return build_artifact.build(rep, rep["lot_details"])


def test_artist_cards_have_coherent_aria(local_html):
    """Cada aria-controls tiene que apuntar a un id que exista."""
    controls = set(re.findall(r"aria-controls='([^']+)'", local_html))
    ids = set(re.findall(r"<tr class='artist-card' id='([^']+)'", local_html))
    assert controls, "no se generaron fichas"
    assert controls <= ids, controls - ids
    # Todas empiezan cerradas: una ficha abierta de salida seria ruido.
    assert "aria-expanded='true'" not in local_html


def test_artist_row_carries_the_join_key(local_html):
    """La fila lleva artist_key para cruzar con el detalle sin pasar por el fold."""
    assert "data-key='fernando_botero'" in local_html


def test_fold_only_artist_is_rendered_without_inventing_a_country(local_html):
    """El caso mayoritario: 863 de 1.521 artistas no tienen pais.

    No puede heredar el de su casa de subastas (Duran => Espania). Hay un test
    equivalente en el pipeline; este cubre la capa de presentacion.
    """
    assert "Artista Sin Ficha" in local_html
    row = re.search(
        r"<tr data-country='__none__'[^>]*data-key='artista sin ficha'[^>]*>.*?</tr>",
        local_html, re.S,
    )
    assert row, "no se encontro la fila del artista sin ficha"
    assert "Sin país informado" in row.group(0)
    assert "España" not in row.group(0)


def test_multi_house_filter_exists_in_both_renderers(local_html, artifact_html):
    """Los artistas que venden en varias casas tienen que poder aislarse.

    El dato estaba en cada fila pero no habia forma de filtrarlo: habia que
    abrir fichas una a una para encontrarlos.
    """
    for html in (local_html, artifact_html):
        assert "id='kind-filter'" in html
        for value in ("multi", "cross_market", "same_market", "single"):
            assert f"<option value='{value}'>" in html, value


def test_multi_house_filter_separates_markets_in_the_rows(local_html):
    """Botero (Bogota+Duran) es cross_market; el de una sola casa, single.

    Sin esa distincion, los 104 artistas que solo repiten en Bogota+Lefebre
    (las dos colombianas) se contarian como internacionales.
    """
    botero = re.search(r"<tr[^>]*data-key='fernando_botero'[^>]*>", local_html)
    assert botero and "data-kind='cross_market'" in botero.group(0)
    solo = re.search(r"<tr[^>]*data-key='artista sin ficha'[^>]*>", local_html)
    assert solo and "data-kind='single'" in solo.group(0)


def test_artifact_house_count_is_derived_not_hardcoded(artifact_html):
    """Decia "Las tres casas" cuando ya eran cuatro."""
    assert "Las tres casas" not in artifact_html
    assert "Las cuatro casas" in artifact_html


def test_min_lots_text_is_not_hardcoded_in_either_renderer(local_html, artifact_html):
    assert narrative.CAVEAT_MIN_LOTS in local_html
    assert narrative.CAVEAT_MIN_LOTS in artifact_html
    for html in (local_html, artifact_html):
        assert "Mínimo 3 lotes vendidos para entrar" not in html


def test_both_renderers_draw_the_four_charts(local_html, artifact_html):
    """Los cuatro graficos existen en las dos versiones.

    El local los dibuja con Plotly (contenedor + funcion draw); el artifact los
    trae como SVG ya generado. Distinta tecnica, misma seccion.
    """
    for cid in ("chart-pareto", "chart-scatter", "chart-generations", "chart-heatmap"):
        assert f"id='{cid}'" in local_html, cid
    for fn in ("drawPareto", "drawScatter", "drawGenerations", "drawHeatmap"):
        assert fn in local_html, fn
    # El artifact no usa contenedores: el SVG va inline.
    assert "class='cum'" in artifact_html, "falta la linea del Pareto"
    assert "class='pt" in artifact_html, "falta el scatter"


def test_missing_birth_dates_are_coverage_not_a_fake_generation_bar(
    local_html, artifact_html
):
    """La ausencia de dato sigue visible, pero queda fuera del eje temporal."""
    for html in (local_html, artifact_html):
        assert "class='generation-coverage'" in html
        assert "Cobertura de fechas del ranking completo" in html
        assert "<strong>Sin fecha</strong>" in html
        # Fixture: 400.000 EUR datados y 5.000 sin fecha.
        assert "style='width:98.8%'" in html
        assert "style='width:1.2%'" in html

    # Plotly filtra el sentinela antes de construir x/y.
    assert "DATA.generations.filter(r => !r.is_sentinel)" in local_html
    # El SVG no puede volver a dibujarlo como una barra normal.
    assert "<title>Sin fecha de nacimiento:" not in artifact_html


def test_narrative_caveats_reach_both_renderers(local_html, artifact_html):
    """Los avisos son parte del grafico, no un adorno opcional."""
    for html in (local_html, artifact_html):
        assert narrative.CAVEAT_PARETO_SCOPE in html
        assert narrative.CAVEAT_SCATTER_LOWN in html
        assert narrative.CAVEAT_GENERATIONS_COVERAGE in html


def test_fx_caveat_is_next_to_the_time_series(local_html):
    """El mapa es una serie temporal con FX de tasa unica: hay que decirlo.

    Sin este aviso, la fila de Colombia se lee como evolucion real del mercado
    cuando buena parte del movimiento es el tipo de cambio.
    """
    assert narrative.CAVEAT_FX_TIMESERIES in local_html
    assert narrative.CAVEAT_COUNTRY_IS_HOUSE in local_html


def test_both_renderers_report_the_same_revenue(local_html, artifact_html):
    """Si las dos versiones publican cifras distintas, una miente.

    Se comprueba sobre el volumen del artista lider, que aparece en las dos
    tablas y viene del mismo agregado.
    """
    def _find(html):
        m = re.search(r"Fernando Botero.*?400[.,]000", html, re.S)
        return bool(m)

    assert _find(local_html)
    assert _find(artifact_html)

"""Tests de pipelines/analytics/narrative.py.

narrative.py existe para que los dos informes (el HTML local con Plotly y el
artifact con SVG) publiquen LAS MISMAS cifras y los mismos avisos. Estos tests
cubren sobre todo lo que, si se rompe, hace que una version diga una cosa y la
otra diga otra, o que un agregado pierda dinero por el camino sin avisar.
"""

import pytest

from pipelines.analytics import narrative
from pipelines.gold.build_insights import MIN_LOTS_FOR_ARTIST_RANK


def _artist(name, revenue, sold=10, avg=None, country="ES", **kw):
    row = {
        "artist_name": name,
        "artist_key": name.lower().replace(" ", "_"),
        "revenue_eur": revenue,
        "lots_sold": sold,
        "lots_offered": sold + 2,
        "avg_sold_price_eur": avg if avg is not None else (revenue / sold if sold else None),
        "country_birth": country,
        "country_birth_es": {"ES": "España", "CO": "Colombia"}.get(country),
        "houses": ["duran_subastas"],
    }
    row.update(kw)
    return row


# --------------------------------------------------------------------------
# Pareto
# --------------------------------------------------------------------------

def test_pareto_shares_are_monotonic_and_end_at_100():
    artists = [_artist(f"A{i}", 100 - i) for i in range(20)]
    points = narrative.pareto_points(artists)
    shares = [p["share_pct"] for p in points]
    assert shares == sorted(shares), "el acumulado no puede bajar"
    assert points[-1]["n"] == len(artists)
    assert points[-1]["share_pct"] == pytest.approx(100.0)


def test_pareto_share_matches_known_values():
    """10 artistas de 100 EUR: el top 3 es exactamente el 30%."""
    artists = [_artist(f"A{i}", 100) for i in range(10)]
    points = {p["n"]: p["share_pct"] for p in narrative.pareto_points(artists, cuts=(3, 5, 10))}
    assert points[3] == pytest.approx(30.0)
    assert points[5] == pytest.approx(50.0)
    assert points[10] == pytest.approx(100.0)


def test_pareto_ignores_cuts_beyond_the_ranking():
    """Un corte mayor que el ranking no puede inventar una fila."""
    artists = [_artist(f"A{i}", 10) for i in range(4)]
    ns = [p["n"] for p in narrative.pareto_points(artists, cuts=(3, 25, 100))]
    assert ns == [3, 4], ns


def test_pareto_empty_ranking_is_empty_not_a_crash():
    assert narrative.pareto_points([]) == []


# --------------------------------------------------------------------------
# Scatter
# --------------------------------------------------------------------------

def test_scatter_keeps_artists_without_country():
    """Los 863 fold_only son mayoria: filtrarlos vaciaria el grafico."""
    artists = [
        _artist("Con Pais", 1000, country="ES"),
        _artist("Sin Pais", 900, country=None),
    ]
    pts = narrative.scatter_points(artists)
    assert len(pts) == 2
    sin = [p for p in pts if p["name"] == "Sin Pais"][0]
    assert sin["country"] is None
    # Nunca se rellena con el pais de la casa.
    assert sin["country_es"] is None


def test_scatter_drops_points_without_usable_axes():
    """Sin precio medio o sin ventas no hay punto que dibujar (log(0))."""
    artists = [
        _artist("Bueno", 1000, sold=10),
        _artist("Sin ventas", 0, sold=0, avg=None),
    ]
    names = {p["name"] for p in narrative.scatter_points(artists)}
    assert names == {"Bueno"}


def test_scatter_marks_top_countries_and_groups_the_rest():
    artists = (
        [_artist(f"E{i}", 1000, country="ES") for i in range(3)]
        + [_artist(f"C{i}", 900, country="CO") for i in range(3)]
        + [_artist("Raro", 10, country="HU")]
    )
    pts = {p["name"]: p for p in narrative.scatter_points(artists, top_countries=2)}
    assert pts["E0"]["group"] == "ES"
    assert pts["C0"]["group"] == "CO"
    # Un pais fuera del top no desaparece: se agrupa como "otros".
    assert pts["Raro"]["group"] == "__other__"


# --------------------------------------------------------------------------
# Heatmap
# --------------------------------------------------------------------------

def _cell(country, year, revenue, method="iso", lots=5):
    return {
        "country": country,
        "country_es": {"ES": "España", "CO": "Colombia"}.get(country),
        "year": year,
        "year_method": method,
        "lots_offered": lots,
        "lots_sold": lots,
        "revenue_eur": revenue,
        "houses": ["duran_subastas"],
    }


def test_heatmap_top_n_plus_rest_conserves_total():
    """Agrupar la cola en "Resto" no puede perder dinero por el camino."""
    rows = [
        _cell("ES", "2020", 1000),
        _cell("CO", "2020", 500),
        _cell("UY", "2020", 100),
        _cell("HU", "2020", 50),
    ]
    m = narrative.heatmap_matrix(rows, top_n=2)
    total_in = sum(r["revenue_eur"] for r in rows)
    total_out = sum(
        c["revenue_eur"] for row in m["rows"] for c in row["cells"] if c["revenue_eur"]
    )
    assert total_out == pytest.approx(total_in)


def test_heatmap_empty_cell_is_none_not_zero():
    """"Sin lotes" y "lotes que no se vendieron" no pueden pintarse igual."""
    rows = [_cell("ES", "2020", 1000), _cell("ES", "2022", 500)]
    m = narrative.heatmap_matrix(rows, top_n=5)
    cells = {c["year"]: c for c in m["rows"][0]["cells"]}
    assert cells["2021"]["revenue_eur"] is None
    assert cells["2020"]["revenue_eur"] == 1000


def test_heatmap_marks_inferred_years():
    rows = [_cell("ES", "2020", 1000, method="auction_id")]
    m = narrative.heatmap_matrix(rows, top_n=5)
    assert m["rows"][0]["cells"][0]["inferred"] is True


def test_heatmap_excludes_unknown_year_from_the_axis():
    """El eje es temporal: "unknown" no es un anio y rompe el orden."""
    rows = [_cell("ES", "2020", 1000), _cell("ES", "unknown", 300)]
    m = narrative.heatmap_matrix(rows, top_n=5)
    assert m["years"] == ["2020"]
    assert m["unknown_year_revenue_eur"] == 300


def test_heatmap_excludes_null_country_row():
    """La fila sin pais no puede ocupar un carril del mapa, pero se cuenta."""
    rows = [_cell("ES", "2020", 1000), _cell(None, "2020", 700)]
    m = narrative.heatmap_matrix(rows, top_n=5)
    assert [r["country"] for r in m["rows"]] == ["ES"]
    assert m["no_country_revenue_eur"] == 700


# --------------------------------------------------------------------------
# Generaciones
# --------------------------------------------------------------------------

def test_generation_bars_keep_the_sentinel_last_and_flagged():
    rows = [
        {"decade": 1920, "decade_label": "1920s", "revenue_eur": 500, "artists": 10,
         "lots_sold": 40, "alive": 2, "top_artist": "X"},
        {"decade": None, "decade_label": "Sin fecha de nacimiento", "revenue_eur": 900,
         "artists": 90, "lots_sold": 100, "alive": 0, "top_artist": "Y"},
    ]
    bars = narrative.generation_bars(rows)
    assert bars[-1]["is_sentinel"] is True
    assert bars[0]["is_sentinel"] is False


def test_generation_coverage_separates_missing_without_losing_totals():
    rows = [
        {"decade": 1920, "decade_label": "1920s", "revenue_eur": 750,
         "artists": 3, "lots_sold": 8},
        {"decade": 1930, "decade_label": "1930s", "revenue_eur": 50,
         "artists": 1, "lots_sold": 1},
        {"decade": None, "decade_label": "Sin fecha de nacimiento",
         "revenue_eur": 200, "artists": 6, "lots_sold": 7},
    ]
    cov = narrative.generation_coverage(rows)
    assert cov["dated_revenue_eur"] == 800
    assert cov["missing_revenue_eur"] == 200
    assert cov["total_revenue_eur"] == 1000
    assert cov["dated_revenue_pct"] == 80.0
    assert cov["missing_revenue_pct"] == 20.0
    assert cov["dated_artists"] == 4
    assert cov["missing_artists"] == 6
    assert cov["dated_artists_pct"] == 40.0


def test_generation_coverage_handles_an_empty_aggregate():
    cov = narrative.generation_coverage([])
    assert cov["total_revenue_eur"] == 0
    assert cov["total_artists"] == 0
    assert cov["dated_revenue_pct"] == 0.0


# --------------------------------------------------------------------------
# Casas: mismo mercado vs mercados distintos
# --------------------------------------------------------------------------

def test_multi_house_kind_classifies_colombian_pair_as_same_market():
    """104 de los 179 artistas multi-casa son Bogota+Lefebre, las dos colombianas.

    Contarlos como "cruza mercados" convertiria 46 casos reales en 179 y daria
    una conclusion falsa sobre lo conectados que estan los dos mercados.
    """
    assert narrative.multi_house_kind(["bogota_auctions", "lefebre_subastas"]) == "same_market"
    assert narrative.multi_house_kind(["bogota_auctions", "duran_subastas"]) == "cross_market"
    assert narrative.multi_house_kind(["duran_subastas"]) == "single"
    assert narrative.multi_house_kind([]) == "single"


def test_multi_house_kind_handles_three_houses():
    kind = narrative.multi_house_kind(
        ["bogota_auctions", "duran_subastas", "lefebre_subastas"]
    )
    assert kind == "cross_market"


# --------------------------------------------------------------------------
# Textos: una sola fuente para los dos informes
# --------------------------------------------------------------------------

def test_min_lots_caveat_text_uses_the_constant():
    """El "3" no puede estar escrito a mano en el texto de dos renderers.

    Estaba duplicado en render_html.py y en build_artifact.py, asi que cambiar
    MIN_LOTS_FOR_ARTIST_RANK dejaba los dos informes mintiendo.
    """
    assert str(MIN_LOTS_FOR_ARTIST_RANK) in narrative.CAVEAT_MIN_LOTS


def test_nationalities_are_translated_to_spanish():
    """El artifact imprimia los codigos ISO crudos ("tb. FR, IT")."""
    assert narrative.nationalities_es(["FR", "IT"]) == "Francia, Italia"
    # Un codigo desconocido se muestra tal cual antes que desaparecer.
    assert narrative.nationalities_es(["ZZ"]) == "ZZ"
    assert narrative.nationalities_es([]) == ""


def test_country_metrics_caveat_mentions_the_gap():
    """El aviso lleva la cifra real, no una vaguedad."""
    text = narrative.country_metrics_caveat(18_449)
    assert "18.449" in text or "18,449" in text

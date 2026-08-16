"""Tests de pipelines/gold/build_insights.py.

Cubren sobre todo las reglas que, si se rompen, corrompen el informe en
silencio: mezclar monedas, contar como vendido lo que no lo esta, y colar
escuelas/atribuciones en el ranking de artistas.
"""

import json

import pytest

from pipelines.gold import build_insights
from pipelines.shared.artist_key import artist_fold


# --------------------------------------------------------------------------
# Filtro de "artistas" que no son autores
# --------------------------------------------------------------------------

@pytest.mark.parametrize(
    "name",
    [
        "Escuela Española S. XVII",
        "escuela flamenca",
        "Taller de Pieter Coecke van Aelst",
        "Atribuido a Goya",
        "Maestro de las medias figuras",
        "Círculo de Rubens",
        "Seguidor de Murillo",
        "Anónimo",
        "",
        "  ",
    ],
)
def test_noise_artists_are_excluded(name):
    assert build_insights.is_noise_artist(name) is True


@pytest.mark.parametrize(
    "name",
    [
        "Fernando Botero",
        "Antoni Tàpies",
        "Yayoi Kusama",
        "Olga de Amaral",
        "Julio Romero de Torres",
    ],
)
def test_real_artists_are_kept(name):
    assert build_insights.is_noise_artist(name) is False


# --------------------------------------------------------------------------
# Agregacion end-to-end sobre un Silver minimo
# --------------------------------------------------------------------------

def _lot(**kw):
    base = {
        "dedupe_key": kw.get("lot_url", "k"),
        "lot_url": "u",
        "house_slug": "duran_subastas",
        "currency": "EUR",
        "status": "VENDIDO",
        "price_sold": 100,
        "artist_name": "Artista Uno",
        "auction_start_date": "2024-05-10T18:00",
    }
    base.update(kw)
    return base


@pytest.fixture
def gold(tmp_path, monkeypatch):
    """Redirige las rutas del modulo a un arbol temporal."""
    silver = tmp_path / "data" / "silver"
    enrich = tmp_path / "data" / "enrichments"
    goldd = tmp_path / "data" / "gold"
    for d in (silver, enrich, goldd):
        d.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(build_insights, "SILVER_ROOT", silver)
    monkeypatch.setattr(build_insights, "ENRICH_ROOT", enrich)
    monkeypatch.setattr(build_insights, "GOLD_ROOT", goldd)
    return silver, enrich, goldd


def _write(path, rows):
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def _read(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def test_revenue_never_mixes_currencies(gold):
    """COP y EUR no se suman en nativo: el total va en EUR convertido.

    Es la regla mas cara del proyecto: sumar 3.4M COP como si fueran euros
    inflaba el KPI unas 3500 veces.
    """
    silver, _, goldd = gold
    _write(
        silver / "lots.jsonl",
        [
            # 1000 EUR
            _lot(lot_url="a", dedupe_key="a", currency="EUR", price_sold=1000,
                 artist_name="Artista Uno"),
            # 1.000.000 COP ~ 232 EUR con la tasa de fx.yaml
            _lot(lot_url="b", dedupe_key="b", currency="COP", price_sold=1_000_000,
                 house_slug="bogota_auctions", artist_name="Artista Uno"),
            # Tercera venta para superar MIN_LOTS_FOR_ARTIST_RANK.
            _lot(lot_url="c", dedupe_key="c", currency="EUR", price_sold=0,
                 artist_name="Artista Uno"),
        ],
    )
    build_insights.build_insights()
    artists = _read(goldd / "agg_artist_metrics.jsonl")
    assert len(artists) == 1
    rev = artists[0]["revenue_eur"]
    # Si se hubieran sumado en nativo el total seria ~1.000.100, no ~1.232.
    assert 1200 < rev < 1300, rev


def test_unknown_currency_is_excluded_not_treated_as_eur(gold):
    """Una moneda sin tasa no puede colarse como si fuera EUR."""
    silver, _, goldd = gold
    _write(
        silver / "lots.jsonl",
        [
            _lot(lot_url="a", dedupe_key="a", currency="EUR", price_sold=500),
            _lot(lot_url="b", dedupe_key="b", currency="JPY", price_sold=999_999),
            _lot(lot_url="c", dedupe_key="c", currency="EUR", price_sold=500),
        ],
    )
    build_insights.build_insights()
    artists = _read(goldd / "agg_artist_metrics.jsonl")
    assert artists[0]["revenue_eur"] == 1000.0


def test_explicit_status_beats_price_presence(gold):
    """NO VENDIDO con precio publicado no cuenta como venta."""
    silver, _, goldd = gold
    _write(
        silver / "lots.jsonl",
        [
            _lot(lot_url="a", dedupe_key="a", status="VENDIDO", price_sold=100),
            # Precio publicado pero NO VENDIDO: no puede contar como venta.
            _lot(lot_url="b", dedupe_key="b", status="NO VENDIDO", price_sold=100),
            _lot(lot_url="c", dedupe_key="c", status="VENDIDO", price_sold=100),
            _lot(lot_url="d", dedupe_key="d", status="VENDIDO", price_sold=100),
        ],
    )
    build_insights.build_insights()
    artists = _read(goldd / "agg_artist_metrics.jsonl")
    assert artists[0]["lots_sold"] == 3
    assert artists[0]["lots_offered"] == 4
    assert artists[0]["revenue_eur"] == 300.0


def test_artists_below_minimum_are_not_ranked(gold):
    """Con 1-2 ventas un 'precio medio' es ruido, no un dato."""
    silver, _, goldd = gold
    rows = [
        _lot(lot_url=f"x{i}", dedupe_key=f"x{i}", artist_name="Prolifico")
        for i in range(build_insights.MIN_LOTS_FOR_ARTIST_RANK)
    ]
    rows.append(_lot(lot_url="y", dedupe_key="y", artist_name="Puntual"))
    _write(silver / "lots.jsonl", rows)
    build_insights.build_insights()
    names = {a["artist_name"] for a in _read(goldd / "agg_artist_metrics.jsonl")}
    assert "Prolifico" in names
    assert "Puntual" not in names


def test_price_bands_partition_without_double_counting(gold):
    """Cada lote cae en un solo tramo: los tramos suman el total."""
    silver, _, goldd = gold
    prices = [50, 150, 700, 2000, 10_000, 50_000]
    _write(
        silver / "lots.jsonl",
        [
            _lot(lot_url=f"p{i}", dedupe_key=f"p{i}", price_sold=p)
            for i, p in enumerate(prices)
        ],
    )
    build_insights.build_insights()
    dist = _read(goldd / "agg_price_distribution.jsonl")[0]
    assert sum(b["lots"] for b in dist["bands"]) == len(prices)
    assert sum(b["revenue_eur"] for b in dist["bands"]) == pytest.approx(sum(prices))
    assert dist["count"] == len(prices)
    assert dist["max"] == 50_000


def test_estimate_accuracy_buckets(gold):
    """Por encima / dentro / por debajo se clasifican por la horquilla."""
    silver, _, goldd = gold
    _write(
        silver / "lots.jsonl",
        [
            # por encima del maximo
            _lot(lot_url="a", dedupe_key="a", price_sold=300,
                 price_estimate_min=100, price_estimate_max=200),
            # dentro
            _lot(lot_url="b", dedupe_key="b", price_sold=150,
                 price_estimate_min=100, price_estimate_max=200),
            # por debajo del minimo
            _lot(lot_url="c", dedupe_key="c", price_sold=50,
                 price_estimate_min=100, price_estimate_max=200),
            # sin estimacion: fuera de la muestra
            _lot(lot_url="d", dedupe_key="d", price_sold=150),
        ],
    )
    build_insights.build_insights()
    est = _read(goldd / "agg_estimate_accuracy.jsonl")[0]
    assert est["total_with_estimate"] == 3
    assert (est["above"], est["within"], est["below"]) == (1, 1, 1)


def test_seasonality_ignores_lots_without_real_date(gold):
    """Solo cuenta el mes cuando hay fecha ISO; el anio inferido no vale."""
    silver, _, goldd = gold
    _write(
        silver / "lots.jsonl",
        [
            _lot(lot_url="a", dedupe_key="a", auction_start_date="2024-05-10T18:00"),
            _lot(lot_url="b", dedupe_key="b", auction_start_date="2024-05-20T18:00"),
            _lot(lot_url="c", dedupe_key="c", auction_start_date="Julio 2014"),
            _lot(lot_url="d", dedupe_key="d", auction_start_date=None),
        ],
    )
    build_insights.build_insights()
    months = _read(goldd / "agg_month_metrics.jsonl")
    assert len(months) == 1
    assert months[0]["month"] == "05"
    assert months[0]["lots_offered"] == 2


def test_categories_come_from_enrichment_and_default_to_other(gold):
    silver, enrich, goldd = gold
    _write(
        silver / "lots.jsonl",
        [
            _lot(lot_url="a", dedupe_key="a"),
            _lot(lot_url="b", dedupe_key="b"),
        ],
    )
    _write(enrich / "category_tags.jsonl", [{"dedupe_key": "a", "category": "painting"}])
    build_insights.build_insights()
    cats = {c["category"]: c for c in _read(goldd / "agg_category_metrics.jsonl")}
    assert cats["painting"]["lots_offered"] == 1
    assert cats["other"]["lots_offered"] == 1


# --------------------------------------------------------------------------
# Identidad de artista y pais
# --------------------------------------------------------------------------

def _resolved(name, **kw):
    """Lote tal como lo deja pipelines/silver/artist_resolve.py."""
    row = _lot(artist_name=name, **kw)
    row.setdefault("attribution_type", "autor")
    row.setdefault("artist_fold", artist_fold(name))
    row.setdefault("artist_display_name", name)
    row.setdefault("artist_id", None)
    row.setdefault("artist_country_birth", None)
    row.setdefault("artist_nationalities", [])
    row.setdefault("artist_resolution", "fold_only")
    return row


def test_artist_variants_merge_into_one_row(gold):
    """Las 4 grafias de Agustin Ubeda son un artista, no cuatro.

    Antes se agrupaba por el nombre CRUDO, asi que sus 368 lotes reales salian
    partidos en 4 filas del ranking y ninguna reflejaba su volumen real.
    """
    silver, _, goldd = gold
    variantes = ["Agustín Úbeda", "Agustin Úbeda", "Agustín Ubeda", "Agustin Ubeda"]
    _write(
        silver / "lots.jsonl",
        [
            _resolved(v, lot_url=f"v{i}", dedupe_key=f"v{i}")
            for i, v in enumerate(variantes)
        ],
    )
    build_insights.build_insights()
    artists = _read(goldd / "agg_artist_metrics.jsonl")
    assert len(artists) == 1
    assert artists[0]["lots_offered"] == 4


def test_two_people_same_fold_stay_separate_when_master_says_so(gold):
    """Francisco Toledo son dos personas distintas con el mismo fold.

    El maestro las separa via artist_id; si Gold agrupara solo por fold, este
    error seria irreparable por construccion.
    """
    silver, _, goldd = gold
    rows = []
    for i in range(3):
        rows.append(_resolved("Francisco Toledo", lot_url=f"mx{i}", dedupe_key=f"mx{i}",
                              artist_id="francisco_toledo_mx", artist_resolution="master",
                              artist_country_birth="MX"))
        rows.append(_resolved("Francisco Toledo", lot_url=f"es{i}", dedupe_key=f"es{i}",
                              artist_id="francisco_toledo_es", artist_resolution="master",
                              artist_country_birth="ES"))
    _write(silver / "lots.jsonl", rows)
    build_insights.build_insights()
    artists = _read(goldd / "agg_artist_metrics.jsonl")
    assert len(artists) == 2
    assert {a["country_birth"] for a in artists} == {"MX", "ES"}


def test_non_authors_never_reach_the_ranking(gold):
    """attribution_type de Silver decide, no un prefijo recalculado en Gold."""
    silver, _, goldd = gold
    rows = []
    for i in range(4):
        rows.append(_resolved("Escuela Española S. XVII", lot_url=f"e{i}",
                              dedupe_key=f"e{i}", attribution_type="escuela"))
        rows.append(_resolved("Anónimo", lot_url=f"a{i}", dedupe_key=f"a{i}",
                              attribution_type="anonimo"))
        rows.append(_resolved("Fernando Botero", lot_url=f"b{i}", dedupe_key=f"b{i}"))
    _write(silver / "lots.jsonl", rows)
    build_insights.build_insights()
    names = {a["artist_name"] for a in _read(goldd / "agg_artist_metrics.jsonl")}
    assert names == {"Fernando Botero"}


def test_country_comes_from_master_not_from_house_free_text(gold):
    """artist_country (texto libre de la casa) no puede conceder pais.

    Solo lo hace artist_country_birth, que escribe el maestro. El campo crudo
    esta poblado en el 2% de los lotes y mezcla ciudades con paises.
    """
    silver, _, goldd = gold
    _write(
        silver / "lots.jsonl",
        [
            _resolved("Artista Sin Ficha", lot_url=f"x{i}", dedupe_key=f"x{i}",
                      artist_country="Colombia")
            for i in range(3)
        ],
    )
    build_insights.build_insights()
    artist = _read(goldd / "agg_artist_metrics.jsonl")[0]
    assert artist["country_birth"] is None
    assert artist["nationalities"] == []


def test_country_metrics_keep_unresolved_visible(gold):
    """La fila de no resueltos existe: ocultarla falsearia la cobertura."""
    silver, _, goldd = gold
    rows = [
        _resolved("Fernando Botero", lot_url=f"b{i}", dedupe_key=f"b{i}",
                  artist_id="fernando_botero", artist_resolution="master",
                  artist_country_birth="CO", artist_nationalities=["CO"])
        for i in range(3)
    ]
    rows += [
        _resolved("Artista Sin Ficha", lot_url=f"x{i}", dedupe_key=f"x{i}")
        for i in range(3)
    ]
    _write(silver / "lots.jsonl", rows)
    build_insights.build_insights()
    countries = {c["country"]: c for c in _read(goldd / "agg_country_metrics.jsonl")}
    assert countries["CO"]["lots_offered"] == 3
    assert countries["CO"]["country_es"] == "Colombia"
    assert countries["CO"]["top_artist"] == "Fernando Botero"
    assert None in countries, "los no resueltos deben verse, no ocultarse"
    assert countries[None]["lots_offered"] == 3


def test_country_lots_are_counted_once(gold):
    """Un lote suma en un solo pais aunque el artista tenga doble nacionalidad.

    Por eso el agregado va por pais de NACIMIENTO. Un agregado por nacionalidad
    seria no aditivo y los totales por pais no cuadrarian con los de la casa.
    """
    silver, _, goldd = gold
    _write(
        silver / "lots.jsonl",
        [
            _resolved("Alejandro Obregón", lot_url=f"o{i}", dedupe_key=f"o{i}",
                      artist_id="alejandro_obregon", artist_resolution="master",
                      artist_country_birth="ES", artist_nationalities=["CO", "ES"])
            for i in range(4)
        ],
    )
    build_insights.build_insights()
    countries = _read(goldd / "agg_country_metrics.jsonl")
    assert sum(c["lots_offered"] for c in countries) == 4
    assert {c["country"] for c in countries} == {"ES"}
    artist = _read(goldd / "agg_artist_metrics.jsonl")[0]
    assert artist["nationalities"] == ["CO", "ES"]


def test_stats_report_country_coverage(gold):
    silver, _, _ = gold
    _write(
        silver / "lots.jsonl",
        [
            _resolved("Fernando Botero", lot_url=f"b{i}", dedupe_key=f"b{i}",
                      artist_id="fernando_botero", artist_resolution="master",
                      artist_country_birth="CO")
            for i in range(3)
        ]
        + [
            _resolved("Artista Sin Ficha", lot_url=f"x{i}", dedupe_key=f"x{i}")
            for i in range(3)
        ],
    )
    stats = build_insights.build_insights()
    assert stats["artists_ranked"] == 2
    assert stats["artists_with_country"] == 1
    assert stats["country_coverage_rate"] == 0.5

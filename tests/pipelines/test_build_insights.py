"""Tests de pipelines/gold/build_insights.py.

Cubren sobre todo las reglas que, si se rompen, corrompen el informe en
silencio: mezclar monedas, contar como vendido lo que no lo esta, y colar
escuelas/atribuciones en el ranking de artistas.
"""

import json

import pytest

from pipelines.gold import build_insights


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

#!/usr/bin/env python3
"""
Analytics report from Gold layer only.
Reads data/gold/*.jsonl and writes analytics_report.json + rich HTML with Plotly.
"""

from __future__ import annotations

import json
from pathlib import Path

from pipelines.analytics.render_html import write_html

ROOT = Path(__file__).resolve().parents[2]
GOLD_ROOT = ROOT / "data" / "gold"


def load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            out.append(json.loads(line))
    return out


def run_report() -> dict:
    house_path = GOLD_ROOT / "agg_house_metrics.jsonl"
    auction_path = GOLD_ROOT / "agg_auction_metrics.jsonl"
    by_year_path = GOLD_ROOT / "agg_lots_by_year.jsonl"
    by_year_house_path = GOLD_ROOT / "agg_lots_by_year_by_house.jsonl"

    house_metrics = load_jsonl(house_path)
    if not house_metrics:
        raise FileNotFoundError(
            f"Gold house metrics not found: {house_path}. Run pipelines/gold/build_gold.py first."
        )

    auction_metrics = load_jsonl(auction_path) if auction_path.exists() else []
    by_year = load_jsonl(by_year_path) if by_year_path.exists() else []
    by_year_by_house = load_jsonl(by_year_house_path) if by_year_house_path.exists() else []

    quality_flags = load_jsonl(GOLD_ROOT / "quality_flags.jsonl")

    # Agregados de segundo nivel (pipelines/gold/build_insights.py). Son
    # opcionales: si no se han construido, el informe se degrada y omite esas
    # secciones en vez de fallar.
    artists = load_jsonl(GOLD_ROOT / "agg_artist_metrics.jsonl")
    countries = load_jsonl(GOLD_ROOT / "agg_country_metrics.jsonl")
    country_year = load_jsonl(GOLD_ROOT / "agg_country_year_metrics.jsonl")
    generations = load_jsonl(GOLD_ROOT / "agg_artist_generation_metrics.jsonl")
    categories = load_jsonl(GOLD_ROOT / "agg_category_metrics.jsonl")
    months = load_jsonl(GOLD_ROOT / "agg_month_metrics.jsonl")
    price_dist_rows = load_jsonl(GOLD_ROOT / "agg_price_distribution.jsonl")
    est_rows = load_jsonl(GOLD_ROOT / "agg_estimate_accuracy.jsonl")

    total_lots = sum(r.get("lots_offered", 0) for r in house_metrics)
    total_sold = sum(r.get("lots_sold", 0) for r in house_metrics)
    # Se suma EUR convertido, NUNCA nativo: cada casa cotiza en su moneda y
    # sumar COP con EUR fue el error que inflaba este KPI unas 3500 veces.
    total_revenue = sum(r.get("revenue_eur", 0) for r in house_metrics)
    sell_through_pct = (total_sold / total_lots * 100) if total_lots else 0
    avg_sold = (total_revenue / total_sold) if total_sold else None

    # Cobertura del maestro de artistas. Se publica aunque sea 0: si el filtro
    # por pais aparece vacio, el informe debe decir por que en vez de parecer
    # roto. Ver pipelines/config/artists/README.md.
    artists_with_country = sum(1 for r in artists if r.get("country_birth"))
    artist_coverage = {
        "artists_ranked": len(artists),
        "artists_with_country": artists_with_country,
        "country_coverage_pct": round(artists_with_country / len(artists) * 100, 1)
        if artists
        else 0.0,
        "countries": sum(1 for r in countries if r.get("country")),
    }

    report = {
        "source": str(GOLD_ROOT),
        "summary": {
            "total_houses": len(house_metrics),
            "total_lots": total_lots,
            "total_sold": total_sold,
            "total_unsold": total_lots - total_sold,
            "sell_through_pct": round(sell_through_pct, 1),
            "total_revenue_eur": round(total_revenue, 2),
            "avg_sold_price_eur": round(avg_sold, 2) if avg_sold is not None else None,
        },
        "quality_flags": quality_flags,
        "artist_coverage": artist_coverage,
        # Los agregados por pais NO aplican el corte de lotes vendidos del
        # ranking, asi que suman mas lotes que la tabla de artistas. El informe
        # publica la diferencia en vez de dejar que parezca un error de suma.
        "country_lots_below_rank_cutoff": max(
            0,
            sum(r.get("lots_offered", 0) for r in countries)
            - sum(r.get("lots_offered", 0) for r in artists),
        ),
        "by_house": [
            {
                "house_slug": r.get("house_slug"),
                "lots_offered": r.get("lots_offered", 0),
                "lots_sold": r.get("lots_sold", 0),
                "sell_through_rate": r.get("sell_through_rate"),
                "currency": r.get("currency"),
                "revenue_native": r.get("revenue_native", 0),
                "revenue_eur": r.get("revenue_eur", 0),
                "avg_sold_price_native": r.get("avg_sold_price_native"),
                "avg_sold_price_eur": r.get("avg_sold_price_eur"),
            }
            for r in house_metrics
        ],
        "by_auction": [],
        "by_year": [],
        "by_year_by_house": [],
        "by_artist": artists,
        "by_country": countries,
        "by_country_year": country_year,
        "by_generation": generations,
        "by_category": categories,
        "by_month": months,
        "price_distribution": price_dist_rows[0] if price_dist_rows else None,
        "estimate_accuracy": est_rows[0] if est_rows else None,
    }

    if by_year:
        report["by_year"] = [
            {
                "year": r.get("year"),
                "lots_offered": r.get("lots_offered", 0),
                "lots_sold": r.get("lots_sold", 0),
                "sell_through_rate": r.get("sell_through_rate"),
                "revenue_eur": r.get("revenue_eur", 0),
            }
            for r in by_year
        ]

    if by_year_by_house:
        report["by_year_by_house"] = [
            {
                "year": r.get("year"),
                "house_slug": r.get("house_slug"),
                "lots_offered": r.get("lots_offered", 0),
                "lots_sold": r.get("lots_sold", 0),
                "sell_through_rate": r.get("sell_through_rate"),
                "revenue_eur": r.get("revenue_eur", 0),
            }
            for r in by_year_by_house
        ]

    if auction_metrics:
        report["by_auction"] = [
            {
                "house_slug": r.get("house_slug"),
                "auction_id": r.get("auction_id"),
                "auction_title": r.get("auction_title"),
                "auction_start_date": r.get("auction_start_date"),
                "lots": r.get("lots", 0),
                "sold": r.get("sold", 0),
                "sell_through_pct": r.get("sell_through_pct"),
                "revenue_eur": r.get("revenue_eur", 0),
            }
            for r in auction_metrics
        ]

    return report



def main() -> None:
    GOLD_ROOT.mkdir(parents=True, exist_ok=True)
    report = run_report()

    out_json = GOLD_ROOT / "analytics_report.json"
    out_json.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Report JSON: {out_json}")

    # El detalle lote a lote alimenta las descargas del HTML, pero NO entra en
    # analytics_report.json: son 13.733 filas que multiplicarian por cinco el
    # tamanio de un fichero pensado para leerse de un vistazo. Quien lo quiera
    # en bruto tiene data/gold/lot_details.jsonl.
    report_html = dict(report)
    report_html["lot_details"] = load_jsonl(GOLD_ROOT / "lot_details.jsonl")

    out_html = GOLD_ROOT / "analytics_report.html"
    write_html(report_html, out_html)
    print(f"Report HTML: {out_html}")

    print("\n--- Resumen ---")
    s = report["summary"]
    print(f"  Casas:           {s['total_houses']}")
    print(f"  Lotes totales:   {s['total_lots']}")
    print(f"  Vendidos:        {s['total_sold']} ({s['sell_through_pct']}%)")
    print(f"  Ingresos totales: {s['total_revenue_eur']:,.2f} €")
    print(f"  Precio medio:   {s['avg_sold_price_eur']} €")


if __name__ == "__main__":
    main()

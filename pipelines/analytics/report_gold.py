#!/usr/bin/env python3
"""
Analytics report from Gold layer only.
Reads data/gold/*.jsonl and writes analytics_report.json + rich HTML with Plotly.
"""

from __future__ import annotations

import json
from pathlib import Path

from pipelines.shared.fx import fx_note

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

    total_lots = sum(r.get("lots_offered", 0) for r in house_metrics)
    total_sold = sum(r.get("lots_sold", 0) for r in house_metrics)
    # Se suma EUR convertido, NUNCA nativo: cada casa cotiza en su moneda y
    # sumar COP con EUR fue el error que inflaba este KPI unas 3500 veces.
    total_revenue = sum(r.get("revenue_eur", 0) for r in house_metrics)
    sell_through_pct = (total_sold / total_lots * 100) if total_lots else 0
    avg_sold = (total_revenue / total_sold) if total_sold else None

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


def house_row_html(h: dict) -> str:
    """Fila de la tabla por casa: moneda nativa y EUR lado a lado.

    Se muestran ambas en la misma fila para que la conversion sea auditable de
    un vistazo y ninguna cifra monetaria aparezca sin su unidad.
    """
    currency = h.get("currency") or "?"
    native = h.get("revenue_native") or 0
    eur = h.get("revenue_eur") or 0
    avg_native = h.get("avg_sold_price_native")
    avg_eur = h.get("avg_sold_price_eur")
    rate = round((h.get("sell_through_rate") or 0) * 100, 1)
    avg_cell = (
        f"{avg_native:,.0f} {currency}<br><span class='muted'>≈ {avg_eur:,.0f} €</span>"
        if avg_native is not None and avg_eur is not None
        else "-"
    )
    return (
        f"<tr><td>{h['house_slug']}</td><td>{h['lots_offered']:,}</td>"
        f"<td>{h['lots_sold']:,}</td><td>{rate}%</td>"
        f"<td>{native:,.0f} {currency}</td>"
        f"<td class='muted'>≈ {eur:,.0f} €</td>"
        f"<td>{avg_cell}</td></tr>"
    )


def build_flags_html(flags: list[dict]) -> str:
    """Panel de avisos de calidad, visible arriba y no como nota al pie."""
    if not flags:
        return ""
    order = {"critical": 0, "warn": 1, "info": 2}
    icon = {"critical": "🔴", "warn": "⚠️", "info": "ℹ️"}
    cards = []
    for f in sorted(flags, key=lambda x: order.get(x.get("level"), 9)):
        level = f.get("level", "info")
        cards.append(
            f"<div class='flag flag-{level}'>"
            f"<span class='flag-icon'>{icon.get(level, '•')}</span>"
            f"<span>{f.get('message', '')}</span></div>"
        )
    return (
        "<div class='flags-panel'>"
        "<h2>Avisos de calidad de datos</h2>"
        + "".join(cards)
        + "</div>"
    )


def write_html(report: dict, path: Path) -> None:
    s = report["summary"]
    flags_html = build_flags_html(report.get("quality_flags", []))

    # Prepare data for Plotly
    auctions = report.get("by_auction", [])
    
    # Data for Treemap (House -> Auction)
    treemap_labels = ["All"]
    treemap_parents = [""]
    treemap_values = [s["total_revenue_eur"]]
    treemap_text = [f"Total: {s['total_revenue_eur']:,.0f} €"]
    
    # Add houses
    for h in report["by_house"]:
        slug = h["house_slug"]
        treemap_labels.append(slug)
        treemap_parents.append("All")
        treemap_values.append(h["revenue_eur"])
        treemap_text.append(f"{slug}<br>Rev: {h['revenue_eur']:,.0f} € (convertido)")
        
    # Add top auctions (limit to avoid clutter, e.g., top 50 by revenue)
    sorted_auctions = sorted(auctions, key=lambda x: x["revenue_eur"], reverse=True)
    for a in sorted_auctions[:50]:
        aid = a["auction_id"]
        house = a["house_slug"]
        # Unique ID for chart
        label = f"{aid[:15]}..." 
        treemap_labels.append(label)
        treemap_parents.append(house)
        treemap_values.append(a["revenue_eur"])
        treemap_text.append(f"{a['auction_title']}<br>Rev: {a['revenue_eur']:,.0f} €")

    treemap_data = [{
        "type": "treemap",
        "labels": treemap_labels,
        "parents": treemap_parents,
        "values": treemap_values,
        "text": treemap_text,
        "textinfo": "label+value+percent parent",
        "hoverinfo": "text",
        "branchvalues": "total"
    }]

    # Data for Bar Chart (Top 20 Auctions by Revenue)
    top_20 = sorted_auctions[:20]
    bar_data = [{
        "x": [a["auction_id"] for a in top_20],
        "y": [a["revenue_eur"] for a in top_20],
        "type": "bar",
        "text": [a["auction_title"] for a in top_20],
        "marker": {"color": "#16213e"}
    }]

    # Data for Histogram (Sell-through rate distribution)
    hist_data = [{
        "x": [a["sell_through_pct"] for a in auctions],
        "type": "histogram",
        "marker": {"color": "#0f3460"},
        "nbinsx": 20
    }]

    # Data for Scatter (Lots vs Revenue)
    scatter_data = []
    houses = set(a["house_slug"] for a in auctions)
    for h in houses:
        house_auctions = [a for a in auctions if a["house_slug"] == h]
        scatter_data.append({
            "x": [a["lots"] for a in house_auctions],
            "y": [a["revenue_eur"] for a in house_auctions],
            "mode": "markers",
            "type": "scatter",
            "name": h,
            "text": [a["auction_title"] for a in house_auctions],
            "marker": {"size": 10, "opacity": 0.7}
        })

    # Data for Lotes por año (bar chart)
    by_year = report.get("by_year", [])
    year_bar_data = [{
        "x": [r["year"] for r in by_year],
        "y": [r["lots_offered"] for r in by_year],
        "type": "bar",
        "name": "Lotes ofertados",
        "marker": {"color": "#16213e"},
        "text": [f"{r['lots_offered']} lotes" for r in by_year],
        "textposition": "outside",
    }] if by_year else []

    by_year_rows = "".join(
        f"<tr><td>{r['year']}</td><td>{r['lots_offered']}</td><td>{r['lots_sold']}</td>"
        f"<td>{round((r.get('sell_through_rate') or 0) * 100, 1)}%</td><td>{r.get('revenue_eur', 0):,.0f} €</td></tr>"
        for r in by_year
    )

    # Lotes por año por casa (stacked bar + table)
    by_year_by_house = report.get("by_year_by_house", [])
    years_ordered = sorted(
        {r["year"] for r in by_year_by_house},
        key=lambda y: (y == "unknown", y),
    )
    houses_ordered = sorted({r["house_slug"] for r in by_year_by_house})
    year_house_map = {(r["year"], r["house_slug"]): r for r in by_year_by_house}
    year_house_bar_traces = []
    colors = ["#16213e", "#0f3460", "#533483", "#e94560"]
    for i, house in enumerate(houses_ordered):
        y_vals = [year_house_map.get((yr, house), {}).get("lots_offered", 0) for yr in years_ordered]
        year_house_bar_traces.append({
            "x": years_ordered,
            "y": y_vals,
            "type": "bar",
            "name": house,
            "marker": {"color": colors[i % len(colors)]},
        })
    by_year_by_house_rows = "".join(
        f"<tr><td>{r['year']}</td><td>{r['house_slug']}</td><td>{r['lots_offered']}</td><td>{r['lots_sold']}</td>"
        f"<td>{round((r.get('sell_through_rate') or 0) * 100, 1)}%</td><td>{r.get('revenue_eur', 0):,.0f} €</td></tr>"
        for r in by_year_by_house
    )
    html = f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="utf-8" />
  <title>Analítica Gold - Dashboard</title>
  <script src="https://cdn.plot.ly/plotly-2.27.0.min.js"></script>
  <style>
    body {{ font-family: system-ui, sans-serif; margin: 0; background: #f0f2f5; color: #333; }}
    .container {{ max_width: 1200px; margin: 0 auto; padding: 2rem; }}
    h1 {{ color: #1a1a2e; margin-bottom: 0.5rem; }}
    .meta {{ color: #666; font-size: 0.9rem; margin-bottom: 2rem; }}
    
    .kpi-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 1.5rem; margin-bottom: 2rem; }}
    .kpi-card {{ background: #fff; padding: 1.5rem; border-radius: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.05); text-align: center; }}
    .kpi-value {{ display: block; font-size: 2rem; font-weight: 700; color: #16213e; margin-bottom: 0.5rem; }}
    .kpi-label {{ color: #666; font-size: 0.9rem; text-transform: uppercase; letter-spacing: 0.5px; }}
    .kpi-note {{ display: block; color: #999; font-size: 0.72rem; margin-top: 0.35rem; font-style: italic; }}
    .muted {{ color: #777; font-weight: 400; }}
    .footer-note {{ color: #777; font-size: 0.82rem; font-style: italic; margin-top: 1.5rem; padding-top: 1rem; border-top: 1px solid #ddd; }}

    .flags-panel {{ background: #fff; padding: 1.25rem 1.5rem; border-radius: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.05); margin-bottom: 2rem; }}
    .flags-panel h2 {{ margin-bottom: 0.9rem; }}
    .flag {{ display: flex; gap: 0.6rem; align-items: flex-start; padding: 0.6rem 0.8rem; border-radius: 8px; margin-bottom: 0.5rem; font-size: 0.88rem; line-height: 1.45; }}
    .flag-icon {{ flex: 0 0 auto; }}
    .flag-critical {{ background: #fdecea; border-left: 4px solid #d93025; color: #8c1d16; }}
    .flag-warn {{ background: #fff8e1; border-left: 4px solid #f4b400; color: #7a5900; }}
    .flag-info {{ background: #eef3fb; border-left: 4px solid #4285f4; color: #1b3a66; }}

    .chart-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 2rem; margin-bottom: 2rem; }}
    .chart-card {{ background: #fff; padding: 1.5rem; border-radius: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.05); }}
    .chart-full {{ grid-column: 1 / -1; }}
    h2 {{ font-size: 1.2rem; margin-top: 0; margin-bottom: 1rem; color: #444; }}

    table {{ width: 100%; border-collapse: collapse; margin-top: 1rem; font-size: 0.9rem; }}
    th, td {{ padding: 0.8rem; text-align: left; border-bottom: 1px solid #eee; }}
    th {{ font-weight: 600; color: #555; }}
    tr:hover {{ background: #f9f9f9; }}
    
    @media (max-width: 768px) {{
        .chart-grid {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
  <div class="container">
    <h1>Dashboard de Subastas (Gold)</h1>
    <p class="meta">Origen de datos: {report['source']}</p>
    
    <div class="kpi-grid">
      <div class="kpi-card">
        <span class="kpi-value">{s['total_houses']}</span>
        <span class="kpi-label">Casas</span>
      </div>
      <div class="kpi-card">
        <span class="kpi-value">{len(auctions)}</span>
        <span class="kpi-label">Subastas</span>
      </div>
      <div class="kpi-card">
        <span class="kpi-value">{s['total_lots']:,}</span>
        <span class="kpi-label">Lotes</span>
      </div>
      <div class="kpi-card">
        <span class="kpi-value">{s['sell_through_pct']}%</span>
        <span class="kpi-label">Tasa Venta</span>
      </div>
      <div class="kpi-card">
        <span class="kpi-value">{s['total_revenue_eur']/1e6:,.1f}M €</span>
        <span class="kpi-label">Ingresos</span>
        <span class="kpi-note">convertido, aprox.</span>
      </div>
    </div>

    {flags_html}

    <div class="chart-grid">
      <div class="chart-card chart-full">
        <h2>Mapa de Ingresos (Treemap: Casa > Subasta)</h2>
        <div id="treemap"></div>
      </div>
      
      <div class="chart-card">
        <h2>Top 20 Subastas por Ingresos</h2>
        <div id="barChart"></div>
      </div>
      
      <div class="chart-card">
        <h2>Distribución de Tasa de Venta</h2>
        <div id="histogram"></div>
      </div>

      <div class="chart-card chart-full">
        <h2>Relación Lotes vs Ingresos (Scatter)</h2>
        <div id="scatter"></div>
      </div>

      <div class="chart-card chart-full">
        <h2>Lotes por año (subastas)</h2>
        <div id="yearBar"></div>
      </div>

      <div class="chart-card chart-full">
        <h2>Lotes por año y por casa de subasta</h2>
        <div id="yearHouseBar"></div>
      </div>
    </div>

    <div class="chart-card">
      <h2>Lotes por año (detalle)</h2>
      <table>
        <thead><tr><th>Año</th><th>Lotes ofertados</th><th>Vendidos</th><th>Tasa venta</th><th>Ingresos (€)</th></tr></thead>
        <tbody>
          {by_year_rows}
        </tbody>
      </table>
    </div>

    <div class="chart-card">
      <h2>Lotes por año y por casa (detalle)</h2>
      <table>
        <thead><tr><th>Año</th><th>Casa</th><th>Lotes</th><th>Vendidos</th><th>Tasa</th><th>Ingresos (€)</th></tr></thead>
        <tbody>
          {by_year_by_house_rows}
        </tbody>
      </table>
    </div>

    <div class="chart-card">
      <h2>Detalle por Casa</h2>
      <table>
        <thead><tr><th>Casa</th><th>Lotes</th><th>Vendidos</th><th>Tasa</th><th>Ingresos (moneda nativa)</th><th>Ingresos (≈ EUR)</th><th>Precio medio</th></tr></thead>
        <tbody>
          {''.join(house_row_html(h) for h in report["by_house"])}
        </tbody>
      </table>
    </div>

    <p class="footer-note">{fx_note()}</p>
  </div>

  <script>
    Plotly.newPlot('treemap', {json.dumps(treemap_data)}, {{margin: {{t:0, l:0, r:0, b:0}}, height: 500}});
    Plotly.newPlot('barChart', {json.dumps(bar_data)}, {{margin: {{t:20, l:40, r:20, b:40}}, height: 400}});
    Plotly.newPlot('histogram', {json.dumps(hist_data)}, {{margin: {{t:20, l:40, r:20, b:40}}, height: 400, xaxis: {{title: 'Tasa de Venta (%)'}}, yaxis: {{title: 'Frecuencia'}} }});
    Plotly.newPlot('scatter', {json.dumps(scatter_data)}, {{margin: {{t:20, l:40, r:20, b:40}}, height: 500, xaxis: {{title: 'Lotes Ofertados'}}, yaxis: {{title: 'Ingresos (€)'}}, hovermode: 'closest'}});
    if ({len(year_bar_data)}) Plotly.newPlot('yearBar', {json.dumps(year_bar_data)}, {{margin: {{t:20, l:40, r:20, b:40}}, height: 400, xaxis: {{title: 'Año'}}, yaxis: {{title: 'Lotes'}}}});
    if ({len(year_house_bar_traces)}) Plotly.newPlot('yearHouseBar', {json.dumps(year_house_bar_traces)}, {{barmode: 'stack', margin: {{t:20, l:40, r:20, b:40}}, height: 400, xaxis: {{title: 'Año'}}, yaxis: {{title: 'Lotes'}}}});
  </script>
</body>
</html>
"""
    path.write_text(html, encoding="utf-8")


def main() -> None:
    GOLD_ROOT.mkdir(parents=True, exist_ok=True)
    report = run_report()

    out_json = GOLD_ROOT / "analytics_report.json"
    out_json.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Report JSON: {out_json}")

    out_html = GOLD_ROOT / "analytics_report.html"
    write_html(report, out_html)
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

#!/usr/bin/env python3
"""Informe de la capa FX: escribe data/gold/fx_report.html.

Es el panel de control de la conversion a euros. Existe aparte del informe
principal porque responde a otra pregunta: no "cuanto se vendio" sino "cuanto
se torcia la cifra cuando 164 meses compartian una sola tasa".

Los graficos son SVG generado en Python, sin libreria de cliente, por la misma
razon que build_artifact.py: un Artifact de Claude bloquea todo host externo.

Ejecutar como modulo desde la raiz:  python -m pipelines.analytics.build_fx_report
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List

import yaml

from pipelines.shared.fx import load_fx, load_fx_history

ROOT = Path(__file__).resolve().parents[2]
GOLD = ROOT / "data" / "gold"
HOUSE_METRICS = GOLD / "agg_house_metrics.jsonl"
TEMPLATE = Path(__file__).resolve().parent / "templates" / "fx_dashboard.html"
OUTPUT = GOLD / "fx_report.html"

# Geometria del grafico principal.
W, H = 1000.0, 340.0
PAD_L, PAD_R, PAD_T, PAD_B = 58.0, 18.0, 24.0, 34.0
Y_LO, Y_HI = 0.75, 1.90


def _x(i: int, n: int) -> float:
    return PAD_L + i * (W - PAD_L - PAD_R) / max(n - 1, 1)


def _y(v: float) -> float:
    return PAD_T + (Y_HI - v) * (H - PAD_T - PAD_B) / (Y_HI - Y_LO)


def _path(vals: List[float]) -> str:
    return "M" + " L".join(f"{_x(i, len(vals)):.1f},{_y(v):.1f}" for i, v in enumerate(vals))


def _area(vals: List[float]) -> str:
    n = len(vals)
    return f"{_path(vals)} L{_x(n-1, n):.1f},{_y(1.0):.1f} L{_x(0, n):.1f},{_y(1.0):.1f} Z"


def _hero(months: List[str], cop_ratio: List[float], usd_ratio: List[float]) -> str:
    """Ratio de la tasa del mes frente a la tasa estatica.

    Se grafica el RATIO y no la tasa cruda a proposito: el cruce por 1,00x es
    justo donde la tasa unica pasaba de infravalorar a inflar el importe.
    """
    n = len(months)
    grid = "".join(
        f'<line x1="{PAD_L}" y1="{_y(v):.1f}" x2="{W-PAD_R}" y2="{_y(v):.1f}" class="g"/>'
        f'<text x="{PAD_L-9}" y="{_y(v)+3.5:.1f}" class="ax" text-anchor="end">{v:.2f}&#215;</text>'
        for v in (0.8, 1.0, 1.2, 1.4, 1.6, 1.8)
    )
    xlab = "".join(
        f'<text x="{_x(i, n):.1f}" y="{H-12}" class="ax" text-anchor="middle">{m[:4]}</text>'
        for i, m in enumerate(months)
        if m.endswith("-01") and int(m[:4]) % 2 == 1
    )
    hi = max(range(n), key=lambda i: cop_ratio[i])
    lo = min(range(n), key=lambda i: cop_ratio[i])
    return f"""<svg viewBox="0 0 {W:.0f} {H:.0f}" class="chart" role="img" aria-label="Ratio de la tasa mensual frente a la tasa estatica entre 2013 y 2026">
<defs><linearGradient id="cf" x1="0" y1="0" x2="0" y2="1">
<stop offset="0" stop-color="var(--cop)" stop-opacity=".30"/><stop offset="1" stop-color="var(--cop)" stop-opacity="0"/>
</linearGradient></defs>
{grid}
<line x1="{PAD_L}" y1="{_y(1.0):.1f}" x2="{W-PAD_R}" y2="{_y(1.0):.1f}" class="base"/>
<path d="{_area(cop_ratio)}" fill="url(#cf)"/>
<path d="{_path(usd_ratio)}" class="ln usd"/>
<path d="{_path(cop_ratio)}" class="ln cop"/>
<circle cx="{_x(hi, n):.1f}" cy="{_y(cop_ratio[hi]):.1f}" r="4" class="dot cop"/>
<circle cx="{_x(lo, n):.1f}" cy="{_y(cop_ratio[lo]):.1f}" r="4" class="dot cop"/>
<text x="{_x(hi, n)+9:.1f}" y="{_y(cop_ratio[hi])+4:.1f}" class="note">{cop_ratio[hi]:.2f}&#215; &#183; {months[hi]}</text>
<text x="{_x(lo, n)-9:.1f}" y="{_y(cop_ratio[lo])+4:.1f}" class="note" text-anchor="end">{cop_ratio[lo]:.2f}&#215; &#183; {months[lo]}</text>
{xlab}
</svg>"""


def _spark(vals: List[float], cls: str) -> str:
    w, h = 150.0, 34.0
    lo, hi = min(vals), max(vals)
    rng = (hi - lo) or 1.0
    pts = " L".join(
        f"{i*w/(len(vals)-1):.1f},{h-2-(v-lo)/rng*(h-6):.1f}" for i, v in enumerate(vals)
    )
    end_y = h - 2 - (vals[-1] - lo) / rng * (h - 6)
    return (
        f'<svg viewBox="0 0 {w:.0f} {h:.0f}" class="spark" aria-hidden="true">'
        f'<path d="M{pts}" class="ln {cls}"/>'
        f'<circle cx="{w:.1f}" cy="{end_y:.1f}" r="2.6" class="dot {cls}"/></svg>'
    )


def _coverage_pct(houses: List[Dict]) -> str:
    """% de lotes vendidos convertidos con la tasa de su mes."""
    monthly = sum((h.get("fx_method_counts") or {}).get("monthly", 0) for h in houses)
    fallback = sum(h.get("fx_fallback_lots", 0) for h in houses)
    total = monthly + fallback
    if not total:
        return "0"
    pct = 100.0 * monthly / total
    # 99,9% no debe redondearse a 100: la diferencia es justo lo que hay que ver.
    return "100" if monthly == total else f"{pct:.1f}".replace(".", ",")


def _rows(houses: List[Dict], series: Dict[str, List[float]]) -> str:
    out = ""
    for h in sorted(houses, key=lambda x: -x["revenue_eur"]):
        cur = h.get("currency") or "EUR"
        cls = cur.lower()
        vals = series.get(cur)
        spark = (
            _spark(vals, cls)
            if vals
            else '<span class="flat">tasa 1.0 &#183; sin conversi&#243;n</span>'
        )
        fb = h.get("fx_fallback_lots", 0)
        pill = (
            f'<span class="pill warn">{fb} est&#225;tica</span>'
            if fb
            else '<span class="pill ok">todo mensual</span>'
        )
        monthly = (h.get("fx_method_counts") or {}).get("monthly", 0)
        out += (
            f'<tr><td class="hn"><span class="sw {cls}"></span>'
            f'{h["house_slug"].replace("_", " ")}</td>'
            f'<td><span class="cur {cls}">{cur}</span></td>'
            f'<td class="n">{h["revenue_native"]:,.0f}</td>'
            f'<td class="n strong">{h["revenue_eur"]:,.0f}</td>'
            f'<td class="n">{h["lots_sold"]:,}</td>'
            f'<td class="n">{monthly:,}</td>'
            f"<td>{pill}</td><td class=\"sp\">{spark}</td></tr>"
        )
    return out


def main() -> None:
    hist = load_fx_history()
    static = load_fx()
    rates = hist["rates_to_eur"]
    months = sorted(rates["COP"])

    cop = [rates["COP"][m] for m in months]
    usd = [rates["USD"][m] for m in months]
    # El ratio frente a la tasa estatica es el dato con significado: 1,00x es
    # exactamente lo que hacia el pipeline antes de fx_history.yaml.
    s_cop = static["rates_to_eur"]["COP"]
    s_usd = static["rates_to_eur"]["USD"]
    cop_ratio = [round(v / s_cop, 4) for v in cop]
    usd_ratio = [round(v / s_usd, 4) for v in usd]

    houses = [json.loads(l) for l in HOUSE_METRICS.read_text(encoding="utf-8").splitlines() if l.strip()]

    html = TEMPLATE.read_text(encoding="utf-8").format(
        gen=hist.get("generated_at", "?"),
        static=str(static.get("as_of", "?")),
        hero=_hero(months, cop_ratio, usd_ratio),
        rows=_rows(houses, {"COP": cop, "USD": usd}),
        tot_eur=f"{sum(h['revenue_eur'] for h in houses)/1e6:.1f}",
        tot_fb=sum(h.get("fx_fallback_lots", 0) for h in houses),
        cov=_coverage_pct(houses),
        last=months[-1],
    )
    OUTPUT.write_text(html, encoding="utf-8")
    print(f"[fx-report] wrote: {OUTPUT} ({len(html)//1024} KB, {len(months)} meses)")


if __name__ == "__main__":
    main()

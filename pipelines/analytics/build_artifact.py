#!/usr/bin/env python3
"""Genera una version del informe apta para publicar como Artifact de Claude.

Por que existe, en vez de publicar analytics_report.html tal cual: un Artifact
sirve la pagina bajo una CSP estricta que BLOQUEA cualquier host externo. El
informe local carga Plotly desde cdn.plot.ly y las fuentes desde Google Fonts,
asi que publicado tal cual saldria sin graficos y con la tipografia caida a la
del sistema.

Aqui se resuelve sin renunciar a nada:
  - los 3 graficos se dibujan como SVG generado en Python (no hace falta
    ninguna libreria en el cliente, y pesa ~20 KB en vez de los 3,5 MB de Plotly)
  - la tipografia usa stacks del sistema elegidas, no una webfont remota
  - todo el CSS y el JS van inline

Mantiene lo que hace util al informe: filtros, totalizador que reacciona al
filtro y descarga en CSV de lo filtrado (tabla y detalle lote a lote), para que
cualquiera pueda auditar las cifras en vez de creerselas.

Uso:
    python -m pipelines.analytics.build_artifact
    python -m pipelines.analytics.build_artifact --out ruta/al/fichero.html
"""

from __future__ import annotations

import argparse
import html
import json
from pathlib import Path

from pipelines.analytics.narrative import (
    CAVEAT_COUNTRY_IS_HOUSE,
    CAVEAT_FX_TIMESERIES,
    CAVEAT_GENERATIONS_COVERAGE,
    CAVEAT_MIN_LOTS,
    CAVEAT_PARETO_SCOPE,
    CAVEAT_SCATTER_LOWN,
    country_metrics_caveat,
    generation_bars,
    generation_coverage,
    heatmap_matrix,
    multi_house_kind,
    nationalities_es,
    pareto_points,
    scatter_points,
)
from pipelines.analytics.render_html import (
    HOUSE_COUNTRY,
    HOUSE_LABELS,
    MONTH_LABELS,
    pack_lot_details,
)
from pipelines.shared.fx import fx_note

ROOT = Path(__file__).resolve().parents[2]
GOLD_ROOT = ROOT / "data" / "gold"
DEFAULT_OUT = GOLD_ROOT / "artifact_report.html"

CATEGORY_LABELS = {
    "painting": "Pintura",
    "prints": "Grabado y múltiples",
    "decorative_arts": "Artes decorativas",
    "books_documents": "Libros y documentos",
    "other": "Otros / sin clasificar",
}

# Cuantos artistas se listan. Mas alla el HTML crece sin que nadie los lea:
# el detalle completo se descarga en CSV.
ARTIST_LIMIT = 200

# Cuantos puntos entran en el scatter SVG. Cada circulo son ~170 bytes de
# marcado, y el Artifact tiene un limite practico de tamanio; ademas, a 320
# unidades de ancho la cola larga se solapa en una mancha sin informacion. El
# recorte se declara al pie del grafico, con el volumen que deja fuera.
SCATTER_LIMIT = 600


def esc(v) -> str:
    return html.escape(str(v if v is not None else ""))


def num(v) -> str:
    return "—" if v is None else f"{v:,.0f}".replace(",", ".")


def eur(v, decimals: int = 0) -> str:
    if v is None:
        return "—"
    s = f"{v:,.{decimals}f}".replace(",", "@").replace(".", ",").replace("@", ".")
    return s + " €"


def pct(v, decimals: int = 1) -> str:
    return "—" if v is None else f"{v:.{decimals}f}".replace(".", ",") + "%"


def generation_coverage_block(generations: list[dict]) -> str:
    """Banda de cobertura equivalente a la del informe Plotly."""
    cov = generation_coverage(generations)
    if not cov["total_revenue_eur"] and not cov["total_artists"]:
        return ""
    dated_w = min(100.0, max(0.0, cov["dated_revenue_pct"]))
    missing_w = min(100.0, max(0.0, cov["missing_revenue_pct"]))
    return (
        "<div class='generation-coverage'>"
        "<div class='generation-coverage-head'>"
        "<span>Cobertura de fechas del ranking completo</span>"
        f"<strong>{esc(pct(cov['dated_revenue_pct']))} del volumen con década</strong>"
        "</div>"
        "<div class='generation-track' aria-hidden='true'>"
        f"<span class='generation-dated' style='width:{dated_w:.1f}%'></span>"
        f"<span class='generation-missing' style='width:{missing_w:.1f}%'></span>"
        "</div>"
        "<div class='generation-legend'>"
        "<span><i class='generation-key generation-key-dated'></i>"
        f"<strong>Con década</strong> {esc(eur(cov['dated_revenue_eur']))} · "
        f"{esc(num(cov['dated_artists']))} artistas</span>"
        "<span><i class='generation-key generation-key-missing'></i>"
        f"<strong>Sin fecha</strong> {esc(eur(cov['missing_revenue_eur']))} · "
        f"{esc(num(cov['missing_artists']))} artistas "
        f"({esc(pct(cov['missing_artists_pct']))})</span>"
        "</div></div>"
    )


def load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


# ---------------------------------------------------------------------------
# Graficos: SVG generado aqui, sin libreria en el cliente
# ---------------------------------------------------------------------------

# Geometria de los graficos, en unidades del viewBox. NO se usa
# preserveAspectRatio='none': estirar el SVG deforma tambien el texto y las
# etiquetas del eje salen aplastadas y solapadas unas sobre otras.
CH_W, CH_H = 320.0, 176.0
CH_PAD_B, CH_PAD_T = 26.0, 6.0
PLOT_H = CH_H - CH_PAD_B - CH_PAD_T


def _svg(inner: str) -> str:
    return (
        f"<svg class='chart' viewBox='0 0 {CH_W:.0f} {CH_H:.0f}' "
        f"preserveAspectRatio='xMidYMid meet' role='img'>{inner}</svg>"
    )


def _axis_labels(labels: list[str], n: int, width: float = CH_W,
                 y: float | None = None, x0: float = 0.0) -> str:
    """Etiquetas del eje X, saltando las que no caben.

    width/y/x0 se parametrizan porque el mapa de calor tiene geometria propia:
    con CH_W y CH_H fijos, sus etiquetas de anio saldrian calculadas sobre el
    ancho equivocado y no cuadrarian con las columnas.
    """
    y = CH_H - 9 if y is None else y
    slot = width / n
    # Cada etiqueta necesita ~26 unidades para no tocar a la vecina.
    step = max(1, int(26 / slot + 0.999))
    out = []
    for idx, lab in enumerate(labels):
        if idx % step and idx != n - 1:
            continue
        out.append(
            f"<text class='axis' x='{x0 + idx * slot + slot / 2:.2f}' "
            f"y='{y:.1f}' text-anchor='middle'>{esc(lab)}</text>"
        )
    return "".join(out)


def bar_chart(items, value_key, label_key, *, fmt=eur) -> str:
    """Barras verticales. Cada barra lleva su valor en el title (tooltip nativo)."""
    if not items:
        return ""
    top = max((i.get(value_key) or 0) for i in items) or 1
    n = len(items)
    slot = CH_W / n
    bw = max(2.0, slot * 0.66)
    parts = [
        f"<line class='base' x1='0' y1='{CH_H - CH_PAD_B:.1f}' "
        f"x2='{CH_W:.0f}' y2='{CH_H - CH_PAD_B:.1f}'/>"
    ]
    for idx, it in enumerate(items):
        v = it.get(value_key) or 0
        h = (v / top) * PLOT_H
        parts.append(
            f"<rect class='bar' x='{idx * slot + (slot - bw) / 2:.2f}' "
            f"y='{CH_H - CH_PAD_B - h:.2f}' width='{bw:.2f}' height='{h:.2f}' rx='1'>"
            f"<title>{esc(it.get(label_key))}: {esc(fmt(v))}</title></rect>"
        )
    parts.append(_axis_labels([str(i.get(label_key)) for i in items], n))
    return _svg("".join(parts))


def bar_line_chart(bars: list[dict], line: list[float], *, labels: list[str],
                   notes: list[tuple[int, str]] | None = None) -> str:
    """Barras con una linea de porcentaje acumulado sobre un eje derecho.

    El eje derecho es implicito: 0-100 mapeado a la altura de trazado. Es el
    Pareto; sin la linea, las barras solas no dicen cuanto se concentra.
    """
    if not bars:
        return ""
    top = max((b.get("value") or 0) for b in bars) or 1
    n = len(bars)
    slot = CH_W / n
    bw = max(2.0, slot * 0.62)
    base_y = CH_H - CH_PAD_B
    parts = [f"<line class='base' x1='0' y1='{base_y:.1f}' x2='{CH_W:.0f}' y2='{base_y:.1f}'/>"]
    for idx, b in enumerate(bars):
        v = b.get("value") or 0
        h = (v / top) * PLOT_H
        parts.append(
            f"<rect class='bar' x='{idx * slot + (slot - bw) / 2:.2f}' "
            f"y='{base_y - h:.2f}' width='{bw:.2f}' height='{h:.2f}' rx='1'>"
            f"<title>{esc(b.get('label'))}: {esc(eur(v))}</title></rect>"
        )
    pts = " ".join(
        f"{idx * slot + slot / 2:.2f},{base_y - (p / 100.0) * PLOT_H:.2f}"
        for idx, p in enumerate(line)
    )
    parts.append(f"<polyline class='cum' points='{pts}'/>")
    for idx, p in enumerate(line):
        cx = idx * slot + slot / 2
        cy = base_y - (p / 100.0) * PLOT_H
        parts.append(
            f"<circle class='cum-dot' cx='{cx:.2f}' cy='{cy:.2f}' r='2'>"
            f"<title>{esc(labels[idx])}: {p:.1f}% acumulado</title></circle>"
        )
    # Las anotaciones son la mitad del mensaje: un Pareto sin cifras escritas
    # es una curva que nadie retiene.
    for idx, text in (notes or []):
        if idx >= len(line):
            continue
        cx = idx * slot + slot / 2
        cy = base_y - (line[idx] / 100.0) * PLOT_H
        anchor = "end" if idx > n / 2 else "start"
        dx = -4 if anchor == "end" else 4
        parts.append(
            f"<text class='note' x='{cx + dx:.2f}' y='{cy - 5:.2f}' "
            f"text-anchor='{anchor}'>{esc(text)}</text>"
        )
    parts.append(_axis_labels(labels, n))
    return _svg("".join(parts))


# Geometria del scatter: mas alto que las barras porque un nube de puntos
# aplastada no se lee.
SC_W, SC_H = 320.0, 240.0
SC_PAD_L, SC_PAD_B, SC_PAD_T, SC_PAD_R = 34.0, 26.0, 8.0, 6.0


def scatter_chart(points: list[dict]) -> str:
    """Precio medio (y) contra lotes vendidos (x), area = volumen.

    Los dos ejes en logaritmo: en lineal, 9 de cada 10 artistas se apilan en la
    esquina inferior izquierda y el grafico no dice nada.
    """
    if not points:
        return ""
    import math

    xs = [p["x"] for p in points if p["x"] > 0]
    ys = [p["y"] for p in points if p["y"] > 0]
    if not xs or not ys:
        return ""
    lx0, lx1 = math.log10(min(xs)), math.log10(max(xs))
    ly0, ly1 = math.log10(min(ys)), math.log10(max(ys))
    if lx1 - lx0 < 1e-9:
        lx1 = lx0 + 1
    if ly1 - ly0 < 1e-9:
        ly1 = ly0 + 1
    pw = SC_W - SC_PAD_L - SC_PAD_R
    ph = SC_H - SC_PAD_B - SC_PAD_T
    max_size = max((p["size"] or 0) for p in points) or 1

    def px(v):
        return SC_PAD_L + (math.log10(v) - lx0) / (lx1 - lx0) * pw

    def py(v):
        return SC_PAD_T + ph - (math.log10(v) - ly0) / (ly1 - ly0) * ph

    parts = [
        f"<line class='base' x1='{SC_PAD_L:.1f}' y1='{SC_PAD_T + ph:.1f}' "
        f"x2='{SC_W - SC_PAD_R:.1f}' y2='{SC_PAD_T + ph:.1f}'/>",
        f"<line class='base' x1='{SC_PAD_L:.1f}' y1='{SC_PAD_T:.1f}' "
        f"x2='{SC_PAD_L:.1f}' y2='{SC_PAD_T + ph:.1f}'/>",
    ]

    # Diagonales de isovolumen: lotes x precio = constante.
    for v, lab in ((1e5, "100 k€"), (1e6, "1 M€")):
        x_a, x_b = min(xs), max(xs)
        y_a, y_b = v / x_a, v / x_b
        if not (min(ys) <= y_a <= max(ys) or min(ys) <= y_b <= max(ys)):
            continue
        y_a = min(max(y_a, min(ys)), max(ys))
        y_b = min(max(y_b, min(ys)), max(ys))
        parts.append(
            f"<line class='iso' x1='{px(x_a):.2f}' y1='{py(y_a):.2f}' "
            f"x2='{px(x_b):.2f}' y2='{py(y_b):.2f}'/>"
        )
        parts.append(
            f"<text class='axis' x='{SC_W - SC_PAD_R:.1f}' y='{py(y_b) - 2:.2f}' "
            f"text-anchor='end'>{esc(lab)}</text>"
        )

    # Grupos discretos: aqui SI funcionan las clases del CSS, a diferencia del
    # mapa de calor, que necesita una escala continua.
    groups = []
    for p in points:
        if p["group"] not in groups:
            groups.append(p["group"])
    for p in points:
        if p["x"] <= 0 or p["y"] <= 0:
            continue
        r = max(1.2, (p["size"] / max_size) ** 0.5 * 9)
        cls = "pt none" if p["group"] == "__none__" else f"pt s{groups.index(p['group']) % len(SERIES_COLORS)}"
        parts.append(
            f"<circle class='{cls}' cx='{px(p['x']):.2f}' cy='{py(p['y']):.2f}' "
            f"r='{r:.2f}'><title>{esc(p['name'])} ({esc(p['country_es'] or 'sin país')}): "
            f"{esc(p['x'])} vendidos, {esc(eur(p['y']))} de media, "
            f"{esc(eur(p['size']))} total</title></circle>"
        )

    # Quien lleva nombre lo decide narrative.scatter_points (p["label"]): los
    # mayores por volumen mas las referencias fijas. Se lee el flag en vez de
    # recortar aqui para que el HTML de Plotly etiquete los mismos nombres.
    for p in points:
        if not p.get("label") or p["x"] <= 0 or p["y"] <= 0:
            continue
        x, y = px(p["x"]), py(p["y"])
        anchor = "end" if x > SC_W * 0.6 else "start"
        parts.append(
            f"<text class='note' x='{x + (-5 if anchor == 'end' else 5):.2f}' "
            f"y='{y - 5:.2f}' text-anchor='{anchor}'>{esc(p['name'])}</text>"
        )

    parts.append(
        f"<text class='axis' x='{SC_PAD_L + pw / 2:.1f}' y='{SC_H - 4:.1f}' "
        f"text-anchor='middle'>Lotes vendidos (escala log)</text>"
    )
    return (
        f"<svg class='chart' viewBox='0 0 {SC_W:.0f} {SC_H:.0f}' "
        f"preserveAspectRatio='xMidYMid meet' role='img'>{''.join(parts)}</svg>"
    )


def heatmap_chart(matrix: dict) -> str:
    """Mapa de calor pais x anio.

    El color va con fill-opacity sobre un solo tono y no con 9 clases CSS: son
    valores continuos, y definir 9 tokens x 3 bloques de tema para una escala
    seria mucho mas fragil que calcular la opacidad aqui.
    """
    import math

    rows = matrix.get("rows") or []
    years = matrix.get("years") or []
    if not rows or not years:
        return ""
    pad_l, pad_t, pad_b = 74.0, 12.0, 18.0
    cell_h = 13.0
    w = CH_W
    cell_w = (w - pad_l) / len(years)
    h = pad_t + cell_h * len(rows) + pad_b

    top = matrix.get("max_revenue_eur") or 1
    low = matrix.get("min_revenue_eur") or 1
    ltop, llow = math.log10(max(top, 1)), math.log10(max(low, 1))
    span = (ltop - llow) or 1

    parts = []
    for ri, row in enumerate(rows):
        y = pad_t + ri * cell_h
        parts.append(
            f"<text class='axis hm-label' x='0' y='{y + cell_h * 0.72:.2f}'>"
            f"{esc(row['label'])}</text>"
        )
        for ci, cell in enumerate(row["cells"]):
            x = pad_l + ci * cell_w
            v = cell["revenue_eur"]
            if not v:
                # Sin lotes NO es volumen cero: se marca como hueco, no con el
                # extremo claro de la escala, que se leeria como "vendio poco".
                parts.append(
                    f"<rect class='hm empty' x='{x:.2f}' y='{y:.2f}' "
                    f"width='{cell_w - 1:.2f}' height='{cell_h - 1:.2f}'>"
                    f"<title>{esc(row['label'])} {esc(cell['year'])}: sin lotes</title></rect>"
                )
                continue
            o = 0.10 + (math.log10(v) - llow) / span * 0.90
            parts.append(
                f"<rect class='hm' x='{x:.2f}' y='{y:.2f}' "
                f"width='{cell_w - 1:.2f}' height='{cell_h - 1:.2f}' "
                f"fill-opacity='{min(1.0, o):.3f}'>"
                f"<title>{esc(row['label'])} {esc(cell['year'])}: {esc(eur(v))} · "
                f"{esc(cell['lots_sold'])} vendidos de {esc(cell['lots_offered'])}"
                f"{' · año inferido' if cell['inferred'] else ''}</title></rect>"
            )
            if cell["inferred"]:
                parts.append(
                    f"<path class='hm-inferred' d='M{x:.2f},{y + cell_h - 1:.2f} "
                    f"L{x + cell_w - 1:.2f},{y:.2f}'/>"
                )
    parts.append(
        _axis_labels(years, len(years), width=w - pad_l, y=h - 6, x0=pad_l)
    )
    return (
        f"<svg class='chart' viewBox='0 0 {w:.0f} {h:.0f}' "
        f"preserveAspectRatio='xMidYMid meet' role='img'>{''.join(parts)}</svg>"
    )


# Un color por serie, en el mismo orden que las clases .s0/.s1/... del CSS.
# La leyenda y el grafico leen de aqui para que no puedan desincronizarse: antes
# la leyenda hacia zip() con una lista de 3 y la 4a casa desaparecia sin aviso.
SERIES_COLORS = ["accent", "sold", "gold", "house4"]


def series_color(index: int) -> str:
    """Color de la serie n. Cicla si algun dia hay mas casas que colores."""
    return SERIES_COLORS[index % len(SERIES_COLORS)]


def stacked_chart(rows, houses) -> str:
    """Barras apiladas por casa y anio."""
    if not rows:
        return ""
    years = sorted({r["year"] for r in rows})
    by = {(r["year"], r["house_slug"]): r.get("revenue_eur") or 0 for r in rows}
    top = max(sum(by.get((y, h), 0) for h in houses) for y in years) or 1
    n = len(years)
    slot = CH_W / n
    bw = max(2.0, slot * 0.66)
    parts = [
        f"<line class='base' x1='0' y1='{CH_H - CH_PAD_B:.1f}' "
        f"x2='{CH_W:.0f}' y2='{CH_H - CH_PAD_B:.1f}'/>"
    ]
    for idx, y in enumerate(years):
        acc = 0.0
        x = idx * slot + (slot - bw) / 2
        for hi, h in enumerate(houses):
            v = by.get((y, h), 0)
            if not v:
                continue
            bh = (v / top) * PLOT_H
            acc += bh
            parts.append(
                f"<rect class='bar s{hi % len(SERIES_COLORS)}' x='{x:.2f}' "
                f"y='{CH_H - CH_PAD_B - acc:.2f}' width='{bw:.2f}' height='{bh:.2f}'>"
                f"<title>{esc(y)} · {esc(HOUSE_LABELS.get(h, h))}: {esc(eur(v))}</title></rect>"
            )
    parts.append(_axis_labels([str(y) for y in years], n))
    return _svg("".join(parts))


# ---------------------------------------------------------------------------
# Estilos
# ---------------------------------------------------------------------------

CSS = """
*,*::before,*::after{box-sizing:border-box}

/* Paleta: tinta y bermellon de catalogo de subastas. El neutro lleva un sesgo
   calido hacia el acento para que no lea como gris de plantilla. */
:root{
  --bg:#F7F5F2; --surface:#FFFDFB; --raised:#F0EDE8;
  --fg:#191512; --fg-soft:#6F675F; --line:#DED8D0;
  --accent:#A8342A; --accent-soft:#F2E3E0;
  --sold:#4F6046; --gold:#8A6C2F; --house4:#3C5A73;
  --s1:8px; --s2:16px; --s3:24px; --s4:40px;
  --mono:ui-monospace,"SF Mono","Cascadia Mono","Segoe UI Mono",Menlo,Consolas,monospace;
  --serif:"Iowan Old Style","Palatino Linotype",Palatino,Georgia,"Times New Roman",serif;
  --sans:system-ui,-apple-system,"Segoe UI",Roboto,"Helvetica Neue",Arial,sans-serif;
}
@media (prefers-color-scheme:dark){
  :root{
    --bg:#131110; --surface:#1C1917; --raised:#252220;
    --fg:#F0EBE5; --fg-soft:#9E948A; --line:#332E2A;
    --accent:#E0685A; --accent-soft:#3A211D;
    --sold:#8FA882; --gold:#C9A45E; --house4:#7FA3C0;
  }
}
:root[data-theme="dark"]{
  --bg:#131110; --surface:#1C1917; --raised:#252220;
  --fg:#F0EBE5; --fg-soft:#9E948A; --line:#332E2A;
  --accent:#E0685A; --accent-soft:#3A211D;
  --sold:#8FA882; --gold:#C9A45E; --house4:#7FA3C0;
}
:root[data-theme="light"]{
  --bg:#F7F5F2; --surface:#FFFDFB; --raised:#F0EDE8;
  --fg:#191512; --fg-soft:#6F675F; --line:#DED8D0;
  --accent:#A8342A; --accent-soft:#F2E3E0;
  --sold:#4F6046; --gold:#8A6C2F; --house4:#3C5A73;
}

body{margin:0;background:var(--bg);color:var(--fg);font-family:var(--sans);
  font-size:15px;line-height:1.55;-webkit-font-smoothing:antialiased}
.wrap{max-width:1120px;margin:0 auto;padding:var(--s4) var(--s3)}
h1,h2,h3{font-family:var(--serif);font-weight:600;text-wrap:balance;margin:0}
a{color:var(--accent)}
a:focus-visible,button:focus-visible,input:focus-visible,select:focus-visible{
  outline:2px solid var(--accent);outline-offset:2px}

/* Cabecera: la tesis primero, no una descripcion generica. */
.masthead{display:flex;justify-content:space-between;align-items:flex-start;
  gap:var(--s3);border-bottom:2px solid var(--fg);padding-bottom:var(--s3);
  margin-bottom:var(--s4);flex-wrap:wrap}
.eyebrow{font-family:var(--mono);font-size:.7rem;letter-spacing:.16em;
  text-transform:uppercase;color:var(--accent);margin:0 0 var(--s1)}
h1{font-size:clamp(1.9rem,4.4vw,3rem);line-height:1.08;letter-spacing:-.015em;max-width:19ch}
.dek{color:var(--fg-soft);margin:var(--s2) 0 0;max-width:56ch;font-size:1rem}
.theme{font:inherit;font-size:.78rem;color:var(--fg-soft);background:var(--surface);
  border:1px solid var(--line);border-radius:999px;padding:7px 14px;cursor:pointer}
.theme:hover{color:var(--fg);border-color:var(--fg-soft)}

/* KPIs: la cifra manda, la etiqueta es servicio. */
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(10.5rem,1fr));
  gap:1px;background:var(--line);border:1px solid var(--line);margin-bottom:var(--s4)}
.kpi{background:var(--surface);padding:var(--s2)}
.kpi.hero{background:var(--accent-soft)}
.kpi-l{display:block;font-family:var(--mono);font-size:.66rem;letter-spacing:.12em;
  text-transform:uppercase;color:var(--fg-soft)}
/* El simbolo de moneda no puede quedarse solo en una linea: la cifra se
   reduce si hace falta, pero no se parte. */
.kpi-v{display:block;font-family:var(--serif);font-size:clamp(1.35rem,2.6vw,1.85rem);
  line-height:1.15;font-variant-numeric:tabular-nums;margin:6px 0 3px;
  letter-spacing:-.015em;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.kpi.hero .kpi-v{color:var(--accent)}
.kpi-n{display:block;font-size:.76rem;color:var(--fg-soft);line-height:1.35}

section{margin-bottom:var(--s4)}
h2{font-size:1.42rem;letter-spacing:-.01em}
.lead{color:var(--fg-soft);margin:6px 0 var(--s2);max-width:68ch;font-size:.92rem}

/* Avisos: van arriba y abiertos. Un panel que esconde sus salvedades invita a
   citar cifras que no aguantan. */
.flags{border:1px solid var(--line);background:var(--surface)}
.flags summary{cursor:pointer;padding:var(--s2);display:flex;gap:var(--s2);
  align-items:baseline;justify-content:space-between;flex-wrap:wrap}
.flags summary h2{font-size:1.15rem}
.flags-n{font-family:var(--mono);font-size:.75rem;color:var(--fg-soft)}
.flag-list{list-style:none;margin:0;padding:0 var(--s2) var(--s2);
  display:flex;flex-direction:column;gap:10px}
.flag{display:grid;grid-template-columns:auto 1fr;gap:var(--s2);align-items:baseline;
  font-size:.88rem;padding-left:10px;border-left:3px solid var(--line)}
.flag-critical{border-left-color:var(--accent)}
.flag-warn{border-left-color:var(--gold)}
.flag-tag{font-family:var(--mono);font-size:.68rem;letter-spacing:.08em;
  text-transform:uppercase;color:var(--fg-soft);white-space:nowrap}
.flag-critical .flag-tag{color:var(--accent)}

/* Tablas */
.scroll{overflow-x:auto;min-width:0;max-width:100%;border:1px solid var(--line);
  background:var(--surface)}
table{width:100%;border-collapse:collapse;font-size:.88rem;min-width:560px}
thead th{text-align:right;font-family:var(--mono);font-size:.66rem;letter-spacing:.1em;
  text-transform:uppercase;color:var(--fg-soft);font-weight:500;
  padding:10px var(--s2);border-bottom:1px solid var(--line);white-space:nowrap}
thead th:first-child,thead th:nth-child(2){text-align:left}
tbody th{text-align:left;font-weight:500;padding:9px var(--s2);
  border-bottom:1px solid var(--line)}
tbody td{padding:9px var(--s2);border-bottom:1px solid var(--line);text-align:right}
tbody tr:last-child th,tbody tr:last-child td{border-bottom:none}
tbody tr:hover{background:var(--raised)}
.n{font-family:var(--mono);font-variant-numeric:tabular-nums;white-space:nowrap}
.strong{font-weight:600}
.rank{font-family:var(--mono);color:var(--fg-soft);text-align:left;width:2.6rem;font-size:.8rem}
.sub{display:block;font-size:.72rem;color:var(--fg-soft)}
.name{display:block;font-weight:600}
.meta{display:block;font-size:.74rem;color:var(--fg-soft)}
.meta.none{opacity:.65;font-style:italic}

/* Ficha de artista. Boton dentro de la celda y no fila clicable: la fila ya
   lleva un enlace al lote record y un <tr> con handler no recibe foco. */
.artist-toggle{display:block;width:100%;text-align:left;background:none;border:0;
  padding:0;font:inherit;color:inherit;cursor:pointer}
.artist-toggle:hover .name{color:var(--accent);text-decoration:underline}
.artist-toggle:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.artist-toggle .name::after{content:'';display:inline-block;margin-left:.4rem;
  border:.28rem solid transparent;border-top-color:currentColor;
  transform:translateY(.15rem);opacity:.5}
.artist-toggle[aria-expanded="true"] .name::after{
  transform:translateY(-.1rem) rotate(180deg);opacity:1}
.artist-card>td{padding:0;background:var(--raised)}
.acard{padding:var(--s2);border-left:3px solid var(--accent)}
.acard-head{display:flex;flex-wrap:wrap;align-items:baseline;gap:8px;
  justify-content:space-between;margin-bottom:var(--s1)}
.acard-head h4{margin:0;font-family:var(--serif);font-size:1.05rem}
.acard-res{font-size:.72rem;color:var(--fg-soft)}
.acard-note{margin:6px 0;font-size:.8rem;color:var(--fg-soft)}
.ministats{display:flex;flex-wrap:wrap;gap:var(--s2);margin-bottom:var(--s1)}
.ministat{display:flex;flex-direction:column}
.ministat-label{font-family:var(--mono);font-size:.64rem;letter-spacing:.08em;
  text-transform:uppercase;color:var(--fg-soft)}
.ministat-value{font-family:var(--mono);font-size:.95rem;font-weight:600}
.chip{display:inline-block;padding:.1rem .5rem;margin-right:.3rem;border-radius:999px;
  background:var(--surface);border:1px solid var(--line);font-size:.72rem}
.acard-lots{overflow-x:auto;margin-top:var(--s1)}
.acard-lots table{font-size:.8rem}
.none{color:var(--fg-soft);opacity:.7}
@media print{.artist-card{display:none}.artist-toggle .name::after{display:none}}

/* Controles */
.controls{display:flex;flex-wrap:wrap;gap:10px;align-items:flex-end;margin-bottom:var(--s2)}
.controls label{display:flex;flex-direction:column;gap:5px;font-family:var(--mono);
  font-size:.66rem;letter-spacing:.1em;text-transform:uppercase;color:var(--fg-soft)}
.controls input,.controls select{font:inherit;font-family:var(--sans);font-size:.88rem;
  text-transform:none;letter-spacing:normal;color:var(--fg);background:var(--surface);
  border:1px solid var(--line);border-radius:3px;padding:8px 10px;min-width:13rem}
.btn{font:inherit;font-size:.78rem;color:var(--fg-soft);cursor:pointer;
  background:var(--surface);border:1px solid var(--line);border-radius:3px;padding:9px 12px}
.btn:hover{background:var(--raised);color:var(--fg)}
.dls{display:flex;gap:6px;margin-left:auto}
.dl{display:inline-flex;align-items:center;gap:6px;font:inherit;font-size:.78rem;
  font-weight:500;color:var(--fg-soft);cursor:pointer;background:var(--surface);
  border:1px solid var(--line);border-radius:3px;padding:9px 11px;white-space:nowrap}
.dl:hover{background:var(--accent-soft);color:var(--accent);border-color:var(--accent)}
.dl svg{flex:0 0 auto}
@media (max-width:660px){.dls{margin-left:0;width:100%}.dl{flex:1;justify-content:center}}

/* Totalizador */
.totals{display:grid;grid-template-columns:repeat(auto-fit,minmax(8.5rem,1fr));
  gap:1px;background:var(--line);border:1px solid var(--line);margin-bottom:var(--s2)}
.totals.on{border-color:var(--accent)}
.tot{background:var(--surface);padding:10px var(--s2);min-width:0}
.tot.hi{background:var(--accent-soft)}
.tot-l{display:block;font-family:var(--mono);font-size:.62rem;letter-spacing:.11em;
  text-transform:uppercase;color:var(--fg-soft)}
.tot-v{display:block;font-family:var(--mono);font-variant-numeric:tabular-nums;
  font-size:1.02rem;font-weight:600;margin-top:3px;white-space:nowrap;
  overflow:hidden;text-overflow:ellipsis}
.tot.hi .tot-v{color:var(--accent)}
.tot-n{display:block;font-family:var(--mono);font-size:.68rem;color:var(--fg-soft)}
.empty{color:var(--fg-soft);font-size:.9rem;padding:var(--s2);margin:0}

/* Graficos SVG */
.charts{display:grid;grid-template-columns:repeat(auto-fit,minmax(19rem,1fr));gap:var(--s3)}
.card{border:1px solid var(--line);background:var(--surface);padding:var(--s2)}
.card h3{font-size:1rem;margin-bottom:2px}
.card p{font-size:.8rem;color:var(--fg-soft);margin:0 0 var(--s2)}
.chart{display:block;width:100%;height:auto}
/* Actos de la seccion narrativa: separadores dentro de una misma seccion, no
   secciones nuevas, para que el bloque siga leyendose como un argumento. */
section h3{margin:var(--s3) 0 6px;padding-top:var(--s2);
  border-top:1px solid var(--line);font-family:var(--serif);font-size:1.02rem}
.chart-box{margin-bottom:var(--s2)}
.chart-box .caveat{margin-top:6px}
.generation-coverage{margin-top:var(--s2);padding:12px var(--s2);
  border:1px solid var(--line);background:var(--raised)}
.generation-coverage-head{display:flex;justify-content:space-between;gap:var(--s2);
  align-items:baseline;flex-wrap:wrap;font-size:.75rem;color:var(--fg-soft)}
.generation-coverage-head>span{font-family:var(--mono);text-transform:uppercase;
  letter-spacing:.07em}
.generation-coverage-head strong{font-family:var(--mono);color:var(--fg)}
.generation-track{display:flex;height:9px;margin:8px 0;border-radius:99px;overflow:hidden;
  background:var(--line)}
.generation-dated{background:var(--accent)}
.generation-missing{background:var(--fg-soft);opacity:.48}
.generation-legend{display:flex;justify-content:space-between;gap:var(--s2);
  flex-wrap:wrap;font-size:.75rem;color:var(--fg-soft)}
.generation-legend span{display:flex;align-items:center;gap:5px}
.generation-legend strong{color:var(--fg);font-weight:600}
.generation-key{width:9px;height:9px;border-radius:2px;flex:0 0 auto}
.generation-key-dated{background:var(--accent)}
.generation-key-missing{background:var(--fg-soft);opacity:.48}
.chart .bar{fill:var(--accent)}
.chart .bar.s1{fill:var(--sold)}
.chart .bar.s2{fill:var(--gold)}
.chart .bar.s3{fill:var(--house4)}
.chart .bar:hover{opacity:.72}
.chart .base{stroke:var(--line);stroke-width:1}
.chart .axis{font-family:var(--mono);font-size:9px;fill:var(--fg-soft)}
/* Pareto: la linea acumulada sobre las barras del tramo. */
.chart .cum{fill:none;stroke:var(--gold);stroke-width:1.6}
.chart .cum-dot{fill:var(--gold)}
.chart .note{font-family:var(--mono);font-size:8.5px;fill:var(--fg)}
/* Scatter: categorias discretas, aqui las clases si sirven. */
.chart .pt{fill:var(--accent);fill-opacity:.72}
.chart .pt.s1{fill:var(--sold)}
.chart .pt.s2{fill:var(--gold)}
.chart .pt.s3{fill:var(--house4)}
.chart .pt.none{fill:var(--fg-soft);fill-opacity:.3}
.chart .iso{stroke:var(--fg-soft);stroke-width:.6;stroke-dasharray:2 2;opacity:.5}
/* Mapa de calor: escala continua por opacidad sobre un solo tono. Nueve tokens
   de color x tres bloques de tema seria mucho mas fragil que esto. */
.chart .hm{fill:var(--accent)}
.chart .hm.empty{fill:none;stroke:var(--line);stroke-width:.5;stroke-dasharray:1 2}
.chart .hm-inferred{stroke:var(--surface);stroke-width:.8;opacity:.7}
.chart .hm-label{font-size:8px}
.legend{display:flex;gap:var(--s2);flex-wrap:wrap;font-size:.75rem;
  color:var(--fg-soft);margin-top:10px}
.key{display:inline-flex;align-items:center;gap:6px}
.key i{width:10px;height:10px;border-radius:2px;display:inline-block}

/* Confirmacion de descarga. En el iframe de un Artifact alert() puede estar
   bloqueado, asi que el aviso vive en la propia pagina. */
.toast{position:fixed;left:50%;bottom:20px;transform:translate(-50%,140%);
  background:var(--fg);color:var(--bg);font-size:.84rem;line-height:1.4;
  padding:11px 18px;border-radius:4px;max-width:min(34rem,90vw);z-index:50;
  box-shadow:0 6px 22px rgba(0,0,0,.22);transition:transform .22s ease;
  pointer-events:none}
.toast.show{transform:translate(-50%,0)}
.toast.bad{background:var(--accent);color:#fff}
@media (prefers-reduced-motion:reduce){.toast{transition:none}}

.caveat{font-size:.82rem;color:var(--fg-soft);margin:var(--s2) 0 0;max-width:72ch;
  padding-top:var(--s2);border-top:1px dashed var(--line)}
.caveat code{font-family:var(--mono);font-size:.94em;background:var(--raised);padding:1px 5px}
footer{border-top:2px solid var(--fg);padding-top:var(--s2);margin-top:var(--s4);
  font-size:.82rem;color:var(--fg-soft)}
footer p{margin:0 0 8px;max-width:74ch}
@media (prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important}}
"""


ICON = (
    "<svg viewBox='0 0 16 16' width='13' height='13' aria-hidden='true' fill='none' "
    "stroke='currentColor' stroke-width='1.5' stroke-linecap='round' "
    "stroke-linejoin='round'><path d='M8 1.5v7.5M5 6.5 8 9.5l3-3'/>"
    "<path d='M2.5 11.5v2h11v-2'/>{}</svg>"
)
ICON_TABLE = ICON.format("<path d='M2.5 3.5h2.5M2.5 6h2.5'/>")
ICON_LOTS = ICON.format("<circle cx='3.6' cy='4' r='1.4'/>")


def dl_buttons(prefix: str) -> str:
    return (
        "<span class='dls'>"
        f"<button type='button' class='dl' id='{prefix}-dl-view' "
        "title='Descargar la tabla tal como se ve, en CSV para Excel'>"
        f"{ICON_TABLE} Tabla</button>"
        f"<button type='button' class='dl' id='{prefix}-dl-lots' "
        "title='Descargar los lotes que hay detras de estas cifras, uno por fila'>"
        f"{ICON_LOTS} Lotes</button></span>"
    )


def totals_block(el_id: str, cards: list[tuple[str, str, str]]) -> str:
    out = [f"<div class='totals' id='{el_id}' role='status' aria-live='polite'>"]
    for cid, label, extra in cards:
        cls = "tot hi" if extra == "hi" else "tot"
        note = f"<span class='tot-n' id='{cid}-n'></span>" if extra == "note" else ""
        out.append(
            f"<div class='{cls}'><span class='tot-l'>{esc(label)}</span>"
            f"<span class='tot-v' id='{cid}'>-</span>{note}</div>"
        )
    return "".join(out) + "</div>"


def build_kpis(rep: dict) -> str:
    s = rep["summary"]
    dist = rep.get("price_distribution") or {}
    est = rep.get("estimate_accuracy") or {}
    cov = rep.get("artist_coverage") or {}
    cards = [
        ("Lotes analizados", num(s["total_lots"]),
         f"{s['total_houses']} casas - {num(len(rep.get('by_auction', [])))} subastas", False),
        ("Lotes vendidos", num(s["total_sold"]),
         f"{pct(s['sell_through_pct'])} de lo ofertado", False),
        ("Volumen adjudicado", eur(s["total_revenue_eur"]),
         "Convertido a EUR - tasa del mes de subasta", True),
        ("Precio mediano", eur(dist.get("median")),
         f"La media ({eur(s.get('avg_sold_price_eur'))}) va inflada por la cola alta", False),
        ("Supera la estimacion", pct(est.get("pct_above")),
         f"De {num(est.get('total_with_estimate'))} lotes con estimacion", False),
        ("Artistas con pais", num(cov.get("artists_with_country")),
         f"De {num(cov.get('artists_ranked'))} rankeados - {cov.get('countries', 0)} paises", False),
    ]
    out = []
    for label, value, note, hero in cards:
        out.append(
            f"<article class='kpi{' hero' if hero else ''}'>"
            f"<span class='kpi-l'>{esc(label)}</span>"
            f"<span class='kpi-v'>{esc(value)}</span>"
            f"<span class='kpi-n'>{esc(note)}</span></article>"
        )
    return f"<section class='kpis'>{''.join(out)}</section>"


def build_flags(flags: list[dict]) -> str:
    if not flags:
        return ""
    order = {"critical": 0, "warn": 1, "info": 2}
    label = {"critical": "Critico", "warn": "Aviso", "info": "Contexto"}
    items = []
    for f in sorted(flags, key=lambda x: order.get(x.get("level"), 9)):
        lvl = f.get("level", "info")
        house = f.get("house_slug")
        msg = f.get("message", "")
        for slug, nice in HOUSE_LABELS.items():
            msg = msg.replace(slug, nice)
        tag = label.get(lvl, lvl) + (f" - {HOUSE_LABELS.get(house, house)}" if house else "")
        items.append(
            f"<li class='flag flag-{esc(lvl)}'><span class='flag-tag'>{esc(tag)}</span>"
            f"<span>{esc(msg)}</span></li>"
        )
    n_crit = sum(1 for f in flags if f.get("level") == "critical")
    resumen = f"{len(flags)} avisos" + (f", {n_crit} critico" if n_crit else "")
    return (
        "<details class='flags' open><summary><h2>Como leer estos datos</h2>"
        f"<span class='flags-n'>{esc(resumen)}</span></summary>"
        f"<ul class='flag-list'>{''.join(items)}</ul></details>"
    )


# Cardinales para el titulo de la tabla de casas. Solo hasta seis: si el
# proyecto pasa de ahi, sale el numero y no una palabra inventada.
_CARDINAL = {1: "una", 2: "dos", 3: "tres", 4: "cuatro", 5: "cinco", 6: "seis"}


def build_house_table(houses: list[dict]) -> str:
    rows = []
    for h in sorted(houses, key=lambda r: -(r.get("revenue_eur") or 0)):
        slug = h["house_slug"]
        cur = h.get("currency") or "?"
        st = (h.get("sell_through_rate") or 0) * 100
        rows.append(
            "<tr><th scope='row'><span class='name'>"
            f"{esc(HOUSE_LABELS.get(slug, slug))}</span>"
            f"<span class='meta'>{esc(HOUSE_COUNTRY.get(slug, ''))} - {esc(cur)}</span></th>"
            f"<td class='n'>{num(h.get('lots_offered'))}</td>"
            f"<td class='n'>{num(h.get('lots_sold'))}</td>"
            f"<td class='n'>{pct(st)}</td>"
            f"<td class='n'>{num(h.get('revenue_native'))} {esc(cur)}"
            f"<span class='sub'>= {esc(eur(h.get('revenue_eur')))}</span></td>"
            f"<td class='n'>{num(h.get('avg_sold_price_native'))} {esc(cur)}"
            f"<span class='sub'>= {esc(eur(h.get('avg_sold_price_eur')))}</span></td></tr>"
        )
    # El titulo se deriva del dato: estuvo escrito como "Las tres casas" cuando
    # ya eran cuatro, y un numero equivocado en un H2 de un informe publicable
    # desacredita todo lo que hay debajo.
    return (
        f"<section><h2>Las {esc(_CARDINAL.get(len(rows), len(rows)))} casas</h2>"
        "<p class='lead'>Cada casa cotiza en su moneda. Se muestran las dos cifras: "
        "la nativa es exacta, la convertida a EUR es la unica comparable entre casas.</p>"
        "<div class='scroll'><table><thead><tr><th>Casa</th><th>Ofertados</th>"
        "<th>Vendidos</th><th>Tasa venta</th><th>Volumen</th><th>Precio medio</th>"
        f"</tr></thead><tbody>{''.join(rows)}</tbody></table></div></section>"
    )


RESOLUTION_LABEL = {
    "master": "Ficha del maestro de artistas",
    "fold_only": "Agrupado por nombre, sin ficha en el maestro",
}
KIND_NOTE = {
    "cross_market": "Vende en casas de países distintos: cruza mercados.",
    "same_market": "Vende en varias casas del mismo mercado.",
    "single": "",
}


def artist_card(a: dict, lots: list[dict]) -> str:
    """Ficha desplegable de un artista, con sus lotes y su actividad."""
    houses = a.get("houses") or []
    chips = "".join(
        f"<span class='chip'>{esc(HOUSE_LABELS.get(h, h))}</span>" for h in houses
    )
    kind = multi_house_kind(houses)
    stats = [
        ("Lotes vendidos",
         f"{num(a.get('lots_sold'))}<span class='sub'>de {num(a.get('lots_offered'))}</span>"),
        ("Tasa de venta", pct((a.get("sell_through_rate") or 0) * 100)),
        ("Volumen", esc(eur(a.get("revenue_eur")))),
        ("Precio medio", esc(eur(a.get("avg_sold_price_eur")))),
    ]
    ministats = "".join(
        f"<div class='ministat'><span class='ministat-label'>{esc(k)}</span>"
        f"<span class='ministat-value'>{v}</span></div>"
        for k, v in stats
    )

    activity = ""
    if a.get("first_year"):
        years = a.get("years_active") or 0
        activity = (
            f"<p class='acard-note'>En subasta entre {esc(a['first_year'])} y "
            f"{esc(a.get('last_year'))} · {num(years)} "
            f"{'año' if years == 1 else 'años'} con lotes.</p>"
        )

    top = sorted(lots, key=lambda l: -(l.get("price_sold_eur") or 0))[:10]
    lot_rows = []
    for l in top:
        title = (
            f"<a href='{esc(l.get('lot_url'))}' target='_blank' rel='noopener'>"
            f"{esc(l.get('lot_title') or 'Ver lote')}</a>"
            if l.get("lot_url") else esc(l.get("lot_title") or "")
        )
        if l.get("price_sold"):
            price = f"{num(l['price_sold'])} {esc(l.get('currency') or '')}"
            if l.get("price_sold_eur"):
                price += f"<span class='sub'>= {esc(eur(l['price_sold_eur']))}</span>"
        else:
            price = "<span class='none'>no vendido</span>"
        lot_rows.append(
            f"<tr><td>{esc((l.get('auction_start_date') or '')[:10] or '—')}</td>"
            f"<td>{esc(HOUSE_LABELS.get(l.get('house_slug'), l.get('house_slug') or ''))}</td>"
            f"<td>{title}</td><td class='n'>{price}</td></tr>"
        )
    lot_table = ""
    if lot_rows:
        more = (
            f"<p class='caveat'>Se muestran los {len(top)} lotes más caros de "
            f"{num(len(lots))}. El resto está en la descarga de lotes.</p>"
            if len(lots) > len(top) else ""
        )
        lot_table = (
            "<div class='acard-lots'><table><thead><tr><th>Fecha</th><th>Casa</th>"
            "<th>Lote</th><th>Precio</th></tr></thead>"
            f"<tbody>{''.join(lot_rows)}</tbody></table></div>{more}"
        )

    # Un artista sin ficha no recibe pais: se explica por que, en vez de dejar
    # el hueco y que parezca un fallo de datos.
    fold_note = (
        "<p class='caveat'>Este artista no está en el maestro curado, así que no consta "
        "su país ni sus fechas. Sus lotes se agrupan por una clave determinista del "
        "nombre, que <strong>agrupa pero no identifica</strong>: dos personas distintas "
        "con el mismo nombre compartirían esta ficha.</p>"
        if a.get("resolution") == "fold_only" else ""
    )

    return (
        f"<div class='acard' role='region' aria-label='Ficha de {esc(a.get('artist_name'))}'>"
        f"<div class='acard-head'><h4>{esc(a.get('artist_name'))}</h4>"
        f"<span class='acard-res'>{esc(RESOLUTION_LABEL.get(a.get('resolution'), ''))}</span></div>"
        f"<div class='ministats'>{ministats}</div>"
        f"{activity}"
        + (f"<p class='acard-note'>{chips} {esc(KIND_NOTE.get(kind, ''))}</p>" if chips else "")
        + lot_table
        + fold_note
        + "<p class='caveat'>Los importes en EUR usan una tasa única; el precio nativo es "
          "el exacto.</p>"
        "</div>"
    )


def build_artist_charts(artists: list[dict], generations: list[dict]) -> str:
    """Los tres graficos de artistas, en SVG. Mismos datos que la version Plotly.

    El calculo va por narrative.py: si cada renderer lo hiciera por su cuenta,
    las dos versiones del informe acabarian publicando cifras distintas.
    """
    if not artists:
        return ""
    pareto = pareto_points(artists)
    bars, line, labels, prev, prev_n = [], [], [], 0.0, 0
    for p in pareto:
        labels.append(f"{prev_n + 1}–{p['n']}" if prev_n else f"Top {p['n']}")
        bars.append({"value": p["revenue_eur"] - prev, "label": labels[-1]})
        line.append(p["share_pct"])
        prev, prev_n = p["revenue_eur"], p["n"]
    notes = [
        (i, f"Top {p['n']}: {p['share_pct']:.0f}%")
        for i, p in enumerate(pareto)
        if p["n"] in (25, 200)
    ]

    gens = generation_bars(generations or [])
    # ``decade=None`` permanece en la banda de cobertura; no se dibuja como si
    # fuera una generacion real.
    gen_items = [
        {"label": g["label"], "revenue_eur": g["revenue_eur"]}
        for g in gens
        if not g["is_sentinel"]
    ]

    # El scatter SVG se recorta: 1.492 circulos son ~250 KB de marcado en un
    # fichero que ya roza el limite del visor, y a 320 unidades de ancho la cola
    # se solapa en una mancha. Se dibujan los de mas volumen y se dice cuantos
    # quedan fuera y cuanto pesan.
    all_pts = scatter_points(artists)
    pts = all_pts[:SCATTER_LIMIT]
    total_size = sum(p["size"] for p in all_pts) or 1
    tail_pct = sum(p["size"] for p in all_pts[SCATTER_LIMIT:]) / total_size * 100

    out = [
        "<h3>Un puñado de nombres concentra el dinero</h3>",
        "<div class='chart-box'>",
        bar_line_chart(bars, line, labels=labels, notes=notes),
        f"<p class='caveat'>{CAVEAT_PARETO_SCOPE}</p></div>",
        "<h3>Vender caro o vender mucho</h3>",
        "<p class='lead'>Cada burbuja es un artista: a la derecha los que venden muchos "
        "lotes, arriba los que los venden caros, y el tamaño es el volumen total.</p>",
        "<div class='chart-box'>",
        scatter_chart(pts),
        f"<p class='caveat'>{CAVEAT_SCATTER_LOWN}</p>",
        # El recorte se declara: un grafico que dice "los artistas" habiendo
        # dibujado la mitad es un grafico que miente por omision.
        (f"<p class='caveat'>Se dibujan los {len(pts)} artistas de mayor volumen de "
         f"{len(all_pts)}. Los restantes aportan menos del "
         f"{tail_pct:.1f}% del total y a este tamaño se solapan en un borrón; "
         "están todos en la tabla y en la descarga.</p>" if len(pts) < len(all_pts) else ""),
        "</div>",
    ]
    if gens:
        out += [
            "<h3>La generación que mueve el mercado</h3>",
            "<div class='chart-box'>",
            bar_chart(gen_items, "revenue_eur", "label"),
            generation_coverage_block(gens),
            f"<p class='caveat'>{CAVEAT_GENERATIONS_COVERAGE}</p></div>",
        ]
    return "".join(out)


def build_artist_table(artists: list[dict], cov: dict,
                       lots_by_artist: dict[str, list[dict]] | None = None,
                       generations: list[dict] | None = None) -> str:
    if not artists:
        return ""
    lots_by_artist = lots_by_artist or {}
    shown = artists[:ARTIST_LIMIT]
    pares = sorted(
        {(a.get("country_birth"), a.get("country_birth_es") or a.get("country_birth"))
         for a in shown if a.get("country_birth")},
        key=lambda t: t[1] or "",
    )
    options = "".join(f"<option value='{esc(c)}'>{esc(l)}</option>" for c, l in pares)
    if any(not a.get("country_birth") for a in shown):
        options += "<option value='__none__'>Sin país informado</option>"

    rows = []
    for i, a in enumerate(shown, 1):
        st = (a.get("sell_through_rate") or 0) * 100
        code = a.get("country_birth")
        label = a.get("country_birth_es") or code
        extra = [n for n in (a.get("nationalities") or []) if n != code]
        meta = label or "Sin país informado"
        if extra:
            # Traducidas: aqui se imprimian los codigos ISO crudos ("tb. FR, IT")
            # mientras el informe local ya escribia "tb. Francia, Italia".
            meta += " · tb. " + nationalities_es(extra)
        # Fechas del maestro, como en report_gold.py: si solo hay una, se dice
        # cual es ("n." / "m."), nunca "1954-", que afirmaria que sigue vivo.
        life = a.get("life_years")
        if life:
            meta += f" · {life}"
        url = a.get("top_lot_url")
        rec = eur(a.get("top_price_eur"))
        rec_cell = (
            f"<a href='{esc(url)}' target='_blank' rel='noopener' "
            f"title='{esc(a.get('top_lot_title') or '')}'>{esc(rec)}</a>"
            if url else esc(rec)
        )
        card_id = f"ficha-{i}"
        rows.append(
            f"<tr data-country='{esc(code or '__none__')}' "
            f"data-name='{esc((a.get('artist_name') or '').lower())}' "
            f"data-key='{esc(a.get('artist_key') or '')}' "
            f"data-card='{card_id}' "
            f"data-kind='{esc(multi_house_kind(a.get('houses') or []))}' "
            f"data-sold='{a.get('lots_sold') or 0}' "
            f"data-offered='{a.get('lots_offered') or 0}' "
            f"data-birth='{a.get('birth_year') or ''}' "
            f"data-death='{a.get('death_year') or ''}' "
            f"data-revenue='{a.get('revenue_eur') or 0}'>"
            f"<td class='rank'>{i}</td>"
            # Boton y no fila clicable, por la misma razon que en el informe
            # local: la fila ya lleva un enlace y un <tr> no recibe foco.
            f"<th scope='row'>"
            f"<button type='button' class='artist-toggle' aria-expanded='false' "
            f"aria-controls='{card_id}'>"
            f"<span class='name'>{esc(a['artist_name'])}</span>"
            f"<span class='meta{'' if label else ' none'}'>{esc(meta)}</span>"
            f"</button></th>"
            f"<td class='n'>{num(a.get('lots_sold'))}"
            f"<span class='sub'>de {num(a.get('lots_offered'))}</span></td>"
            f"<td class='n'>{pct(st)}</td>"
            f"<td class='n strong'>{esc(eur(a.get('revenue_eur')))}</td>"
            f"<td class='n'>{rec_cell}</td></tr>"
            # La ficha va renderizada desde Python y oculta, no construida en
            # cliente: el visor del Artifact puede restringir JS y una ficha que
            # solo existe si el script corre es una ficha que puede no existir.
            f"<tr class='artist-card' id='{card_id}' hidden>"
            f"<td colspan='6'>{artist_card(a, lots_by_artist.get(a.get('artist_key')) or [])}</td>"
            "</tr>"
        )

    con, tot = cov.get("artists_with_country") or 0, cov.get("artists_ranked") or 0
    caveats = (
        "<p class='caveat'>El récord enlaza al lote original en la web de la casa: "
        "cada cifra de esta tabla se puede comprobar en la fuente.</p>"
        f"<p class='caveat'>Los totales suman lo que hay filtrado, que son los "
        f"{num(len(shown))} primeros artistas de {num(tot)} rankeados. No son el total "
        "del mercado: ese está en las tarjetas de cabecera.</p>"
        f"<p class='caveat'>Tienen país informado {num(con)} de {num(tot)} artistas "
        f"({pct(cov.get('country_coverage_pct'))}). El resto aparece como “sin país "
        "informado”: la nacionalidad sale de un maestro curado a mano, nunca se deduce "
        "del país de la casa de subastas.</p>"
    )
    # Las dos coberturas de fechas: la de la tabla visible y la del ranking
    # entero. Publicar solo la primera daria una idea falsa del maestro, porque
    # la curaduria se prioriza por facturacion y la cola queda peor cubierta.
    dated_shown = sum(1 for a in shown if a.get("birth_year"))
    dated_tot = sum(1 for a in artists if a.get("birth_year"))
    if shown and tot:
        caveats += (
            f"<p class='caveat'>Las fechas salen del mismo maestro: las tienen "
            f"{num(dated_shown)} de los {num(len(shown))} artistas de esta tabla "
            f"({pct(dated_shown / len(shown) * 100)}), pero solo {num(dated_tot)} de "
            f"{num(tot)} en el ranking completo ({pct(dated_tot / tot * 100)}): la "
            "curaduría se ha priorizado por facturación.</p>"
        )
        # "n. 1954" no equivale a "vivo": ver la misma nota en render_html.py.
        caveats += (
            "<p class='caveat'>“n. 1954” significa <strong>nacido en 1954 y sin año de "
            "muerte registrado</strong>, que no es lo mismo que estar vivo: puede ser una "
            "ficha incompleta. Cuando el artista tendría más de 105 años se marca "
            "“n. 1905 (?)”, porque ahí el hueco es casi seguro un dato que falta.</p>"
        )
    return (
        "<section><h2>Quién mueve el dinero</h2>"
        + build_artist_charts(artists, generations or [])
        + "<h3>El ranking, nombre a nombre</h3>"
        f"<p class='lead'>Los {num(len(shown))} artistas con mayor volumen adjudicado. "
        "Pulsa en un nombre para ver su ficha y sus lotes. "
        # El corte sale de la constante del pipeline: estaba escrito a mano aqui
        # y en render_html.py, asi que cambiarlo dejaba mintiendo a los dos.
        f"{CAVEAT_MIN_LOTS}</p>"
        "<div class='controls'>"
        "<label>Buscar artista<input type='search' id='artist-search' "
        "placeholder='p. ej. Botero' autocomplete='off'></label>"
        "<label>País de nacimiento<select id='country-filter'>"
        f"<option value=''>Todos</option>{options}</select></label>"
        # Presencia en varias casas. "Mismo mercado" y "cruza mercados" van
        # separados porque Bogota y Lefebre son las dos colombianas.
        "<label>Presencia<select id='kind-filter'>"
        "<option value=''>Todos</option>"
        "<option value='multi'>En más de una casa</option>"
        "<option value='cross_market'>· cruzando mercados</option>"
        "<option value='same_market'>· en el mismo mercado</option>"
        "<option value='single'>En una sola casa</option>"
        "</select></label>"
        "<button type='button' class='btn' id='artist-reset'>Limpiar</button>"
        + dl_buttons("artist") + "</div>"
        + totals_block("artist-totals", [
            ("t-artists", "Artistas", ""), ("t-sold", "Lotes vendidos", "note"),
            ("t-rate", "Tasa de venta", ""), ("t-revenue", "Volumen adjudicado", "hi"),
            ("t-avg", "Precio medio", ""),
            # Cobertura del maestro: sin esta tarjeta, "200 artistas" se lee
            # como 200 fichas completas.
            ("t-dated", "Con fechas", "note"),
        ])
        + "<div class='scroll'><table id='artist-table'><thead><tr><th>#</th>"
        "<th>Artista</th><th>Vendidos</th><th>Tasa venta</th><th>Volumen</th>"
        f"<th>Récord</th></tr></thead><tbody>{''.join(rows)}</tbody></table></div>"
        "<p class='empty' id='artist-empty' hidden>Ningún artista coincide con el filtro.</p>"
        + caveats + "</section>"
    )


def build_country_table(countries: list[dict],
                        country_year: list[dict] | None = None,
                        gap: int = 0) -> str:
    known = [c for c in countries if c.get("country")]
    unknown = next((c for c in countries if not c.get("country")), None)
    if not known:
        return ""
    rows = []
    for i, c in enumerate(known, 1):
        st = (c.get("sell_through_rate") or 0) * 100
        name = c.get("country_es") or c.get("country")
        rows.append(
            f"<tr data-name='{esc((name or '').lower())}' "
            f"data-code='{esc(c.get('country') or '')}' "
            f"data-artists='{c.get('artists') or 0}' "
            f"data-sold='{c.get('lots_sold') or 0}' "
            f"data-offered='{c.get('lots_offered') or 0}' "
            f"data-revenue='{c.get('revenue_eur') or 0}'>"
            f"<td class='rank'>{i}</td>"
            f"<th scope='row'><span class='name'>{esc(name)}</span>"
            f"<span class='meta'>{num(c.get('artists'))} artistas</span></th>"
            f"<td class='n'>{num(c.get('lots_sold'))}"
            f"<span class='sub'>de {num(c.get('lots_offered'))}</span></td>"
            f"<td class='n'>{pct(st)}</td>"
            f"<td class='n strong'>{esc(eur(c.get('revenue_eur')))}</td>"
            f"<td>{esc(c.get('top_artist') or '')}</td></tr>"
        )
    caveats = (
        "<p class='caveat'>Se agrupa por país de <strong>nacimiento</strong>, así que "
        "cada lote cuenta una sola vez. Un artista con doble nacionalidad aparece en un "
        "solo país aquí; sus otras nacionalidades se ven junto a su nombre.</p>"
        "<p class='caveat'>Ojo al comparar países: solo 66 de unos 15.000 nombres "
        "coinciden entre Durán (mercado español) y Bogotá (colombiano), así que el país "
        "del artista va casi calcado al de la casa. Un gráfico “España vs Colombia” "
        "está, en buena medida, comparando esas dos casas.</p>"
        "<p class='caveat'><strong>Zorrilla no entra en este ranking</strong>: su fuente "
        "no publica un campo de artista separado, así que sus lotes no tienen autor que "
        "atribuir.</p>"
    )
    if unknown and unknown.get("lots_offered"):
        caveats += (
            f"<p class='caveat'>Quedan {num(unknown.get('lots_offered'))} lotes de "
            "artistas sin país en el maestro. No se reparten entre los países conocidos: "
            "se dejan fuera para no inflar ninguno.</p>"
        )
    # Los totales por pais no aplican el corte del ranking y la tabla de
    # artistas si: sin decirlo, la diferencia parece un error de suma.
    if gap:
        caveats += f"<p class='caveat'>{country_metrics_caveat(gap)}</p>"
    heat = heatmap_matrix(country_year or [])
    heat_block = ""
    if heat.get("rows"):
        heat_block = (
            "<h3>Doce años, país por país</h3>"
            "<div class='chart-box'>"
            + heatmap_chart(heat)
            + f"<p class='caveat'>{CAVEAT_COUNTRY_IS_HOUSE}</p>"
            + f"<p class='caveat'>{CAVEAT_FX_TIMESERIES}</p>"
            "</div>"
        )
    return (
        "<section><h2>De dónde viene el arte</h2>"
        "<p class='lead'>Volumen adjudicado por país de nacimiento del artista, según el "
        "maestro de artistas.</p>"
        + heat_block
        + "<h3>El detalle por país</h3>"
        "<div class='controls'>"
        "<label>Buscar país<input type='search' id='country-search' "
        "placeholder='p. ej. Colombia' autocomplete='off'></label>"
        "<button type='button' class='btn' id='country-reset'>Limpiar</button>"
        + dl_buttons("country") + "</div>"
        + totals_block("country-totals", [
            ("c-countries", "Países", ""), ("c-artists", "Artistas", ""),
            ("c-sold", "Lotes vendidos", "note"), ("c-rate", "Tasa de venta", ""),
            ("c-revenue", "Volumen adjudicado", "hi"),
        ])
        + "<div class='scroll'><table id='country-table'><thead><tr><th>#</th>"
        "<th>País</th><th>Vendidos</th><th>Tasa venta</th><th>Volumen</th>"
        f"<th>Artista destacado</th></tr></thead><tbody>{''.join(rows)}</tbody>"
        "</table></div>"
        "<p class='empty' id='country-empty' hidden>Ningún país coincide con el filtro.</p>"
        + caveats + "</section>"
    )


def build_charts(rep: dict) -> str:
    by_year = rep.get("by_year", [])
    by_month = [
        {"label": MONTH_LABELS.get(m["month"], m["month"]),
         "revenue_eur": m.get("revenue_eur", 0)}
        for m in rep.get("by_month", [])
    ]
    by_yh = rep.get("by_year_by_house", [])
    houses = [h["house_slug"] for h in sorted(
        rep.get("by_house", []), key=lambda r: -(r.get("revenue_eur") or 0))]
    # Se recorren TODAS las casas: un zip() con una lista corta de colores
    # dejaria fuera de la leyenda a las que sobren, y en silencio.
    keys = "".join(
        f"<span class='key'><i style='background:var(--{series_color(i)})'></i>"
        f"{esc(HOUSE_LABELS.get(h, h))}</span>"
        for i, h in enumerate(houses)
    )
    return (
        "<section><h2>Cómo se mueve el mercado</h2>"
        "<p class='lead'>Volumen adjudicado en euros. Pasa el ratón por una barra para "
        "ver la cifra exacta.</p>"
        "<div class='charts'>"
        "<div class='card'><h3>Por año</h3><p>Todo el periodo cubierto.</p>"
        + bar_chart(by_year, "revenue_eur", "year") + "</div>"
        "<div class='card'><h3>Por mes</h3><p>Estacionalidad: solo lotes con fecha real.</p>"
        + bar_chart(by_month, "revenue_eur", "label") + "</div>"
        "<div class='card'><h3>Por año y casa</h3><p>Quién aporta cada año.</p>"
        + stacked_chart(by_yh, houses) + f"<div class='legend'>{keys}</div></div>"
        "</div></section>"
    )


# ---------------------------------------------------------------------------
# JS: filtro + totalizador + descarga CSV. Todo inline, sin dependencias.
# ---------------------------------------------------------------------------

JS = r"""
(function () {
  var root = document.documentElement;
  var toggle = document.getElementById('theme');
  function isDark() {
    var t = root.getAttribute('data-theme');
    if (t) return t === 'dark';
    return window.matchMedia('(prefers-color-scheme: dark)').matches;
  }
  function label() { toggle.textContent = isDark() ? 'Modo claro' : 'Modo oscuro'; }
  toggle.addEventListener('click', function () {
    root.setAttribute('data-theme', isDark() ? 'light' : 'dark');
    label();
  });
  label();

  // Se pliegan los acentos para que buscar "tapies" encuentre "Tapies" con acento.
  function fold(s) {
    return (s || '').normalize('NFKD').replace(/[̀-ͯ]/g, '')
      .toLowerCase().trim();
  }
  var nf = new Intl.NumberFormat('es-ES');
  // En espaniol Intl deja "6190" sin punto de millar (es la norma ortografica),
  // pero en una columna de dinero se lee mal.
  function miles(v) {
    var s = nf.format(v);
    return /^\d{4}$/.test(s) ? s.slice(0, 1) + '.' + s.slice(1) : s;
  }
  function money(v) {
    if (v >= 1e6) return nf.format(Math.round(v / 1e4) / 100) + ' M€';
    if (v >= 1e4) return miles(Math.round(v / 1e3)) + ' k€';
    return miles(Math.round(v)) + ' €';
  }
  // El precio medio es un importe unitario: "11 k€" esconde si son 11.000 o 11.400.
  function unit(v) { return v >= 1e6 ? money(v) : miles(Math.round(v)) + ' €'; }
  function set(id, t) { var e = document.getElementById(id); if (e) e.textContent = t; }

  // Separador ';' y BOM: es lo que abre bien el Excel en espaniol. Con ',' mete
  // toda la fila en una celda, y sin BOM se rompen los acentos.
  function csv(head, rows) {
    function cell(v) {
      if (v === null || v === undefined) return '';
      var s = String(v);
      return /[";\n\r]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
    }
    return '﻿' + [head].concat(rows).map(function (r) {
      return r.map(cell).join(';');
    }).join('\r\n');
  }
  // Aviso propio: en el iframe de un Artifact, alert() puede estar bloqueado y
  // si lanza se lleva por delante el resto del manejador.
  function say(msg, bad) {
    var box = document.getElementById('toast');
    if (!box) return;
    box.textContent = msg;
    box.className = 'toast show' + (bad ? ' bad' : '');
    clearTimeout(box._t);
    box._t = setTimeout(function () { box.className = 'toast'; }, 5000);
  }

  // La descarga se intenta por tres vias. Un Artifact corre en un iframe con
  // sandbox, donde <a download> sobre un blob puede quedar bloqueado sin avisar:
  // por eso hay plan B (abrir en pestania) y plan C (copiar al portapapeles),
  // y el usuario siempre recibe una confirmacion de lo que ha pasado.
  function save(name, text, filas) {
    var ok = false;
    try {
      var blob = new Blob([text], {type: 'text/csv;charset=utf-8;'});
      if (navigator.msSaveBlob) {                       // Edge antiguo
        navigator.msSaveBlob(blob, name);
        ok = true;
      } else {
        var url = URL.createObjectURL(blob);
        var a = document.createElement('a');
        if ('download' in a) {
          a.href = url; a.download = name;
          a.style.display = 'none';
          document.body.appendChild(a);
          a.click();
          document.body.removeChild(a);
          ok = true;
        }
        setTimeout(function () { URL.revokeObjectURL(url); }, 4000);
      }
    } catch (e) { ok = false; }

    if (ok) { say('Descargado ' + name + ' · ' + filas + ' filas'); return; }

    // Plan B: abrir el CSV en una pestania para guardarlo a mano.
    try {
      var w = window.open('', '_blank');
      if (w) {
        w.document.write('<pre>' + text.replace(/[<&]/g, function (c) {
          return c === '<' ? '&lt;' : '&amp;';
        }) + '</pre>');
        w.document.close();
        say('Tu navegador bloqueó la descarga directa: el CSV se ha abierto en ' +
            'otra pestaña para que lo guardes.');
        return;
      }
    } catch (e) {}

    // Plan C: al portapapeles.
    try {
      navigator.clipboard.writeText(text).then(function () {
        say('Descarga bloqueada aquí. El CSV (' + filas + ' filas) está en el ' +
            'portapapeles: pégalo en un fichero .csv.');
      }, function () {
        say('Este visor no permite descargar. Abre el informe fuera del panel ' +
            'para guardar el CSV.', true);
      });
    } catch (e) {
      say('Este visor no permite descargar. Abre el informe fuera del panel ' +
          'para guardar el CSV.', true);
    }
  }
  function slug(s) {
    return fold(s).replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') || 'todo';
  }

  // Detalle lote a lote, desempaquetado del formato comprimido.
  var LOTS = (function () {
    var p = window.LOT_DETAILS;
    if (!p || !p.rows) return [];
    return p.rows.map(function (r) {
      var o = {};
      p.cols.forEach(function (c, i) { o[c] = p.dict[c] ? p.dict[c][r[i]] : r[i]; });
      return o;
    });
  })();
  var LOT_HEAD = ['Artista', 'Pais', 'Casa', 'Subasta', 'Fecha', 'Lote', 'Titulo',
                  'Estado', 'Vendido', 'Precio', 'Moneda', 'Precio EUR', 'URL',
                  'Clave artista'];
  function lotLine(l) {
    return [l.artist_name, l.country, l.house_slug, l.auction_id, l.auction_start_date,
            l.lot_number, l.lot_title, l.status, l.sold ? 'si' : 'no', l.price_sold,
            l.currency, l.price_sold_eur, l.lot_url, l.artist_key];
  }

  function wire(cfg) {
    var table = document.getElementById(cfg.table);
    if (!table) return;
    // Las fichas quedan fuera: son detalle de la fila de arriba, no filas de
    // datos. Si entraran, contarian como artista en los totales.
    var rows = Array.prototype.slice.call(table.tBodies[0].rows)
      .filter(function (r) { return r.className.indexOf('artist-card') < 0; });
    var empty = document.getElementById(cfg.empty);
    var totals = document.getElementById(cfg.totals);
    var inputs = cfg.inputs.map(function (id) { return document.getElementById(id); })
      .filter(Boolean);
    var reset = document.getElementById(cfg.reset);

    function visible() {
      return rows.filter(function (r) { return !r.hidden; });
    }

    function apply() {
      var q = fold(cfg.search ? (document.getElementById(cfg.search) || {}).value : '');
      var sel = cfg.select ? (document.getElementById(cfg.select) || {}).value : '';
      var n = 0, sold = 0, offered = 0, revenue = 0, artists = 0, dated = 0;
      // Filtro extra opcional (presencia en varias casas), aparte del selector
      // de pais para que wire() siga sirviendo a las dos tablas.
      var extraEl = cfg.extra ? document.getElementById(cfg.extra) : null;
      var extra = extraEl ? extraEl.value : '';
      rows.forEach(function (row) {
        var okExtra = !extra ||
          (extra === 'multi' ? row.dataset.kind !== 'single'
                             : row.dataset.kind === extra);
        var ok = (!q || fold(row.dataset.name).indexOf(q) >= 0) &&
                 (!sel || row.dataset.country === sel) && okExtra;
        row.hidden = !ok;
        // La ficha sigue a su fila: al ocultarse el artista se cierra, o
        // quedaria abierta bajo un filtro que ya no la incluye.
        if (row.dataset.card) {
          var fcard = document.getElementById(row.dataset.card);
          if (fcard && !ok && !fcard.hidden) {
            fcard.hidden = true;
            var fbtn = row.querySelector('.artist-toggle');
            if (fbtn) fbtn.setAttribute('aria-expanded', 'false');
          }
        }
        if (!ok) return;
        n++;
        sold += Number(row.dataset.sold) || 0;
        offered += Number(row.dataset.offered) || 0;
        revenue += Number(row.dataset.revenue) || 0;
        artists += Number(row.dataset.artists) || 0;
        // Basta el anio de nacimiento: exigir los dos dejaria fuera a los
        // artistas vivos, que no son un hueco de datos.
        if (row.dataset.birth) dated++;
      });
      // La tasa se recalcula sobre los totales. Promediar las tasas de cada fila
      // da un numero distinto y equivocado cuando las filas tienen tamanios
      // diferentes.
      set(cfg.ids.count, miles(n));
      if (cfg.ids.artists) set(cfg.ids.artists, miles(artists));
      set(cfg.ids.sold, miles(sold));
      set(cfg.ids.sold + '-n', offered ? 'de ' + miles(offered) + ' ofertados' : '');
      set(cfg.ids.rate, offered ? (sold / offered * 100).toFixed(1).replace('.', ',') + '%' : '—');
      set(cfg.ids.revenue, money(revenue));
      if (cfg.ids.avg) set(cfg.ids.avg, sold ? unit(revenue / sold) : '—');
      if (cfg.ids.dated) {
        set(cfg.ids.dated, n ? (dated / n * 100).toFixed(0) + '%' : '—');
        set(cfg.ids.dated + '-n', n ? miles(dated) + ' de ' + miles(n) + ' artistas' : '');
      }
      empty.hidden = n !== 0;
      totals.classList.toggle('on', n !== rows.length);
    }

    inputs.forEach(function (el) {
      el.addEventListener(el.tagName === 'SELECT' ? 'change' : 'input', apply);
    });
    if (reset) reset.addEventListener('click', function () {
      inputs.forEach(function (el) { el.value = ''; });
      apply();
    });

    function tag() {
      return inputs.map(function (el) { return el.value; }).filter(Boolean).join('-');
    }
    var dv = document.getElementById(cfg.dlView);
    if (dv) dv.addEventListener('click', function () {
      var vis = visible();
      if (!vis.length) { say('No hay filas que descargar con este filtro.', true); return; }
      save(cfg.prefix + '-' + slug(tag()) + '.csv',
           csv(cfg.viewHead, vis.map(cfg.viewLine)), vis.length);
    });
    var dl = document.getElementById(cfg.dlLots);
    if (dl) dl.addEventListener('click', function () {
      var keys = {};
      visible().forEach(function (r) { keys[cfg.matchKey(r)] = 1; });
      var sel = LOTS.filter(function (l) { return keys[cfg.lotKey(l)]; });
      if (!sel.length) {
        say('No hay detalle de lotes para esta selección: solo se exportan los ' +
            'lotes de artistas con país en el maestro.', true);
        return;
      }
      save(cfg.prefix + '-lotes-' + slug(tag()) + '.csv',
           csv(LOT_HEAD, sel.map(lotLine)), sel.length);
    });

    apply();
  }

  function rate(row) {
    return row.dataset.offered > 0
      ? (row.dataset.sold / row.dataset.offered * 100).toFixed(1) : '';
  }

  wire({
    table: 'artist-table', empty: 'artist-empty', totals: 'artist-totals',
    search: 'artist-search', select: 'country-filter', reset: 'artist-reset',
    extra: 'kind-filter',
    inputs: ['artist-search', 'country-filter', 'kind-filter'],
    ids: {count: 't-artists', sold: 't-sold', rate: 't-rate',
          revenue: 't-revenue', avg: 't-avg', dated: 't-dated'},
    dlView: 'artist-dl-view', dlLots: 'artist-dl-lots', prefix: 'artistas',
    viewHead: ['Artista', 'Pais nacimiento', 'Nacimiento', 'Muerte',
               'Nacionalidades', 'Lotes vendidos',
               'Lotes ofertados', 'Tasa venta', 'Volumen EUR', 'Record EUR'],
    viewLine: function (row) {
      return [row.cells[1].querySelector('.name').textContent,
              row.dataset.country === '__none__' ? '' : row.dataset.country,
              // Columnas propias: dentro de .meta acabarian en "Nacionalidades".
              row.dataset.birth || '', row.dataset.death || '',
              row.cells[1].querySelector('.meta').textContent,
              row.dataset.sold, row.dataset.offered, rate(row),
              row.dataset.revenue, row.cells[5].textContent.trim()];
    },
    // Por la clave del pipeline, no por el nombre plegado: el fold junta a dos
    // personas distintas que se llaman igual.
    matchKey: function (row) { return row.dataset.key; },
    lotKey: function (l) { return l.artist_key; },
  });

  wire({
    table: 'country-table', empty: 'country-empty', totals: 'country-totals',
    search: 'country-search', reset: 'country-reset', inputs: ['country-search'],
    ids: {count: 'c-countries', artists: 'c-artists', sold: 'c-sold',
          rate: 'c-rate', revenue: 'c-revenue'},
    dlView: 'country-dl-view', dlLots: 'country-dl-lots', prefix: 'paises',
    viewHead: ['Pais', 'Artistas', 'Lotes vendidos', 'Lotes ofertados', 'Tasa venta',
               'Volumen EUR', 'Artista destacado'],
    viewLine: function (row) {
      return [row.cells[1].querySelector('.name').textContent, row.dataset.artists,
              row.dataset.sold, row.dataset.offered, rate(row),
              row.dataset.revenue, row.cells[5].textContent.trim()];
    },
    // El detalle guarda el codigo ISO ("CO"), la tabla muestra "Colombia":
    // se cruza por el codigo, que es la clave real.
    matchKey: function (row) { return row.dataset.code; },
    lotKey: function (l) { return l.country; },
  });

  // Fichas de artista. El contenido ya viene renderizado desde Python, asi que
  // esto solo abre y cierra: si el visor restringiera el script, la ficha
  // seguiria estando en el documento.
  (function () {
    var table = document.getElementById('artist-table');
    if (!table) return;
    var openBtn = null;

    function close(btn) {
      if (!btn) return;
      var card = document.getElementById(btn.getAttribute('aria-controls'));
      if (card) card.hidden = true;
      btn.setAttribute('aria-expanded', 'false');
      if (openBtn === btn) openBtn = null;
    }

    table.addEventListener('click', function (ev) {
      var btn = ev.target;
      while (btn && btn !== table && btn.className.indexOf('artist-toggle') < 0) {
        btn = btn.parentNode;
      }
      if (!btn || btn === table) return;
      var card = document.getElementById(btn.getAttribute('aria-controls'));
      if (!card) return;
      var isOpen = btn.getAttribute('aria-expanded') === 'true';
      // Acordeon: dos fichas abiertas en 200 filas hacen perder el sitio.
      if (openBtn && openBtn !== btn) close(openBtn);
      if (isOpen) { close(btn); return; }
      card.hidden = false;
      btn.setAttribute('aria-expanded', 'true');
      openBtn = btn;
    });

    // Escape cierra y devuelve el foco al boton: sin esto, quien navega con
    // teclado se queda huerfano al final de la tabla.
    table.addEventListener('keydown', function (ev) {
      if (ev.key !== 'Escape' || !openBtn) return;
      var btn = openBtn;
      close(btn);
      btn.focus();
    });
  })();
})();
"""


def build(rep: dict, details: list[dict]) -> str:
    s = rep["summary"]
    # Lotes por artista para las fichas. Se indexa una vez: buscarlos por
    # artista dentro del bucle seria O(artistas x lotes) sobre 22.888 filas.
    lots_by_artist: dict[str, list[dict]] = {}
    for d in details:
        key = d.get("artist_key")
        if key:
            lots_by_artist.setdefault(key, []).append(d)
    dist = rep.get("price_distribution") or {}
    years = [r["year"] for r in rep.get("by_year", []) if str(r.get("year", "")).isdigit()]
    span = f"{min(years)}–{max(years)}" if years else "histórico"

    bands = dist.get("bands") or []
    if bands:
        tl = sum(b["lots"] for b in bands) or 1
        tr = sum(b["revenue_eur"] for b in bands) or 1
        top = bands[-1]
        dek = (
            f"{num(s['total_lots'])} lotes de {s['total_houses']} casas de subastas, "
            f"{span}. El {top['lots'] / tl * 100:.1f}% más caro de lo vendido concentra "
            f"el {top['revenue_eur'] / tr * 100:.0f}% del dinero."
        ).replace(".", ",", 1)
    else:
        dek = f"{num(s['total_lots'])} lotes de {s['total_houses']} casas, {span}."

    body = "".join([
        "<div class='wrap'>",
        "<header class='masthead'><div>",
        "<p class='eyebrow'>Informe Gold · Mercado del arte</p>",
        "<h1>Qué se vende, a quién y por cuánto</h1>",
        f"<p class='dek'>{esc(dek)}</p></div>",
        "<button type='button' class='theme' id='theme'>Modo oscuro</button>",
        "</header>",
        build_kpis(rep),
        build_flags(rep.get("quality_flags", [])),
        build_charts(rep),
        build_house_table(rep.get("by_house", [])),
        build_artist_table(rep.get("by_artist", []), rep.get("artist_coverage") or {},
                           lots_by_artist, rep.get("by_generation") or []),
        build_country_table(rep.get("by_country", []),
                            rep.get("by_country_year") or [],
                            rep.get("country_lots_below_rank_cutoff") or 0),
        "<footer>",
        f"<p><strong>Conversión de moneda.</strong> {esc(fx_note())}</p>",
        "<p><strong>Procedencia.</strong> Datos extraídos de las webs públicas de las "
        "casas de subastas y refinados por una cadena bronze → silver → gold. Este "
        "informe lee únicamente la capa Gold.</p>",
        "<p><strong>Verificación.</strong> Los botones “Tabla” y “Lotes” de cada sección "
        "descargan en CSV exactamente lo que hay filtrado en pantalla, con el enlace al "
        "lote original en la web de la casa. Las cifras no hay que creérselas: se "
        "comprueban.</p>",
        "</footer></div>",
        "<div class='toast' id='toast' role='status' aria-live='polite'></div>",
    ])

    packed = json.dumps(pack_lot_details(details), ensure_ascii=False, separators=(",", ":"))
    return (
        "<div id='app'></div>"
        f"<style>{CSS}</style>{body}"
        f"<script>window.LOT_DETAILS={packed};</script>"
        f"<script>{JS}</script>"
    )


def main() -> None:
    ap = argparse.ArgumentParser(description="Genera el informe para publicar como Artifact.")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args()

    report_path = GOLD_ROOT / "analytics_report.json"
    if not report_path.exists():
        raise SystemExit(
            f"No encontrado: {report_path}. Ejecuta antes "
            "python -m pipelines.analytics.report_gold"
        )
    rep = json.loads(report_path.read_text(encoding="utf-8"))
    details = load_jsonl(GOLD_ROOT / "lot_details.jsonl")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(build(rep, details), encoding="utf-8")
    size = args.out.stat().st_size / 1024 / 1024
    print(f"[artifact] {args.out}  ({size:.2f} MB, {len(details):,} lotes de detalle)")


if __name__ == "__main__":
    main()

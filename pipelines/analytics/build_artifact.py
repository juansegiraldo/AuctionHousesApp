#!/usr/bin/env python3
"""La app del mercado del arte: una carpeta estatica, pensada primero para movil.

Es el unico renderer del informe. Antes habia dos (Plotly local + este) y vivian
divergiendo: uno decia "las tres casas" con cuatro, el otro imprimia codigos
ISO. Se quedo este porque no depende de ningun CDN: funciona igual publicado
como Artifact de Claude (CSP que bloquea todo host externo) que servido desde
Vercel o cualquier hosting estatico.

Salida (data/gold/app/):
  - index.html  la app: CSS, JS y graficos SVG inline. Ligera a proposito.
  - lots.json   detalle lote a lote para el CSV de "Lotes". Se pide al abrir
                el menu de descargas, no al cargar: son ~7 MB que el 99% de
                las visitas desde el movil no necesitan.
  - cards.json  las fichas de artista ya renderizadas en Python. Se pide al
                entrar en Artistas. Iban inline (1.292 fichas, ~4 MB de DOM
                oculto) y eran la mitad del peso del fichero.

fetch() no funciona abriendo index.html con file://. En local:
    python -m http.server -d data/gold/app

Graficos: SVG generado en Python, sin libreria en el cliente. Cada marca lleva
data-x/data-l/data-v y un unico manejador de puntero escribe su valor en una
lectura encima del grafico: en una pantalla tactil el <title> del SVG no sale
nunca, asi que sin esto las cifras exactas eran inaccesibles desde el movil.

Uso:
    python -m pipelines.analytics.build_artifact
    python -m pipelines.analytics.build_artifact --out ruta/a/carpeta
"""

from __future__ import annotations

import argparse
import html
import json
import math
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
    _rank_selection,
    pack_lot_details,
)
from pipelines.shared.fx import fx_note

ROOT = Path(__file__).resolve().parents[2]
GOLD_ROOT = ROOT / "data" / "gold"
DEFAULT_OUT = GOLD_ROOT / "app"

# Cuantos artistas se listan. Mas alla el HTML crece sin que nadie los lea:
# el detalle completo se descarga en CSV.
ARTIST_LIMIT = 200

# Cuantos puntos entran en el scatter SVG. A 320 unidades de ancho la cola larga
# se solapa en una mancha sin informacion, y cada circulo pesa. El recorte se
# declara al pie del grafico, con el volumen que deja fuera.
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


def money(v) -> str:
    """Importe corto. Replica money() del JS: la cifra de la cabecera la escribe
    Python y luego la reanima el script, y no pueden salir con formatos distintos."""
    if v is None:
        return "—"
    if v >= 1e6:
        s = f"{round(v / 1e4) / 100:.2f}".rstrip("0").rstrip(".")
        return s.replace(".", ",") + " M€"
    if v >= 1e4:
        return num(round(v / 1e3)) + " k€"
    return num(round(v)) + " €"


def short_house(slug: str) -> str:
    return HOUSE_LABELS.get(slug, slug).split()[0]


def generation_coverage_block(generations: list[dict]) -> str:
    """Banda de cobertura: la ausencia de fecha queda visible, fuera del eje."""
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
        f"<strong>Con década</strong> {esc(eur(cov['dated_revenue_eur']))}, "
        f"{esc(num(cov['dated_artists']))} artistas</span>"
        "<span><i class='generation-key generation-key-missing'></i>"
        f"<strong>Sin fecha</strong> {esc(eur(cov['missing_revenue_eur']))}, "
        f"{esc(num(cov['missing_artists']))} artistas "
        f"({esc(pct(cov['missing_artists_pct']))})</span>"
        "</div></div>"
    )


def load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def notes(*paras: str, summary: str = "Cómo leer este dato") -> str:
    """Salvedades plegadas bajo su grafico.

    Siguen pegadas al dato que matizan (no en un apendice), pero en el movil
    seis parrafos abiertos entierran el grafico que explican.
    """
    paras = tuple(p for p in paras if p)
    if not paras:
        return ""
    body = "".join(f"<p>{p}</p>" for p in paras)
    return f"<details class='notes'><summary>{esc(summary)}</summary>{body}</details>"


# ---------------------------------------------------------------------------
# Graficos: SVG generado aqui, sin libreria en el cliente
# ---------------------------------------------------------------------------

# Geometria de los graficos, en unidades del viewBox. NO se usa
# preserveAspectRatio='none': estirar el SVG deforma tambien el texto y las
# etiquetas del eje salen aplastadas y solapadas unas sobre otras.
CH_W, CH_H = 320.0, 188.0
CH_PAD_B, CH_PAD_T = 26.0, 6.0
PLOT_H = CH_H - CH_PAD_B - CH_PAD_T


def _svg(inner: str, *, w: float = CH_W, h: float = CH_H, mode: str = "x",
         extra_cls: str = "", label: str = "") -> str:
    # tabindex: el grafico se recorre con las flechas, no solo con el dedo.
    return (
        f"<svg class='chart scrub {extra_cls}' viewBox='0 0 {w:.0f} {h:.0f}' "
        f"preserveAspectRatio='xMidYMid meet' role='img' tabindex='0' "
        f"data-mode='{mode}' data-base='{h - CH_PAD_B:.1f}' "
        f"aria-label='{esc(label)}'>{inner}</svg>"
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
    # Cada etiqueta necesita ~30 unidades para no tocar a la vecina a 10px.
    step = max(1, int(30 / slot + 0.999))
    out = []
    for idx, lab in enumerate(labels):
        if idx % step and idx != n - 1:
            continue
        out.append(
            f"<text class='axis' x='{x0 + idx * slot + slot / 2:.2f}' "
            f"y='{y:.1f}' text-anchor='middle'>{esc(lab)}</text>"
        )
    return "".join(out)


def bar_chart(items, value_key, label_key, *, fmt=money, label: str = "") -> str:
    """Barras verticales, una serie. Cada barra lleva su lectura en data-*."""
    if not items:
        return ""
    top = max((i.get(value_key) or 0) for i in items) or 1
    n = len(items)
    slot = CH_W / n
    bw = max(2.0, slot * 0.62)
    base = CH_H - CH_PAD_B
    parts = [f"<line class='base' x1='0' y1='{base:.1f}' x2='{CH_W:.0f}' y2='{base:.1f}'/>"]
    for idx, it in enumerate(items):
        v = it.get(value_key) or 0
        h = (v / top) * PLOT_H
        lab = it.get(label_key)
        parts.append(
            f"<rect class='bar' x='{idx * slot + (slot - bw) / 2:.2f}' "
            f"y='{base - h:.2f}' width='{bw:.2f}' height='{h:.2f}' rx='2' "
            f"style='--i:{idx}' data-x='{idx * slot + slot / 2:.2f}' "
            f"data-l='{esc(lab)}' data-v='{esc(fmt(v))}'>"
            f"<title>{esc(lab)}: {esc(fmt(v))}</title></rect>"
        )
    parts.append(_axis_labels([str(i.get(label_key)) for i in items], n))
    return _svg("".join(parts), label=label)


def bar_line_chart(bars: list[dict], line: list[float], *, labels: list[str],
                   notes: list[tuple[int, str]] | None = None) -> str:
    """Barras con una linea de porcentaje acumulado.

    La linea va sobre 0-100 mapeado a la misma altura de trazado: es el Pareto,
    y sin ella las barras solas no dicen cuanto se concentra.
    """
    if not bars:
        return ""
    top = max((b.get("value") or 0) for b in bars) or 1
    n = len(bars)
    slot = CH_W / n
    bw = max(2.0, slot * 0.6)
    base_y = CH_H - CH_PAD_B
    parts = [f"<line class='base' x1='0' y1='{base_y:.1f}' x2='{CH_W:.0f}' y2='{base_y:.1f}'/>"]
    for idx, b in enumerate(bars):
        v = b.get("value") or 0
        h = (v / top) * PLOT_H
        parts.append(
            f"<rect class='bar' x='{idx * slot + (slot - bw) / 2:.2f}' "
            f"y='{base_y - h:.2f}' width='{bw:.2f}' height='{h:.2f}' rx='2' "
            f"data-x='{idx * slot + slot / 2:.2f}' data-l='{esc(b.get('label'))}' "
            f"data-v='{esc(money(v))}' data-d='{line[idx]:.0f}% acumulado'>"
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
            f"<circle class='cum-dot' cx='{cx:.2f}' cy='{cy:.2f}' r='2.4'>"
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
        dx = -5 if anchor == "end" else 5
        parts.append(
            f"<text class='note' x='{cx + dx:.2f}' y='{cy - 6:.2f}' "
            f"text-anchor='{anchor}'>{esc(text)}</text>"
        )
    parts.append(_axis_labels(labels, n))
    return _svg("".join(parts), label="Concentración del volumen por tramos del ranking")


# Geometria del scatter: mas alto que las barras porque una nube de puntos
# aplastada no se lee.
SC_W, SC_H = 320.0, 260.0
SC_PAD_L, SC_PAD_B, SC_PAD_T, SC_PAD_R = 34.0, 26.0, 8.0, 6.0


def scatter_chart(points: list[dict]) -> str:
    """Precio medio (y) contra lotes vendidos (x), area = volumen.

    Los dos ejes en logaritmo: en lineal, 9 de cada 10 artistas se apilan en la
    esquina inferior izquierda y el grafico no dice nada.
    """
    if not points:
        return ""
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
            f"<text class='axis' x='{SC_W - SC_PAD_R:.1f}' y='{py(y_b) - 3:.2f}' "
            f"text-anchor='end'>{esc(lab)}</text>"
        )

    # El color sigue al grupo (pais), por orden de aparicion: la leyenda lee la
    # misma lista para que no puedan desincronizarse.
    groups: list[str] = []
    names: dict[str, str] = {}
    for p in points:
        if p["group"] not in groups:
            groups.append(p["group"])
            names[p["group"]] = (
                "Sin país" if p["group"] == "__none__"
                else "Otros países" if p["group"] == "__other__"
                else (p.get("country_es") or p["group"])
            )
    coloured = [g for g in groups if g != "__none__"]

    def cls_for(g: str) -> str:
        if g == "__none__":
            return "pt none"
        return f"pt {series_color(coloured.index(g))}"

    for p in points:
        if p["x"] <= 0 or p["y"] <= 0:
            continue
        r = max(1.4, (p["size"] / max_size) ** 0.5 * 10)
        cx, cy = px(p["x"]), py(p["y"])
        parts.append(
            f"<circle class='{cls_for(p['group'])}' cx='{cx:.2f}' cy='{cy:.2f}' "
            f"r='{r:.2f}' data-x='{cx:.2f}' data-y='{cy:.2f}' "
            f"data-l='{esc(p['name'])}' data-v='{esc(money(p['size']))}' "
            f"data-d='{esc(p['country_es'] or 'sin país')}, {esc(num(p['x']))} vendidos, "
            f"{esc(eur(p['y']))} de media'>"
            f"<title>{esc(p['name'])} ({esc(p['country_es'] or 'sin país')}): "
            f"{esc(p['x'])} vendidos, {esc(eur(p['y']))} de media, "
            f"{esc(eur(p['size']))} total</title></circle>"
        )

    # Quien lleva nombre lo decide narrative.scatter_points (p["label"]): los
    # mayores por volumen mas las referencias fijas.
    for p in points:
        if not p.get("label") or p["x"] <= 0 or p["y"] <= 0:
            continue
        x, y = px(p["x"]), py(p["y"])
        anchor = "end" if x > SC_W * 0.6 else "start"
        parts.append(
            f"<text class='note' x='{x + (-6 if anchor == 'end' else 6):.2f}' "
            f"y='{y - 6:.2f}' text-anchor='{anchor}'>{esc(p['name'])}</text>"
        )

    parts.append(
        f"<text class='axis' x='{SC_PAD_L + pw / 2:.1f}' y='{SC_H - 5:.1f}' "
        f"text-anchor='middle'>Lotes vendidos (escala log)</text>"
    )
    legend = "".join(
        f"<span class='key'><i class='{'none' if g == '__none__' else series_color(coloured.index(g))}'>"
        f"</i>{esc(names[g])}</span>"
        for g in groups
    )
    return (
        _svg("".join(parts), w=SC_W, h=SC_H, mode="xy",
             label="Artistas por lotes vendidos y precio medio")
        + f"<div class='legend'>{legend}</div>"
    )


def heatmap_chart(matrix: dict) -> str:
    """Mapa de calor pais x anio.

    El color va con fill-opacity sobre un solo tono y no con 9 clases CSS: son
    valores continuos, y definir 9 tokens x 3 bloques de tema para una escala
    seria mucho mas fragil que calcular la opacidad aqui.
    """
    rows = matrix.get("rows") or []
    years = matrix.get("years") or []
    if not rows or not years:
        return ""
    pad_l, pad_t, pad_b = 78.0, 12.0, 20.0
    cell_h = 16.0
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
            f"<text class='axis hm-label' x='0' y='{y + cell_h * 0.68:.2f}'>"
            f"{esc(row['label'])}</text>"
        )
        for ci, cell in enumerate(row["cells"]):
            x = pad_l + ci * cell_w
            v = cell["revenue_eur"]
            data = (
                f"data-x='{x + cell_w / 2:.2f}' data-y='{y + cell_h / 2:.2f}' "
                f"data-l='{esc(row['label'])} {esc(cell['year'])}'"
            )
            if not v:
                # Sin lotes NO es volumen cero: se marca como hueco, no con el
                # extremo claro de la escala, que se leeria como "vendio poco".
                parts.append(
                    f"<rect class='hm empty' x='{x:.2f}' y='{y:.2f}' "
                    f"width='{cell_w - 1.5:.2f}' height='{cell_h - 1.5:.2f}' rx='2' "
                    f"{data} data-v='Sin lotes'>"
                    f"<title>{esc(row['label'])} {esc(cell['year'])}: sin lotes</title></rect>"
                )
                continue
            o = 0.12 + (math.log10(v) - llow) / span * 0.88
            detail = (
                f"{num(cell['lots_sold'])} vendidos de {num(cell['lots_offered'])}"
                + (", año inferido" if cell["inferred"] else "")
            )
            parts.append(
                f"<rect class='hm' x='{x:.2f}' y='{y:.2f}' "
                f"width='{cell_w - 1.5:.2f}' height='{cell_h - 1.5:.2f}' rx='2' "
                f"fill-opacity='{min(1.0, o):.3f}' {data} data-v='{esc(money(v))}' "
                f"data-d='{esc(detail)}'>"
                f"<title>{esc(row['label'])} {esc(cell['year'])}: {esc(eur(v))}, "
                f"{esc(detail)}</title></rect>"
            )
            if cell["inferred"]:
                parts.append(
                    f"<path class='hm-inferred' d='M{x:.2f},{y + cell_h - 1.5:.2f} "
                    f"L{x + cell_w - 1.5:.2f},{y:.2f}'/>"
                )
    parts.append(
        _axis_labels(years, len(years), width=w - pad_l, y=h - 6, x0=pad_l)
    )
    return _svg("".join(parts), w=w, h=h, mode="xy",
                label="Volumen por país de nacimiento y año")


WORLD_PATH = ROOT / "pipelines" / "config" / "world_110m.json"

# Tramos fijos en decadas, no cuantiles: "entre 100 k€ y 1 M€" se entiende sin
# leer la leyenda dos veces, y no cambia de significado al reconstruir el dato.
# Con la cola tan larga, una escala lineal pintaria dos paises azules y el
# resto del mundo del mismo celeste.
MAP_BINS = [
    (5e6, "q5", "5 M€ o más"),
    (1e6, "q4", "1–5 M€"),
    (1e5, "q3", "100 k€–1 M€"),
    (1e4, "q2", "10–100 k€"),
    (0.0, "q1", "Menos de 10 k€"),
]

# Encuadres en coordenadas ya proyectadas (Equal Earth, ver
# scripts/build_world_map.py). En un movil Europa entera mide dos centimetros:
# sin zoom, media docena de paises con ventas serian intocables.
MAP_VIEWS = [
    ("mundo", "Mundo", None),
    ("america", "América", "175 -120 251 311"),
    ("europa", "Europa", "472 -204 109 77"),
]


def map_bin(revenue: float) -> str:
    return next(cls for floor, cls, _ in MAP_BINS if revenue >= floor)


def world_map(countries: list[dict], world: dict | None = None) -> tuple[str, list[str]]:
    """Coropletas por pais de nacimiento: gris sin ventas, azul mas oscuro cuanto
    mas vendido. Devuelve el SVG y los paises con ventas que no tienen forma en
    el mapa (Checoslovaquia), para declararlos en vez de perderlos en silencio."""
    if world is None:
        if not WORLD_PATH.exists():
            return "", []
        world = json.loads(WORLD_PATH.read_text(encoding="utf-8"))
    shapes = world["countries"]
    data = {c["country"]: c for c in countries if c.get("country")}
    missing = [c.get("country_es") or code for code, c in data.items() if code not in shapes]

    sold, empty = [], []
    for code, shape in shapes.items():
        c = data.get(code)
        cx, cy = shape["c"]
        common = f"d='{shape['d']}' data-x='{cx}' data-y='{cy}'"
        if c and (c.get("revenue_eur") or 0) > 0:
            name = c.get("country_es") or shape["name"]
            sold.append(
                f"<path class='geo {map_bin(c['revenue_eur'])}' {common} "
                f"data-l='{esc(name)}' data-v='{esc(money(c['revenue_eur']))}' "
                f"data-d='{esc(num(c.get('artists')))} artistas, "
                f"{esc(num(c.get('lots_sold')))} lotes vendidos'>"
                f"<title>{esc(name)}: {esc(eur(c['revenue_eur']))}</title></path>"
            )
        else:
            empty.append(
                f"<path class='geo' {common} data-l='{esc(shape['name'])}' "
                f"data-v='Sin ventas' data-d='ningún artista nacido aquí en el ranking'/>"
            )
    vb = " ".join(f"{v:g}" for v in world["viewBox"])
    # Los paises con ventas van despues: su borde resaltado no queda tapado
    # por el vecino gris.
    svg = (
        f"<svg class='chart scrub map' viewBox='{vb}' data-vb='{vb}' "
        "preserveAspectRatio='xMidYMid meet' role='img' tabindex='0' data-mode='xy' "
        "aria-label='Mapa del volumen vendido por país de nacimiento del artista'>"
        f"{''.join(empty)}{''.join(sold)}</svg>"
    )
    zoom = "<div class='zoom' role='group' aria-label='Zona del mapa'>" + "".join(
        f"<button type='button' data-vb='{esc(v or vb)}' "
        f"aria-pressed='{'true' if key == 'mundo' else 'false'}'>{esc(label)}</button>"
        for key, label, v in MAP_VIEWS
    ) + "</div>"
    legend = "<div class='legend'>" + "".join(
        f"<span class='key'><i class='{cls}'></i>{esc(label)}</span>"
        for _, cls, label in reversed(MAP_BINS)
    ) + "<span class='key'><i class='nd'></i>Sin ventas</span></div>"
    return zoom + svg + legend, missing


# Un color por serie, en el mismo orden que las clases .s0/.s1/... del CSS.
# La leyenda y el grafico leen de aqui para que no puedan desincronizarse: antes
# la leyenda hacia zip() con una lista de 3 y la 4a casa desaparecia sin aviso.
# Paleta validada con el script del skill dataviz (CVD por pares adyacentes) en
# los dos temas; el amarillo y el aguamarina no llegan a 3:1 sobre blanco, y por
# eso todo grafico multiserie lleva leyenda y lectura en texto.
SERIES_COLORS = ["s0", "s1", "s2", "s3"]


def series_color(index: int) -> str:
    """Color de la serie n. Cicla si algun dia hay mas casas que colores."""
    return SERIES_COLORS[index % len(SERIES_COLORS)]


def stacked_chart(rows, houses, *, grow: bool = False) -> str:
    """Barras apiladas por casa y anio, con una columna tactil por anio."""
    if not rows:
        return ""
    years = sorted({r["year"] for r in rows})
    by = {(r["year"], r["house_slug"]): r.get("revenue_eur") or 0 for r in rows}
    top = max(sum(by.get((y, h), 0) for h in houses) for y in years) or 1
    n = len(years)
    slot = CH_W / n
    bw = max(2.0, slot * 0.62)
    base = CH_H - CH_PAD_B
    parts = [f"<line class='base' x1='0' y1='{base:.1f}' x2='{CH_W:.0f}' y2='{base:.1f}'/>"]
    for idx, y in enumerate(years):
        acc = 0.0
        x = idx * slot + (slot - bw) / 2
        total = 0.0
        breakdown = []
        for hi, h in enumerate(houses):
            v = by.get((y, h), 0)
            if not v:
                continue
            total += v
            breakdown.append(f"{short_house(h)} {money(v)}")
            bh = (v / top) * PLOT_H
            acc += bh
            # 1,5 unidades de hueco entre segmentos: sin el, dos casas de color
            # parecido se funden en una sola barra.
            parts.append(
                f"<rect class='bar {series_color(hi)}' x='{x:.2f}' "
                f"y='{base - acc:.2f}' width='{bw:.2f}' "
                f"height='{max(0.6, bh - 1.5):.2f}' style='--i:{idx}' data-col='{idx}'>"
                f"<title>{esc(y)}, {esc(HOUSE_LABELS.get(h, h))}: {esc(eur(v))}</title></rect>"
            )
        parts.append(
            f"<rect class='hit' x='{idx * slot:.2f}' y='0' width='{slot:.2f}' "
            f"height='{base:.2f}' data-col='{idx}' data-x='{idx * slot + slot / 2:.2f}' "
            f"data-l='{esc(y)}' data-v='{esc(money(total))}' "
            f"data-d='{esc(', '.join(breakdown))}'/>"
        )
    parts.append(_axis_labels([str(y) for y in years], n))
    return _svg("".join(parts), extra_cls="grow" if grow else "",
                label="Volumen por año, apilado por casa")


def house_legend(houses: list[str]) -> str:
    # Se recorren TODAS las casas: un zip() con una lista corta de colores
    # dejaria fuera de la leyenda a las que sobren, y en silencio.
    return "<div class='legend'>" + "".join(
        f"<span class='key'><i class='{series_color(i)}'></i>"
        f"{esc(HOUSE_LABELS.get(h, h))}</span>"
        for i, h in enumerate(houses)
    ) + "</div>"


def chart_card(svg: str, value: str, label: str, *, title: str = "",
               extra: str = "", cls: str = "", n: float | None = None) -> str:
    """Tarjeta de grafico con su lectura encima.

    La lectura arranca con un valor util (el pico, el total) y no vacia: es lo
    primero que se lee, y al soltar el dedo vuelve a el.
    """
    if not svg:
        return ""
    head = f"<h3>{esc(title)}</h3>" if title else ""
    data_n = f" data-n='{n:.2f}'" if n is not None else ""
    return (
        f"<figure class='card {cls}'><figcaption>{head}"
        "<p class='ro' aria-live='polite'>"
        f"<span class='ro-v' data-d='{esc(value)}'{data_n}>{esc(value)}</span>"
        f"<span class='ro-l' data-d='{esc(label)}'>{esc(label)}</span></p>"
        f"</figcaption>{svg}{extra}</figure>"
    )


def peak(items: list[dict], vkey: str, lkey: str) -> tuple[str, str]:
    if not items:
        return "—", ""
    best = max(items, key=lambda i: i.get(vkey) or 0)
    return money(best.get(vkey) or 0), f"Máximo en {best.get(lkey)}"


# ---------------------------------------------------------------------------
# Estilos
# ---------------------------------------------------------------------------

# Direccion: data-app tipo Tide Guide. La interfaz es monocroma (tinta sobre un
# gris frio de pared de galeria) y el color se reserva para los datos, asi que
# cada tono que aparece significa una casa o una magnitud, nunca adorno.
CSS = """
*,*::before,*::after{box-sizing:border-box}
/* Varias piezas tienen display propio (.pager, filas en grid): sin esto,
   hidden no las oculta y el paginador sale con un solo resultado. */
[hidden]{display:none!important}
:root{
  color-scheme:light;
  --bg:#EDF1F5; --surface:#FFFFFF; --raised:#F3F6F9;
  --ink:#0F1B2A; --ink-soft:#566375; --line:#DCE2E9; --tint:rgb(15 27 42/.07);
  --s0:#2a78d6; --s1:#eb6834; --s2:#1baf7a; --s3:#eda100;
  --crit:#c93636;
  /* Escala del mapa (validada como ordinal con el script de dataviz) y gris de
     "sin ventas": la ausencia no puede leerse como el tramo mas bajo. */
  --q1:#86b6ef; --q2:#5598e7; --q3:#2a78d6; --q4:#1c5cab; --q5:#104281; --nd:#D3DAE2;
  --glass:rgb(255 255 255/.74);
  --shadow:0 12px 32px rgb(15 27 42/.16);
  --num:ui-rounded,"SF Pro Rounded","Segoe UI Variable Display",system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;
  --sans:system-ui,-apple-system,"Segoe UI",Roboto,"Helvetica Neue",Arial,sans-serif;
  --spring:linear(0,.22 6%,.62 14%,.9 23%,1.03 32%,1.05 40%,1.02 55%,1 70%,1);
}
@media (prefers-color-scheme:dark){
  :root:not([data-theme="light"]){
    color-scheme:dark;
    --bg:#0A1119; --surface:#131C26; --raised:#1A2532;
    --ink:#EAF0F6; --ink-soft:#93A2B3; --line:#243140; --tint:rgb(234 240 246/.08);
    --s0:#3987e5; --s1:#d95926; --s2:#199e70; --s3:#c98500;
    --crit:#e66767;
    --q1:#184f95; --q2:#2a78d6; --q3:#5598e7; --q4:#86b6ef; --q5:#b7d3f6; --nd:#2A3644;
    --glass:rgb(19 28 38/.72);
    --shadow:0 12px 32px rgb(0 0 0/.5);
  }
}
:root[data-theme="dark"]{
  color-scheme:dark;
  --bg:#0A1119; --surface:#131C26; --raised:#1A2532;
  --ink:#EAF0F6; --ink-soft:#93A2B3; --line:#243140; --tint:rgb(234 240 246/.08);
  --s0:#3987e5; --s1:#d95926; --s2:#199e70; --s3:#c98500;
  --crit:#e66767;
  --q1:#184f95; --q2:#2a78d6; --q3:#5598e7; --q4:#86b6ef; --q5:#b7d3f6; --nd:#2A3644;
  --glass:rgb(19 28 38/.72);
  --shadow:0 12px 32px rgb(0 0 0/.5);
}

html{-webkit-text-size-adjust:100%;scroll-padding-top:12px}
body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.5 var(--sans);
  -webkit-font-smoothing:antialiased;overflow-x:hidden;-webkit-tap-highlight-color:transparent}
a{color:var(--s0)}
:focus-visible{outline:2px solid var(--s0);outline-offset:2px}
h1,h2,h3,h4{margin:0;text-wrap:balance}
figure{margin:0}

.app{max-width:1080px;margin:0 auto;
  padding:0 16px calc(104px + env(safe-area-inset-bottom))}
.bar{display:flex;align-items:center;justify-content:space-between;
  padding:calc(12px + env(safe-area-inset-top)) 0 0}
.brand{display:flex;align-items:center;gap:8px;font-size:.92rem;font-weight:600;color:var(--ink-soft)}
.brand svg{color:var(--ink)}
.icon-btn{width:44px;height:44px;display:grid;place-items:center;border-radius:50%;
  border:0;background:var(--surface);color:var(--ink);cursor:pointer;
  box-shadow:inset 0 0 0 1px var(--line)}

.large{font-family:var(--num);font-size:clamp(2.05rem,8.6vw,2.8rem);font-weight:700;
  letter-spacing:-.025em;line-height:1.04;margin:14px 0 18px;max-width:16ch}
.lead{color:var(--ink-soft);margin:-8px 0 18px;max-width:58ch}
h3{font-size:1rem;font-weight:600}
.group{margin:28px 2px 12px;font-size:1.15rem;font-weight:650;letter-spacing:-.01em}
html.js .screen:not([hidden]){animation:in .28s ease both}
@keyframes in{from{opacity:0}}

/* Tarjeta de grafico: la lectura manda, el grafico la responde. */
.card{background:var(--surface);border-radius:22px;padding:16px 14px 14px;margin:0 0 12px;min-width:0}
.card figcaption{margin:0 2px 10px}
.card h3{color:var(--ink-soft);font-size:.86rem;font-weight:500}
.ro{margin:2px 0 0;display:flex;flex-direction:column}
.ro-v{font-family:var(--num);font-weight:700;font-size:1.7rem;letter-spacing:-.015em;
  line-height:1.15;font-variant-numeric:tabular-nums}
.ro-l{font-size:.84rem;color:var(--ink-soft);min-height:2.6em;line-height:1.3}
.hero{padding:20px 16px 14px}
.hero .ro-v{font-size:clamp(3.1rem,16vw,5rem);line-height:.98;letter-spacing:-.035em}
.hero .ro-l{font-size:.95rem;margin-top:6px;min-height:2.5em}

.chart{display:block;width:100%;height:auto;overflow:visible}
svg.scrub{touch-action:pan-y;cursor:crosshair;border-radius:8px}
.chart .bar{fill:var(--s0)}
.chart .s0{fill:var(--s0)} .chart .s1{fill:var(--s1)}
.chart .s2{fill:var(--s2)} .chart .s3{fill:var(--s3)}
.chart .bar,.chart .pt,.chart .hm{transition:opacity .15s}
.chart .hit{fill:transparent}
.chart .base{stroke:var(--line);stroke-width:1}
.chart .axis{font-family:var(--sans);font-size:10px;fill:var(--ink-soft)}
.chart .guide{stroke:var(--ink);stroke-width:1;stroke-dasharray:2 2;opacity:0;pointer-events:none}
.scrubbing .bar:not(.on),.scrubbing .pt:not(.on),.scrubbing .hm:not(.on){opacity:.32}
.chart .cum{fill:none;stroke:var(--ink);stroke-width:1.6;stroke-linejoin:round}
.chart .cum-dot{fill:var(--ink)}
.chart .note{font-family:var(--sans);font-size:9.5px;font-weight:600;fill:var(--ink);
  paint-order:stroke;stroke:var(--surface);stroke-width:3px;stroke-linejoin:round;pointer-events:none}
.chart .pt{fill-opacity:.78;stroke:var(--surface);stroke-width:.8}
.chart .pt.none{fill:var(--ink-soft);fill-opacity:.3}
.chart .pt.on{fill-opacity:1;stroke:var(--ink);stroke-width:1.4}
.chart .iso{stroke:var(--ink-soft);stroke-width:.6;stroke-dasharray:2 2;opacity:.6}
.chart .hm{fill:var(--s0)}
.chart .hm.empty{fill:none;stroke:var(--line);stroke-width:.6;stroke-dasharray:1.5 2}
.chart .hm.on{stroke:var(--ink);stroke-width:1.4}
.chart .hm-inferred{stroke:var(--surface);stroke-width:.8;opacity:.7;pointer-events:none}
.chart .hm-label{font-size:9px}
/* Mapa: caja de proporcion fija, para que cambiar de zona no haga saltar la
   pagina; el viewBox se encaja dentro con 'meet'. */
.chart.map{aspect-ratio:7/4;background:var(--raised);border-radius:14px;overflow:hidden}
.chart .geo{fill:var(--nd);stroke:var(--surface);stroke-width:.7;vector-effect:non-scaling-stroke;
  stroke-linejoin:round;transition:fill .2s}
.chart .geo.q1{fill:var(--q1)} .chart .geo.q2{fill:var(--q2)} .chart .geo.q3{fill:var(--q3)}
.chart .geo.q4{fill:var(--q4)} .chart .geo.q5{fill:var(--q5)}
.chart .geo.on{stroke:var(--ink);stroke-width:1.8}
.key i.q1{background:var(--q1)} .key i.q2{background:var(--q2)} .key i.q3{background:var(--q3)}
.key i.q4{background:var(--q4)} .key i.q5{background:var(--q5)} .key i.nd{background:var(--nd)}
.zoom{display:inline-flex;gap:2px;padding:3px;margin:0 0 10px;border-radius:13px;background:var(--raised)}
.zoom button{min-height:40px;padding:0 14px;border:0;border-radius:10px;background:none;
  font:inherit;font-size:.86rem;color:var(--ink-soft);cursor:pointer}
.zoom button[aria-pressed="true"]{background:var(--surface);color:var(--ink);
  box-shadow:0 1px 3px rgb(15 27 42/.14)}
/* El unico momento orquestado: las barras de la cabecera crecen al abrir. */
.grow .bar{transform-box:fill-box;transform-origin:50% 100%;
  animation:grow .8s var(--spring) both;animation-delay:calc(var(--i,0) * 40ms)}
@keyframes grow{from{transform:scaleY(0)}}
.legend{display:flex;flex-wrap:wrap;gap:6px 14px;font-size:.82rem;color:var(--ink-soft);margin:12px 2px 0}
.key{display:inline-flex;align-items:center;gap:6px}
.key i{width:10px;height:10px;border-radius:3px;background:var(--s0)}
.key i.s1{background:var(--s1)} .key i.s2{background:var(--s2)} .key i.s3{background:var(--s3)}
.key i.none{background:var(--ink-soft);opacity:.4}

/* KPIs: carril horizontal en el movil, rejilla en escritorio. */
.rail{display:grid;grid-auto-flow:column;grid-auto-columns:minmax(9.5rem,46%);gap:10px;
  overflow-x:auto;scroll-snap-type:x mandatory;margin:0 -16px 12px;padding:2px 16px 4px;
  scrollbar-width:none;scroll-padding:0 16px}
.rail::-webkit-scrollbar{display:none}
.kpi{scroll-snap-align:start;background:var(--surface);border-radius:18px;padding:14px}
.kpi-l{display:block;font-size:.8rem;color:var(--ink-soft)}
.kpi-v{display:block;font-family:var(--num);font-weight:700;font-size:1.55rem;
  letter-spacing:-.015em;font-variant-numeric:tabular-nums;margin:2px 0;white-space:nowrap}
.kpi-n{display:block;font-size:.76rem;color:var(--ink-soft);line-height:1.35}
.insight{font-size:1.08rem;line-height:1.45;margin:6px 2px 18px;max-width:46ch}

/* Avisos: el critico se ve siempre; el resto, a un toque. */
.alert{display:grid;grid-template-columns:auto 1fr;gap:10px;align-items:start;
  background:var(--surface);border-radius:16px;padding:12px 14px;margin:0 0 10px;font-size:.9rem}
.alert svg{color:var(--crit);margin-top:2px}
.alert strong{display:block;font-weight:600}
details>summary{list-style:none;cursor:pointer}
details>summary::-webkit-details-marker{display:none}
.flags{background:var(--surface);border-radius:16px;margin:0 0 12px}
.flags>summary,.notes>summary{display:flex;align-items:center;gap:8px;min-height:48px;
  padding:0 14px;font-size:.9rem;font-weight:500}
.flags>summary::after,.notes>summary::after{content:'';width:7px;height:7px;margin-left:auto;
  border:solid currentColor;border-width:0 1.6px 1.6px 0;transform:rotate(45deg);
  transition:transform .25s var(--spring);opacity:.6}
.flags[open]>summary::after,.notes[open]>summary::after{transform:rotate(-135deg)}
.flag-list{list-style:none;margin:0;padding:0 14px 14px;display:flex;flex-direction:column;gap:12px}
.flag{font-size:.86rem;line-height:1.45;padding-left:12px;border-left:3px solid var(--line)}
.flag-critical{border-left-color:var(--crit)}
.flag-tag{display:block;font-size:.76rem;color:var(--ink-soft);font-weight:600}
.notes{margin:12px -14px -14px;border-top:1px solid var(--line);font-size:.86rem;color:var(--ink-soft)}
.notes>summary{color:var(--ink);font-size:.86rem;min-height:46px}
.notes p{margin:0 14px 10px;max-width:68ch}
.notes p:last-child{margin-bottom:14px}
.notes code{font-size:.92em;background:var(--raised);padding:1px 5px;border-radius:4px}
.box-notes{background:var(--surface);border-radius:16px;margin:0 0 12px}
.box-notes .notes{margin:0;border:0}

/* Casas */
.houses{display:grid;gap:12px;grid-template-columns:repeat(auto-fit,minmax(17rem,1fr));margin-bottom:12px}
.house{background:var(--surface);border-radius:22px;padding:16px}
.house-head{display:flex;align-items:center;gap:9px}
.house-head h3{font-size:1.02rem}
.dot{width:12px;height:12px;border-radius:50%;flex:0 0 auto;background:var(--s0)}
.dot.s1{background:var(--s1)} .dot.s2{background:var(--s2)} .dot.s3{background:var(--s3)}
.where{margin-left:auto;font-size:.8rem;color:var(--ink-soft);white-space:nowrap}
.house-v{font-family:var(--num);font-size:2.2rem;font-weight:700;letter-spacing:-.025em;
  margin:12px 0 0;line-height:1.1;font-variant-numeric:tabular-nums}
.house-native{font-size:.82rem;color:var(--ink-soft);margin:2px 0 14px}
.meter{height:8px;border-radius:99px;background:var(--raised);overflow:hidden}
.meter span{display:block;height:100%;border-radius:99px;background:var(--ink)}
.house dl{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin:14px 0 0}
.house dt{font-size:.76rem;color:var(--ink-soft)}
.house dd{margin:0;font-family:var(--num);font-weight:650;font-variant-numeric:tabular-nums}

/* Controles: se quedan pegados arriba al bajar por la lista. */
.controls{position:sticky;top:0;z-index:6;display:flex;flex-wrap:wrap;gap:8px;align-items:flex-end;
  padding:10px 16px;margin:0 -16px 10px;background:var(--glass);
  -webkit-backdrop-filter:saturate(1.6) blur(18px);backdrop-filter:saturate(1.6) blur(18px)}
.controls label{display:flex;flex-direction:column;gap:4px;font-size:.75rem;color:var(--ink-soft);
  flex:1 1 8rem;min-width:0}
/* Buscador y menu de descargas comparten la primera linea. */
.controls label.search{flex:1 1 calc(100% - 60px);order:-2}
.controls .more{order:-1}
.controls label:not(.search){flex:1 1 7rem}
.controls input,.controls select{font:inherit;font-size:16px;color:var(--ink);background:var(--surface);
  border:1px solid var(--line);border-radius:12px;padding:0 12px;min-height:44px;width:100%;min-width:0}
.btn,.pager-btn,.more>summary{display:inline-flex;align-items:center;justify-content:center;gap:6px;
  min-height:44px;padding:0 14px;border-radius:12px;border:1px solid var(--line);
  background:var(--surface);color:var(--ink);font:inherit;font-size:.9rem;cursor:pointer}
.more{position:relative}
.more>summary{padding:0;width:44px}
.menu{position:absolute;right:0;top:calc(100% + 6px);z-index:8;min-width:16rem;padding:6px;
  background:var(--surface);border-radius:16px;box-shadow:var(--shadow);display:flex;flex-direction:column}
.dl{display:flex;align-items:center;gap:10px;min-height:46px;padding:0 12px;border:0;border-radius:10px;
  background:none;color:var(--ink);font:inherit;font-size:.92rem;text-align:left;cursor:pointer}
.dl:hover{background:var(--raised)}
.dl small{display:block;color:var(--ink-soft);font-size:.76rem}

/* Totalizador */
.totals{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px;margin-bottom:12px}
.tot{background:var(--surface);border-radius:14px;padding:10px 11px;min-width:0}
.tot-l{display:block;font-size:.72rem;color:var(--ink-soft);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.tot-v{display:block;font-family:var(--num);font-weight:700;font-size:1.06rem;margin-top:1px;
  font-variant-numeric:tabular-nums;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.tot-n{display:block;font-size:.68rem;color:var(--ink-soft);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.totals.on .tot{box-shadow:inset 0 0 0 1px var(--ink-soft)}

/* Tablas que en pantalla son listas. Siguen siendo <table>: el filtro, la
   paginacion y los totales del JS trabajan sobre sus filas. */
.list{display:block;width:100%;border-collapse:separate}
.list thead{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}
.list tbody{display:grid;gap:8px}
.list tr{display:grid;grid-template-columns:1.9rem minmax(0,auto) minmax(0,1fr) auto;
  column-gap:10px;row-gap:3px;align-items:baseline;background:var(--surface);
  border-radius:16px;padding:12px 14px 12px 8px}
.list tr[hidden]{display:none}
.list th,.list td{padding:0;border:0;text-align:left;min-width:0;font-weight:inherit}
.list .rank{grid-row:1/3;align-self:start;text-align:center;font-family:var(--num);
  font-size:.84rem;color:var(--ink-soft);padding-top:2px}
.list th{grid-column:2/4;grid-row:1/3}
.list td.n.strong{color:var(--ink);grid-column:4;grid-row:1;text-align:right;font-family:var(--num);
  font-weight:700;font-size:1.06rem;white-space:nowrap;font-variant-numeric:tabular-nums}
.list td:nth-child(3){grid-column:2;grid-row:3}
.list td:nth-child(4){grid-column:3;grid-row:3}
.list td:nth-child(6){grid-column:4;grid-row:2/4;text-align:right;align-self:end}
.list td.n{font-size:.8rem;color:var(--ink-soft);white-space:nowrap;font-variant-numeric:tabular-nums}
.list td:nth-child(4)::after{content:' vendido'}
#artist-table td:nth-child(6)::before{content:'récord ';color:var(--ink-soft)}
#artist-table td:nth-child(6){font-size:.8rem}
#country-table td:nth-child(6){font-size:.8rem;color:var(--ink-soft);max-width:11rem;
  overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.list tr::after{content:'';grid-column:2/-1;grid-row:4;height:3px;border-radius:2px;margin-top:8px;
  background:linear-gradient(90deg,var(--s0) calc(var(--w,0) * 100%),var(--raised) 0)}
.sub{font-size:.76rem;color:var(--ink-soft);margin-left:.25em}
.name{display:block;font-weight:600;line-height:1.3}
.meta{display:block;font-size:.8rem;color:var(--ink-soft);line-height:1.35}
.meta.none{font-style:italic;opacity:.8}
.artist-toggle{display:block;width:100%;min-height:44px;text-align:left;background:none;border:0;
  padding:0;font:inherit;color:inherit;cursor:pointer}
.artist-toggle .name::after{content:'';display:inline-block;width:6px;height:6px;margin-left:.45rem;
  border:solid var(--ink-soft);border-width:1.6px 1.6px 0 0;transform:translateY(-1px) rotate(45deg)}
.empty{color:var(--ink-soft);font-size:.92rem;padding:24px 4px;margin:0;text-align:center}
.pager{display:flex;align-items:center;justify-content:center;gap:12px;padding:14px 0 0;flex-wrap:wrap}
.pager-btn:disabled{opacity:.4;cursor:default}
.pager-info{font-size:.85rem;color:var(--ink-soft);font-variant-numeric:tabular-nums}

/* Generaciones */
.generation-coverage{margin-top:14px;padding:12px;border-radius:14px;background:var(--raised)}
.generation-coverage-head{display:flex;justify-content:space-between;gap:10px;align-items:baseline;
  flex-wrap:wrap;font-size:.78rem;color:var(--ink-soft)}
.generation-coverage-head strong{color:var(--ink)}
.generation-track{display:flex;height:8px;margin:8px 0;border-radius:99px;overflow:hidden;background:var(--line)}
.generation-dated{background:var(--s0)}
.generation-missing{background:var(--ink-soft);opacity:.45}
.generation-legend{display:flex;flex-direction:column;gap:4px;font-size:.78rem;color:var(--ink-soft)}
.generation-legend span{display:flex;align-items:center;gap:6px}
.generation-legend strong{color:var(--ink);font-weight:600}
.generation-key{width:9px;height:9px;border-radius:2px;flex:0 0 auto}
.generation-key-dated{background:var(--s0)}
.generation-key-missing{background:var(--ink-soft);opacity:.45}

/* Hoja inferior: la ficha de artista. <dialog> nativo, sin libreria. */
.sheet{margin:auto auto 0;width:100%;max-width:680px;max-height:90dvh;padding:0;border:0;
  border-radius:24px 24px 0 0;background:var(--surface);color:var(--ink);box-shadow:var(--shadow)}
.sheet[open]{display:flex;flex-direction:column;animation:up .5s var(--spring)}
.sheet::backdrop{background:rgb(8 14 22/.42)}
@keyframes up{from{transform:translateY(100%)}}
.sheet-top{display:flex;justify-content:flex-end;padding:8px 8px 0;position:relative}
.sheet-top::before{content:'';position:absolute;left:50%;top:8px;width:38px;height:5px;
  margin-left:-19px;border-radius:99px;background:var(--line)}
.sheet-top form{margin:0}
.sheet-body{overflow:auto;overscroll-behavior:contain;padding:0 16px calc(20px + env(safe-area-inset-bottom))}
.loading{color:var(--ink-soft);padding:30px 0;text-align:center;margin:0}
.acard-head{margin:0 0 14px}
.acard-head h4{font-family:var(--num);font-size:1.7rem;font-weight:700;letter-spacing:-.02em;line-height:1.1}
.acard-res{display:block;margin-top:4px;font-size:.8rem;color:var(--ink-soft)}
.ministats{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:12px}
.ministat{background:var(--raised);border-radius:14px;padding:10px 12px;display:flex;flex-direction:column}
.ministat-label{font-size:.74rem;color:var(--ink-soft)}
.ministat-value{font-family:var(--num);font-weight:700;font-size:1.15rem;font-variant-numeric:tabular-nums}
.ministat-value .sub{display:block;margin:0;font-weight:400}
.acard-note{margin:8px 0;font-size:.86rem;color:var(--ink-soft)}
.chip{display:inline-block;padding:3px 10px;margin:0 4px 4px 0;border-radius:99px;background:var(--raised);
  font-size:.78rem;color:var(--ink)}
.acard-lots{margin:14px 0 0}
.acard-lots table{display:block;width:100%}
.acard-lots thead{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0)}
.acard-lots tbody{display:flex;flex-direction:column}
.acard-lots tr{display:grid;grid-template-columns:minmax(0,1fr) auto;column-gap:12px;
  padding:10px 0;border-bottom:1px solid var(--line)}
.acard-lots td{padding:0;font-size:.8rem;color:var(--ink-soft)}
.acard-lots td:nth-child(3){grid-row:1;grid-column:1;font-size:.92rem;color:var(--ink)}
.acard-lots td:nth-child(4){grid-row:1/3;grid-column:2;text-align:right;font-family:var(--num);
  font-weight:650;color:var(--ink);font-size:.92rem;white-space:nowrap}
.acard-lots td:nth-child(1){grid-row:2;grid-column:1}
.acard-lots td:nth-child(2){display:none}
.acard-lots td:nth-child(4) .sub{display:block;margin:0;font-weight:400}
.acard-lots a{color:var(--ink);text-decoration-color:var(--line);text-underline-offset:3px}
.none{color:var(--ink-soft);opacity:.75}
.caveat{font-size:.82rem;color:var(--ink-soft);margin:12px 0 0;max-width:68ch}

/* Barra de pestanias flotante, de cristal. */
.tabs{position:fixed;z-index:10;left:50%;bottom:calc(10px + env(safe-area-inset-bottom));
  transform:translateX(-50%);width:min(560px,calc(100% - 20px));display:flex;padding:6px;
  border-radius:26px;background:var(--glass);box-shadow:var(--shadow),inset 0 0 0 1px var(--line);
  -webkit-backdrop-filter:saturate(1.8) blur(22px);backdrop-filter:saturate(1.8) blur(22px)}
.tabs a{flex:1;min-width:0;display:flex;flex-direction:column;align-items:center;justify-content:center;
  gap:2px;min-height:52px;border-radius:20px;color:var(--ink-soft);text-decoration:none;
  font-size:.68rem;font-weight:550;transition:background .3s var(--spring),color .2s}
.tabs a[aria-current]{color:var(--ink);background:var(--tint)}
.tabs svg{width:22px;height:22px}

.toast{position:fixed;left:50%;bottom:calc(88px + env(safe-area-inset-bottom));z-index:20;
  transform:translate(-50%,24px);opacity:0;background:var(--ink);color:var(--bg);font-size:.86rem;
  line-height:1.4;padding:12px 18px;border-radius:16px;max-width:min(34rem,90vw);
  transition:transform .35s var(--spring),opacity .2s;pointer-events:none}
.toast.show{transform:translate(-50%,0);opacity:1}
.toast.bad{background:var(--crit);color:#fff}

@media (min-width:760px){
  .app{padding-left:24px;padding-right:24px}
  .rail{grid-auto-flow:row;grid-template-columns:repeat(5,minmax(0,1fr));overflow:visible;margin:0 0 12px;padding:0}
  .totals{grid-template-columns:repeat(6,minmax(0,1fr))}
  .controls{margin:0 0 10px;border-radius:0 0 18px 18px}
  .list tbody{grid-template-columns:1fr 1fr}
  .pair{display:grid;grid-template-columns:1fr 1fr;gap:12px}
  .pair>.card{margin:0}
  /* El viewBox esta pensado para el ancho de un movil: a 1.100 px se
     estiraria hasta tener ejes de 30 px. */
  .card .chart{max-height:340px}
  .ministats{grid-template-columns:repeat(4,1fr)}
  .sheet{margin:auto;border-radius:24px;max-height:86vh}
}
@media (prefers-reduced-motion:reduce){*,*::before,*::after{animation:none!important;transition:none!important}}
"""


def _icon(path: str, size: int = 22) -> str:
    return (
        f"<svg viewBox='0 0 24 24' width='{size}' height='{size}' aria-hidden='true' fill='none' "
        "stroke='currentColor' stroke-width='1.8' stroke-linecap='round' "
        f"stroke-linejoin='round'>{path}</svg>"
    )


ICONS = {
    "resumen": _icon("<path d='M4 19V9M10 19V5M16 19v-7M22 19H2'/>"),
    "mercado": _icon("<path d='M3 17l5-6 4 3 7-8'/><path d='M15 6h4v4'/>"),
    "casas": _icon("<path d='M3 10l9-6 9 6'/><path d='M5 10v9h14v-9M9 19v-5h6v5'/>"),
    "artistas": _icon("<circle cx='13.5' cy='6.5' r='1'/><circle cx='17.5' cy='10.5' r='1'/>"
                      "<circle cx='8.5' cy='7.5' r='1'/><path d='M12 21a9 9 0 1 1 9-9c0 2-1.5 3-3 3h-2"
                      "a2 2 0 0 0-1.5 3.3A1.7 1.7 0 0 1 12 21z'/>"),
    "paises": _icon("<circle cx='12' cy='12' r='9'/><path d='M3 12h18M12 3a14 14 0 0 1 0 18"
                    "M12 3a14 14 0 0 0 0 18'/>"),
}
ICON_MOON = _icon("<path d='M20 14.5A8 8 0 0 1 9.5 4 8 8 0 1 0 20 14.5z'/>", 20)
ICON_SUN = _icon("<circle cx='12' cy='12' r='4'/><path d='M12 2v2M12 20v2M4.9 4.9l1.4 1.4"
                 "M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4'/>", 20)
ICON_ALERT = _icon("<path d='M12 3 2 20h20L12 3z'/><path d='M12 10v4M12 17h.01'/>", 20)
ICON_MORE = _icon("<circle cx='5' cy='12' r='1'/><circle cx='12' cy='12' r='1'/>"
                  "<circle cx='19' cy='12' r='1'/>", 20)
ICON_DL = _icon("<path d='M12 3v12M7 10l5 5 5-5M4 20h16'/>", 20)
ICON_CLOSE = _icon("<path d='M6 6l12 12M18 6 6 18'/>", 20)
ICON_GAVEL = _icon("<path d='m14 13-7.5 7.5a2.1 2.1 0 0 1-3-3L11 10'/>"
                   "<path d='m16 16 6-6M8 8l6-6M9 7l8 8M21 11l-8-8'/>", 18)

TABS = [
    ("resumen", "Resumen"), ("mercado", "Mercado"), ("casas", "Casas"),
    ("artistas", "Artistas"), ("paises", "Países"),
]


def dl_menu(prefix: str) -> str:
    """Las descargas, en un menu: en el movil dos botones anchos se comian la barra."""
    return (
        f"<details class='more' id='{prefix}-more'><summary aria-label='Descargar en CSV'>"
        f"{ICON_MORE}</summary><div class='menu'>"
        f"<button type='button' class='dl' id='{prefix}-dl-view'>{ICON_DL}"
        "<span>Descargar la lista<small>Lo filtrado, en CSV para Excel</small></span></button>"
        f"<button type='button' class='dl' id='{prefix}-dl-lots'>{ICON_DL}"
        "<span>Descargar los lotes<small>Uno por fila, con enlace a la casa</small></span></button>"
        "</div></details>"
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
    # El volumen no esta aqui: es la cifra de la cabecera.
    cards = [
        ("Lotes vendidos", num(s["total_sold"]),
         f"{pct(s['sell_through_pct'])} de {num(s['total_lots'])} ofertados"),
        ("Precio mediano", eur(dist.get("median")),
         f"La media ({eur(s.get('avg_sold_price_eur'))}) la infla la cola alta"),
        ("Superan la estimación", pct(est.get("pct_above")),
         f"De {num(est.get('total_with_estimate'))} lotes con estimación"),
        ("Subastas", num(len(rep.get("by_auction", []))),
         f"En {s['total_houses']} casas"),
        ("Artistas con país", num(cov.get("artists_with_country")),
         f"De {num(cov.get('artists_ranked'))} en el ranking, {cov.get('countries', 0)} países"),
    ]
    out = "".join(
        f"<article class='kpi'><span class='kpi-l'>{esc(label)}</span>"
        f"<span class='kpi-v'>{esc(value)}</span>"
        f"<span class='kpi-n'>{esc(note)}</span></article>"
        for label, value, note in cards
    )
    return f"<div class='rail'>{out}</div>"


def _flag_msg(f: dict) -> str:
    msg = f.get("message", "")
    for slug, nice in HOUSE_LABELS.items():
        msg = msg.replace(slug, nice)
    return msg


def critical_alerts(flags: list[dict]) -> str:
    return "".join(
        f"<div class='alert' role='note'>{ICON_ALERT}<div><strong>Ojo al comparar"
        f"{' ' + esc(HOUSE_LABELS.get(f.get('house_slug'), '')) if f.get('house_slug') else ''}"
        f"</strong>{esc(_flag_msg(f))}</div></div>"
        for f in flags if f.get("level") == "critical"
    )


def build_flags(flags: list[dict]) -> str:
    """Avisos de calidad. Los criticos van abiertos y fuera del desplegable: un
    panel que esconde sus salvedades invita a citar cifras que no aguantan."""
    if not flags:
        return ""
    order = {"critical": 0, "warn": 1, "info": 2}
    label = {"critical": "Crítico", "warn": "Aviso", "info": "Contexto"}
    ordered = sorted(flags, key=lambda x: order.get(x.get("level"), 9))
    alerts = critical_alerts(ordered)
    items = []
    for f in ordered:
        lvl = f.get("level", "info")
        house = f.get("house_slug")
        tag = label.get(lvl, lvl) + (f", {HOUSE_LABELS.get(house, house)}" if house else "")
        items.append(
            f"<li class='flag flag-{esc(lvl)}'><span class='flag-tag'>{esc(tag)}</span>"
            f"{esc(_flag_msg(f))}</li>"
        )
    return (
        alerts
        + "<details class='flags'><summary>"
        f"Los {len(flags)} avisos sobre estos datos</summary>"
        f"<ul class='flag-list'>{''.join(items)}</ul></details>"
    )


# Cardinales para el titulo de la pantalla de casas. Solo hasta seis: si el
# proyecto pasa de ahi, sale el numero y no una palabra inventada.
_CARDINAL = {1: "una", 2: "dos", 3: "tres", 4: "cuatro", 5: "cinco", 6: "seis"}


def house_order(houses: list[dict]) -> list[str]:
    """Orden de las casas por volumen. Fija el color de cada una en toda la app:
    el color sigue a la casa, nunca a su posicion en un grafico concreto."""
    return [h["house_slug"] for h in sorted(houses, key=lambda r: -(r.get("revenue_eur") or 0))]


def build_houses(houses: list[dict], flags: list[dict] | None = None) -> str:
    order = house_order(houses)
    by_slug = {h["house_slug"]: h for h in houses}
    cards = []
    for i, slug in enumerate(order):
        h = by_slug[slug]
        cur = h.get("currency") or "?"
        st = (h.get("sell_through_rate") or 0) * 100
        cards.append(
            "<article class='house'>"
            f"<div class='house-head'><i class='dot {series_color(i)}'></i>"
            f"<h3>{esc(HOUSE_LABELS.get(slug, slug))}</h3>"
            f"<span class='where'>{esc(HOUSE_COUNTRY.get(slug, ''))}, {esc(cur)}</span></div>"
            f"<p class='house-v'>{esc(money(h.get('revenue_eur')))}</p>"
            f"<p class='house-native'>{num(h.get('revenue_native'))} {esc(cur)} en su moneda</p>"
            f"<div class='meter' role='img' aria-label='{esc(pct(st))} vendido'>"
            f"<span style='width:{min(100.0, st):.1f}%'></span></div>"
            "<dl>"
            f"<div><dt>Vendido</dt><dd>{pct(st)}</dd></div>"
            f"<div><dt>Lotes</dt><dd>{num(h.get('lots_sold'))} de {num(h.get('lots_offered'))}</dd></div>"
            f"<div><dt>Precio medio</dt><dd>{esc(eur(h.get('avg_sold_price_eur')))}</dd></div>"
            + (f"<div><dt>En {esc(cur)}</dt><dd>{num(h.get('avg_sold_price_native'))}</dd></div>"
               if cur != "EUR" else "") +
            "</dl></article>"
        )
    # El titulo se deriva del dato: estuvo escrito como "Las tres casas" cuando
    # ya eran cuatro, y un numero equivocado en un titulo desacredita todo.
    title = f"Las {_CARDINAL.get(len(cards), len(cards))} casas"
    return (
        f"<h2 class='large'>{esc(title)}</h2>"
        "<p class='lead'>Cada casa cotiza en su moneda. La cifra grande está en euros, "
        "la única comparable entre casas; debajo, la exacta en su moneda.</p>"
        # La tasa de venta de cada casa se lee aqui: su salvedad tiene que
        # estar al lado, no solo en Resumen.
        + critical_alerts(flags or [])
        + f"<div class='houses'>{''.join(cards)}</div>"
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


def lot_date(raw) -> str:
    """Fecha legible del lote. Bogota guarda ISO ("2024-06-07T19:00") y Duran
    texto ("Octubre 2020"): cortar todo a 10 caracteres dejaba "Octubre 20"."""
    raw = (raw or "").strip()
    if len(raw) >= 10 and raw[4] == "-" and raw[:4].isdigit():
        return raw[:10]
    return raw or "—"


def artist_card(a: dict, lots: list[dict]) -> str:
    """Ficha de un artista, con sus lotes y su actividad. Va a cards.json."""
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
            f"{esc(a.get('last_year'))}, {num(years)} "
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
            if l.get("price_sold_eur") and l.get("currency") != "EUR":
                price += f"<span class='sub'>= {esc(eur(l['price_sold_eur']))}</span>"
        else:
            price = "<span class='none'>no vendido</span>"
        house = HOUSE_LABELS.get(l.get("house_slug"), l.get("house_slug") or "")
        lot_rows.append(
            f"<tr><td>{esc(lot_date(l.get('auction_start_date')))}, {esc(house)}</td>"
            f"<td>{esc(house)}</td>"
            f"<td>{title}</td><td class='n'>{price}</td></tr>"
        )
    lot_table = ""
    if lot_rows:
        more = (
            f"<p class='caveat'>Los {len(top)} lotes más caros de "
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
        + "<p class='caveat'>Los importes en euros usan la tasa del mes de la subasta; "
          "el precio en la moneda de la casa es el exacto.</p>"
        "</div>"
    )


def build_artist_charts(artists: list[dict], generations: list[dict]) -> str:
    """Los tres graficos de artistas. El calculo va por narrative.py."""
    if not artists:
        return ""
    pareto = pareto_points(artists)
    bars, line, labels, prev, prev_n = [], [], [], 0.0, 0
    for p in pareto:
        labels.append(f"{prev_n + 1}–{p['n']}" if prev_n else f"Top {p['n']}")
        bars.append({"value": p["revenue_eur"] - prev, "label": labels[-1]})
        line.append(p["share_pct"])
        prev, prev_n = p["revenue_eur"], p["n"]
    marks = [
        (i, f"Top {p['n']}: {p['share_pct']:.0f}%")
        for i, p in enumerate(pareto)
        if p["n"] in (25, 200)
    ]
    head = next((p for p in pareto if p["n"] == 25), pareto[0] if pareto else None)

    gens = generation_bars(generations or [])
    # ``decade=None`` permanece en la banda de cobertura; no se dibuja como si
    # fuera una generacion real.
    gen_items = [
        {"label": g["label"], "revenue_eur": g["revenue_eur"]}
        for g in gens
        if not g["is_sentinel"]
    ]

    all_pts = scatter_points(artists)
    pts = all_pts[:SCATTER_LIMIT]
    total_size = sum(p["size"] for p in all_pts) or 1
    tail_pct = sum(p["size"] for p in all_pts[SCATTER_LIMIT:]) / total_size * 100

    out = ["<h3 class='group'>Cómo se reparte el dinero</h3>"]
    if head:
        out.append(chart_card(
            bar_line_chart(bars, line, labels=labels, notes=marks),
            f"{head['share_pct']:.0f}%".replace(".", ","),
            f"del volumen va a los {head['n']} primeros artistas",
            title="Un puñado de nombres concentra el dinero",
            extra=notes(CAVEAT_PARETO_SCOPE),
        ))
    if pts:
        out.append(chart_card(
            scatter_chart(pts),
            pts[0]["name"] or "—",
            f"El de mayor volumen: {money(pts[0]['size'])}. Toca una burbuja.",
            title="Vender caro o vender mucho",
            extra=notes(
                "Cada burbuja es un artista: a la derecha los que venden muchos lotes, "
                "arriba los que los venden caros, y el tamaño es el volumen total.",
                CAVEAT_SCATTER_LOWN,
                # El recorte se declara: un grafico que dice "los artistas" habiendo
                # dibujado la mitad es un grafico que miente por omision.
                (f"Se dibujan los {len(pts)} artistas de mayor volumen de "
                 f"{len(all_pts)}. Los restantes aportan menos del "
                 f"{tail_pct:.1f}% del total y a este tamaño se solapan en un borrón; "
                 "están todos en el ranking y en la descarga."
                 if len(pts) < len(all_pts) else ""),
            ),
        ))
    if gens:
        v, lab = peak(gen_items, "revenue_eur", "label")
        out.append(chart_card(
            bar_chart(gen_items, "revenue_eur", "label",
                      label="Volumen por década de nacimiento del artista"),
            v, f"{lab}, por década de nacimiento",
            title="La generación que mueve el mercado",
            extra=generation_coverage_block(gens) + notes(CAVEAT_GENERATIONS_COVERAGE),
        ))
    return "".join(out)


def build_artist_table(artists: list[dict], cov: dict,
                       generations: list[dict] | None = None) -> str:
    if not artists:
        return ""
    # Misma seleccion que cards.json (build_cards): top global MAS top por pais.
    # Si las dos divergieran, data-card apuntaria a la ficha de otro artista.
    shown = _rank_selection(artists, ARTIST_LIMIT)
    pares = sorted(
        {(a.get("country_birth"), a.get("country_birth_es") or a.get("country_birth"))
         for a in shown if a.get("country_birth")},
        key=lambda t: t[1] or "",
    )
    options = "".join(f"<option value='{esc(c)}'>{esc(l)}</option>" for c, l in pares)
    if any(not a.get("country_birth") for a in shown):
        options += "<option value='__none__'>Sin país informado</option>"

    top_rev = max((a.get("revenue_eur") or 0) for a in shown) or 1
    rows = []
    for i, a in enumerate(shown, 1):
        st = (a.get("sell_through_rate") or 0) * 100
        code = a.get("country_birth")
        label = a.get("country_birth_es") or code
        extra = [n for n in (a.get("nationalities") or []) if n != code]
        meta = label or "Sin país informado"
        if extra:
            meta += " · tb. " + nationalities_es(extra)
        # Fechas del maestro: si solo hay una, se dice cual es ("n." / "m."),
        # nunca "1954-", que afirmaria que sigue vivo.
        life = a.get("life_years")
        if life:
            meta += f" · {life}"
        url = a.get("top_lot_url")
        rec = money(a.get("top_price_eur"))
        rec_cell = (
            f"<a href='{esc(url)}' target='_blank' rel='noopener' "
            f"title='{esc(a.get('top_lot_title') or '')}'>{esc(rec)}</a>"
            if url else esc(rec)
        )
        rows.append(
            f"<tr data-country='{esc(code or '__none__')}' "
            f"data-name='{esc((a.get('artist_name') or '').lower())}' "
            f"data-key='{esc(a.get('artist_key') or '')}' "
            f"data-card='ficha-{i}' "
            f"data-kind='{esc(multi_house_kind(a.get('houses') or []))}' "
            f"data-sold='{a.get('lots_sold') or 0}' "
            f"data-offered='{a.get('lots_offered') or 0}' "
            f"data-birth='{a.get('birth_year') or ''}' "
            f"data-death='{a.get('death_year') or ''}' "
            f"data-revenue='{a.get('revenue_eur') or 0}' "
            f"style='--w:{(a.get('revenue_eur') or 0) / top_rev:.4f}'>"
            f"<td class='rank'>{i}</td>"
            # Boton y no fila clicable: la fila ya lleva un enlace y un <tr> no
            # recibe foco.
            f"<th scope='row'>"
            f"<button type='button' class='artist-toggle' aria-haspopup='dialog' "
            f"aria-controls='sheet'>"
            f"<span class='name'>{esc(a['artist_name'])}</span>"
            f"<span class='meta{'' if label else ' none'}'>{esc(meta)}</span>"
            f"</button></th>"
            f"<td class='n'>{num(a.get('lots_sold'))}"
            f"<span class='sub'>de {num(a.get('lots_offered'))}</span></td>"
            f"<td class='n'>{pct(st)}</td>"
            f"<td class='n strong'>{esc(eur(a.get('revenue_eur')))}</td>"
            f"<td class='n'>{rec_cell}</td></tr>"
        )

    con, tot = cov.get("artists_with_country") or 0, cov.get("artists_ranked") or 0
    paras = [
        # El corte sale de la constante del pipeline: estaba escrito a mano y
        # cambiarlo dejaba mintiendo al texto.
        CAVEAT_MIN_LOTS,
        "El récord enlaza al lote original en la web de la casa: cada cifra se puede "
        "comprobar en la fuente.",
        f"Los totales suman lo filtrado, que son los {num(len(shown))} primeros artistas "
        f"de {num(tot)} en el ranking. No son el total del mercado: ese está en Resumen.",
        f"Tienen país informado {num(con)} de {num(tot)} artistas "
        f"({pct(cov.get('country_coverage_pct'))}). El resto aparece como “sin país "
        "informado”: la nacionalidad sale de un maestro curado a mano, nunca se deduce "
        "del país de la casa de subastas.",
    ]
    # Las dos coberturas de fechas: la de la lista visible y la del ranking
    # entero. Publicar solo la primera daria una idea falsa del maestro, porque
    # la curaduria se prioriza por facturacion y la cola queda peor cubierta.
    dated_shown = sum(1 for a in shown if a.get("birth_year"))
    dated_tot = sum(1 for a in artists if a.get("birth_year"))
    if shown and tot:
        paras.append(
            f"Las fechas salen del mismo maestro: las tienen {num(dated_shown)} de los "
            f"{num(len(shown))} artistas de esta lista "
            f"({pct(dated_shown / len(shown) * 100)}), pero solo {num(dated_tot)} de "
            f"{num(tot)} en el ranking completo ({pct(dated_tot / tot * 100)}): la "
            "curaduría se ha priorizado por facturación."
        )
        paras.append(
            "“n. 1954” significa <strong>nacido en 1954 y sin año de muerte "
            "registrado</strong>, que no es lo mismo que estar vivo: puede ser una ficha "
            "incompleta. Cuando el artista tendría más de 105 años se marca “n. 1905 (?)”, "
            "porque ahí el hueco es casi seguro un dato que falta."
        )
    return (
        "<h2 class='large'>Quién mueve el dinero</h2>"
        f"<p class='lead'>Los {num(len(shown))} artistas con más volumen adjudicado. "
        "Toca un nombre para abrir su ficha.</p>"
        "<div class='controls'>"
        "<label class='search'>Buscar artista<input type='search' id='artist-search' "
        "placeholder='Botero, Sorolla…' autocomplete='off' enterkeyhint='search'></label>"
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
        + dl_menu("artist") + "</div>"
        + totals_block("artist-totals", [
            ("t-artists", "Artistas", ""), ("t-revenue", "Volumen", "hi"),
            ("t-sold", "Vendidos", "note"), ("t-rate", "Tasa de venta", ""),
            ("t-avg", "Precio medio", ""),
            # Cobertura del maestro: sin esta tarjeta, "200 artistas" se lee
            # como 200 fichas completas.
            ("t-dated", "Con fechas", "note"),
        ])
        + "<table class='list' id='artist-table'><thead><tr><th>#</th>"
        "<th>Artista</th><th>Vendidos</th><th>Tasa venta</th><th>Volumen</th>"
        f"<th>Récord</th></tr></thead><tbody>{''.join(rows)}</tbody></table>"
        "<p class='empty' id='artist-empty' hidden>Ningún artista coincide con el filtro. "
        "Prueba con otro nombre o pulsa Limpiar.</p>"
        # La lista ronda las 1.300 filas y filtrar un pais grande devuelve 200.
        "<div class='pager' id='artist-pager' hidden>"
        "<button type='button' id='artist-page-prev' class='pager-btn'>Anterior</button>"
        "<span class='pager-info' id='artist-page-info' aria-live='polite'></span>"
        "<button type='button' id='artist-page-next' class='pager-btn'>Siguiente</button>"
        "</div>"
        f"<div class='box-notes'>{notes(*paras, summary='Cómo leer el ranking')}</div>"
        + build_artist_charts(artists, generations or [])
    )


def build_country_table(countries: list[dict],
                        country_year: list[dict] | None = None,
                        gap: int = 0) -> str:
    known = [c for c in countries if c.get("country")]
    unknown = next((c for c in countries if not c.get("country")), None)
    if not known:
        return ""
    top_rev = max((c.get("revenue_eur") or 0) for c in known) or 1
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
            f"data-revenue='{c.get('revenue_eur') or 0}' "
            f"style='--w:{(c.get('revenue_eur') or 0) / top_rev:.4f}'>"
            f"<td class='rank'>{i}</td>"
            f"<th scope='row'><span class='name'>{esc(name)}</span>"
            f"<span class='meta'>{num(c.get('artists'))} artistas</span></th>"
            f"<td class='n'>{num(c.get('lots_sold'))}"
            f"<span class='sub'>de {num(c.get('lots_offered'))}</span></td>"
            f"<td class='n'>{pct(st)}</td>"
            f"<td class='n strong'>{esc(eur(c.get('revenue_eur')))}</td>"
            f"<td>{esc(c.get('top_artist') or '')}</td></tr>"
        )
    paras = [
        "Se agrupa por país de <strong>nacimiento</strong>, así que cada lote cuenta una "
        "sola vez. Un artista con doble nacionalidad aparece en un solo país aquí; sus "
        "otras nacionalidades se ven junto a su nombre.",
        "Ojo al comparar países: solo 66 de unos 15.000 nombres coinciden entre Durán "
        "(mercado español) y Bogotá (colombiano), así que el país del artista va casi "
        "calcado al de la casa. Un gráfico “España vs Colombia” está, en buena medida, "
        "comparando esas dos casas.",
        "<strong>Zorrilla no entra en este ranking</strong>: su fuente no publica un "
        "campo de artista separado, así que sus lotes no tienen autor que atribuir.",
    ]
    if unknown and unknown.get("lots_offered"):
        paras.append(
            f"Quedan {num(unknown.get('lots_offered'))} lotes de artistas sin país en el "
            "maestro. No se reparten entre los países conocidos: se dejan fuera para no "
            "inflar ninguno."
        )
    # Los totales por pais no aplican el corte del ranking y la lista de
    # artistas si: sin decirlo, la diferencia parece un error de suma.
    if gap:
        paras.append(country_metrics_caveat(gap))
    heat = heatmap_matrix(country_year or [])
    heat_block = ""
    if heat.get("rows"):
        heat_block = chart_card(
            heatmap_chart(heat),
            f"{len(heat['rows'])} países",
            "Toca una celda para ver ese país en ese año.",
            title="Doce años, país por país",
            extra=notes(CAVEAT_COUNTRY_IS_HOUSE, CAVEAT_FX_TIMESERIES),
        )
    map_svg, unmapped = world_map(known)
    map_block = ""
    if map_svg:
        mapped_rev = sum(c.get("revenue_eur") or 0 for c in known)
        map_block = chart_card(
            map_svg,
            money(mapped_rev),
            f"vendido por artistas nacidos en {len(known)} países. Toca uno para ver el suyo.",
            title="El mapa del dinero",
            extra=notes(
                "Cada país se pinta por lo que han vendido los artistas que nacieron en él, "
                "no por dónde está la casa de subastas. Gris es que ningún artista nacido "
                "allí aparece en el ranking, que no es lo mismo que no tener arte.",
                CAVEAT_COUNTRY_IS_HOUSE,
                # Se declara en vez de repartirlo: asignarlo a Chequia o a
                # Eslovaquia seria inventar un pais de nacimiento.
                (f"Sin forma en el mapa actual: {esc(', '.join(unmapped))}. Su volumen "
                 "está en la lista de abajo y no se reparte entre los países de hoy."
                 if unmapped else ""),
            ),
        )
    return (
        "<h2 class='large'>De dónde viene el arte</h2>"
        "<p class='lead'>Volumen adjudicado por país de nacimiento del artista.</p>"
        + map_block
        + heat_block
        + "<h3 class='group'>País por país</h3>"
        "<div class='controls'>"
        "<label class='search'>Buscar país<input type='search' id='country-search' "
        "placeholder='Colombia, España…' autocomplete='off' enterkeyhint='search'></label>"
        + dl_menu("country") + "</div>"
        + totals_block("country-totals", [
            ("c-countries", "Países", ""), ("c-revenue", "Volumen", "hi"),
            ("c-artists", "Artistas", ""), ("c-sold", "Vendidos", "note"),
            ("c-rate", "Tasa de venta", ""),
        ])
        + "<table class='list' id='country-table'><thead><tr><th>#</th>"
        "<th>País</th><th>Vendidos</th><th>Tasa venta</th><th>Volumen</th>"
        f"<th>Artista destacado</th></tr></thead><tbody>{''.join(rows)}</tbody>"
        "</table>"
        "<p class='empty' id='country-empty' hidden>Ningún país coincide con la búsqueda.</p>"
        f"<div class='box-notes'>{notes(*paras, summary='Cómo leer los países')}</div>"
    )


def _dated(rows: list[dict]) -> tuple[list[dict], float]:
    """Separa las filas con anio real de las 'unknown'. Un eje temporal con una
    barra 'unknown' al final la presenta como el anio mas reciente."""
    dated = [r for r in rows if str(r.get("year", "")).isdigit()]
    undated = sum(r.get("revenue_eur") or 0 for r in rows if not str(r.get("year", "")).isdigit())
    return dated, undated


def build_summary(rep: dict, span: str, dek: str, houses: list[str]) -> str:
    s = rep["summary"]
    by_yh, undated = _dated(rep.get("by_year_by_house", []))
    hero = chart_card(
        stacked_chart(by_yh, houses, grow=True) + house_legend(houses),
        money(s["total_revenue_eur"]),
        f"Vendido {span}, en {num(s['total_sold'])} lotes. Desliza el dedo por los años.",
        cls="hero", n=s["total_revenue_eur"],
        extra=notes(
            "Volumen adjudicado convertido a euros con la tasa del mes de cada subasta. "
            "Es la única cifra que se puede sumar entre casas.",
            (f"{esc(money(undated))} corresponden a lotes sin año y no están en el gráfico; "
             "sí en el total." if undated else ""),
        ),
    )
    return (
        "<h1 class='large'>Qué se vende, a quién y por cuánto</h1>"
        + hero
        + f"<p class='insight'>{esc(dek)}</p>"
        + build_kpis(rep)
        + build_flags(rep.get("quality_flags", []))
        + "<div class='box-notes'>"
        + notes(
            f"<strong>Conversión de moneda.</strong> {esc(fx_note())}",
            "<strong>Procedencia.</strong> Datos extraídos de las webs públicas de las casas "
            "de subastas y refinados por una cadena bronze → silver → gold. Esta app lee "
            "únicamente la capa Gold.",
            "<strong>Verificación.</strong> Las descargas de Artistas y Países bajan en CSV "
            "exactamente lo filtrado, con el enlace al lote original en la web de la casa. "
            "Las cifras no hay que creérselas: se comprueban.",
            summary="De dónde salen estos datos",
        )
        + "</div>"
    )


MONTH_FULL = {
    "01": "enero", "02": "febrero", "03": "marzo", "04": "abril", "05": "mayo",
    "06": "junio", "07": "julio", "08": "agosto", "09": "septiembre",
    "10": "octubre", "11": "noviembre", "12": "diciembre",
}


def build_market(rep: dict) -> str:
    by_year, undated = _dated(rep.get("by_year", []))
    by_month = [
        {"label": MONTH_LABELS.get(m["month"], m["month"]),
         "full": MONTH_FULL.get(m["month"], m["month"]),
         "revenue_eur": m.get("revenue_eur", 0)}
        for m in rep.get("by_month", [])
    ]
    yv, yl = peak(by_year, "revenue_eur", "year")
    mv, ml = peak(by_month, "revenue_eur", "full")
    return (
        "<h2 class='large'>Cómo se mueve el mercado</h2>"
        "<p class='lead'>Volumen adjudicado en euros. Desliza el dedo por un gráfico "
        "para leer cada barra.</p>"
        "<div class='pair'>"
        + chart_card(
            bar_chart(by_year, "revenue_eur", "year", label="Volumen por año"),
            yv, yl, title="Por año",
            extra=notes(
                "Todo el periodo cubierto. Las casas no entran todas a la vez: Durán "
                "arranca en 2014 y Bogotá en 2019, así que los primeros años son solo España.",
                (f"{esc(money(undated))} son de lotes sin año y quedan fuera del eje."
                 if undated else ""),
            ),
        )
        + chart_card(
            bar_chart(by_month, "revenue_eur", "label", label="Volumen por mes del año"),
            mv, ml, title="Por mes del año",
            extra=notes("Estacionalidad: suma todos los años, y solo cuenta lotes con fecha real."),
        )
        + "</div>"
    )


# ---------------------------------------------------------------------------
# JS: navegacion, lectura de graficos, filtro + totalizador, fichas y CSV.
# Todo inline, sin dependencias.
# ---------------------------------------------------------------------------

JS = r"""
(function () {
  var root = document.documentElement;
  root.classList.add('js');
  var reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  // --- Tema --------------------------------------------------------------
  var toggle = document.getElementById('theme');
  function isDark() {
    var t = root.getAttribute('data-theme');
    if (t) return t === 'dark';
    return window.matchMedia('(prefers-color-scheme: dark)').matches;
  }
  function label() {
    var dark = isDark();
    toggle.setAttribute('aria-label', dark ? 'Modo claro' : 'Modo oscuro');
    toggle.innerHTML = document.getElementById(dark ? 'ic-sun' : 'ic-moon').innerHTML;
  }
  toggle.addEventListener('click', function () {
    root.setAttribute('data-theme', isDark() ? 'light' : 'dark');
    label();
  });
  label();

  // --- Formatos ----------------------------------------------------------
  // Se pliegan los acentos para que buscar "tapies" encuentre "Tàpies".
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
  // Mismo formato que money() en Python: la cabecera la escribe Python y la
  // reanima este script.
  function money(v) {
    if (v >= 1e6) return nf.format(Math.round(v / 1e4) / 100) + ' M€';
    if (v >= 1e4) return miles(Math.round(v / 1e3)) + ' k€';
    return miles(Math.round(v)) + ' €';
  }
  // El precio medio es un importe unitario: "11 k€" esconde si son 11.000 o 11.400.
  function unit(v) { return v >= 1e6 ? money(v) : miles(Math.round(v)) + ' €'; }
  function set(id, t) { var e = document.getElementById(id); if (e) e.textContent = t; }

  // --- Datos bajo demanda ------------------------------------------------
  // lots.json y cards.json viven junto a index.html. No van inline: eran 12 MB
  // que el movil descargaba y parseaba para enseñar una cabecera.
  function loadJSON(url) {
    return fetch(url).then(function (r) {
      if (!r.ok) throw new Error(url + ' ' + r.status);
      return r.json();
    });
  }
  var cardsP = null, lotsP = null;
  function cards() {
    return cardsP || (cardsP = loadJSON('cards.json').catch(function (e) {
      cardsP = null; throw e;
    }));
  }
  function lots() {
    return lotsP || (lotsP = loadJSON('lots.json').then(function (p) {
      if (!p || !p.rows) return [];
      return p.rows.map(function (r) {
        var o = {};
        p.cols.forEach(function (c, i) { o[c] = p.dict[c] ? p.dict[c][r[i]] : r[i]; });
        return o;
      });
    }).catch(function (e) { lotsP = null; throw e; }));
  }

  // --- Navegacion por pestanias -------------------------------------------
  var screens = [].slice.call(document.querySelectorAll('.screen'));
  var tabs = [].slice.call(document.querySelectorAll('.tabs a'));
  var pos = {}, current = null;
  function go(id) {
    if (!screens.some(function (s) { return s.id === id; })) id = 'resumen';
    if (current) pos[current] = window.scrollY;
    screens.forEach(function (s) { s.hidden = s.id !== id; });
    tabs.forEach(function (t) {
      if (t.dataset.tab === id) t.setAttribute('aria-current', 'page');
      else t.removeAttribute('aria-current');
    });
    current = id;
    // Cada pestania recuerda donde se quedo: volver a Artistas tras mirar una
    // casa no puede devolverte al principio de 1.300 filas.
    window.scrollTo(0, pos[id] || 0);
    // La ficha se pide al entrar en Artistas, antes del primer toque.
    if (id === 'artistas') cards().catch(function () {});
  }
  window.addEventListener('hashchange', function () { go(location.hash.slice(1)); });
  go(location.hash.slice(1));

  // --- Lectura de graficos (arrastrar el dedo) ------------------------------
  var NS = 'http://www.w3.org/2000/svg';
  var scrubbers = [];
  [].slice.call(document.querySelectorAll('svg.scrub')).forEach(function (svg) {
    var card = svg.closest('.card');
    var ro = card && card.querySelector('.ro');
    if (!ro) return;
    var rv = ro.querySelector('.ro-v'), rl = ro.querySelector('.ro-l');
    var marks = [].slice.call(svg.querySelectorAll('[data-l]'));
    if (!marks.length) return;
    marks.forEach(function (m) { m._x = +m.dataset.x; m._y = +(m.dataset.y || 0); });
    var xy = svg.getAttribute('data-mode') === 'xy';
    var guide = null;
    if (!xy) {
      guide = document.createElementNS(NS, 'line');
      guide.setAttribute('class', 'guide');
      guide.setAttribute('y1', '0');
      guide.setAttribute('y2', svg.getAttribute('data-base'));
      svg.appendChild(guide);
    }
    var cur = null, lit = [];
    function show(m) {
      if (!m || m === cur) return;
      lit.forEach(function (e) { e.classList.remove('on'); });
      cur = m;
      var col = m.dataset.col;
      lit = col ? [].slice.call(svg.querySelectorAll('[data-col="' + col + '"]')) : [m];
      lit.forEach(function (e) { e.classList.add('on'); });
      // En el mapa el pais va al frente, o sus vecinos le tapan el borde.
      if (svg.classList.contains('map')) m.parentNode.appendChild(m);
      svg.classList.add('scrubbing');
      rv.textContent = m.dataset.v;
      rl.textContent = m.dataset.l + (m.dataset.d ? ': ' + m.dataset.d : '');
      if (guide) {
        guide.setAttribute('x1', m._x); guide.setAttribute('x2', m._x);
        guide.style.opacity = '1';
      }
    }
    function reset() {
      if (!cur) return;
      lit.forEach(function (e) { e.classList.remove('on'); });
      cur = null; lit = [];
      svg.classList.remove('scrubbing');
      rv.textContent = rv.dataset.d;
      rl.textContent = rl.dataset.d;
      if (guide) guide.style.opacity = '0';
    }
    function pick(ev) {
      // Lo que hay bajo el dedo manda. El centro mas cercano es solo el plan B
      // para el hueco entre barras o el mar: en el mapa, tocar el borde de
      // Brasil no puede seleccionar Paraguay porque su centro quede mas cerca.
      var hit = ev.target.closest && ev.target.closest('[data-l]');
      if (hit && svg.contains(hit)) { show(hit); return; }
      var ctm = svg.getScreenCTM();
      if (!ctm) return;
      var p = svg.createSVGPoint();
      p.x = ev.clientX; p.y = ev.clientY;
      p = p.matrixTransform(ctm.inverse());
      var best = null, bd = Infinity;
      for (var i = 0; i < marks.length; i++) {
        var dx = marks[i]._x - p.x, dy = xy ? marks[i]._y - p.y : 0;
        var d = dx * dx + dy * dy;
        if (d < bd) { bd = d; best = marks[i]; }
      }
      show(best);
    }
    svg.addEventListener('pointerdown', pick);
    svg.addEventListener('pointermove', pick);
    // Con raton la lectura vuelve al soltar; con el dedo se queda hasta tocar
    // fuera, para poder leerla sin tapar el grafico con la mano.
    svg.addEventListener('pointerleave', function (ev) {
      if (ev.pointerType === 'mouse') reset();
    });
    svg.addEventListener('keydown', function (ev) {
      if (ev.key !== 'ArrowRight' && ev.key !== 'ArrowLeft' && ev.key !== 'Escape') return;
      ev.preventDefault();
      if (ev.key === 'Escape') { reset(); return; }
      var i = cur ? marks.indexOf(cur) : -1;
      i += ev.key === 'ArrowRight' ? 1 : -1;
      show(marks[Math.max(0, Math.min(marks.length - 1, i))]);
    });
    svg.addEventListener('blur', reset);
    scrubbers.push({svg: svg, reset: reset});
  });
  document.addEventListener('pointerdown', function (ev) {
    scrubbers.forEach(function (s) { if (!s.svg.contains(ev.target)) s.reset(); });
  });

  // Zoom del mapa: se anima el viewBox para que se vea de donde a donde va.
  [].slice.call(document.querySelectorAll('.zoom')).forEach(function (group) {
    var svg = group.closest('.card').querySelector('svg.map');
    if (!svg) return;
    var anim = null;
    group.addEventListener('click', function (ev) {
      var btn = ev.target.closest('button');
      if (!btn) return;
      [].slice.call(group.querySelectorAll('button')).forEach(function (b) {
        b.setAttribute('aria-pressed', b === btn ? 'true' : 'false');
      });
      var to = btn.dataset.vb.split(' ').map(Number);
      var v = svg.viewBox.baseVal, from = [v.x, v.y, v.width, v.height];
      cancelAnimationFrame(anim);
      if (reduced) { svg.setAttribute('viewBox', to.join(' ')); return; }
      var t0 = null;
      var step = function (t) {
        t0 = t0 || t;
        var k = Math.min(1, (t - t0) / 480), e = 1 - Math.pow(1 - k, 3);
        svg.setAttribute('viewBox', from.map(function (f, i) {
          return f + (to[i] - f) * e;
        }).join(' '));
        if (k < 1) anim = requestAnimationFrame(step);
      };
      anim = requestAnimationFrame(step);
    });
  });

  // La cifra de la cabecera cuenta hasta su valor una vez, al abrir.
  var hv = document.querySelector('.hero .ro-v');
  if (hv && hv.dataset.n && !reduced) {
    var target = +hv.dataset.n, t0 = null;
    var step = function (t) {
      t0 = t0 || t;
      var k = Math.min(1, (t - t0) / 1100);
      hv.textContent = k < 1 ? money(target * (1 - Math.pow(1 - k, 3))) : hv.dataset.d;
      if (k < 1) requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  }

  // --- CSV ---------------------------------------------------------------
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

    if (ok) { say('Descargado ' + name + ', ' + filas + ' filas'); return; }

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
        say('Este visor no permite descargar. Abre la app en el navegador ' +
            'para guardar el CSV.', true);
      });
    } catch (e) {
      say('Este visor no permite descargar. Abre la app en el navegador ' +
          'para guardar el CSV.', true);
    }
  }
  function slug(s) {
    return fold(s).replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') || 'todo';
  }

  var LOT_HEAD = ['Artista', 'Pais', 'Casa', 'Subasta', 'Fecha', 'Lote', 'Titulo',
                  'Estado', 'Vendido', 'Precio', 'Moneda', 'Precio EUR', 'URL',
                  'Clave artista'];
  function lotLine(l) {
    return [l.artist_name, l.country, l.house_slug, l.auction_id, l.auction_start_date,
            l.lot_number, l.lot_title, l.status, l.sold ? 'si' : 'no', l.price_sold,
            l.currency, l.price_sold_eur, l.lot_url, l.artist_key];
  }

  // --- Listas filtrables -------------------------------------------------
  function wire(cfg) {
    var table = document.getElementById(cfg.table);
    if (!table) return;
    var rows = [].slice.call(table.tBodies[0].rows);
    var empty = document.getElementById(cfg.empty);
    var totals = document.getElementById(cfg.totals);
    var inputs = cfg.inputs.map(function (id) { return document.getElementById(id); })
      .filter(Boolean);
    var reset = document.getElementById(cfg.reset);

    function visible() {
      // dataset.match, no !hidden: con la paginacion hidden solo dice si la
      // fila cae en la pagina actual, y descargar "lo que se ve" tiene que
      // seguir significando todo lo filtrado.
      return rows.filter(function (r) { return r.dataset.match; });
    }

    function apply() {
      var q = fold(cfg.search ? (document.getElementById(cfg.search) || {}).value : '');
      var sel = cfg.select ? (document.getElementById(cfg.select) || {}).value : '';
      var n = 0, sold = 0, offered = 0, revenue = 0, artists = 0, dated = 0;
      // Filtro extra opcional (presencia en varias casas), aparte del selector
      // de pais para que wire() siga sirviendo a las dos listas.
      var extraEl = cfg.extra ? document.getElementById(cfg.extra) : null;
      var extra = extraEl ? extraEl.value : '';
      rows.forEach(function (row) {
        var okExtra = !extra ||
          (extra === 'multi' ? row.dataset.kind !== 'single'
                             : row.dataset.kind === extra);
        var ok = (!q || fold(row.dataset.name).indexOf(q) >= 0) &&
                 (!sel || row.dataset.country === sel) && okExtra;
        row.dataset.match = ok ? '1' : '';
        row.hidden = !ok;
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
      set(cfg.ids.sold + '-n', offered ? 'de ' + miles(offered) : '');
      set(cfg.ids.rate, offered ? (sold / offered * 100).toFixed(1).replace('.', ',') + '%' : '—');
      set(cfg.ids.revenue, money(revenue));
      if (cfg.ids.avg) set(cfg.ids.avg, sold ? unit(revenue / sold) : '—');
      if (cfg.ids.dated) {
        set(cfg.ids.dated, n ? (dated / n * 100).toFixed(0) + '%' : '—');
        set(cfg.ids.dated + '-n', n ? miles(dated) + ' de ' + miles(n) : '');
      }
      empty.hidden = n !== 0;
      totals.classList.toggle('on', n !== rows.length);
      paginate();
    }

    // Paginacion: solo afecta a lo que se pinta. Los totales ya estan sumados
    // sobre todo lo filtrado y visible() lee dataset.match, asi que cambiar de
    // pagina no mueve ni un KPI ni un CSV.
    var PAGE_SIZE = 50;
    var page = 0;
    var pgr = document.getElementById(cfg.table.replace('-table', '-pager'));
    var pinf = document.getElementById(cfg.table.replace('-table', '-page-info'));
    var pprv = document.getElementById(cfg.table.replace('-table', '-page-prev'));
    var pnxt = document.getElementById(cfg.table.replace('-table', '-page-next'));

    function paginate() {
      var matched = rows.filter(function (r) { return r.dataset.match; });
      var pages = Math.max(1, Math.ceil(matched.length / PAGE_SIZE));
      if (page >= pages) page = pages - 1;
      if (page < 0) page = 0;
      matched.forEach(function (r, i) {
        r.hidden = !(i >= page * PAGE_SIZE && i < (page + 1) * PAGE_SIZE);
      });
      if (!pgr) return;
      pgr.hidden = matched.length <= PAGE_SIZE;
      if (pinf) {
        var desde = matched.length ? page * PAGE_SIZE + 1 : 0;
        var hasta = Math.min((page + 1) * PAGE_SIZE, matched.length);
        pinf.textContent = desde + '–' + hasta + ' de ' + miles(matched.length);
      }
      if (pprv) pprv.disabled = page === 0;
      if (pnxt) pnxt.disabled = page >= pages - 1;
    }

    function goPage(d) {
      page += d;
      paginate();
      table.scrollIntoView({block: 'start', behavior: reduced ? 'auto' : 'smooth'});
    }
    if (pprv) pprv.addEventListener('click', function () { goPage(-1); });
    if (pnxt) pnxt.addEventListener('click', function () { goPage(1); });

    inputs.forEach(function (el) {
      // Un filtro nuevo empieza por la pagina 1: quedarse en la 4 tras filtrar
      // a 12 resultados enseñaria una lista vacia.
      el.addEventListener(el.tagName === 'SELECT' ? 'change' : 'input',
                          function () { page = 0; });
      el.addEventListener(el.tagName === 'SELECT' ? 'change' : 'input', apply);
    });
    if (reset) reset.addEventListener('click', function () {
      inputs.forEach(function (el) { el.value = ''; });
      page = 0;
      apply();
    });

    function tag() {
      return inputs.map(function (el) { return el.value; }).filter(Boolean).join('-');
    }
    var more = document.getElementById(cfg.prefix === 'artistas' ? 'artist-more' : 'country-more');
    function closeMenu() { if (more) more.open = false; }
    // Abrir el menu ya pide lots.json: cuando llega el toque en "lotes", el
    // fichero suele estar en memoria y la descarga sigue dentro del gesto, que
    // es lo que Safari exige para no bloquearla.
    if (more) more.addEventListener('toggle', function () {
      if (more.open) lots().catch(function () {});
    });
    var dv = document.getElementById(cfg.dlView);
    if (dv) dv.addEventListener('click', function () {
      closeMenu();
      var vis = visible();
      if (!vis.length) { say('No hay filas que descargar con este filtro.', true); return; }
      save(cfg.prefix + '-' + slug(tag()) + '.csv',
           csv(cfg.viewHead, vis.map(cfg.viewLine)), vis.length);
    });
    var dl = document.getElementById(cfg.dlLots);
    if (dl) dl.addEventListener('click', function () {
      closeMenu();
      var keys = {};
      visible().forEach(function (r) { keys[cfg.matchKey(r)] = 1; });
      lots().then(function (all) {
        var sel = all.filter(function (l) { return keys[cfg.lotKey(l)]; });
        if (!sel.length) {
          say('No hay detalle de lotes para esta selección: solo se exportan los ' +
              'lotes de artistas con país en el maestro.', true);
          return;
        }
        save(cfg.prefix + '-lotes-' + slug(tag()) + '.csv',
             csv(LOT_HEAD, sel.map(lotLine)), sel.length);
      }, function () {
        say('No se pudo cargar el detalle de lotes. Comprueba la conexión y vuelve ' +
            'a intentarlo.', true);
      });
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
    search: 'country-search', inputs: ['country-search'],
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
    // El detalle guarda el codigo ISO ("CO"), la lista muestra "Colombia":
    // se cruza por el codigo, que es la clave real.
    matchKey: function (row) { return row.dataset.code; },
    lotKey: function (l) { return l.country; },
  });

  // --- Ficha de artista en hoja inferior -----------------------------------
  (function () {
    var table = document.getElementById('artist-table');
    var sheet = document.getElementById('sheet');
    if (!table || !sheet || !sheet.showModal) return;
    var body = sheet.querySelector('.sheet-body');
    table.addEventListener('click', function (ev) {
      var btn = ev.target.closest && ev.target.closest('.artist-toggle');
      if (!btn) return;
      var id = btn.closest('tr').dataset.card;
      body.innerHTML = "<p class='loading'>Cargando la ficha…</p>";
      body.scrollTop = 0;
      sheet.showModal();
      cards().then(function (c) {
        body.innerHTML = c[id] || "<p class='loading'>Esta ficha no está disponible.</p>";
      }, function () {
        body.innerHTML = "<p class='loading'>No se pudo cargar la ficha. Comprueba la " +
          "conexión y vuelve a tocar el nombre.</p>";
      });
    });
    // Tocar el fondo cierra, como en cualquier hoja del sistema.
    sheet.addEventListener('click', function (ev) { if (ev.target === sheet) sheet.close(); });
  })();
})();
"""


def _lots_by_artist(details: list[dict]) -> dict[str, list[dict]]:
    # Se indexa una vez: buscarlos por artista dentro del bucle seria
    # O(artistas x lotes) sobre 22.888 filas.
    out: dict[str, list[dict]] = {}
    for d in details:
        key = d.get("artist_key")
        if key:
            out.setdefault(key, []).append(d)
    return out


def build_cards(rep: dict, details: list[dict]) -> dict[str, str]:
    """Fichas de artista para cards.json, con las mismas claves que data-card.

    Usa la misma seleccion que build_artist_table: si divergieran, tocar un
    nombre abriria la ficha de otro.
    """
    by_artist = _lots_by_artist(details)
    shown = _rank_selection(rep.get("by_artist", []), ARTIST_LIMIT)
    return {
        f"ficha-{i}": artist_card(a, by_artist.get(a.get("artist_key")) or [])
        for i, a in enumerate(shown, 1)
    }


def build(rep: dict) -> str:
    """index.html completo. Sin datos de lotes inline: van en lots.json/cards.json."""
    s = rep["summary"]
    dist = rep.get("price_distribution") or {}
    years = [r["year"] for r in rep.get("by_year", []) if str(r.get("year", "")).isdigit()]
    span = f"entre {min(years)} y {max(years)}" if years else "en todo el histórico"

    bands = dist.get("bands") or []
    if bands:
        tl = sum(b["lots"] for b in bands) or 1
        tr = sum(b["revenue_eur"] for b in bands) or 1
        top = bands[-1]
        dek = (
            f"El {top['lots'] / tl * 100:.1f}% más caro de lo vendido concentra "
            f"el {top['revenue_eur'] / tr * 100:.0f}% del dinero."
        ).replace(".", ",", 1)
    else:
        dek = f"{num(s['total_lots'])} lotes de {s['total_houses']} casas, {span}."

    houses = house_order(rep.get("by_house", []))
    screens = {
        "resumen": build_summary(rep, span, dek, houses),
        "mercado": build_market(rep),
        "casas": build_houses(rep.get("by_house", []), rep.get("quality_flags", [])),
        "artistas": build_artist_table(rep.get("by_artist", []),
                                       rep.get("artist_coverage") or {},
                                       rep.get("by_generation") or []),
        "paises": build_country_table(rep.get("by_country", []),
                                      rep.get("by_country_year") or [],
                                      rep.get("country_lots_below_rank_cutoff") or 0),
    }
    sections = "".join(
        f"<section class='screen' id='{sid}' aria-label='{esc(name)}'>{screens[sid]}</section>"
        for sid, name in TABS
    )
    nav = "".join(
        f"<a href='#{sid}' data-tab='{sid}'>{ICONS[sid]}<span>{esc(name)}</span></a>"
        for sid, name in TABS
    )
    return (
        "<!doctype html><html lang='es'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1,viewport-fit=cover'>"
        "<meta name='theme-color' content='#EDF1F5' media='(prefers-color-scheme: light)'>"
        "<meta name='theme-color' content='#0A1119' media='(prefers-color-scheme: dark)'>"
        "<title>Mercado del arte</title>"
        f"<style>{CSS}</style></head><body>"
        "<div class='app'>"
        f"<header class='bar'><span class='brand'>{ICON_GAVEL}Mercado del arte</span>"
        f"<button type='button' class='icon-btn' id='theme' aria-label='Modo oscuro'>{ICON_MOON}</button>"
        "</header>"
        f"<main>{sections}</main></div>"
        f"<nav class='tabs' aria-label='Secciones'>{nav}</nav>"
        "<dialog class='sheet' id='sheet' aria-label='Ficha de artista'>"
        "<div class='sheet-top'><form method='dialog'>"
        f"<button class='icon-btn' aria-label='Cerrar la ficha'>{ICON_CLOSE}</button>"
        "</form></div><div class='sheet-body'></div></dialog>"
        "<div class='toast' id='toast' role='status' aria-live='polite'></div>"
        f"<template id='ic-moon'>{ICON_MOON}</template><template id='ic-sun'>{ICON_SUN}</template>"
        f"<script>{JS}</script></body></html>"
    )


def write_app(rep: dict, details: list[dict], out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    (out / "index.html").write_text(build(rep), encoding="utf-8")
    (out / "lots.json").write_text(
        json.dumps(pack_lot_details(details), ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    (out / "cards.json").write_text(
        json.dumps(build_cards(rep, details), ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )


def main() -> None:
    ap = argparse.ArgumentParser(description="Genera la app (carpeta estatica).")
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

    write_app(rep, details, args.out)
    for name in ("index.html", "cards.json", "lots.json"):
        size = (args.out / name).stat().st_size / 1024
        print(f"[app] {args.out / name}  ({size:,.0f} KB)")
    print(f"[app] {len(details):,} lotes de detalle. Sirvela con: "
          f"python -m http.server -d {args.out}")


if __name__ == "__main__":
    main()

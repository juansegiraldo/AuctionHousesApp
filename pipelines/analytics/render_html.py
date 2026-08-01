#!/usr/bin/env python3
"""
Renderizado HTML del informe Gold.

Separado de report_gold.py a proposito: ese modulo decide QUE datos entran en el
informe, este decide COMO se ven. Asi se puede rehacer el diseno sin tocar la
logica de agregacion.

Sistema de diseno (ui-ux-pro-max, estilo "Data-Dense Dashboard"):
  - Tipografia: Fira Sans (texto) + Fira Code (cifras tabulares).
  - Color: azul de datos + ambar de acento, tokens semanticos en :root.
  - Densidad alta (escala 8-32px) porque es un dashboard, no una landing.
  - Soporta modo claro y oscuro, y respeta prefers-reduced-motion.

Regla que atraviesa todo el fichero: ninguna cifra monetaria se muestra sin su
moneda, y ningun total cross-house se muestra en moneda nativa.
"""

from __future__ import annotations

import html
import json
from pathlib import Path

from pipelines.shared.fx import fx_as_of, fx_note

# Nombres legibles: los slugs son claves tecnicas, no etiquetas de interfaz.
HOUSE_LABELS = {
    "bogota_auctions": "Bogotá Auctions",
    "duran_subastas": "Durán Subastas",
}
HOUSE_COUNTRY = {
    "bogota_auctions": "Colombia",
    "duran_subastas": "España",
}
CATEGORY_LABELS = {
    "painting": "Pintura",
    "prints": "Grabado y múltiples",
    "decorative_arts": "Artes decorativas",
    "books_documents": "Libros y documentos",
    "other": "Otros / sin clasificar",
}
MONTH_LABELS = {
    "01": "Ene", "02": "Feb", "03": "Mar", "04": "Abr",
    "05": "May", "06": "Jun", "07": "Jul", "08": "Ago",
    "09": "Sep", "10": "Oct", "11": "Nov", "12": "Dic",
}


def esc(value) -> str:
    return html.escape(str(value if value is not None else ""))


def house_label(slug: str) -> str:
    return HOUSE_LABELS.get(slug, slug)


def eur(value, decimals: int = 0) -> str:
    """Formatea EUR. El simbolo va siempre: una cifra sin moneda es un bug."""
    if value is None:
        return "—"
    return f"{value:,.{decimals}f} €"


def num(value) -> str:
    return "—" if value is None else f"{value:,.0f}"


def pct(value, decimals: int = 1) -> str:
    return "—" if value is None else f"{value:.{decimals}f}%"


# --------------------------------------------------------------------------
# Bloques
# --------------------------------------------------------------------------

def build_kpis(report: dict) -> str:
    s = report["summary"]
    dist = report.get("price_distribution") or {}
    est = report.get("estimate_accuracy") or {}

    median = dist.get("median")
    avg = s.get("avg_sold_price_eur")

    cards = [
        {
            "label": "Lotes analizados",
            "value": num(s["total_lots"]),
            "note": f"{s['total_houses']} casas · {len(report.get('by_auction', []))} subastas",
        },
        {
            "label": "Lotes vendidos",
            "value": num(s["total_sold"]),
            "note": f"{pct(s['sell_through_pct'])} del total ofertado",
        },
        {
            "label": "Volumen adjudicado",
            "value": eur(s["total_revenue_eur"]),
            "note": f"Convertido a EUR · tasa {fx_as_of()}",
            "accent": True,
        },
        {
            "label": "Precio mediano",
            "value": eur(median),
            "note": f"La media ({eur(avg)}) va inflada por la cola alta",
        },
    ]
    if est.get("pct_above") is not None:
        cards.append(
            {
                "label": "Supera la estimación alta",
                "value": pct(est["pct_above"]),
                "note": f"Sobre {num(est['total_with_estimate'])} lotes con estimación publicada",
            }
        )

    out = []
    for c in cards:
        cls = "kpi kpi-accent" if c.get("accent") else "kpi"
        out.append(
            f"<article class='{cls}'>"
            f"<p class='kpi-label'>{esc(c['label'])}</p>"
            f"<p class='kpi-value'>{esc(c['value'])}</p>"
            f"<p class='kpi-note'>{esc(c['note'])}</p>"
            f"</article>"
        )
    return f"<section class='kpi-grid'>{''.join(out)}</section>"


def humanize_flag(message: str) -> str:
    """Sustituye los slugs tecnicos por el nombre legible de la casa.

    Los mensajes se generan en el pipeline con el slug (`bogota_auctions`), que
    es la clave correcta ahi pero no una etiqueta de interfaz. La casa ya se
    muestra como tag en la propia tarjeta, asi que en el texto sobra repetirla
    en formato tecnico.
    """
    out = message or ""
    for slug, label in HOUSE_LABELS.items():
        out = out.replace(f"de {slug}", f"de {label}").replace(slug, label)
    return out


def build_flags(flags: list[dict]) -> str:
    """Avisos de calidad. Van arriba y abiertos: son parte de la lectura.

    Un dashboard que esconde sus salvedades invita a citar cifras que no
    aguantan. Aqui el aviso critico (sell-through no comparable) se lee antes
    que cualquier grafico de sell-through.
    """
    if not flags:
        return ""
    order = {"critical": 0, "warn": 1, "info": 2}
    label = {"critical": "Crítico", "warn": "Aviso", "info": "Contexto"}
    items = []
    for f in sorted(flags, key=lambda x: order.get(x.get("level"), 9)):
        lvl = f.get("level", "info")
        house = f.get("house_slug")
        tag = f" · {esc(house_label(house))}" if house else ""
        items.append(
            f"<li class='flag flag-{esc(lvl)}'>"
            f"<span class='flag-tag'>{esc(label.get(lvl, lvl))}{tag}</span>"
            f"<span class='flag-msg'>{esc(humanize_flag(f.get('message', '')))}</span>"
            f"</li>"
        )
    n_crit = sum(1 for f in flags if f.get("level") == "critical")
    summary = f"{len(flags)} avisos" + (f", {n_crit} crítico" if n_crit else "")
    return (
        "<details class='panel flags' open>"
        "<summary><h2>Cómo leer estos datos</h2>"
        f"<span class='flags-count'>{esc(summary)}</span></summary>"
        f"<ul class='flag-list'>{''.join(items)}</ul>"
        "</details>"
    )


def build_house_table(houses: list[dict]) -> str:
    """Tabla por casa con moneda nativa y EUR lado a lado (conversion auditable)."""
    rows = []
    for h in sorted(houses, key=lambda r: -(r.get("revenue_eur") or 0)):
        slug = h["house_slug"]
        cur = h.get("currency") or "?"
        st = (h.get("sell_through_rate") or 0) * 100
        rows.append(
            "<tr>"
            f"<th scope='row'><span class='house-name'>{esc(house_label(slug))}</span>"
            f"<span class='house-meta'>{esc(HOUSE_COUNTRY.get(slug, ''))} · {esc(cur)}</span></th>"
            f"<td class='n'>{num(h.get('lots_offered'))}</td>"
            f"<td class='n'>{num(h.get('lots_sold'))}</td>"
            f"<td class='n'>{pct(st)}</td>"
            f"<td class='n'>{num(h.get('revenue_native'))} {esc(cur)}"
            f"<span class='sub'>≈ {esc(eur(h.get('revenue_eur')))}</span></td>"
            f"<td class='n'>{num(h.get('avg_sold_price_native'))} {esc(cur)}"
            f"<span class='sub'>≈ {esc(eur(h.get('avg_sold_price_eur')))}</span></td>"
            "</tr>"
        )
    return (
        "<section class='panel'>"
        "<h2>Las dos casas, una al lado de la otra</h2>"
        "<p class='panel-lead'>Cada casa cotiza en su moneda. La columna nativa es el dato exacto; "
        "el EUR es la conversión aproximada que permite compararlas.</p>"
        "<div class='table-scroll'><table>"
        "<thead><tr><th scope='col'>Casa</th><th scope='col'>Ofertados</th>"
        "<th scope='col'>Vendidos</th><th scope='col'>Tasa venta</th>"
        "<th scope='col'>Volumen</th><th scope='col'>Precio medio</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table></div>"
        "<p class='caveat'>La tasa de venta <strong>no es comparable entre estas dos casas</strong>: "
        "Bogotá publica casi solo lotes vendidos, Durán publica también los no vendidos. "
        "Es una propiedad de la fuente, no una diferencia de rendimiento.</p>"
        "</section>"
    )


def build_artist_table(artists: list[dict], limit: int = 15) -> str:
    if not artists:
        return ""
    rows = []
    for i, a in enumerate(artists[:limit], 1):
        st = (a.get("sell_through_rate") or 0) * 100
        title = a.get("top_lot_title") or ""
        url = a.get("top_lot_url")
        top = eur(a.get("top_price_eur"))
        top_cell = (
            f"<a href='{esc(url)}' target='_blank' rel='noopener' title='{esc(title)}'>{esc(top)}</a>"
            if url
            else esc(top)
        )
        country = a.get("country")
        rows.append(
            "<tr>"
            f"<td class='rank'>{i}</td>"
            f"<th scope='row'><span class='artist-name'>{esc(a['artist_name'])}</span>"
            + (f"<span class='house-meta'>{esc(country)}</span>" if country else "")
            + "</th>"
            f"<td class='n'>{num(a.get('lots_sold'))}<span class='sub'>de {num(a.get('lots_offered'))}</span></td>"
            f"<td class='n'>{pct(st)}</td>"
            f"<td class='n strong'>{esc(eur(a.get('revenue_eur')))}</td>"
            f"<td class='n'>{top_cell}</td>"
            "</tr>"
        )
    return (
        "<section class='panel'>"
        "<h2>Quién mueve el dinero</h2>"
        "<p class='panel-lead'>Los 15 artistas con mayor volumen adjudicado. "
        "Se excluyen escuelas, talleres y atribuciones (“Escuela Española”, “Atribuido a…”), "
        "que agrupan cientos de lotes de autoría distinta y falsearían el ranking. "
        "Mínimo 3 lotes vendidos para entrar.</p>"
        "<div class='table-scroll'><table>"
        "<thead><tr><th scope='col'>#</th><th scope='col'>Artista</th>"
        "<th scope='col'>Vendidos</th><th scope='col'>Tasa venta</th>"
        "<th scope='col'>Volumen</th><th scope='col'>Récord</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table></div>"
        "<p class='caveat'>El récord enlaza al lote original en la web de la casa.</p>"
        "</section>"
    )


def build_category_table(cats: list[dict]) -> str:
    if not cats:
        return ""
    total_rev = sum(c.get("revenue_eur") or 0 for c in cats) or 1
    rows = []
    for c in cats:
        share = (c.get("revenue_eur") or 0) / total_rev * 100
        st = (c.get("sell_through_rate") or 0) * 100
        rows.append(
            "<tr>"
            f"<th scope='row'>{esc(CATEGORY_LABELS.get(c['category'], c['category']))}</th>"
            f"<td class='n'>{num(c.get('lots_offered'))}</td>"
            f"<td class='n'>{pct(st)}</td>"
            f"<td class='n strong'>{esc(eur(c.get('revenue_eur')))}</td>"
            f"<td class='bar-cell'><span class='bar' style='--w:{share:.1f}%'></span>"
            f"<span class='bar-val'>{pct(share)}</span></td>"
            "</tr>"
        )
    return (
        "<section class='panel'>"
        "<h2>Qué se vende, y qué factura</h2>"
        "<p class='panel-lead'>No son la misma cosa: los libros y las artes decorativas se venden "
        "casi siempre, pero la pintura concentra el dinero.</p>"
        "<div class='table-scroll'><table>"
        "<thead><tr><th scope='col'>Categoría</th><th scope='col'>Lotes</th>"
        "<th scope='col'>Tasa venta</th><th scope='col'>Volumen</th>"
        "<th scope='col'>% del volumen</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table></div>"
        "<p class='caveat'>Categoría asignada automáticamente por palabras clave del título y la "
        "técnica (<code>category_tag</code>). “Otros” recoge lo que no encaja en una regla, "
        "no es una categoría real del mercado.</p>"
        "</section>"
    )


def build_concentration(dist: dict) -> str:
    """El hallazgo mas fuerte del dataset: la cola alta se lo lleva casi todo."""
    if not dist or not dist.get("bands"):
        return ""
    bands = dist["bands"]
    total_lots = sum(b["lots"] for b in bands) or 1
    total_rev = sum(b["revenue_eur"] for b in bands) or 1
    top = bands[-1]
    top_share_lots = top["lots"] / total_lots * 100
    top_share_rev = top["revenue_eur"] / total_rev * 100

    rows = []
    for b in bands:
        l_share = b["lots"] / total_lots * 100
        r_share = b["revenue_eur"] / total_rev * 100
        rows.append(
            "<tr>"
            f"<th scope='row'>{esc(b['band'].replace('k', ' 000').replace('+', ' y más'))} €</th>"
            f"<td class='n'>{num(b['lots'])}</td>"
            f"<td class='bar-cell'><span class='bar bar-muted' style='--w:{l_share:.1f}%'></span>"
            f"<span class='bar-val'>{pct(l_share)}</span></td>"
            f"<td class='n strong'>{esc(eur(b['revenue_eur']))}</td>"
            f"<td class='bar-cell'><span class='bar bar-accent' style='--w:{r_share:.1f}%'></span>"
            f"<span class='bar-val'>{pct(r_share)}</span></td>"
            "</tr>"
        )

    stats = [
        ("Mediana", eur(dist.get("median")), "La mitad de los lotes se vende por debajo"),
        ("Percentil 90", eur(dist.get("p90")), "Solo 1 de cada 10 supera esta cifra"),
        ("Percentil 99", eur(dist.get("p99")), "El 1% más caro empieza aquí"),
        ("Récord", eur(dist.get("max")), "Lote más caro del conjunto"),
    ]
    stat_html = "".join(
        f"<div class='ministat'><p class='ministat-label'>{esc(l)}</p>"
        f"<p class='ministat-value'>{esc(v)}</p>"
        f"<p class='ministat-note'>{esc(n)}</p></div>"
        for l, v, n in stats
    )

    return (
        "<section class='panel highlight'>"
        "<h2>El mercado es una cola larga</h2>"
        f"<p class='panel-lead big'>{top_share_lots:.1f}% de los lotes vendidos "
        f"({num(top['lots'])} obras por encima de 25 000 €) generan "
        f"<strong>{top_share_rev:.0f}% de todo el volumen</strong>. "
        "El grueso del catálogo es de precio bajo; el dinero está en la punta.</p>"
        f"<div class='ministat-grid'>{stat_html}</div>"
        "<div class='table-scroll'><table>"
        "<thead><tr><th scope='col'>Tramo de precio</th><th scope='col'>Lotes</th>"
        "<th scope='col'>% de lotes</th><th scope='col'>Volumen</th>"
        "<th scope='col'>% del volumen</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table></div>"
        f"<p class='caveat'>Sobre {num(dist.get('count'))} lotes vendidos con precio publicado, "
        "convertidos a EUR.</p>"
        "</section>"
    )


def build_estimate(est: dict) -> str:
    if not est or not est.get("total_with_estimate"):
        return ""
    total = est["total_with_estimate"]
    segs = [
        ("above", "Por encima de la estimación alta", est.get("above", 0)),
        ("within", "Dentro de la horquilla", est.get("within", 0)),
        ("below", "Por debajo de la estimación baja", est.get("below", 0)),
    ]
    bar = "".join(
        f"<span class='seg seg-{k}' style='--w:{v / total * 100:.2f}%' "
        f"title='{esc(lbl)}: {num(v)}'></span>"
        for k, lbl, v in segs
    )
    legend = "".join(
        f"<li><span class='dot dot-{k}'></span>{esc(lbl)}"
        f"<strong>{pct(v / total * 100)}</strong>"
        f"<span class='sub'>{num(v)} lotes</span></li>"
        for k, lbl, v in segs
    )
    house_rows = []
    for h in sorted(est.get("by_house", []), key=lambda r: -r.get("total", 0)):
        t = h.get("total") or 1
        house_rows.append(
            "<tr>"
            f"<th scope='row'>{esc(house_label(h['house_slug']))}</th>"
            f"<td class='n'>{num(h.get('total'))}</td>"
            f"<td class='n'>{pct(h.get('above', 0) / t * 100)}</td>"
            f"<td class='n'>{pct(h.get('within', 0) / t * 100)}</td>"
            f"<td class='n'>{pct(h.get('below', 0) / t * 100)}</td>"
            "</tr>"
        )
    return (
        "<section class='panel'>"
        "<h2>Las estimaciones se quedan cortas</h2>"
        f"<p class='panel-lead'>De {num(total)} lotes vendidos con estimación publicada, "
        f"<strong>{pct(est.get('pct_above'))} superó el precio máximo estimado</strong> y solo "
        f"{pct(est.get('pct_below'))} se quedó por debajo del mínimo. "
        "Una horquilla que casi nunca se rompe por abajo sugiere estimaciones conservadoras, "
        "no una tasación fallida.</p>"
        f"<div class='segbar' role='img' aria-label='Distribución del precio final frente a la estimación'>{bar}</div>"
        f"<ul class='legend'>{legend}</ul>"
        "<div class='table-scroll'><table>"
        "<thead><tr><th scope='col'>Casa</th><th scope='col'>Lotes con estimación</th>"
        "<th scope='col'>Por encima</th><th scope='col'>Dentro</th>"
        "<th scope='col'>Por debajo</th></tr></thead>"
        f"<tbody>{''.join(house_rows)}</tbody></table></div>"
        "<p class='caveat'>Solo entran lotes vendidos que publican estimación mínima y máxima; "
        "es una submuestra, no el catálogo completo.</p>"
        "</section>"
    )


def build_charts_section() -> str:
    """Contenedores de los graficos. Los datos se inyectan como JSON aparte."""
    return (
        "<section class='panel'>"
        "<h2>Doce años de actividad</h2>"
        "<p class='panel-lead'>Volumen adjudicado y tasa de venta por año. "
        "La serie combina ambas casas en EUR; los lotes sin fecha fiable quedan fuera.</p>"
        "<div id='chart-year' class='chart' style='height:340px'></div>"
        "</section>"
        "<div class='grid-2'>"
        "<section class='panel'>"
        "<h2>El calendario manda</h2>"
        "<p class='panel-lead'>Volumen por mes de subasta, sumando todos los años.</p>"
        "<div id='chart-month' class='chart' style='height:300px'></div>"
        "</section>"
        "<section class='panel'>"
        "<h2>Volumen por casa y año</h2>"
        "<p class='panel-lead'>Las dos casas no cubren el mismo periodo.</p>"
        "<div id='chart-house-year' class='chart' style='height:300px'></div>"
        "</section>"
        "</div>"
    )


def build_top_auctions(auctions: list[dict], limit: int = 10) -> str:
    if not auctions:
        return ""
    top = sorted(auctions, key=lambda r: -(r.get("revenue_eur") or 0))[:limit]
    rows = []
    for i, a in enumerate(top, 1):
        date = (a.get("auction_start_date") or "")[:10] or "—"
        rows.append(
            "<tr>"
            f"<td class='rank'>{i}</td>"
            f"<th scope='row'><span class='artist-name'>{esc(a.get('auction_title') or a.get('auction_id'))}</span>"
            f"<span class='house-meta'>{esc(house_label(a.get('house_slug')))} · {esc(date)}</span></th>"
            f"<td class='n'>{num(a.get('lots'))}</td>"
            f"<td class='n'>{pct(a.get('sell_through_pct'))}</td>"
            f"<td class='n strong'>{esc(eur(a.get('revenue_eur')))}</td>"
            "</tr>"
        )
    return (
        "<section class='panel'>"
        "<h2>Las diez subastas más grandes</h2>"
        "<p class='panel-lead'>Ordenadas por volumen adjudicado en EUR.</p>"
        "<div class='table-scroll'><table>"
        "<thead><tr><th scope='col'>#</th><th scope='col'>Subasta</th>"
        "<th scope='col'>Lotes</th><th scope='col'>Tasa venta</th>"
        "<th scope='col'>Volumen</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table></div>"
        "</section>"
    )


# --------------------------------------------------------------------------
# CSS
# --------------------------------------------------------------------------

CSS = """
*,*::before,*::after{box-sizing:border-box}
:root{
  --c-primary:#1E40AF; --c-secondary:#3B82F6; --c-accent:#B45309;
  --c-bg:#F4F6FB; --c-surface:#FFFFFF; --c-fg:#111C3A; --c-fg-soft:#4B5A78;
  --c-muted:#E9EEF6; --c-border:#D6E0F0; --c-danger:#B91C1C; --c-warn:#92400E;
  --c-ok:#166534;
  --space-1:8px; --space-2:12px; --space-3:16px; --space-4:24px; --space-5:32px;
  --radius:10px; --radius-sm:6px;
  --shadow:0 1px 2px rgba(16,32,64,.06),0 4px 16px rgba(16,32,64,.06);
  --font-sans:'Fira Sans',system-ui,-apple-system,Segoe UI,sans-serif;
  --font-mono:'Fira Code',ui-monospace,SFMono-Regular,Menlo,monospace;
}
@media (prefers-color-scheme:dark){
  :root{
    --c-primary:#7BA2F7; --c-secondary:#5B8DEF; --c-accent:#F0A83C;
    --c-bg:#0C1120; --c-surface:#141B2E; --c-fg:#EAF0FB; --c-fg-soft:#9CACC9;
    --c-muted:#1D2740; --c-border:#293552; --c-danger:#F2A0A0; --c-warn:#E8C07A;
    --c-ok:#8ED9A6;
    --shadow:0 1px 2px rgba(0,0,0,.4),0 4px 18px rgba(0,0,0,.35);
  }
}
:root[data-theme="dark"]{
  --c-primary:#7BA2F7; --c-secondary:#5B8DEF; --c-accent:#F0A83C;
  --c-bg:#0C1120; --c-surface:#141B2E; --c-fg:#EAF0FB; --c-fg-soft:#9CACC9;
  --c-muted:#1D2740; --c-border:#293552; --c-danger:#F2A0A0; --c-warn:#E8C07A;
  --c-ok:#8ED9A6;
  --shadow:0 1px 2px rgba(0,0,0,.4),0 4px 18px rgba(0,0,0,.35);
}
:root[data-theme="light"]{
  --c-primary:#1E40AF; --c-secondary:#3B82F6; --c-accent:#B45309;
  --c-bg:#F4F6FB; --c-surface:#FFFFFF; --c-fg:#111C3A; --c-fg-soft:#4B5A78;
  --c-muted:#E9EEF6; --c-border:#D6E0F0; --c-danger:#B91C1C; --c-warn:#92400E;
  --c-ok:#166534;
  --shadow:0 1px 2px rgba(16,32,64,.06),0 4px 16px rgba(16,32,64,.06);
}
body{margin:0;background:var(--c-bg);color:var(--c-fg);font-family:var(--font-sans);
  font-size:16px;line-height:1.55;-webkit-font-smoothing:antialiased}
.wrap{max-width:1220px;margin:0 auto;padding:var(--space-4) var(--space-3) 64px}
a{color:var(--c-primary)}
a:focus-visible,summary:focus-visible,button:focus-visible{outline:2px solid var(--c-secondary);
  outline-offset:2px;border-radius:var(--radius-sm)}

header.masthead{padding:var(--space-5) 0 var(--space-4);border-bottom:1px solid var(--c-border);
  margin-bottom:var(--space-4);display:flex;justify-content:space-between;
  align-items:flex-start;gap:var(--space-3);flex-wrap:wrap}
.eyebrow{font-family:var(--font-mono);font-size:.75rem;letter-spacing:.12em;
  text-transform:uppercase;color:var(--c-primary);margin:0 0 var(--space-1)}
h1{font-size:clamp(1.7rem,3.4vw,2.5rem);line-height:1.15;margin:0 0 var(--space-2);
  letter-spacing:-.02em;font-weight:700}
.dek{margin:0;color:var(--c-fg-soft);max-width:62ch;font-size:1.02rem}
.theme-toggle{background:var(--c-surface);border:1px solid var(--c-border);color:var(--c-fg-soft);
  border-radius:var(--radius-sm);padding:8px 14px;font:inherit;font-size:.85rem;
  cursor:pointer;transition:background .18s ease,color .18s ease;min-height:44px}
.theme-toggle:hover{background:var(--c-muted);color:var(--c-fg)}

.kpi-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));
  gap:var(--space-2);margin-bottom:var(--space-4)}
.kpi{background:var(--c-surface);border:1px solid var(--c-border);border-radius:var(--radius);
  padding:var(--space-3);box-shadow:var(--shadow)}
.kpi-accent{border-color:var(--c-primary);box-shadow:0 0 0 1px var(--c-primary),var(--shadow)}
.kpi-label{margin:0 0 6px;font-size:.76rem;letter-spacing:.07em;text-transform:uppercase;
  color:var(--c-fg-soft);font-weight:600}
/* La cifra no debe partirse dejando el simbolo de moneda solo en otra linea:
   se escala el tamano al ancho disponible en vez de permitir el salto. */
.kpi-value{margin:0;font-family:var(--font-mono);
  font-size:clamp(1.3rem,4.2vw,1.85rem);font-weight:600;
  letter-spacing:-.02em;font-variant-numeric:tabular-nums;
  white-space:nowrap;overflow-wrap:normal}
.kpi-note{margin:6px 0 0;font-size:.8rem;color:var(--c-fg-soft);line-height:1.4}

.panel{background:var(--c-surface);border:1px solid var(--c-border);border-radius:var(--radius);
  padding:var(--space-4);box-shadow:var(--shadow);margin-bottom:var(--space-4)}
.panel h2{margin:0 0 6px;font-size:1.22rem;letter-spacing:-.01em;font-weight:650}
.panel-lead{margin:0 0 var(--space-3);color:var(--c-fg-soft);max-width:78ch;font-size:.94rem}
.panel-lead.big{font-size:1.05rem;color:var(--c-fg)}
.panel-lead strong{color:var(--c-fg)}
.highlight{border-left:4px solid var(--c-accent)}
.grid-2{display:grid;grid-template-columns:repeat(auto-fit,minmax(360px,1fr));gap:var(--space-4)}
.grid-2 .panel{margin-bottom:0}
.caveat{margin:var(--space-3) 0 0;padding-top:var(--space-2);border-top:1px dashed var(--c-border);
  font-size:.82rem;color:var(--c-fg-soft)}
/* overflow-wrap:anywhere porque el pie muestra una ruta Windows larga y sin
   espacios: sin esto empuja el ancho de la pagina entera en movil. */
code{font-family:var(--font-mono);font-size:.86em;background:var(--c-muted);
  padding:1px 5px;border-radius:4px;overflow-wrap:anywhere}

.flags summary{cursor:pointer;display:flex;align-items:baseline;gap:var(--space-2);
  list-style:none;min-height:44px}
.flags summary::-webkit-details-marker{display:none}
.flags summary h2{margin:0}
.flags summary::after{content:'▾';margin-left:auto;color:var(--c-fg-soft);transition:transform .2s ease}
.flags[open] summary::after{transform:rotate(180deg)}
.flags-count{font-size:.8rem;color:var(--c-fg-soft);font-family:var(--font-mono)}
.flag-list{list-style:none;margin:var(--space-3) 0 0;padding:0;display:grid;gap:var(--space-1)}
.flag{display:grid;grid-template-columns:minmax(140px,auto) 1fr;gap:var(--space-2);
  padding:10px var(--space-2);border-radius:var(--radius-sm);background:var(--c-muted);
  border-left:3px solid var(--c-border);font-size:.88rem;align-items:baseline}
.flag-tag{font-family:var(--font-mono);font-size:.72rem;text-transform:uppercase;
  letter-spacing:.06em;font-weight:600}
.flag-critical{border-left-color:var(--c-danger)}
.flag-critical .flag-tag{color:var(--c-danger)}
.flag-warn{border-left-color:var(--c-warn)}
.flag-warn .flag-tag{color:var(--c-warn)}
.flag-info{border-left-color:var(--c-secondary)}
/* El tag usa --c-primary y no --c-secondary: sobre el fondo --c-muted el azul
   claro se quedaba en 3.16:1, por debajo del 4.5:1 que exige texto pequeno. */
.flag-info .flag-tag{color:var(--c-primary)}

/* min-width:0 es imprescindible: sin el, el hijo de un grid/flex no baja de su
   ancho de contenido y la tabla desborda la pagina en vez de scrollear dentro. */
.table-scroll{overflow-x:auto;-webkit-overflow-scrolling:touch;min-width:0;max-width:100%}
.panel,.grid-2>.panel{min-width:0}
table{width:100%;border-collapse:collapse;font-size:.9rem;min-width:520px}
thead th{text-align:right;font-size:.74rem;letter-spacing:.06em;text-transform:uppercase;
  color:var(--c-fg-soft);font-weight:600;padding:0 var(--space-2) var(--space-1);
  border-bottom:1px solid var(--c-border);white-space:nowrap}
thead th:first-child{text-align:left}
tbody th{text-align:left;font-weight:500;padding:10px var(--space-2);
  border-bottom:1px solid var(--c-border)}
tbody td{padding:10px var(--space-2);border-bottom:1px solid var(--c-border);text-align:right}
tbody tr:last-child th,tbody tr:last-child td{border-bottom:none}
tbody tr{transition:background .15s ease}
tbody tr:hover{background:var(--c-muted)}
td.n,.n{font-family:var(--font-mono);font-variant-numeric:tabular-nums;white-space:nowrap}
.strong{font-weight:600}
.rank{font-family:var(--font-mono);color:var(--c-fg-soft);text-align:left;width:2.4rem}
.sub{display:block;font-size:.76rem;color:var(--c-fg-soft);font-weight:400}
.house-name,.artist-name{display:block;font-weight:600}
.house-meta{display:block;font-size:.76rem;color:var(--c-fg-soft);font-weight:400}

.bar-cell{min-width:130px;display:flex;align-items:center;gap:var(--space-1);justify-content:flex-end}
.bar{display:block;height:8px;width:var(--w);min-width:2px;border-radius:99px;
  background:var(--c-secondary);flex:0 0 auto}
.bar-muted{background:var(--c-fg-soft);opacity:.5}
.bar-accent{background:var(--c-accent)}
.bar-val{font-family:var(--font-mono);font-size:.8rem;color:var(--c-fg-soft);
  width:3.6rem;text-align:right;flex:0 0 auto}

.ministat-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));
  gap:var(--space-2);margin-bottom:var(--space-3)}
.ministat{background:var(--c-muted);border-radius:var(--radius-sm);padding:var(--space-2)}
.ministat-label{margin:0;font-size:.74rem;text-transform:uppercase;letter-spacing:.06em;
  color:var(--c-fg-soft);font-weight:600}
.ministat-value{margin:2px 0 0;font-family:var(--font-mono);font-size:1.25rem;font-weight:600;
  font-variant-numeric:tabular-nums}
.ministat-note{margin:2px 0 0;font-size:.76rem;color:var(--c-fg-soft);line-height:1.35}

.segbar{display:flex;height:34px;border-radius:var(--radius-sm);overflow:hidden;
  margin-bottom:var(--space-3);background:var(--c-muted)}
.seg{width:var(--w);transition:opacity .18s ease}
.seg:hover{opacity:.82}
.seg-above{background:var(--c-accent)}
.seg-within{background:var(--c-secondary)}
.seg-below{background:var(--c-fg-soft)}
.legend{list-style:none;margin:0 0 var(--space-3);padding:0;display:grid;
  grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:var(--space-2)}
.legend li{display:flex;align-items:baseline;gap:8px;font-size:.87rem;flex-wrap:wrap}
.legend strong{font-family:var(--font-mono);margin-left:auto}
.legend .sub{width:100%;margin-left:20px}
.dot{width:10px;height:10px;border-radius:3px;flex:0 0 auto}
.dot-above{background:var(--c-accent)}
.dot-within{background:var(--c-secondary)}
.dot-below{background:var(--c-fg-soft)}

.chart{width:100%}
footer{margin-top:var(--space-5);padding-top:var(--space-3);border-top:1px solid var(--c-border);
  color:var(--c-fg-soft);font-size:.82rem}
footer p{margin:0 0 6px;max-width:80ch}

@media (max-width:640px){
  .wrap{padding:var(--space-2) var(--space-2) 48px}
  .panel{padding:var(--space-3)}
  .flag{grid-template-columns:1fr;gap:2px}
  table{min-width:440px;font-size:.85rem}
  thead th,tbody th,tbody td{padding:8px var(--space-1)}
  .bar-cell{min-width:92px}
  .bar-val{width:3rem;font-size:.75rem}
  /* Pista visible de que la tabla scrollea en horizontal. */
  .table-scroll{border-right:1px solid var(--c-border)}
}
@media (prefers-reduced-motion:reduce){
  *{animation-duration:.01ms!important;animation-iteration-count:1!important;
    transition-duration:.01ms!important;scroll-behavior:auto!important}
}
@media print{
  body{background:#fff}
  .panel{break-inside:avoid;box-shadow:none;border-color:#ccc}
  .theme-toggle{display:none}
}
"""


# --------------------------------------------------------------------------
# JS (Plotly)
# --------------------------------------------------------------------------

JS_TEMPLATE = """
const DATA = __DATA__;

const isDark = () => {
  const attr = document.documentElement.getAttribute('data-theme');
  if (attr) return attr === 'dark';
  return window.matchMedia('(prefers-color-scheme: dark)').matches;
};
const css = (name) => getComputedStyle(document.documentElement)
  .getPropertyValue(name).trim();

// prefers-reduced-motion: Plotly anima transiciones por defecto.
const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

function baseLayout() {
  const fg = css('--c-fg'), soft = css('--c-fg-soft'), border = css('--c-border');
  return {
    paper_bgcolor: 'rgba(0,0,0,0)',
    plot_bgcolor: 'rgba(0,0,0,0)',
    font: { family: "'Fira Sans', system-ui, sans-serif", size: 12, color: fg },
    margin: { l: 56, r: 20, t: 16, b: 44 },
    xaxis: { gridcolor: border, zerolinecolor: border, tickfont: { color: soft } },
    yaxis: { gridcolor: border, zerolinecolor: border, tickfont: { color: soft } },
    hoverlabel: { font: { family: "'Fira Code', monospace", size: 12 } },
    legend: { orientation: 'h', y: -0.2, font: { color: soft } },
    transition: reduceMotion ? undefined : { duration: 250, easing: 'cubic-out' }
  };
}
const CONFIG = { displayModeBar: false, responsive: true, locale: 'es' };

function drawYear() {
  const el = document.getElementById('chart-year');
  if (!el || !DATA.by_year.length) return;
  // 'unknown' fuera del eje temporal: no es un año, y colocarlo rompe la serie.
  const rows = DATA.by_year.filter(r => /^\\d{4}$/.test(r.year))
    .sort((a, b) => a.year.localeCompare(b.year));
  const L = baseLayout();
  L.margin.r = 56;
  L.yaxis.title = { text: 'Volumen (EUR)', font: { size: 11, color: css('--c-fg-soft') } };
  L.yaxis2 = { overlaying: 'y', side: 'right', range: [0, 100], gridcolor: 'rgba(0,0,0,0)',
    tickfont: { color: css('--c-fg-soft') }, ticksuffix: '%',
    title: { text: 'Tasa de venta', font: { size: 11, color: css('--c-fg-soft') } } };
  Plotly.newPlot(el, [
    { x: rows.map(r => r.year), y: rows.map(r => r.revenue_eur), type: 'bar',
      name: 'Volumen adjudicado', marker: { color: css('--c-secondary') },
      hovertemplate: '%{x}<br>%{y:,.0f} €<extra></extra>' },
    { x: rows.map(r => r.year), y: rows.map(r => (r.sell_through_rate * 100)),
      type: 'scatter', mode: 'lines+markers', name: 'Tasa de venta', yaxis: 'y2',
      line: { color: css('--c-accent'), width: 2.5 }, marker: { size: 6 },
      hovertemplate: '%{x}<br>%{y:.1f}% vendido<extra></extra>' }
  ], L, CONFIG);
}

function drawMonth() {
  const el = document.getElementById('chart-month');
  if (!el || !DATA.by_month.length) return;
  const rows = DATA.by_month;
  const L = baseLayout();
  L.yaxis.title = { text: 'Volumen (EUR)', font: { size: 11, color: css('--c-fg-soft') } };
  Plotly.newPlot(el, [{
    x: rows.map(r => r.label), y: rows.map(r => r.revenue_eur), type: 'bar',
    marker: { color: css('--c-primary') },
    hovertemplate: '%{x}<br>%{y:,.0f} €<br>%{customdata:,} lotes<extra></extra>',
    customdata: rows.map(r => r.lots_offered)
  }], L, CONFIG);
}

function drawHouseYear() {
  const el = document.getElementById('chart-house-year');
  if (!el || !DATA.by_year_by_house.length) return;
  const rows = DATA.by_year_by_house.filter(r => /^\\d{4}$/.test(r.year));
  const houses = [...new Set(rows.map(r => r.house_slug))];
  const palette = [css('--c-secondary'), css('--c-accent'), css('--c-primary')];
  const traces = houses.map((h, i) => {
    const sub = rows.filter(r => r.house_slug === h).sort((a, b) => a.year.localeCompare(b.year));
    return {
      x: sub.map(r => r.year), y: sub.map(r => r.revenue_eur), type: 'bar',
      name: DATA.house_labels[h] || h, marker: { color: palette[i % palette.length] },
      hovertemplate: '%{x}<br>%{y:,.0f} €<extra>' + (DATA.house_labels[h] || h) + '</extra>'
    };
  });
  const L = baseLayout();
  L.barmode = 'stack';
  L.yaxis.title = { text: 'Volumen (EUR)', font: { size: 11, color: css('--c-fg-soft') } };
  Plotly.newPlot(el, traces, L, CONFIG);
}

function drawAll() { drawYear(); drawMonth(); drawHouseYear(); }

// Toggle de tema: el usuario manda sobre la preferencia del sistema.
const toggle = document.getElementById('theme-toggle');
function applyTheme(mode) {
  document.documentElement.setAttribute('data-theme', mode);
  try { localStorage.setItem('auction-theme', mode); } catch (e) {}
  toggle.setAttribute('aria-pressed', String(mode === 'dark'));
  toggle.textContent = mode === 'dark' ? 'Modo claro' : 'Modo oscuro';
  drawAll();
}
try {
  const saved = localStorage.getItem('auction-theme');
  if (saved) applyTheme(saved);
} catch (e) {}
toggle.addEventListener('click', () => applyTheme(isDark() ? 'light' : 'dark'));
window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => {
  if (!document.documentElement.getAttribute('data-theme')) drawAll();
});

drawAll();
if (!toggle.textContent.trim()) {
  toggle.textContent = isDark() ? 'Modo claro' : 'Modo oscuro';
}
"""


def build_chart_data(report: dict) -> dict:
    months = [
        {
            "label": MONTH_LABELS.get(m["month"], m["month"]),
            "revenue_eur": m.get("revenue_eur", 0),
            "lots_offered": m.get("lots_offered", 0),
        }
        for m in report.get("by_month", [])
    ]
    return {
        "by_year": report.get("by_year", []),
        "by_year_by_house": report.get("by_year_by_house", []),
        "by_month": months,
        "house_labels": HOUSE_LABELS,
    }


def write_html(report: dict, path: Path) -> None:
    s = report["summary"]
    dist = report.get("price_distribution") or {}
    est = report.get("estimate_accuracy") or {}

    years = [r["year"] for r in report.get("by_year", []) if str(r.get("year", "")).isdigit()]
    span = f"{min(years)}–{max(years)}" if years else "histórico"

    # Titular: el dato mas fuerte del conjunto, no una descripcion generica.
    bands = dist.get("bands") or []
    if bands:
        total_lots = sum(b["lots"] for b in bands) or 1
        total_rev = sum(b["revenue_eur"] for b in bands) or 1
        top = bands[-1]
        dek = (
            f"{num(s['total_lots'])} lotes de {s['total_houses']} casas de subastas, "
            f"{span}. El {top['lots'] / total_lots * 100:.1f}% más caro de lo vendido "
            f"concentra el {top['revenue_eur'] / total_rev * 100:.0f}% del dinero."
        )
    else:
        dek = f"{num(s['total_lots'])} lotes de {s['total_houses']} casas de subastas, {span}."

    chart_json = json.dumps(build_chart_data(report), ensure_ascii=False)
    js = JS_TEMPLATE.replace("__DATA__", chart_json)

    body = "".join(
        [
            "<header class='masthead'><div>",
            "<p class='eyebrow'>Informe Gold · Mercado del arte</p>",
            "<h1>Qué se vende, a quién y por cuánto</h1>",
            f"<p class='dek'>{esc(dek)}</p>",
            "</div>",
            "<button id='theme-toggle' class='theme-toggle' type='button' "
            "aria-pressed='false'>Modo oscuro</button>",
            "</header>",
            build_kpis(report),
            build_flags(report.get("quality_flags", [])),
            build_concentration(dist),
            build_estimate(est),
            build_charts_section(),
            build_house_table(report.get("by_house", [])),
            build_artist_table(report.get("by_artist", [])),
            build_category_table(report.get("by_category", [])),
            build_top_auctions(report.get("by_auction", [])),
            "<footer>",
            f"<p><strong>Conversión de moneda.</strong> {esc(fx_note())}</p>",
            "<p><strong>Procedencia.</strong> Datos extraídos de las webs públicas de las casas "
            "y refinados por una cadena bronze → silver → gold. Este informe lee únicamente la "
            "capa Gold; las cifras se reconstruyen ejecutando "
            "<code>python -m pipelines.analytics.report_gold</code>.</p>",
            f"<p>Fuente: <code>{esc(report.get('source', ''))}</code></p>",
            "</footer>",
        ]
    )

    doc = f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>Qué se vende, a quién y por cuánto · Informe Gold</title>
<meta name="description" content="{esc(dek)}" />
<link rel="preconnect" href="https://fonts.googleapis.com" />
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
<link href="https://fonts.googleapis.com/css2?family=Fira+Code:wght@400;500;600&family=Fira+Sans:wght@300;400;500;600;700&display=swap" rel="stylesheet" />
<script src="https://cdn.plot.ly/plotly-2.27.0.min.js" charset="utf-8"></script>
<style>{CSS}</style>
</head>
<body>
<div class="wrap">
{body}
</div>
<script>{js}</script>
</body>
</html>
"""
    path.write_text(doc, encoding="utf-8")

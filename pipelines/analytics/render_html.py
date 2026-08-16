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

from pipelines.shared.artist_master import country_es
from pipelines.shared.fx import fx_as_of, fx_note

# Nombres legibles: los slugs son claves tecnicas, no etiquetas de interfaz.
HOUSE_LABELS = {
    "bogota_auctions": "Bogotá Auctions",
    "duran_subastas": "Durán Subastas",
    "zorrilla_subastas": "Zorrilla Subastas",
    "lefebre_subastas": "Lefebre Subastas",
}
# Donde OCURRE la subasta. NO es la nacionalidad del artista: esa sale del
# maestro (pipelines/config/artists/) via artist_country_birth. Usar esta tabla
# como nacionalidad ya seria falso hoy para los 46 artistas espanioles, 26
# alemanes y 25 panamenios que ha vendido Bogota.
HOUSE_COUNTRY = {
    "bogota_auctions": "Colombia",
    "duran_subastas": "España",
    "zorrilla_subastas": "Uruguay",
    "lefebre_subastas": "Colombia",
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


# Iconos inline: el informe es un HTML suelto que se abre con doble clic, sin
# servidor ni red, asi que no puede depender de una fuente de iconos externa.
_SVG = (
    "<svg viewBox='0 0 16 16' width='14' height='14' aria-hidden='true' "
    "fill='none' stroke='currentColor' stroke-width='1.5' "
    "stroke-linecap='round' stroke-linejoin='round'>{}</svg>"
)
# Flecha hacia una bandeja: descargar.
_ARROW = "<path d='M8 1.5v7.5M5 6.5 8 9.5l3-3'/><path d='M2.5 11.5v2h11v-2'/>"
ICON_TABLE = _SVG.format(_ARROW + "<path d='M2.5 3.5h3M2.5 6h3M2.5 8.5h3'/>")
ICON_LOTS = _SVG.format(_ARROW + "<circle cx='4' cy='4' r='1.6'/>")


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
        "<h2>Las casas, una al lado de la otra</h2>"
        "<p class='panel-lead'>Cada casa cotiza en su moneda. La columna nativa es el dato exacto; "
        "el EUR es la conversión aproximada que permite compararlas.</p>"
        "<div class='table-scroll'><table>"
        "<thead><tr><th scope='col'>Casa</th><th scope='col'>Ofertados</th>"
        "<th scope='col'>Vendidos</th><th scope='col'>Tasa venta</th>"
        "<th scope='col'>Volumen</th><th scope='col'>Precio medio</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table></div>"
        "<p class='caveat'><strong>Bogotá queda fuera de cualquier comparación de tasa de venta</strong>: "
        "publica casi solo lotes vendidos, así que su ~99% mide qué publica, no cómo vende. "
        "Durán, Zorrilla y Lefebre sí publican los no vendidos y sí son comparables entre sí. "
        "Es una propiedad de la fuente, no una diferencia de rendimiento.</p>"
        "</section>"
    )


def build_artist_table(artists: list[dict], coverage: dict | None = None,
                       limit: int = 200) -> str:
    """Ranking de artistas con filtro por nombre y por pais.

    Se renderizan hasta `limit` filas y el filtrado es JS de cliente sobre el
    DOM: el informe HTML es el producto, no hay servicio que consultar.
    """
    if not artists:
        return ""

    # Opciones del desplegable: solo los paises realmente presentes.
    countries = sorted(
        {
            (a.get("country_birth"), a.get("country_birth_es") or a.get("country_birth"))
            for a in artists[:limit]
            if a.get("country_birth")
        },
        key=lambda pair: pair[1] or "",
    )
    options = "".join(
        f"<option value='{esc(code)}'>{esc(label)}</option>" for code, label in countries
    )
    unknown_option = (
        "<option value='__none__'>Sin país informado</option>"
        if any(not a.get("country_birth") for a in artists[:limit])
        else ""
    )

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
        code = a.get("country_birth")
        label = a.get("country_birth_es") or code
        # Nacionalidades adicionales a la de nacimiento, para el caso Obregon.
        extra = [n for n in (a.get("nationalities") or []) if n != code]
        meta = label or "Sin país informado"
        if extra:
            meta += " · tb. " + ", ".join(esc(country_es(n) or n) for n in extra)
        # Fechas del maestro. Solo 755 de 897 fichas las tienen, asi que la
        # linea se construye con lo que haya en vez de reservar el hueco: un
        # "(?-?)" en la mitad de las filas es ruido, no informacion.
        life = a.get("life_years")
        if life:
            meta += f" · {esc(life)}"
        # Las cifras viajan tambien como datos para que el totalizador pueda
        # sumarlas al filtrar sin volver a parsear el texto ya formateado.
        rows.append(
            f"<tr data-country='{esc(code or '__none__')}' "
            f"data-name='{esc((a.get('artist_name') or '').lower())}' "
            f"data-sold='{a.get('lots_sold') or 0}' "
            f"data-offered='{a.get('lots_offered') or 0}' "
            f"data-birth='{a.get('birth_year') or ''}' "
            f"data-death='{a.get('death_year') or ''}' "
            f"data-revenue='{a.get('revenue_eur') or 0}'>"
            f"<td class='rank'>{i}</td>"
            f"<th scope='row'><span class='artist-name'>{esc(a['artist_name'])}</span>"
            f"<span class='house-meta{'' if label else ' muted'}'>{meta}</span></th>"
            f"<td class='n'>{num(a.get('lots_sold'))}<span class='sub'>de {num(a.get('lots_offered'))}</span></td>"
            f"<td class='n'>{pct(st)}</td>"
            f"<td class='n strong'>{esc(eur(a.get('revenue_eur')))}</td>"
            f"<td class='n'>{top_cell}</td>"
            "</tr>"
        )

    shown = min(limit, len(artists))
    # Cobertura de fechas: la de la tabla visible y la del ranking entero. Basta
    # birth_year, porque un artista vivo no tiene death_year y eso no es un hueco.
    dated_shown = sum(1 for a in artists[:limit] if a.get("birth_year"))
    dated_ranked = sum(1 for a in artists if a.get("birth_year"))
    caveat = (
        "<p class='caveat'>El récord enlaza al lote original en la web de la casa.</p>"
    )
    if len(artists) > shown:
        # Sin esto, los totales de la tabla se leerian como el total del
        # mercado, y son solo los de los artistas mostrados.
        caveat += (
            f"<p class='caveat'>Los totales de arriba suman lo que hay filtrado en la "
            f"tabla, que son los {num(shown)} primeros artistas de {num(len(artists))} "
            "rankeados. No son el total del mercado: ese está en las tarjetas de "
            "cabecera del informe.</p>"
        )
    if coverage:
        ranked = coverage.get("artists_ranked") or 0
        with_country = coverage.get("artists_with_country") or 0
        cov = coverage.get("country_coverage_pct") or 0
        if with_country == 0:
            caveat += (
                "<p class='caveat'><strong>El filtro por país está vacío a propósito.</strong> "
                "El maestro de artistas (<code>pipelines/config/artists/</code>) todavía no "
                "se ha poblado, así que ningún artista tiene país asignado. El sistema "
                "prefiere no informar país antes que inventarlo: la nacionalidad no se "
                "deduce del país de la casa de subastas.</p>"
            )
        else:
            caveat += (
                f"<p class='caveat'>Tienen país informado {num(with_country)} de "
                f"{num(ranked)} artistas del ranking ({pct(cov)}). El resto aparece como "
                "“sin país informado”: no se deduce del país de la casa.</p>"
            )
            # La cobertura de la tabla visible y la del ranking completo son muy
            # distintas (los primeros por volumen son los mejor documentados), y
            # publicar solo la primera daria una idea falsa del maestro.
            if dated_shown is not None and shown:
                caveat += (
                    f"<p class='caveat'>Las fechas de nacimiento y muerte salen del maestro "
                    f"de artistas, no del texto del lote: cuando no constan, no se deducen. "
                    f"Las tienen {num(dated_shown)} de los {num(shown)} artistas de esta tabla "
                    f"({pct(dated_shown / shown * 100)}), pero solo {num(dated_ranked)} de los "
                    f"{num(ranked)} del ranking completo ({pct(dated_ranked / ranked * 100)}): "
                    "los artistas que más venden son también los mejor documentados. "
                    "Un artista vivo aparece como “n. 1954”, sin año de muerte.</p>"
                )

    return (
        "<section class='panel'>"
        "<h2>Quién mueve el dinero</h2>"
        f"<p class='panel-lead'>Los {num(shown)} artistas con mayor volumen adjudicado. "
        "Se excluyen escuelas, talleres y atribuciones (“Escuela Española”, “Atribuido a…”), "
        "que agrupan cientos de lotes de autoría distinta y falsearían el ranking. "
        "Mínimo 3 lotes vendidos para entrar.</p>"
        "<div class='filters'>"
        "<label>Buscar artista"
        "<input type='search' id='artist-search' placeholder='p. ej. Botero' "
        "autocomplete='off'></label>"
        "<label>País de nacimiento"
        f"<select id='country-filter'><option value=''>Todos</option>{options}{unknown_option}</select></label>"
        "<button type='button' class='filter-reset' id='artist-reset'>Limpiar</button>"
        "<span class='downloads'>"
        "<button type='button' class='dl' id='artist-dl-view' "
        "title='Descargar la tabla tal como se ve, en CSV para Excel'>"
        f"{ICON_TABLE} Tabla</button>"
        "<button type='button' class='dl' id='artist-dl-lots' "
        "title='Descargar los lotes que hay detrás de estas cifras, uno por fila'>"
        f"{ICON_LOTS} Lotes</button>"
        "</span>"
        "</div>"
        # Totalizador: se recalcula con cada filtro para que la seleccion tenga
        # sus propios KPIs y no haya que sumar a ojo las filas visibles.
        "<div class='totals' id='artist-totals' role='status' aria-live='polite'>"
        "<div class='total'><span class='total-label'>Artistas</span>"
        "<span class='total-value' id='t-artists'>—</span></div>"
        "<div class='total'><span class='total-label'>Lotes vendidos</span>"
        "<span class='total-value' id='t-sold'>—</span>"
        "<span class='total-note' id='t-offered'></span></div>"
        "<div class='total'><span class='total-label'>Tasa de venta</span>"
        "<span class='total-value' id='t-rate'>—</span></div>"
        "<div class='total total-accent'><span class='total-label'>Volumen adjudicado</span>"
        "<span class='total-value' id='t-revenue'>—</span></div>"
        "<div class='total'><span class='total-label'>Precio medio</span>"
        "<span class='total-value' id='t-avg'>—</span></div>"
        # KPI de cobertura: sin el, "200 artistas" se lee como 200 fichas
        # completas. Se recalcula al filtrar, y ahi dice algo que el numero
        # global esconde: pais y fechas son campos independientes del maestro,
        # asi que filtrando sale 76% en Espania y 100% en Uruguay.
        "<div class='total'><span class='total-label'>Con fechas</span>"
        "<span class='total-value' id='t-dated'>—</span>"
        "<span class='total-note' id='t-dated-note'></span></div>"
        "</div>"
        "<div class='table-scroll'><table id='artist-table'>"
        "<thead><tr><th scope='col'>#</th><th scope='col'>Artista</th>"
        "<th scope='col'>Vendidos</th><th scope='col'>Tasa venta</th>"
        "<th scope='col'>Volumen</th><th scope='col'>Récord</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table></div>"
        "<p class='empty-msg' id='artist-empty' hidden>Ningún artista coincide con el filtro.</p>"
        + caveat
        + "</section>"
    )


def build_country_table(countries: list[dict], limit: int = 25) -> str:
    """De donde viene el arte que se vende, por pais de nacimiento del artista."""
    if not countries:
        return ""
    known = [c for c in countries if c.get("country")]
    unknown = next((c for c in countries if not c.get("country")), None)
    if not known:
        # Sin maestro poblado no hay nada que mostrar; el aviso ya lo da la
        # tabla de artistas. Mejor omitir la seccion que ensenar una fila vacia.
        return ""

    rows = []
    for i, c in enumerate(known[:limit], 1):
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
            f"<th scope='row'><span class='artist-name'>{esc(name)}</span>"
            f"<span class='house-meta'>{num(c.get('artists'))} artistas</span></th>"
            f"<td class='n'>{num(c.get('lots_sold'))}<span class='sub'>de {num(c.get('lots_offered'))}</span></td>"
            f"<td class='n'>{pct(st)}</td>"
            f"<td class='n strong'>{esc(eur(c.get('revenue_eur')))}</td>"
            f"<td>{esc(c.get('top_artist') or '')}</td>"
            "</tr>"
        )

    caveat = (
        "<p class='caveat'>Los totales de arriba suman los países filtrados en la tabla. "
        "Cubren solo los lotes con artista identificado en el maestro, no todo el mercado.</p>"
        "<p class='caveat'>Se agrupa por país de <strong>nacimiento</strong>, así que cada "
        "lote cuenta una sola vez. Un artista con doble nacionalidad aparece en un solo "
        "país aquí; sus otras nacionalidades se ven en la ficha del artista.</p>"
        "<p class='caveat'>Ojo al leer comparaciones entre países: solo 66 de unos 15.000 "
        "nombres coinciden entre Durán (mercado español) y Bogotá (colombiano), así que el "
        "país del artista va casi calcado al de la casa. Un gráfico “España vs Colombia” "
        "está, en buena medida, comparando esas dos casas.</p>"
        "<p class='caveat'><strong>Zorrilla no entra en este ranking</strong>: LiveAuctioneers "
        "no publica un campo de artista separado —el título del lote es la descripción del "
        "objeto—, así que sus lotes no tienen <code>artist_name</code> que atribuir.</p>"
    )
    if unknown and unknown.get("lots_offered"):
        caveat += (
            f"<p class='caveat'>Quedan {num(unknown.get('lots_offered'))} lotes de artistas "
            "sin país en el maestro. No se reparten entre los países conocidos: se dejan "
            "fuera para no inflar ninguno.</p>"
        )

    return (
        "<section class='panel'>"
        "<h2>De dónde viene el arte</h2>"
        "<p class='panel-lead'>Volumen adjudicado por país de nacimiento del artista, "
        "según el maestro de artistas.</p>"
        "<div class='filters'>"
        "<label>Buscar país"
        "<input type='search' id='country-search' placeholder='p. ej. Colombia' "
        "autocomplete='off'></label>"
        "<button type='button' class='filter-reset' id='country-reset'>Limpiar</button>"
        "<span class='downloads'>"
        "<button type='button' class='dl' id='country-dl-view' "
        "title='Descargar la tabla tal como se ve, en CSV para Excel'>"
        f"{ICON_TABLE} Tabla</button>"
        "<button type='button' class='dl' id='country-dl-lots' "
        "title='Descargar los lotes que hay detrás de estas cifras, uno por fila'>"
        f"{ICON_LOTS} Lotes</button>"
        "</span>"
        "</div>"
        "<div class='totals' id='country-totals' role='status' aria-live='polite'>"
        "<div class='total'><span class='total-label'>Países</span>"
        "<span class='total-value' id='c-countries'>—</span></div>"
        "<div class='total'><span class='total-label'>Artistas</span>"
        "<span class='total-value' id='c-artists'>—</span></div>"
        "<div class='total'><span class='total-label'>Lotes vendidos</span>"
        "<span class='total-value' id='c-sold'>—</span>"
        "<span class='total-note' id='c-offered'></span></div>"
        "<div class='total'><span class='total-label'>Tasa de venta</span>"
        "<span class='total-value' id='c-rate'>—</span></div>"
        "<div class='total total-accent'><span class='total-label'>Volumen adjudicado</span>"
        "<span class='total-value' id='c-revenue'>—</span></div>"
        "</div>"
        "<div class='table-scroll'><table id='country-table'>"
        "<thead><tr><th scope='col'>#</th><th scope='col'>País</th>"
        "<th scope='col'>Vendidos</th><th scope='col'>Tasa venta</th>"
        "<th scope='col'>Volumen</th><th scope='col'>Artista destacado</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table></div>"
        "<p class='empty-msg' id='country-empty' hidden>Ningún país coincide con el filtro.</p>"
        + caveat
        + "</section>"
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
        "La serie combina todas las casas en EUR; los lotes sin fecha fiable quedan fuera.</p>"
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
        "<p class='panel-lead'>Las casas no cubren el mismo periodo.</p>"
        # 340px: la leyenda horizontal de cuatro casas vive sobre el area de
        # trazado, y con 300px se comia el grafico.
        "<div id='chart-house-year' class='chart' style='height:340px'></div>"
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
.house-meta.muted{opacity:.6;font-style:italic}

/* Filtros de artista y pais. El informe HTML es el producto: el filtrado es JS
   de cliente sobre el DOM, no hay servicio que consultar. */
.filters{display:flex;flex-wrap:wrap;gap:var(--space-2);align-items:flex-end;
  margin:0 0 var(--space-2)}
.filters label{display:flex;flex-direction:column;gap:4px;font-size:.74rem;
  letter-spacing:.06em;text-transform:uppercase;color:var(--c-fg-soft);font-weight:600}
.filters input,.filters select{font:inherit;font-size:.9rem;text-transform:none;
  letter-spacing:normal;color:var(--c-fg);background:var(--c-bg);
  border:1px solid var(--c-border);border-radius:6px;padding:7px 10px;min-width:13rem}
.filters input:focus-visible,.filters select:focus-visible{outline:2px solid var(--c-accent);
  outline-offset:1px}
.filter-count{font-family:var(--font-mono);font-size:.8rem;color:var(--c-fg-soft);
  padding-bottom:8px}
.filter-reset{font:inherit;font-size:.8rem;color:var(--c-fg-soft);cursor:pointer;
  background:var(--c-surface);border:1px solid var(--c-border);border-radius:6px;
  padding:8px 12px}
.filter-reset:hover{background:var(--c-muted);color:var(--c-fg)}
.downloads{display:flex;gap:6px;margin-left:auto;padding-bottom:0}
.dl{display:inline-flex;align-items:center;gap:5px;font:inherit;font-size:.78rem;
  font-weight:500;color:var(--c-fg-soft);cursor:pointer;background:var(--c-surface);
  border:1px solid var(--c-border);border-radius:6px;padding:8px 10px;white-space:nowrap}
.dl:hover{background:var(--c-muted);color:var(--c-accent);border-color:var(--c-accent)}
.dl:focus-visible{outline:2px solid var(--c-accent);outline-offset:1px}
.dl svg{flex:0 0 auto}
@media (max-width:640px){.downloads{margin-left:0;width:100%}.dl{flex:1;justify-content:center}}
.empty-msg{color:var(--c-fg-soft);font-size:.9rem;padding:var(--space-2) 0;margin:0}

/* Confirmacion de descarga: sustituye a alert(), que puede estar bloqueado
   segun donde se abra el informe. */
.toast{position:fixed;left:50%;bottom:20px;transform:translate(-50%,140%);
  background:var(--c-fg);color:var(--c-bg);font-size:.85rem;line-height:1.4;
  padding:11px 18px;border-radius:6px;max-width:min(34rem,90vw);z-index:50;
  box-shadow:0 6px 22px rgba(0,0,0,.22);transition:transform .22s ease;
  pointer-events:none}
.toast.show{transform:translate(-50%,0)}
.toast.bad{background:var(--c-accent);color:#fff}

/* Totalizador: KPIs de lo que hay filtrado en ese momento. Sin el, filtrar por
   pais obligaba a sumar a ojo las filas visibles. */
.totals{display:grid;grid-template-columns:repeat(auto-fit,minmax(9rem,1fr));
  gap:1px;background:var(--c-border);border:1px solid var(--c-border);
  border-radius:8px;overflow:hidden;margin:0 0 var(--space-2)}
.total{background:var(--c-surface);padding:10px var(--space-2);min-width:0}
.total-accent{background:var(--c-muted)}
.total-label{display:block;font-size:.68rem;letter-spacing:.06em;
  text-transform:uppercase;color:var(--c-fg-soft);font-weight:600}
.total-value{display:block;font-family:var(--font-mono);font-variant-numeric:tabular-nums;
  font-size:1.05rem;font-weight:600;margin-top:2px;white-space:nowrap;
  overflow:hidden;text-overflow:ellipsis}
.total-accent .total-value{color:var(--c-accent)}
.total-note{display:block;font-size:.72rem;color:var(--c-fg-soft);font-family:var(--font-mono)}
.totals.is-filtered{border-color:var(--c-accent)}

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
  // Orden fijo por volumen total: el color sigue a la casa, no al orden de llegada
  // de las filas. Si manana se filtra una casa, las demas conservan su color.
  const totals = {};
  rows.forEach(r => { totals[r.house_slug] = (totals[r.house_slug] || 0) + (r.revenue_eur || 0); });
  const houses = [...new Set(rows.map(r => r.house_slug))].sort((a, b) => totals[b] - totals[a]);
  // Cuatro slots validados (dataviz validate_palette.js, seis checks, ambos modos):
  // antes eran tres y la cuarta casa reciclaba el color de la primera via i % 3,
  // asi que Duran y Bogota salian del mismo azul en la misma barra apilada.
  const palette = isDark()
    ? ['#3B82F6', '#D67329', '#0EA5A5', '#8B5CF6']
    : ['#2563EB', '#C2410C', '#0D9488', '#7C3AED'];
  const surface = css('--c-surface');
  const traces = houses.map((h, i) => {
    const sub = rows.filter(r => r.house_slug === h).sort((a, b) => a.year.localeCompare(b.year));
    return {
      x: sub.map(r => r.year), y: sub.map(r => r.revenue_eur), type: 'bar',
      name: DATA.house_labels[h] || h,
      // El separador de 2px en color superficie es lo que hace legible el apilado:
      // dos segmentos contiguos se distinguen por el hueco, no por el borde.
      marker: { color: palette[i % palette.length], line: { color: surface, width: 2 } },
      hovertemplate: '%{x}<br>%{y:,.0f} €<extra>' + (DATA.house_labels[h] || h) + '</extra>'
    };
  });
  const L = baseLayout();
  L.barmode = 'stack';
  L.bargap = 0.3;
  // La leyenda va encima del grafico: con cuatro casas y 300px de alto, colgarla
  // bajo el eje (y:-0.2) la solapaba con las etiquetas de anio.
  // La leyenda horizontal ya sale en el orden del apilado leido de arriba abajo
  // (Lefebre corona la barra y abre la leyenda), asi que no se toca traceorder.
  L.legend = { orientation: 'h', y: 1.02, yanchor: 'bottom', x: 0, xanchor: 'left',
    font: { color: css('--c-fg-soft'), size: 10.5 } };
  // t:52 reserva las dos lineas que ocupa la leyenda: cuatro nombres de casa no
  // caben en una sola fila en la columna estrecha del grid-2.
  L.margin = { l: 56, r: 20, t: 52, b: 40 };
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

// Filtro + totalizador de las tablas de artistas y paises. Se hace sobre el DOM
// ya renderizado: el informe HTML es el producto, no hay servicio al que
// consultar. Los KPIs se recalculan con cada filtro, para que la seleccion
// tenga sus propias cifras y no haya que sumar a ojo las filas visibles.
(function () {
  // Se pliegan los acentos igual que artist_fold() en el pipeline, para que
  // buscar "tapies" encuentre "Antoni Tapies" con acento.
  function fold(s) {
    return (s || '').normalize('NFKD').replace(/[\\u0300-\\u036f]/g, '').toLowerCase().trim();
  }
  // minimumIntegerDigits fuerza el punto de millar tambien en cifras de 4
  // digitos: en espaniol Intl deja "6190" sin separador (es la norma
  // ortografica), pero en una columna de dinero se lee mal.
  const nf = new Intl.NumberFormat('es-ES', { useGrouping: true });
  function miles(v) {
    const s = nf.format(v);
    return /^\\d{4}$/.test(s) ? s.slice(0, 1) + '.' + s.slice(1) : s;
  }
  function money(v) {
    // Se abrevia por encima del millon: en una tarjeta estrecha, 11.135.695 €
    // se corta y deja de leerse. Dos decimales para no perder precision util:
    // 1,1 M€ y 1,15 M€ son 50.000 EUR de diferencia.
    if (v >= 1e6) return nf.format(Math.round(v / 1e4) / 100) + ' M€';
    if (v >= 1e4) return miles(Math.round(v / 1e3)) + ' k€';
    return miles(Math.round(v)) + ' €';
  }
  // El precio medio es un importe UNITARIO: abreviarlo a "11 k€" esconde si son
  // 11.000 o 11.400. Se muestra entero salvo que sea disparatadamente grande.
  function unit(v) {
    return v >= 1e6 ? money(v) : miles(Math.round(v)) + ' €';
  }
  function set(id, text) {
    const el = document.getElementById(id);
    if (el) el.textContent = text;
  }

  function wire(cfg) {
    const table = document.getElementById(cfg.table);
    if (!table) return;
    const rows = Array.from(table.tBodies[0].rows);
    const empty = document.getElementById(cfg.empty);
    const totals = document.getElementById(cfg.totals);
    const inputs = cfg.inputs.map((id) => document.getElementById(id)).filter(Boolean);
    const reset = document.getElementById(cfg.reset);

    function apply() {
      const q = fold(cfg.search ? (document.getElementById(cfg.search) || {}).value : '');
      const sel = cfg.select ? (document.getElementById(cfg.select) || {}).value : '';
      let n = 0, sold = 0, offered = 0, revenue = 0, artists = 0, dated = 0;

      for (const row of rows) {
        const okName = !q || fold(row.dataset.name).includes(q);
        const okSel = !sel || row.dataset.country === sel;
        const visible = okName && okSel;
        row.hidden = !visible;
        if (!visible) continue;
        n++;
        sold += Number(row.dataset.sold) || 0;
        offered += Number(row.dataset.offered) || 0;
        revenue += Number(row.dataset.revenue) || 0;
        artists += Number(row.dataset.artists) || 0;
        // Cuenta de cobertura: basta el anio de nacimiento. Exigir los dos
        // dejaria fuera a los artistas vivos, que no es falta de dato.
        if (row.dataset.birth) dated++;
      }

      // Tasa de venta y precio medio se recalculan sobre los totales, no se
      // promedian los porcentajes de cada fila: promediar tasas da un numero
      // distinto y equivocado cuando las filas tienen tamanios diferentes.
      // count = filas visibles (artistas en una tabla, paises en la otra).
      // artists solo existe en la de paises, donde cada fila agrega varios.
      set(cfg.ids.count, miles(n));
      if (cfg.ids.artists) set(cfg.ids.artists, miles(artists));
      set(cfg.ids.sold, miles(sold));
      set(cfg.ids.offered, offered ? 'de ' + miles(offered) + ' ofertados' : '');
      set(cfg.ids.rate, offered ? (sold / offered * 100).toFixed(1) + '%' : '—');
      set(cfg.ids.revenue, money(revenue));
      if (cfg.ids.avg) set(cfg.ids.avg, sold ? unit(revenue / sold) : '—');
      // Se muestra el recuento y no solo el %: "160 de 200" dice cuantas fichas
      // faltan, que es lo accionable para ampliar el maestro.
      if (cfg.ids.dated) {
        set(cfg.ids.dated, n ? (dated / n * 100).toFixed(0) + '%' : '—');
        set(cfg.ids.datedNote, n ? miles(dated) + ' de ' + miles(n) + ' artistas' : '');
      }

      empty.hidden = n !== 0;
      const filtrado = n !== rows.length;
      totals.classList.toggle('is-filtered', filtrado);
      if (reset) reset.hidden = !filtrado;
    }

    inputs.forEach((el) => el.addEventListener(el.tagName === 'SELECT' ? 'change' : 'input', apply));
    if (reset) {
      reset.addEventListener('click', () => {
        inputs.forEach((el) => { el.value = ''; });
        apply();
      });
    }

    // Las descargas leen las filas visibles en el momento de pulsar, asi que
    // exportan siempre lo que se esta viendo.
    if (cfg.dlView) {
      wireDownloads(
        cfg,
        () => rows.filter((r) => !r.hidden),
        () => inputs.map((el) => el.value).filter(Boolean).join('-'),
      );
    }

    apply();
  }

  // ---- Descargas -------------------------------------------------------
  // Se genera el CSV en el navegador desde lo que hay filtrado, para que lo
  // descargado sea exactamente lo que se esta viendo y se pueda comprobar.

  // Separador ';' y BOM: es lo que abre bien el Excel en espaniol. Con ',' mete
  // toda la fila en una celda, y sin BOM se rompen los acentos.
  function csv(headers, rows) {
    const cell = (v) => {
      if (v === null || v === undefined) return '';
      const s = String(v);
      return /[";\\n\\r]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
    };
    return '\\uFEFF' + [headers, ...rows].map((r) => r.map(cell).join(';')).join('\\r\\n');
  }

  // Aviso propio en vez de alert(): dentro de un iframe (o de un visor
  // embebido) alert() puede estar bloqueado, y si lanza se lleva por delante
  // el resto del manejador de la descarga.
  function say(msg, bad) {
    const box = document.getElementById('toast');
    if (!box) return;
    box.textContent = msg;
    box.className = 'toast show' + (bad ? ' bad' : '');
    clearTimeout(box._t);
    box._t = setTimeout(() => { box.className = 'toast'; }, 5000);
  }

  function save(name, text, filas) {
    let ok = false;
    try {
      const blob = new Blob([text], { type: 'text/csv;charset=utf-8;' });
      if (navigator.msSaveBlob) {
        navigator.msSaveBlob(blob, name);
        ok = true;
      } else {
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        if ('download' in a) {
          a.href = url;
          a.download = name;
          a.style.display = 'none';
          document.body.appendChild(a);
          a.click();
          document.body.removeChild(a);
          ok = true;
        }
        setTimeout(() => URL.revokeObjectURL(url), 4000);
      }
    } catch (e) { ok = false; }

    if (ok) { say('Descargado ' + name + ' · ' + filas + ' filas'); return; }
    say('Tu navegador ha bloqueado la descarga. Abre el fichero HTML '
        + 'directamente en el navegador para guardar el CSV.', true);
  }

  function slug(s) {
    return fold(s).replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') || 'todo';
  }

  // Detalle lote a lote, desempaquetado del formato comprimido que embebe
  // build_chart_data(). Puede no existir si Gold es anterior a esta version.
  const packed = (typeof DATA !== 'undefined' && DATA.lot_details) || null;
  function lotRows() {
    if (!packed || !packed.rows) return [];
    const cols = packed.cols, dic = packed.dict;
    return packed.rows.map((r) => {
      const o = {};
      cols.forEach((c, i) => { o[c] = dic[c] ? dic[c][r[i]] : r[i]; });
      return o;
    });
  }
  const LOTS = lotRows();

  const LOT_HEAD = ['Artista', 'Pais', 'Casa', 'Subasta', 'Fecha', 'Lote',
                    'Titulo', 'Estado', 'Vendido', 'Precio', 'Moneda',
                    'Precio EUR', 'URL'];
  function lotLine(l) {
    return [l.artist_name, l.country, l.house_slug, l.auction_id,
            l.auction_start_date, l.lot_number, l.lot_title, l.status,
            l.sold ? 'si' : 'no', l.price_sold, l.currency, l.price_sold_eur,
            l.lot_url];
  }

  function wireDownloads(cfg, visibleRows, filterLabel) {
    const view = document.getElementById(cfg.dlView);
    const lots = document.getElementById(cfg.dlLots);

    if (view) view.onclick = () => {
      const vis = visibleRows();
      if (!vis.length) { say('No hay filas que descargar con este filtro.', true); return; }
      save(cfg.prefix + '-' + slug(filterLabel()) + '.csv',
           csv(cfg.viewHead, vis.map(cfg.viewLine)), vis.length);
    };

    if (lots) lots.onclick = () => {
      const keys = new Set(visibleRows().map(cfg.matchKey));
      const sel = LOTS.filter((l) => keys.has(cfg.lotKey(l)));
      if (!sel.length) {
        say('No hay detalle de lotes para esta selección: solo se exportan los '
            + 'lotes de artistas con país en el maestro.', true);
        return;
      }
      save(cfg.prefix + '-lotes-' + slug(filterLabel()) + '.csv',
           csv(LOT_HEAD, sel.map(lotLine)), sel.length);
    };
  }

  const artistCfg = {
    table: 'artist-table', empty: 'artist-empty', totals: 'artist-totals',
    search: 'artist-search', select: 'country-filter', reset: 'artist-reset',
    inputs: ['artist-search', 'country-filter'],
    ids: { count: 't-artists', sold: 't-sold', offered: 't-offered',
           rate: 't-rate', revenue: 't-revenue', avg: 't-avg',
           dated: 't-dated', datedNote: 't-dated-note' },
    dlView: 'artist-dl-view', dlLots: 'artist-dl-lots', prefix: 'artistas',
    viewHead: ['Artista', 'Pais nacimiento', 'Nacimiento', 'Muerte',
               'Nacionalidades', 'Lotes vendidos',
               'Lotes ofertados', 'Tasa venta', 'Volumen EUR', 'Record EUR'],
    viewLine: (row) => {
      const cells = row.cells;
      return [cells[1].querySelector('.artist-name').textContent,
              row.dataset.country === '__none__' ? '' : row.dataset.country,
              // Anios en columnas propias y numericas: si viajaran dentro del
              // texto de .house-meta acabarian dentro de "Nacionalidades".
              row.dataset.birth || '', row.dataset.death || '',
              cells[1].querySelector('.house-meta').textContent,
              row.dataset.sold, row.dataset.offered,
              (row.dataset.offered > 0
                ? (row.dataset.sold / row.dataset.offered * 100).toFixed(1)
                : ''),
              row.dataset.revenue, cells[5].textContent.trim()];
    },
    matchKey: (row) => fold(row.dataset.name),
    lotKey: (l) => fold(l.artist_name),
  };

  const countryCfg = {
    table: 'country-table', empty: 'country-empty', totals: 'country-totals',
    search: 'country-search', reset: 'country-reset',
    inputs: ['country-search'],
    ids: { count: 'c-countries', artists: 'c-artists', sold: 'c-sold',
           offered: 'c-offered', rate: 'c-rate', revenue: 'c-revenue' },
    dlView: 'country-dl-view', dlLots: 'country-dl-lots', prefix: 'paises',
    viewHead: ['Pais', 'Artistas', 'Lotes vendidos', 'Lotes ofertados',
               'Tasa venta', 'Volumen EUR', 'Artista destacado'],
    viewLine: (row) => {
      const cells = row.cells;
      return [cells[1].querySelector('.artist-name').textContent,
              row.dataset.artists, row.dataset.sold, row.dataset.offered,
              (row.dataset.offered > 0
                ? (row.dataset.sold / row.dataset.offered * 100).toFixed(1)
                : ''),
              row.dataset.revenue, cells[5].textContent.trim()];
    },
    // El detalle guarda el codigo ISO ("CO"), la tabla muestra el nombre
    // ("Colombia"): se cruza por el codigo, que es la clave real.
    matchKey: (row) => row.dataset.code,
    lotKey: (l) => l.country,
  };

  wire(artistCfg);
  wire(countryCfg);
})();
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
        "lot_details": pack_lot_details(report.get("lot_details") or []),
    }


# Orden de las columnas del detalle empaquetado. El JS lo usa para reconstruir
# cada fila, asi que cambiar el orden aqui obliga a cambiarlo alli.
LOT_DETAIL_COLUMNS = (
    "artist_name", "country", "house_slug", "auction_id", "auction_start_date",
    "lot_number", "lot_title", "status", "sold", "price_sold", "currency",
    "price_sold_eur", "lot_url",
)


def pack_lot_details(details: list[dict]) -> dict:
    """Empaqueta el detalle lote a lote para embeberlo en el HTML.

    Son 13.733 filas: como JSON de objetos ocupan ~4 MB porque repiten el nombre
    de la clave y el del artista en cada una. Aqui van como filas posicionales y
    los valores que se repiten (artista, pais, casa, subasta, moneda, estado)
    como indices a un diccionario. Baja a menos de 1 MB sin perder un dato.
    """
    if not details:
        return {"cols": list(LOT_DETAIL_COLUMNS), "dict": {}, "rows": []}

    # Columnas de baja cardinalidad: merece la pena indexarlas.
    indexed = ("artist_name", "country", "house_slug", "auction_id", "status", "currency")
    tables: dict[str, list] = {c: [] for c in indexed}
    lookup: dict[str, dict] = {c: {} for c in indexed}

    rows = []
    for d in details:
        row = []
        for col in LOT_DETAIL_COLUMNS:
            value = d.get(col)
            if col in indexed:
                if value not in lookup[col]:
                    lookup[col][value] = len(tables[col])
                    tables[col].append(value)
                row.append(lookup[col][value])
            elif col == "sold":
                row.append(1 if value else 0)
            else:
                row.append(value)
        rows.append(row)

    return {"cols": list(LOT_DETAIL_COLUMNS), "dict": tables, "rows": rows}


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
            build_artist_table(
                report.get("by_artist", []), report.get("artist_coverage")
            ),
            build_country_table(report.get("by_country", [])),
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
            "<div class='toast' id='toast' role='status' aria-live='polite'></div>",
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

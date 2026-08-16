#!/usr/bin/env python3
"""
Calculo y textos compartidos por los dos renderizados del informe.

El informe se publica dos veces: analytics_report.html (Plotly, se abre con
doble clic) y artifact_report.html (SVG generado en Python, para publicar como
Artifact bajo CSP estricta). Dibujan distinto a proposito, pero las CIFRAS y los
AVISOS tienen que ser los mismos, y cuando cada uno los calculaba por su cuenta
divergian en silencio: el artifact llego a decir "las tres casas" con cuatro en
produccion, a imprimir los codigos ISO crudos ("tb. FR, IT") donde el HTML local
escribia "tb. Francia, Italia", y los dos llevaban el corte de 3 lotes escrito a
mano en el texto, asi que cambiar la constante los dejaba a ambos mintiendo.

Aqui vive solo el calculo puro y el texto. Ni HTML ni SVG: el markup es de cada
renderer, porque tienen sistemas de diseno distintos por decision.

Regla heredada del resto del pipeline: nada se inventa. Un artista sin pais no
recibe el de su casa de subastas, una celda sin lotes no se pinta como una celda
de volumen cero, y un pais fuera del top no se descarta, se agrupa.
"""

from __future__ import annotations

from collections import defaultdict

from pipelines.gold.build_insights import MIN_LOTS_FOR_ARTIST_RANK
from pipelines.shared.artist_master import country_es
from pipelines.shared.fx import fx_as_of

# Pais donde OCURRE la subasta, para decidir si un artista que vende en varias
# casas esta cruzando mercados o repitiendo en el mismo. NO es la nacionalidad
# del artista: esa sale del maestro. Duplica HOUSE_COUNTRY de render_html.py a
# proposito para no importar el renderer desde aqui (la dependencia va al reves).
_HOUSE_MARKET = {
    "bogota_auctions": "CO",
    "duran_subastas": "ES",
    "zorrilla_subastas": "UY",
    "lefebre_subastas": "CO",
}

# Cortes del Pareto. Son los que el informe cita en texto, asi que viven aqui y
# no en cada renderer.
PARETO_CUTS = (10, 25, 50, 100, 200, 500)

# Se agrupa la cola del mapa de calor a partir de este numero de paises.
HEATMAP_TOP_N = 12


# --------------------------------------------------------------------------
# Concentracion (Pareto)
# --------------------------------------------------------------------------

def pareto_points(artists: list[dict], cuts: tuple[int, ...] = PARETO_CUTS) -> list[dict]:
    """Fraccion acumulada del volumen que se llevan los N primeros artistas.

    `artists` llega ya ordenado por revenue_eur descendente desde build_insights,
    pero se reordena aqui igualmente: el calculo no puede depender de que quien
    llame haya conservado el orden.
    """
    rows = sorted(artists, key=lambda a: -(a.get("revenue_eur") or 0))
    total = sum(a.get("revenue_eur") or 0 for a in rows)
    if not rows or not total:
        return []

    # El ultimo corte es siempre el ranking entero: sin el, la curva termina
    # antes del 100% y parece que falta dinero.
    ns = sorted({n for n in cuts if n < len(rows)} | {len(rows)})
    out, acc, idx = [], 0.0, 0
    for n in ns:
        while idx < n:
            acc += rows[idx].get("revenue_eur") or 0
            idx += 1
        out.append(
            {
                "n": n,
                "revenue_eur": round(acc, 2),
                "share_pct": round(acc / total * 100, 1),
            }
        )
    return out


# --------------------------------------------------------------------------
# Scatter: vender caro contra vender mucho
# --------------------------------------------------------------------------

def scatter_points(artists: list[dict], top_countries: int = 5) -> list[dict]:
    """Un punto por artista: lotes vendidos (x), precio medio (y), volumen (area).

    Los dos ejes van en escala logaritmica en el renderer, asi que aqui se
    descarta lo que no tiene logaritmo: sin ventas o sin precio medio no hay
    punto que dibujar. Los artistas sin pais SI entran (son 863 de 1.521): se
    marcan como grupo propio, nunca se les asigna el pais de la casa.
    """
    revenue_by_country: dict[str, float] = defaultdict(float)
    for a in artists:
        if a.get("country_birth"):
            revenue_by_country[a["country_birth"]] += a.get("revenue_eur") or 0
    top = {
        c
        for c, _ in sorted(revenue_by_country.items(), key=lambda kv: -kv[1])[:top_countries]
    }

    out = []
    for a in artists:
        sold = a.get("lots_sold") or 0
        avg = a.get("avg_sold_price_eur")
        if sold <= 0 or not avg or avg <= 0:
            continue
        code = a.get("country_birth")
        out.append(
            {
                "name": a.get("artist_name"),
                "key": a.get("artist_key"),
                "country": code,
                "country_es": a.get("country_birth_es") or country_es(code),
                # Grupo de color: top N, "otros", o sin pais. Agrupar no es
                # descartar; el punto se dibuja en los tres casos.
                "group": code if code in top else ("__other__" if code else "__none__"),
                "x": sold,
                "y": avg,
                "size": a.get("revenue_eur") or 0,
                "offered": a.get("lots_offered") or 0,
                "houses": a.get("houses") or [],
                "house_kind": multi_house_kind(a.get("houses") or []),
            }
        )
    # De mayor a menor volumen: las burbujas grandes se dibujan primero y las
    # pequenias encima, para que ninguna quede tapada del todo.
    out.sort(key=lambda p: -p["size"])
    return out


# --------------------------------------------------------------------------
# Mapa de calor pais x anio
# --------------------------------------------------------------------------

def heatmap_matrix(country_year: list[dict], top_n: int = HEATMAP_TOP_N) -> dict:
    """Matriz densa pais x anio a partir de las celdas dispersas de Gold.

    Tres decisiones que el renderer no puede tomar por su cuenta:
      - "unknown" no es un anio: sale del eje temporal, pero su volumen se
        devuelve aparte para que el informe pueda declararlo.
      - La fila sin pais no ocupa carril (no es un pais), y tambien se declara.
      - Los paises fuera del top se agrupan en "Resto", nunca se pierden: hay un
        test que comprueba que top_n + resto suma exactamente el total.
    """
    # El eje es temporal y continuo: un anio sin actividad tiene que verse como
    # hueco, no desaparecer. Si solo se listaran los anios presentes, 2020 y
    # 2022 quedarian pegados y el mapa insinuaria una continuidad que no hubo.
    present = {int(r["year"]) for r in country_year if str(r.get("year", "")).isdigit()}
    years = [str(y) for y in range(min(present), max(present) + 1)] if present else []

    unknown_year_revenue = sum(
        r.get("revenue_eur") or 0
        for r in country_year
        if not str(r.get("year", "")).isdigit()
    )
    no_country_revenue = sum(
        r.get("revenue_eur") or 0 for r in country_year if not r.get("country")
    )

    # Solo filas con pais Y anio utilizable entran en la matriz.
    usable = [
        r
        for r in country_year
        if r.get("country") and str(r.get("year", "")).isdigit()
    ]

    revenue_by_country: dict[str, float] = defaultdict(float)
    for r in usable:
        revenue_by_country[r["country"]] += r.get("revenue_eur") or 0
    ranked = sorted(revenue_by_country.items(), key=lambda kv: -kv[1])
    top_codes = [c for c, _ in ranked[:top_n]]
    rest_codes = {c for c, _ in ranked[top_n:]}

    labels = {r["country"]: r.get("country_es") for r in usable}
    cells: dict[tuple, dict] = {}
    for r in usable:
        bucket = "__rest__" if r["country"] in rest_codes else r["country"]
        cell = cells.setdefault(
            (bucket, r["year"]),
            {"revenue_eur": 0.0, "lots_offered": 0, "lots_sold": 0,
             "inferred": False, "houses": set()},
        )
        cell["revenue_eur"] += r.get("revenue_eur") or 0
        cell["lots_offered"] += r.get("lots_offered") or 0
        cell["lots_sold"] += r.get("lots_sold") or 0
        # Basta que una celda agregada traiga un anio inferido para marcarla.
        if r.get("year_method") == "auction_id":
            cell["inferred"] = True
        cell["houses"].update(h for h in (r.get("houses") or []) if h)

    def _row(bucket: str, label: str, artists_note: str | None = None) -> dict:
        row_cells = []
        for y in years:
            c = cells.get((bucket, y))
            row_cells.append(
                {
                    "year": y,
                    # None, no 0: "no hubo lote" y "hubo lote sin venta" son
                    # cosas distintas y no pueden pintarse igual.
                    "revenue_eur": round(c["revenue_eur"], 2) if c else None,
                    "lots_offered": c["lots_offered"] if c else 0,
                    "lots_sold": c["lots_sold"] if c else 0,
                    "inferred": bool(c and c["inferred"]),
                    "houses": sorted(c["houses"]) if c else [],
                }
            )
        return {
            "country": None if bucket == "__rest__" else bucket,
            "label": label,
            "is_rest": bucket == "__rest__",
            "revenue_eur": round(revenue_total(row_cells), 2),
            "cells": row_cells,
            "note": artists_note,
        }

    rows = [_row(c, labels.get(c) or c) for c in top_codes]
    if rest_codes:
        rows.append(_row("__rest__", f"Resto ({len(rest_codes)} países)"))

    all_values = [
        c["revenue_eur"] for row in rows for c in row["cells"] if c["revenue_eur"]
    ]
    return {
        "years": years,
        "rows": rows,
        "max_revenue_eur": max(all_values) if all_values else 0,
        "min_revenue_eur": min(all_values) if all_values else 0,
        "unknown_year_revenue_eur": round(unknown_year_revenue, 2),
        "no_country_revenue_eur": round(no_country_revenue, 2),
        "has_inferred": any(c["inferred"] for row in rows for c in row["cells"]),
    }


def revenue_total(cells: list[dict]) -> float:
    return sum(c["revenue_eur"] or 0 for c in cells)


# --------------------------------------------------------------------------
# Generaciones
# --------------------------------------------------------------------------

def generation_bars(generations: list[dict]) -> list[dict]:
    """Barras por decada de nacimiento, con la fila sin fecha marcada y al final.

    La fila sentinela es la mayor del conjunto (986 artistas, 5,56 M EUR) y no
    es una decada: si se dibujara como una mas, el grafico diria que existe una
    generacion enorme que en realidad es "no sabemos cuando nacieron".
    """
    bars = []
    for g in generations:
        bars.append(
            {
                "decade": g.get("decade"),
                "label": g.get("decade_label"),
                "revenue_eur": g.get("revenue_eur") or 0,
                "artists": g.get("artists") or 0,
                "lots_sold": g.get("lots_sold") or 0,
                "alive": g.get("alive") or 0,
                "top_artist": g.get("top_artist"),
                "is_sentinel": g.get("decade") is None,
            }
        )
    bars.sort(key=lambda b: (b["is_sentinel"], b["decade"] or 0))
    return bars


# --------------------------------------------------------------------------
# Casas de un artista
# --------------------------------------------------------------------------

def multi_house_kind(houses: list[str]) -> str:
    """'single' | 'same_market' | 'cross_market' segun el PAIS de las casas.

    De los 179 artistas que venden en mas de una casa, 104 lo hacen en Bogota y
    Lefebre, que son las dos colombianas: eso no es cruzar mercados, es repetir
    en el mismo. Los que de verdad cruzan Espania<->Colombia son 46. Contarlos
    por numero de casas en vez de por pais multiplicaria el dato por cuatro.
    """
    real = [h for h in houses if h]
    if len(real) < 2:
        return "single"
    markets = {_HOUSE_MARKET.get(h) for h in real}
    markets.discard(None)
    return "cross_market" if len(markets) > 1 else "same_market"


def nationalities_es(codes: list[str]) -> str:
    """Codigos ISO -> nombres en espaniol, separados por coma.

    Un codigo que no este en _countries.yaml se muestra tal cual: perder el dato
    seria peor que ensenar el codigo.
    """
    return ", ".join(country_es(c) or c for c in (codes or []))


# --------------------------------------------------------------------------
# Avisos. Un solo texto para los dos informes.
# --------------------------------------------------------------------------

CAVEAT_MIN_LOTS = (
    f"Entra en el ranking todo artista con al menos {MIN_LOTS_FOR_ARTIST_RANK} lote vendido: "
    "no se recorta la cola, porque una sola pieza puede facturar más que veinte de otro autor. "
    "Eso sí, <strong>el “precio medio” de quien tiene una o dos ventas no es una media</strong>, "
    "es el precio de esas piezas: para comparar precios medios, mírese la columna de lotes. "
    "Se excluyen escuelas, talleres y atribuciones (“Escuela Española”, "
    "“Atribuido a…”), que agrupan cientos de lotes de autoría distinta."
)

CAVEAT_COUNTRY_IS_HOUSE = (
    "El país es el de <strong>nacimiento del artista</strong>, según el maestro, no el de "
    "la casa. Ojo al comparar: solo 66 de unos 15.000 nombres coinciden entre Durán "
    "(mercado español) y Bogotá (colombiano), así que la fila de España es casi Durán y la "
    "de Colombia casi Bogotá + Lefebre. Esto mide, en buena medida, dos mercados que "
    "apenas se tocan."
)

CAVEAT_FX_TIMESERIES = (
    f"Los importes se convierten a EUR con una tasa única de {fx_as_of()} aplicada a todo "
    "el periodo. <strong>Las series en moneda distinta del euro están distorsionadas por "
    "eso</strong>: el peso colombiano no valía en 2014 lo que vale hoy, y aquí se trata "
    "como si sí. Comparar años dentro de una misma fila en COP o USD no es válido; "
    "comparar países dentro de un mismo año, sí."
)

CAVEAT_PARETO_SCOPE = (
    "Los porcentajes son sobre el volumen de los artistas rankeados, "
    "<strong>no sobre el total del mercado</strong>: quedan fuera los lotes sin autor, las "
    "escuelas y atribuciones, y las joyas de Zorrilla, que no llevan artista. La cola sí "
    "entra entera, así que la curva no está recortada por abajo."
)

CAVEAT_SCATTER_LOWN = (
    "Los dos ejes van en escala logarítmica: sin ella, 9 de cada 10 artistas se solapan en "
    "una esquina. <strong>El precio medio de un artista con una venta no es comparable con "
    "el de uno con 200</strong>: cuanto más a la izquierda está un punto, más ruido tiene "
    "su altura. Con una sola venta, la altura <em>es</em> el precio de esa pieza, no una media."
)

CAVEAT_GENERATIONS_COVERAGE = (
    "La década sale del año de nacimiento del maestro de artistas, que no lo tiene para "
    "todos. La barra “sin fecha de nacimiento” son los artistas sin ficha datada y "
    "<strong>no se reparte entre las décadas</strong>: repartirla sería inventar. Por eso "
    "es la más alta del gráfico, y mide desconocimiento, no una generación."
)


def country_metrics_caveat(lots_below_cutoff: int) -> str:
    """Aviso de que los totales por pais y el ranking no cuadran, con la cifra.

    Antes la diferencia era sobre todo el corte de 3 ventas. Con el corte en 1
    lo que queda son los lotes con autoria que NO llegan al ranking por otras
    razones (sin venta registrada, o el artista no resuelve a una identidad).
    Sin declararlo parece un error de suma.
    """
    return (
        f"Los totales por país incluyen a todos los artistas con autoría, también los "
        f"{lots_below_cutoff:,.0f} lotes que no llegan a la tabla de artistas (sin precio "
        "de venta registrado, o con un nombre que no resuelve a una identidad concreta). "
        "Es la razón de que la suma de la tabla no cuadre con estas cifras."
    ).replace(",", ".")

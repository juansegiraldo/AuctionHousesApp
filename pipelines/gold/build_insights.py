#!/usr/bin/env python3
"""
Capa Gold: agregados analiticos "de segundo nivel" a partir de Silver.

build_gold.py cubre los agregados basicos (casa, subasta, anio). Este modulo
anade las dimensiones que el informe necesita para contar una historia y que
antes se quedaban sin explotar en Silver/enrichments: artistas, categorias,
fiabilidad de la estimacion, distribucion de precios y estacionalidad.

Reglas que se respetan aqui (ver CLAUDE.md, son load-bearing):
  - NUNCA se suman precios entre casas en moneda nativa. Todo agregado
    cross-house va en EUR via pipelines.shared.fx.to_eur().
  - "Vendido" se decide con pipelines.shared.schema.is_sold(), no con
    "tiene precio", salvo donde la casa no publica estado.
  - El anio se extrae con extract_year(), que es especifico por casa.

Salida: data/gold/agg_*.jsonl (un fichero por dimension).
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

import orjson

from pipelines.shared.artist_key import artist_fold, attribution_type
from pipelines.shared.artist_master import artist_years, country_es, format_life_years
from pipelines.shared.fx import to_eur
from pipelines.shared.schema import extract_year, is_sold

ROOT = Path(__file__).resolve().parents[2]
SILVER_ROOT = ROOT / "data" / "silver"
ENRICH_ROOT = ROOT / "data" / "enrichments"
GOLD_ROOT = ROOT / "data" / "gold"

# Por debajo de este numero de lotes vendidos, un "precio medio" de artista es
# ruido estadistico. El informe muestra el corte para que no se lea como ranking.
MIN_LOTS_FOR_ARTIST_RANK = 3

# Etiqueta de la fila sin decada. Solo 535 de los 1.521 artistas del ranking
# tienen fecha de nacimiento en el maestro, asi que los otros 986 necesitan una
# fila propia: repartirlos entre decadas seria inventar, y ocultarlos haria que
# el grafico pareciera cubrir todo el ranking cuando cubre un tercio.
NO_BIRTH_YEAR_LABEL = "Sin fecha de nacimiento"


def birth_decade(year: int | None) -> int | None:
    """Decada de nacimiento (1874 -> 1870). None si no consta la fecha."""
    return None if year is None else (year // 10) * 10


def load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as f:
        for r in rows:
            f.write(orjson.dumps(r, option=orjson.OPT_APPEND_NEWLINE))


def is_noise_artist(name: str) -> bool:
    """Escuelas/atribuciones/anonimos: agregados, no autores.

    La logica vive ahora en pipelines/shared/artist_key.attribution_type(), que
    la aplica Silver una sola vez para todo el pipeline. Antes esto era un match
    de prefijo sobre el nombre en minusculas SIN plegar acentos, asi que la
    lista tenia que llevar "circulo de" y "circulo de" acentuado por separado y
    cualquier variante nueva se colaba en el ranking.

    Se conserva la funcion porque sigue siendo el modo de decidirlo cuando se
    lee un Silver antiguo, anterior a artist_resolve.py.
    """
    return attribution_type(name) != "autor"


def artist_identity(row: dict) -> tuple[str | None, str]:
    """(clave de agrupacion, nombre a mostrar) para un lote de Silver.

    Agrupa por artist_id del maestro cuando existe y, si no, por el fold. Antes
    se agrupaba por el NOMBRE CRUDO, y por eso las 4 grafias de "Agustin Ubeda"
    (368 lotes) salian como 4 filas distintas del ranking.

    Degrada sin fallar si el Silver no paso todavia por artist_resolve.py.
    """
    raw = (row.get("artist_name") or "").strip()
    key = row.get("artist_id") or row.get("artist_fold") or artist_fold(raw)
    display = row.get("artist_display_name") or raw or None
    return key, display


def load_categories() -> dict[str, str]:
    """dedupe_key -> categoria (del enrichment category_tag)."""
    out = {}
    for r in load_jsonl(ENRICH_ROOT / "category_tags.jsonl"):
        key = r.get("dedupe_key")
        if key:
            out[key] = r.get("category") or "other"
    return out


def build_insights() -> dict:
    lots_path = SILVER_ROOT / "lots.jsonl"
    if not lots_path.exists():
        raise FileNotFoundError(
            f"Silver no encontrado: {lots_path}. Ejecuta primero pipelines/silver/build_silver.py"
        )

    key2cat = load_categories()

    artists: dict[str, dict] = defaultdict(
        lambda: {
            "artist_name": None,
            "artist_id": None,
            "lots_offered": 0,
            "lots_sold": 0,
            "revenue_eur": 0.0,
            "top_price_eur": 0.0,
            "top_lot_title": None,
            "top_lot_url": None,
            "country_birth": None,
            "nationalities": set(),
            "resolution": None,
            "houses": set(),
            # Anios con al menos un lote, para el rango de actividad de la ficha.
            "years": set(),
        }
    )
    # Agregado por pais de nacimiento del artista. Cuenta un lote una sola vez.
    countries: dict[str | None, dict] = defaultdict(
        lambda: {
            "lots_offered": 0,
            "lots_sold": 0,
            "revenue_eur": 0.0,
            "artists": set(),
            "houses": set(),
            "top_artist": None,
            "top_artist_revenue": 0.0,
        }
    )
    # Pais de nacimiento x anio de subasta: la matriz del mapa de calor. El anio
    # sale de extract_year(), que entiende el formato de cada casa; un slice de
    # los 4 primeros caracteres solo leeria el ISO de Bogota y tiraria en
    # silencio los 40.442 lotes de Duran ("Octubre 2014").
    country_year: dict[tuple, dict] = defaultdict(
        lambda: {"lots_offered": 0, "lots_sold": 0, "revenue_eur": 0.0, "houses": set()}
    )
    cats: dict[str, dict] = defaultdict(
        lambda: {"lots_offered": 0, "lots_sold": 0, "revenue_eur": 0.0}
    )
    # Detalle lote a lote de los artistas con identidad, para que el informe
    # pueda exportar el drill-down y cualquiera audite de donde sale cada euro
    # en vez de tener que fiarse del agregado. Se agrupa por artista porque el
    # corte del ranking no se conoce hasta despues de leer todo el Silver.
    lots_by_artist: dict[str, list[dict]] = defaultdict(list)
    # Fiabilidad de la estimacion: solo tiene sentido con estimacion Y precio.
    est = {"below": 0, "within": 0, "above": 0}
    est_by_house: dict[str, dict] = defaultdict(
        lambda: {"below": 0, "within": 0, "above": 0}
    )
    months: dict[str, dict] = defaultdict(
        lambda: {"lots_offered": 0, "lots_sold": 0, "revenue_eur": 0.0}
    )
    prices_eur: list[float] = []
    # Distribucion por tramo de precio: donde esta el volumen vs donde el dinero.
    bands = [
        ("0-100", 0, 100),
        ("100-500", 100, 500),
        ("500-1k", 500, 1_000),
        ("1k-5k", 1_000, 5_000),
        ("5k-25k", 5_000, 25_000),
        ("25k+", 25_000, float("inf")),
    ]
    band_stats: dict[str, dict] = {
        b[0]: {"lots": 0, "revenue_eur": 0.0} for b in bands
    }

    total = 0
    with open(lots_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            total += 1

            house = r.get("house_slug")
            currency = r.get("currency") or "COP"
            price = r.get("price_sold")
            sold = is_sold(r.get("status"), price)
            # to_eur devuelve None si la moneda no tiene tasa: no lo tratamos
            # como euros, se queda fuera de los agregados monetarios.
            eur = to_eur(price, currency) if (sold and price) else None

            # --- categorias ---
            cat = key2cat.get(r.get("dedupe_key")) or "other"
            c = cats[cat]
            c["lots_offered"] += 1
            if sold:
                c["lots_sold"] += 1
                if eur:
                    c["revenue_eur"] += eur

            # --- artistas ---
            # attribution_type lo escribe Silver (artist_resolve.py). Si el
            # Silver es anterior a esa etapa, se recalcula al vuelo.
            attribution = r.get("attribution_type") or attribution_type(
                r.get("artist_name")
            )
            key, display = artist_identity(r)
            year, year_method = extract_year(
                r.get("auction_start_date"), r.get("auction_id")
            )
            if attribution == "autor" and key:
                a = artists[key]
                a["lots_offered"] += 1
                a["houses"].add(house)
                a["years"].add(year)
                if not a["artist_name"]:
                    a["artist_name"] = display
                # Identidad y pais: gana el primer valor NO nulo, no el primer
                # lote visto. Cuando estas asignaciones vivian dentro del
                # `if not a["artist_name"]` de arriba, un artista cuyo primer
                # lote llegara sin resolver se quedaba sin pais para siempre
                # aunque los siguientes lo trajeran.
                if a["artist_id"] is None:
                    a["artist_id"] = r.get("artist_id")
                if a["resolution"] is None:
                    a["resolution"] = r.get("artist_resolution")
                # El pais sale SOLO del maestro (artist_country_birth), nunca
                # del texto libre artist_country de la casa: ese campo esta
                # poblado en el 2% de los lotes y mezcla ciudades con paises.
                if a["country_birth"] is None:
                    a["country_birth"] = r.get("artist_country_birth")
                a["nationalities"].update(r.get("artist_nationalities") or [])
                if sold:
                    a["lots_sold"] += 1
                    if eur:
                        a["revenue_eur"] += eur
                        if eur > a["top_price_eur"]:
                            a["top_price_eur"] = eur
                            a["top_lot_title"] = r.get("lot_title")
                            a["top_lot_url"] = r.get("lot_url")

                # --- paises ---
                # Se agrupa por pais de NACIMIENTO para que cada lote cuente una
                # sola vez. Un agregado por nacionalidad seria no aditivo (un
                # artista con doble nacionalidad sumaria en dos filas).
                c_row = countries[r.get("artist_country_birth")]
                c_row["lots_offered"] += 1
                c_row["artists"].add(key)
                c_row["houses"].add(house)
                if sold:
                    c_row["lots_sold"] += 1
                    if eur:
                        c_row["revenue_eur"] += eur

                # --- pais x anio, para el mapa de calor ---
                # Mismo grano que el agregado de paises de arriba, partido por
                # anio. Se acumula aqui dentro para que las dos vistas cuadren
                # siempre: si una filtrase algo que la otra no, el mapa dejaria
                # de sumar lo que dice la tabla que tiene justo debajo.
                cy = country_year[(r.get("artist_country_birth"), year, year_method)]
                cy["lots_offered"] += 1
                cy["houses"].add(house)
                if sold:
                    cy["lots_sold"] += 1
                    if eur:
                        cy["revenue_eur"] += eur

                # --- detalle para el drill-down ---
                # Antes solo entraban los lotes con artist_country_birth, y eso
                # dejaba a los 863 artistas fold_only sin un solo lote que
                # ensenar en su ficha aunque el ranking dijera que habian
                # vendido 40 veces. Ahora entra todo artista que pase el corte
                # del ranking, con pais o sin el; el corte se mantiene porque
                # sin el son ~39.500 filas embebidas en cada informe.
                lots_by_artist[key].append(
                    {
                        "artist_key": key,
                        "artist_name": display,
                        "country": r.get("artist_country_birth"),
                        "house_slug": house,
                        "auction_id": r.get("auction_id"),
                        "auction_start_date": r.get("auction_start_date"),
                        "lot_number": r.get("lot_number"),
                        "lot_title": r.get("lot_title"),
                        "status": r.get("status"),
                        "sold": sold,
                        # Nativo Y en EUR: el nativo es exacto, el EUR es el
                        # unico comparable entre casas. Nunca se suman los
                        # nativos entre monedas distintas.
                        "price_sold": price,
                        "currency": currency,
                        "price_sold_eur": eur,
                        "lot_url": r.get("lot_url"),
                    }
                )

            # --- fiabilidad de estimacion ---
            emin, emax = r.get("price_estimate_min"), r.get("price_estimate_max")
            if sold and price and emin and emax:
                if price < emin:
                    bucket = "below"
                elif price > emax:
                    bucket = "above"
                else:
                    bucket = "within"
                est[bucket] += 1
                est_by_house[house][bucket] += 1

            # --- distribucion de precio ---
            if eur and eur > 0:
                prices_eur.append(eur)
                for label, lo, hi in bands:
                    if lo <= eur < hi:
                        band_stats[label]["lots"] += 1
                        band_stats[label]["revenue_eur"] += eur
                        break

            # --- estacionalidad: solo con fecha real, no con anio inferido ---
            start = r.get("auction_start_date") or ""
            if len(start) >= 7 and start[:4].isdigit() and start[4] == "-":
                month = start[5:7]
                m = months[month]
                m["lots_offered"] += 1
                if sold:
                    m["lots_sold"] += 1
                    if eur:
                        m["revenue_eur"] += eur

    # ---------- serializacion ----------
    artist_rows = []
    for key, a in artists.items():
        if a["lots_sold"] < MIN_LOTS_FOR_ARTIST_RANK:
            continue
        # Los anios salen del maestro por artist_id, igual que el pais. Un
        # artista en fold_only no tiene id, asi que se queda sin fechas: no se
        # deducen del texto del lote (artist_raw viene truncado a 60 chars).
        years = artist_years(a["artist_id"])
        # Rango de actividad en subasta. Es del LOTE (cuando se vendio), no del
        # artista: nada que ver con birth_year/death_year, que salen del maestro.
        # "unknown" no es un anio, asi que no puede marcar ni el primero ni el
        # ultimo; sin descartarlo, un lote sin fecha fiable ordenaria al final.
        active = sorted(y for y in a["years"] if y.isdigit())
        artist_rows.append(
            {
                "artist_name": a["artist_name"] or key,
                "artist_id": a["artist_id"],
                "artist_key": key,
                "birth_year": years["birth_year"],
                "death_year": years["death_year"],
                "life_years": format_life_years(
                    years["birth_year"], years["death_year"]
                ),
                "first_year": active[0] if active else None,
                "last_year": active[-1] if active else None,
                "years_active": len(active),
                # DEPRECADA: duplicado exacto de country_birth, conservada por
                # compatibilidad con consumidores externos del JSONL. No leerla
                # en codigo nuevo; los dos renderers ya usan country_birth.
                "country": a["country_birth"],
                "country_birth": a["country_birth"],
                "country_birth_es": country_es(a["country_birth"]),
                "nationalities": sorted(a["nationalities"]),
                "resolution": a["resolution"],
                "houses": sorted(h for h in a["houses"] if h),
                "lots_offered": a["lots_offered"],
                "lots_sold": a["lots_sold"],
                "sell_through_rate": round(a["lots_sold"] / a["lots_offered"], 4)
                if a["lots_offered"]
                else None,
                "revenue_eur": round(a["revenue_eur"], 2),
                "avg_sold_price_eur": round(a["revenue_eur"] / a["lots_sold"], 2)
                if a["lots_sold"]
                else None,
                "top_price_eur": round(a["top_price_eur"], 2),
                "top_lot_title": a["top_lot_title"],
                "top_lot_url": a["top_lot_url"],
            }
        )
    artist_rows.sort(key=lambda r: -r["revenue_eur"])

    # El artista top de cada pais sale del ranking ya ordenado por ingresos.
    top_artist_by_country: dict[str | None, str] = {}
    for row in artist_rows:
        top_artist_by_country.setdefault(row["country_birth"], row["artist_name"])

    country_rows = []
    for code, c in countries.items():
        country_rows.append(
            {
                "country": code,
                "country_es": country_es(code),
                "artists": len(c["artists"]),
                "lots_offered": c["lots_offered"],
                "lots_sold": c["lots_sold"],
                "sell_through_rate": round(c["lots_sold"] / c["lots_offered"], 4)
                if c["lots_offered"]
                else None,
                "revenue_eur": round(c["revenue_eur"], 2),
                "avg_sold_price_eur": round(c["revenue_eur"] / c["lots_sold"], 2)
                if c["lots_sold"]
                else None,
                "top_artist": top_artist_by_country.get(code),
                "houses": sorted(h for h in c["houses"] if h),
            }
        )
    # Los no resueltos (country=None) van al final, pero NO se ocultan: taparlos
    # haria que el informe pareciera completo cuando no lo esta.
    country_rows.sort(key=lambda r: (r["country"] is None, -r["revenue_eur"]))

    country_year_rows = [
        {
            "country": code,
            "country_es": country_es(code),
            "year": year,
            # El metodo viaja hasta el informe para que la celda pueda marcar
            # el anio que se dedujo del slug en vez de leerse de una fecha.
            "year_method": method,
            "lots_offered": v["lots_offered"],
            "lots_sold": v["lots_sold"],
            "revenue_eur": round(v["revenue_eur"], 2),
            "houses": sorted(h for h in v["houses"] if h),
        }
        for (code, year, method), v in country_year.items()
    ]
    country_year_rows.sort(key=lambda r: (r["country"] is None, r["country"] or "", r["year"]))

    # --- generaciones: decada de nacimiento del artista ---
    # Se construye sobre artist_rows (el ranking ya filtrado), no sobre un
    # acumulador propio, para que los totales cuadren con la tabla por
    # definicion y no por coincidencia.
    gens: dict[int | None, dict] = defaultdict(
        lambda: {
            "artists": 0,
            "alive": 0,
            "lots_offered": 0,
            "lots_sold": 0,
            "revenue_eur": 0.0,
            "top_artist": None,
        }
    )
    for row in artist_rows:
        g = gens[birth_decade(row["birth_year"])]
        g["artists"] += 1
        # Sin death_year: vivo, o muerto sin fecha registrada. La etiqueta del
        # informe lo dice asi; afirmar "vivo" seria pasarse de lo que se sabe.
        if row["birth_year"] and not row["death_year"]:
            g["alive"] += 1
        g["lots_offered"] += row["lots_offered"]
        g["lots_sold"] += row["lots_sold"]
        g["revenue_eur"] += row["revenue_eur"]
        # artist_rows ya viene ordenado por ingresos, asi que el primero que
        # cae en cada decada es el de mayor volumen.
        if g["top_artist"] is None:
            g["top_artist"] = row["artist_name"]

    generation_rows = [
        {
            "decade": dec,
            "decade_label": f"{dec}s" if dec is not None else NO_BIRTH_YEAR_LABEL,
            "artists": v["artists"],
            "alive": v["alive"],
            "lots_offered": v["lots_offered"],
            "lots_sold": v["lots_sold"],
            "revenue_eur": round(v["revenue_eur"], 2),
            "avg_sold_price_eur": round(v["revenue_eur"] / v["lots_sold"], 2)
            if v["lots_sold"]
            else None,
            "top_artist": v["top_artist"],
        }
        for dec, v in gens.items()
    ]
    # La fila sin decada va al final, visible, igual que la de pais desconocido.
    generation_rows.sort(key=lambda r: (r["decade"] is None, r["decade"] or 0))

    cat_rows = [
        {
            "category": k,
            "lots_offered": v["lots_offered"],
            "lots_sold": v["lots_sold"],
            "sell_through_rate": round(v["lots_sold"] / v["lots_offered"], 4)
            if v["lots_offered"]
            else None,
            "revenue_eur": round(v["revenue_eur"], 2),
            "avg_sold_price_eur": round(v["revenue_eur"] / v["lots_sold"], 2)
            if v["lots_sold"]
            else None,
        }
        for k, v in cats.items()
    ]
    cat_rows.sort(key=lambda r: -r["revenue_eur"])

    month_rows = [
        {
            "month": k,
            "lots_offered": v["lots_offered"],
            "lots_sold": v["lots_sold"],
            "revenue_eur": round(v["revenue_eur"], 2),
        }
        for k, v in sorted(months.items())
    ]

    prices_eur.sort()

    def pct(p: float):
        if not prices_eur:
            return None
        idx = min(int(p * len(prices_eur)), len(prices_eur) - 1)
        return round(prices_eur[idx], 2)

    band_rows = [
        {
            "band": label,
            "lots": band_stats[label]["lots"],
            "revenue_eur": round(band_stats[label]["revenue_eur"], 2),
        }
        for label, _, _ in bands
    ]

    est_total = sum(est.values())
    price_dist = {
        "count": len(prices_eur),
        "p25": pct(0.25),
        "median": pct(0.50),
        "p75": pct(0.75),
        "p90": pct(0.90),
        "p95": pct(0.95),
        "p99": pct(0.99),
        "max": round(prices_eur[-1], 2) if prices_eur else None,
        "bands": band_rows,
    }
    estimate_accuracy = {
        "total_with_estimate": est_total,
        "below": est["below"],
        "within": est["within"],
        "above": est["above"],
        "pct_above": round(est["above"] / est_total * 100, 1) if est_total else None,
        "pct_within": round(est["within"] / est_total * 100, 1) if est_total else None,
        "pct_below": round(est["below"] / est_total * 100, 1) if est_total else None,
        "by_house": [
            {
                "house_slug": h,
                "below": v["below"],
                "within": v["within"],
                "above": v["above"],
                "total": sum(v.values()),
            }
            for h, v in est_by_house.items()
        ],
    }

    # El detalle se vuelca solo para los artistas que entraron en el ranking, y
    # se ordena como el (artista por ingresos, y dentro por precio descendente)
    # para que el CSV exportado se lea sin reordenar.
    orden = {row["artist_key"]: i for i, row in enumerate(artist_rows)}
    lot_details = [d for k in orden for d in lots_by_artist.get(k, [])]
    lot_details.sort(
        key=lambda d: (
            orden.get(d["artist_key"], len(orden)),
            -(d["price_sold_eur"] or 0),
        )
    )

    write_jsonl(GOLD_ROOT / "agg_artist_metrics.jsonl", artist_rows)
    write_jsonl(GOLD_ROOT / "agg_country_metrics.jsonl", country_rows)
    write_jsonl(GOLD_ROOT / "agg_country_year_metrics.jsonl", country_year_rows)
    write_jsonl(GOLD_ROOT / "agg_artist_generation_metrics.jsonl", generation_rows)
    write_jsonl(GOLD_ROOT / "lot_details.jsonl", lot_details)
    write_jsonl(GOLD_ROOT / "agg_category_metrics.jsonl", cat_rows)
    write_jsonl(GOLD_ROOT / "agg_month_metrics.jsonl", month_rows)
    write_jsonl(GOLD_ROOT / "agg_price_distribution.jsonl", [price_dist])
    write_jsonl(GOLD_ROOT / "agg_estimate_accuracy.jsonl", [estimate_accuracy])

    ranked_with_country = sum(1 for r in artist_rows if r["country_birth"])
    # Los agregados por pais NO aplican el corte del ranking, asi que suman mas
    # lotes que la tabla de artistas. La diferencia se publica para que el aviso
    # del informe lleve la cifra real en vez de una vaguedad.
    country_lots = sum(r["lots_offered"] for r in country_rows)
    ranked_lots = sum(r["lots_offered"] for r in artist_rows)
    return {
        "lots_read": total,
        "artists_ranked": len(artist_rows),
        "artists_with_country": ranked_with_country,
        "country_coverage_rate": round(ranked_with_country / len(artist_rows), 4)
        if artist_rows
        else None,
        "countries": sum(1 for r in country_rows if r["country"]),
        "country_year_cells": len(country_year_rows),
        "generations": len(generation_rows),
        "country_lots_below_rank_cutoff": country_lots - ranked_lots,
        "lot_details": len(lot_details),
        "categories": len(cat_rows),
        "priced_lots": len(prices_eur),
        "estimate_sample": est_total,
    }


def main() -> None:
    stats = build_insights()
    print("--- Gold insights ---")
    for k, v in stats.items():
        print(f"  {k}: {v:,}" if isinstance(v, int) else f"  {k}: {v}")
    print(f"Escrito en: {GOLD_ROOT}")


if __name__ == "__main__":
    main()

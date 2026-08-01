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

from pipelines.shared.fx import to_eur
from pipelines.shared.schema import is_sold

ROOT = Path(__file__).resolve().parents[2]
SILVER_ROOT = ROOT / "data" / "silver"
ENRICH_ROOT = ROOT / "data" / "enrichments"
GOLD_ROOT = ROOT / "data" / "gold"

# Por debajo de este numero de lotes vendidos, un "precio medio" de artista es
# ruido estadistico. El informe muestra el corte para que no se lea como ranking.
MIN_LOTS_FOR_ARTIST_RANK = 3

# Entradas de artista que no son personas: escuelas, atribuciones y anonimos.
# Agrupan cientos de lotes heterogeneos y falsean cualquier ranking de autor.
ARTIST_NOISE_PREFIXES = (
    "escuela ",
    "taller de",
    "atrib",
    "anonimo",
    "anónimo",
    "maestro de",
    "circulo de",
    "círculo de",
    "seguidor de",
    "copia de",
    "escultura ",
)


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
    """Escuelas/atribuciones/anonimos: agregados, no autores."""
    low = name.strip().lower()
    if len(low) < 3:
        return True
    return any(low.startswith(p) for p in ARTIST_NOISE_PREFIXES)


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
            "lots_offered": 0,
            "lots_sold": 0,
            "revenue_eur": 0.0,
            "top_price_eur": 0.0,
            "top_lot_title": None,
            "top_lot_url": None,
            "country": None,
            "houses": set(),
        }
    )
    cats: dict[str, dict] = defaultdict(
        lambda: {"lots_offered": 0, "lots_sold": 0, "revenue_eur": 0.0}
    )
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
            name = (r.get("artist_name") or "").strip()
            if name and not is_noise_artist(name):
                a = artists[name]
                a["lots_offered"] += 1
                a["houses"].add(house)
                if not a["country"]:
                    a["country"] = r.get("artist_country")
                if sold:
                    a["lots_sold"] += 1
                    if eur:
                        a["revenue_eur"] += eur
                        if eur > a["top_price_eur"]:
                            a["top_price_eur"] = eur
                            a["top_lot_title"] = r.get("lot_title")
                            a["top_lot_url"] = r.get("lot_url")

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
    for name, a in artists.items():
        if a["lots_sold"] < MIN_LOTS_FOR_ARTIST_RANK:
            continue
        artist_rows.append(
            {
                "artist_name": name,
                "country": a["country"],
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

    write_jsonl(GOLD_ROOT / "agg_artist_metrics.jsonl", artist_rows)
    write_jsonl(GOLD_ROOT / "agg_category_metrics.jsonl", cat_rows)
    write_jsonl(GOLD_ROOT / "agg_month_metrics.jsonl", month_rows)
    write_jsonl(GOLD_ROOT / "agg_price_distribution.jsonl", [price_dist])
    write_jsonl(GOLD_ROOT / "agg_estimate_accuracy.jsonl", [estimate_accuracy])

    return {
        "lots_read": total,
        "artists_ranked": len(artist_rows),
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

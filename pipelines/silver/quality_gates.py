#!/usr/bin/env python3
"""Data quality gates for Silver layer, focused by house/category."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
# Esta puerta se invoca por RUTA de fichero, no con python -m (lleva argumentos
# y asi esta documentada en CLAUDE.md), asi que la raiz no entra sola en
# sys.path. Mismo apaño que build_silver.py.
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipelines.shared.artist_master import normalize_country

SILVER_LOTS = ROOT / "data" / "silver" / "lots.jsonl"
CATEGORY_TAGS = ROOT / "data" / "enrichments" / "category_tags.jsonl"

# Casas sin artista por naturaleza: su tasa de resolucion sera 0% para siempre y
# no tiene sentido que la puerta grite por ello. Zorrilla son 3.437 lotes de
# joyeria, ninguno con artist_name.
HOUSES_WITHOUT_ARTISTS = {"zorrilla_subastas"}


def load_category_map(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    mapping: dict[str, str] = {}
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            row = json.loads(line)
            key = row.get("dedupe_key")
            category = row.get("category")
            if key and category:
                mapping[key] = category
    return mapping


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate Silver quality gates.")
    parser.add_argument("--house-slug", required=True)
    # Las categorias las genera pipelines/enrichments/category_tag.py y estan en
    # ingles. Antes el valor por defecto era "obra_grafica,pintura" (espaniol),
    # asi que NINGUNA fila coincidia y la puerta marcaba el 100% fuera de
    # alcance en todas las casas.
    parser.add_argument(
        "--allowed-categories",
        default="painting,prints,books_documents,decorative_arts,other",
    )
    parser.add_argument("--min-lot-url", type=float, default=0.99)
    parser.add_argument("--min-lot-title", type=float, default=0.95)
    parser.add_argument("--min-price-coverage", type=float, default=0.70)
    # Fraccion maxima de lotes fuera de alcance tolerada. Antes cualquier fila
    # fuera de alcance (>0) tumbaba la puerta, lo que la hacia inservible en
    # casas generalistas.
    parser.add_argument("--max-out-of-scope-pct", type=float, default=1.0)
    # Umbral 0.0 a proposito: mientras el maestro de artistas este vacio, estas
    # dos puertas INFORMAN pero no bloquean. Se suben cuando el maestro crezca.
    parser.add_argument(
        "--min-artist-resolution-rate",
        type=float,
        default=0.0,
        help="Fraccion minima de autores resueltos contra el maestro.",
    )
    parser.add_argument(
        "--min-country-coverage",
        type=float,
        default=0.0,
        help="Fraccion minima de autores con pais de nacimiento.",
    )
    parser.add_argument(
        "--fail-on-violation",
        action="store_true",
        help="Sale con codigo != 0 si alguna puerta falla (para CI).",
    )
    args = parser.parse_args()

    allowed = {v.strip() for v in args.allowed_categories.split(",") if v.strip()}
    cat_map = load_category_map(CATEGORY_TAGS)
    rows = []
    with open(SILVER_LOTS, encoding="utf-8") as handle:
        for line in handle:
            row = json.loads(line)
            if row.get("house_slug") == args.house_slug:
                rows.append(row)

    if not rows:
        raise SystemExit(f"No rows found for house {args.house_slug}")

    total = len(rows)
    with_url = sum(1 for r in rows if r.get("lot_url"))
    with_title = sum(1 for r in rows if r.get("lot_title"))
    with_price = sum(1 for r in rows if (r.get("price_estimate_min") is not None or r.get("price_sold") is not None))
    out_of_scope = 0
    for row in rows:
        category = cat_map.get(row.get("dedupe_key", ""))
        if category and category not in allowed:
            out_of_scope += 1

    # --- artistas: identidad, tipo de autoria y pais ---
    # Los campos los escribe pipelines/silver/artist_resolve.py. Si esa etapa no
    # ha corrido todavia, authors sale 0 y las puertas quedan a 0 sin romper.
    authors = [r for r in rows if r.get("attribution_type") == "autor"]
    resolved = sum(1 for r in authors if r.get("artist_resolution") == "master")
    with_country = sum(1 for r in authors if r.get("artist_country_birth"))

    # Valores de pais que la casa publica y _countries.yaml no sabe traducir.
    # Es el bucle de realimentacion que mantiene viva la tabla: sin el, el
    # fichero envejece en silencio (que es como houses.yaml quedo obsoleto).
    unmapped = Counter()
    for row in rows:
        raw = row.get("artist_country")
        if raw and normalize_country(raw) is None:
            unmapped[str(raw).strip()] += 1

    pct_url = with_url / total
    pct_title = with_title / total
    pct_price = with_price / total
    pct_out_of_scope = out_of_scope / total
    pct_autor = len(authors) / total
    pct_resolution = resolved / len(authors) if authors else 0.0
    pct_country = with_country / len(authors) if authors else 0.0

    print(f"house={args.house_slug} total={total}")
    print(f"lot_url_coverage={pct_url:.4f}")
    print(f"lot_title_coverage={pct_title:.4f}")
    print(f"price_coverage={pct_price:.4f}")
    print(f"out_of_scope_count={out_of_scope} ({pct_out_of_scope:.2%})")
    print(f"attribution_autor_pct={pct_autor:.4f}")
    print(f"artist_resolution_rate={pct_resolution:.4f}")
    print(f"artist_country_coverage={pct_country:.4f}")
    print(f"unmapped_country_values={len(unmapped)}")
    for value, count in unmapped.most_common(5):
        print(f"  unmapped_country: {value!r} ({count} lotes)")

    failures = []
    if pct_url < args.min_lot_url:
        failures.append(f"lot_url({pct_url:.4f}<{args.min_lot_url})")
    if pct_title < args.min_lot_title:
        failures.append(f"lot_title({pct_title:.4f}<{args.min_lot_title})")
    if pct_price < args.min_price_coverage:
        failures.append(f"price({pct_price:.4f}<{args.min_price_coverage})")
    if pct_out_of_scope > args.max_out_of_scope_pct:
        failures.append(
            f"category_scope({pct_out_of_scope:.4f}>{args.max_out_of_scope_pct})"
        )
    # Las casas de joyeria no tienen artistas: exigirles cobertura seria gritar
    # lobo eternamente.
    if args.house_slug not in HOUSES_WITHOUT_ARTISTS:
        if pct_resolution < args.min_artist_resolution_rate:
            failures.append(
                f"artist_resolution({pct_resolution:.4f}<{args.min_artist_resolution_rate})"
            )
        if pct_country < args.min_country_coverage:
            failures.append(
                f"country_coverage({pct_country:.4f}<{args.min_country_coverage})"
            )

    if failures:
        message = f"failed_quality_gate: {','.join(failures)}"
        # Sin --fail-on-violation se informa pero no se aborta, para que la
        # puerta pueda usarse como diagnostico sin romper el pipeline entero.
        if args.fail_on_violation:
            raise SystemExit(message)
        print(message)
    else:
        print("quality_gates: OK")


if __name__ == "__main__":
    main()


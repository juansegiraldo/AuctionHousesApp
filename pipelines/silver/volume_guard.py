"""Corta la cadena si Silver encogio respecto a lo que Supabase ya vio.

    python -m pipelines.silver.volume_guard [--allow-shrink]

auction.raw_lots es solo de insercion y load_raw corre justo antes, asi que la
base tiene todo lote que alguna vez se scrapeo. Si Silver trae MENOS lotes de
una casa, algo se perdio por el camino (una particion de Bronze movida, un
output borrado, un re-scrape parcial): antes eso pasaba sin que nadie lo viera.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from pipelines.bronze import load_raw

SILVER_LOTS = Path(__file__).resolve().parents[2] / "data" / "silver" / "lots.jsonl"


def shrunk_houses(silver: dict[str, int], db: dict[str, int]) -> list[str]:
    """Casas con menos lotes en Silver que en la base. Una casa que solo esta en
    Silver no es un fallo: es que aun no se ha cargado (corrida sin red)."""
    return sorted(house for house, n in db.items() if silver.get(house, 0) < n)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--allow-shrink", action="store_true",
                    help="avisa pero no corta (cuando se ha retirado una fuente a proposito)")
    args = ap.parse_args()

    silver: Counter = Counter()
    with SILVER_LOTS.open(encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                silver[json.loads(line)["house_slug"]] += 1

    try:
        stats = load_raw.call("auction", {"op": "stats"})
    except (OSError, SystemExit) as exc:
        print(f"[volumen] AVISO: Supabase no responde ({exc}); no se puede comparar.")
        return
    db = {h["house_slug"]: h["lots"] for h in stats["houses"]}

    bad = shrunk_houses(silver, db)
    for house in sorted(silver.keys() | db.keys()):
        mark = "  <-- ENCOGIO" if house in bad else ""
        print(f"[volumen] {house}: Silver {silver.get(house, 0):,} / base {db.get(house, 0):,}{mark}")
    if bad and not args.allow_shrink:
        raise SystemExit(f"[volumen] Silver encogio en: {', '.join(bad)}. "
                         "Revisa Bronze/outputs o restaura con scripts.db_restore.")


if __name__ == "__main__":
    main()

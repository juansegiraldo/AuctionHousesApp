"""Reconstruye los ficheros de lotes desde auction.raw_lots (Supabase).

    python -m scripts.db_restore --out C:/Temp/restore          # solo bajar
    python -m scripts.db_restore --out C:/Temp/restore --check  # + simulacro

Cada version vuelve al fichero donde se vio por primera vez (`source_file`), asi
que la carpeta de salida tiene la misma forma que el repo: data/bronze/<casa>/
ingestion_date=…/…jsonl. Para recuperarse de un disco perdido: restaurar sobre
la raiz del repo y lanzar scripts/run_all.ps1.

--check es el simulacro: construye Silver sobre lo restaurado y lo compara, lote
a lote, con el Silver actual. Una copia de seguridad que nunca se ha restaurado
no es una copia de seguridad.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import orjson

from pipelines.bronze.ingest import load_house_registry
from pipelines.bronze.load_raw import ROOT, call

# Campos que legitimamente difieren: sellos de tiempo/ruta de la corrida y lo que
# anade artist_resolve despues de build_silver.
IGNORED = {"scraped_at", "ingested_at", "source_file", "artist_id", "artist_fold",
           "artist_display_name", "attribution_type", "artist_country_birth",
           "artist_nationalities", "artist_resolution"}


def restore(out: Path, schema: str) -> int:
    handles: dict[str, object] = {}
    total = 0
    try:
        for house in load_house_registry():
            after = None
            while True:
                rows = call(schema, {"op": "export", "house_slug": house["slug"],
                                     "after": after, "limit": 1000})["rows"]
                if not rows:
                    break
                for row in rows:
                    rel = row["source_file"]
                    if rel not in handles:
                        path = out / rel
                        path.parent.mkdir(parents=True, exist_ok=True)
                        handles[rel] = path.open("wb")
                    handles[rel].write(orjson.dumps(row["payload"], option=orjson.OPT_APPEND_NEWLINE))
                total += len(rows)
                after = [rows[-1]["lot_url"], rows[-1]["content_hash"]]
            print(f"{house['slug']}: restaurada")
    finally:
        for fh in handles.values():
            fh.close()
    print(f"{total} versiones en {len(handles)} ficheros -> {out}")
    return total


def check(out: Path) -> None:
    from pipelines.silver import build_silver

    build_silver.ROOT = out
    build_silver.BRONZE_ROOT = out / "data" / "bronze"
    build_silver.SILVER_ROOT = out / "data" / "silver"
    build_silver.main()

    def load(path: Path) -> dict[str, dict]:
        with path.open("rb") as fh:
            return {r["dedupe_key"]: r for r in map(orjson.loads, fh)}

    current = load(ROOT / "data" / "silver" / "lots.jsonl")
    restored = load(out / "data" / "silver" / "lots.jsonl")
    missing = current.keys() - restored.keys()
    extra = restored.keys() - current.keys()
    differ = [k for k in current.keys() & restored.keys()
              if any(current[k].get(f) != restored[k].get(f)
                     for f in (current[k].keys() | restored[k].keys()) - IGNORED)]
    print(f"Silver actual {len(current)} lotes, restaurado {len(restored)}; "
          f"faltan {len(missing)}, sobran {len(extra)}, distintos {len(differ)}")
    for k in differ[:5]:
        fields = [f for f in (current[k].keys() | restored[k].keys()) - IGNORED
                  if current[k].get(f) != restored[k].get(f)]
        print("  distinto:", k[:110], fields)
    if missing or extra or differ:
        raise SystemExit("SIMULACRO FALLIDO: lo restaurado no reproduce el Silver actual")
    print("SIMULACRO OK: Supabase reproduce el Silver actual lote a lote")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", required=True, type=Path, help="carpeta de salida (vacia)")
    ap.add_argument("--schema", default="auction", choices=["auction", "auction_des"])
    ap.add_argument("--check", action="store_true", help="simulacro: compara con el Silver actual")
    args = ap.parse_args()
    if args.out.exists() and any(args.out.iterdir()):
        raise SystemExit(f"{args.out} no esta vacia: no se restaura encima de nada")
    restore(args.out, args.schema)
    if args.check:
        check(args.out)


if __name__ == "__main__":
    main()

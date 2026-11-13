"""Carga lo scrapeado en auction.raw_lots (Supabase), el registro duradero.

    python -m pipelines.bronze.load_raw --dry-run             # cuenta, no envia
    python -m pipelines.bronze.load_raw --schema auction_des  # outputs actuales
    python -m pipelines.bronze.load_raw --backfill            # + todo Bronze

Idempotente: la clave es (house_slug, lot_url, content_hash) y la base hace
`on conflict do nothing`, asi que repetir una carga no duplica ni pisa nada.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import os
import subprocess
import time
import urllib.error
import urllib.request
from collections import Counter
from pathlib import Path

import orjson

from pipelines.bronze.ingest import is_ingestable, load_house_registry

ROOT = Path(__file__).resolve().parents[2]
BATCH = 500
# auction_index.jsonl lista subastas, no lotes: build_silver tambien lo salta.
NOT_LOTS = {"auction_index.jsonl"}
RETRIES = 4
_urlopen = urllib.request.urlopen  # los tests lo sustituyen: ninguno sale a la red


def content_hash(record: dict) -> str:
    # Sin scraped_at: re-scrapear el mismo lote sin cambios no es una version nueva.
    body = {k: v for k, v in record.items() if k != "scraped_at"}
    return hashlib.sha256(orjson.dumps(body, option=orjson.OPT_SORT_KEYS)).hexdigest()


def degraded_exceeds(degraded: int, house_lots: int) -> bool:
    # Hasta el 1 % de la casa es normal: un arreglo de parser legitimo tambien
    # quita campos (p. ej. dejar de inventar un artista). Mas es un scrape roto.
    return degraded > 0.01 * house_lots


def read_file(path: Path, house_slug: str) -> tuple[list[dict], Counter]:
    """Filas listas para enviar + descartes por motivo. Una linea rota se cuenta,
    no tumba la carga (un scraper matado a medias deja la ultima linea cortada)."""
    rows: list[dict] = []
    rejects: Counter = Counter()
    source = path.relative_to(ROOT).as_posix()
    with path.open("rb") as fh:
        for line in fh:
            if not line.strip():
                continue
            try:
                rec = orjson.loads(line)
            except orjson.JSONDecodeError:
                rejects["linea_rota"] += 1
                continue
            if not isinstance(rec, dict) or not rec.get("lot_url"):
                rejects["sin_lot_url"] += 1
                continue
            rows.append({
                "house_slug": house_slug,
                "lot_url": rec["lot_url"],
                "content_hash": content_hash(rec),
                "payload": rec,
                "source_file": source,
            })
    return rows, rejects


def source_files(house: dict, backfill: bool) -> list[Path]:
    """Bronze de la particion mas vieja a la mas nueva y, al final, el output
    actual: asi first_run_id/source_file apuntan a la primera vez que se vio."""
    files: list[Path] = []
    if backfill:
        bronze = ROOT / "data" / "bronze" / house["slug"]
        for part in sorted(bronze.glob("ingestion_date=*")):
            files += sorted(part.glob("*.jsonl"))
    files += sorted((ROOT / house["output_dir"]).glob("*.jsonl"))
    return files


def _env(name: str) -> str:
    if name in os.environ:
        return os.environ[name]
    for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        if line.startswith(name + "="):
            return line.split("=", 1)[1].strip()
    raise SystemExit(f"Falta {name} en el entorno o en .env")


def call(schema: str, body: dict) -> dict:
    req = urllib.request.Request(
        _env("AUCTION_INGEST_URL"),
        data=gzip.compress(orjson.dumps(body)),
        headers={
            "Content-Type": "application/json",
            "x-gzip": "1",
            "x-schema": schema,
            "x-ingest-token": _env("AUCTION_INGEST_TOKEN"),
        },
    )
    # Una carga completa son ~190 peticiones: un solo corte de TLS a mitad
    # ("bad record mac", visto el 2026-11-13) tumbaba la corrida entera. Todas
    # las operaciones son repetibles (raw hace `on conflict do nothing`).
    for attempt in range(1, RETRIES + 1):
        try:
            with _urlopen(req, timeout=120) as resp:
                return orjson.loads(resp.read())
        except urllib.error.HTTPError as e:
            if e.code < 500 or attempt == RETRIES:
                # El cuerpo trae el error de Postgres; sin el, un 500 no dice nada.
                raise SystemExit(f"auction-ingest {body['op']} -> {e.code}: {e.read().decode()[:500]}")
        except OSError:  # URLError, SSLError, timeout
            if attempt == RETRIES:
                raise
        time.sleep(2 ** attempt)
    raise AssertionError("inalcanzable")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--schema", default="auction", choices=["auction", "auction_des"])
    ap.add_argument("--house", help="solo esta casa (slug)")
    ap.add_argument("--backfill", action="store_true", help="incluye todas las particiones de Bronze")
    ap.add_argument("--dry-run", action="store_true", help="cuenta versiones sin enviar nada")
    ap.add_argument("--allow-degraded", action="store_true",
                    help="no cortar aunque un re-scrape traiga menos datos (cambio de parser deliberado)")
    ap.add_argument("--best-effort", action="store_true",
                    help="si Supabase no responde, avisa y sale con 0 (para run_all.ps1)")
    args = ap.parse_args()

    houses = [h for h in load_house_registry() if not args.house or h["slug"] == args.house]
    if not houses:
        raise SystemExit(f"Casa desconocida: {args.house}")

    run_id = None
    if not args.dry_run:
        sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT,
                             capture_output=True, text=True).stdout.strip() or None
        try:
            run_id = call(args.schema, {"op": "run_start", "git_sha": sha})["run_id"]
        except (OSError, SystemExit) as exc:  # URLError y timeout son OSError
            # El pipeline tiene que poder correr sin red: la carga es idempotente,
            # asi que saltarsela hoy solo la deja pendiente para la proxima corrida.
            if not args.best_effort:
                raise
            print(f"AVISO: Supabase no responde ({exc}). La carga queda pendiente; "
                  "es idempotente y se puede repetir.")
            return

    seen: set[tuple[str, str, str]] = set()  # las 34 particiones repiten casi todo
    counts: dict[str, dict] = {}
    reject_rows: list[dict] = []
    status = "ok"
    try:
        for house in houses:
            slug = house["slug"]
            c = counts[slug] = {"versions": 0, "lots": 0, "inserted": 0, "payload_bytes": 0}
            lots: set[str] = set()
            unique: list[dict] = []

            for path in source_files(house, args.backfill):
                source = path.relative_to(ROOT).as_posix()
                if path.name in NOT_LOTS:
                    continue
                if not is_ingestable(path.name):
                    reject_rows.append({"house_slug": slug, "source_file": source, "motivo": "fichero_de_prueba", "n": 1})
                    continue
                rows, rejects = read_file(path, slug)
                reject_rows += [{"house_slug": slug, "source_file": source, "motivo": m, "n": n}
                                for m, n in rejects.items()]
                for row in rows:
                    key = (slug, row["lot_url"], row["content_hash"])
                    if key in seen:
                        continue
                    seen.add(key)
                    lots.add(row["lot_url"])
                    c["versions"] += 1
                    c["payload_bytes"] += len(orjson.dumps(row["payload"]))
                    unique.append(row)
            c["lots"] = len(lots)
            if not args.dry_run:
                # Se pregunta primero que hashes faltan y se envia solo eso: una
                # corrida sin novedades son unas pocas peticiones, no 111 MB.
                hashes = [r["content_hash"] for r in unique]
                missing: set[str] = set()
                for i in range(0, len(hashes), 5000):
                    missing.update(call(args.schema, {"op": "missing", "house_slug": slug,
                                                      "hashes": hashes[i:i + 5000]})["missing"])
                new = [r for r in unique if r["content_hash"] in missing]
                for i in range(0, len(new), BATCH):
                    c["inserted"] += call(args.schema, {"op": "raw", "run_id": run_id,
                                                        "rows": new[i:i + BATCH]})["inserted"]
            print(f"{slug}: {c['lots']} lotes, {c['versions']} versiones, "
                  f"{c['payload_bytes'] / 1e6:.0f} MB, {c['inserted']} insertadas")

        if run_id is not None:
            # Un re-scrape en el que falla la pagina de detalle guarda el lote solo
            # con los campos del catalogo, y como gana la version mas nueva, pisaba
            # en silencio el registro completo. Aqui se ve y se corta la cadena.
            degraded = [h for h in call(args.schema, {"op": "degraded", "run_id": run_id})["houses"]
                        if degraded_exceeds(h["degraded"], counts[h["house_slug"]]["lots"])]
            for h in degraded:
                counts[h["house_slug"]]["degraded"] = h["degraded"]
                print(f"{h['house_slug']}: {h['degraded']} lotes con MENOS datos que su version anterior")
            if degraded and not args.allow_degraded:
                raise SystemExit("Re-scrape degradado. Revisa el scraper antes de reconstruir Silver, "
                                 "o repite con --allow-degraded si el cambio es deliberado.")
    except BaseException:
        status = "failed"
        raise
    finally:
        by_reason = Counter()
        for r in reject_rows:
            by_reason[r["motivo"]] += r["n"]
        print("descartes:", dict(by_reason) or "ninguno")
        if run_id is not None:
            if reject_rows:
                call(args.schema, {"op": "rejects", "run_id": run_id, "rows": reject_rows})
            call(args.schema, {"op": "run_finish", "run_id": run_id, "status": status,
                               "stage_failed": None if status == "ok" else "load_raw", "counts": counts})


if __name__ == "__main__":
    main()

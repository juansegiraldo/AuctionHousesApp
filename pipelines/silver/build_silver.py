#!/usr/bin/env python3
"""Build Silver datasets from Bronze JSONL files."""

from __future__ import annotations

import json
import re
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipelines.shared.schema import normalize_lot
from scraping.common.atomic import atomic_write

BRONZE_ROOT = ROOT / "data" / "bronze"
SILVER_ROOT = ROOT / "data" / "silver"
NON_LOT_FILES = {"auction_index.jsonl"}
MERGED_FILE = "historic_all_lots.jsonl"
# Unas pocas colas truncadas (un scraper matado a mitad de linea) son normales;
# por encima de esto es corrupcion masiva y Silver no debe publicarse.
MAX_MALFORMED_RATE = 0.001
_PARTITION_RE = re.compile(r"^ingestion_date=(\d{4}-\d{2}-\d{2})$")


def _file_order(path: Path) -> tuple[bool, str]:
    # historic_all es la concatenacion de los ficheros por subasta al cerrar la
    # corrida y no se regenera si luego se re-scrapea una subasta suelta: va el
    # ultimo, para que solo aporte los lotes que no estan en otro fichero.
    return (path.name == MERGED_FILE, path.name)


def iter_bronze_rows(stats: dict | None = None):
    """Filas de Bronze en orden de precedencia: gana la primera de cada dedupe_key.

    Particion MAS NUEVA primero. Bronze copia todo el output en cada ingesta, asi
    que con la mas antigua primero un re-scrape o un arreglo del parser nunca
    llegaba a un lote ya cargado. Los lotes que solo estan en particiones viejas
    entran igual.

    stats, si se pasa, recibe "lines" (lineas leidas) y "malformed"
    ({fichero: lineas rotas}): una linea que no es JSON se salta y se cuenta.
    """
    if stats is None:
        stats = {}
    stats.setdefault("lines", 0)
    stats.setdefault("malformed", {})
    for house_dir in sorted(BRONZE_ROOT.iterdir()):
        if not house_dir.is_dir():
            continue
        house_slug = house_dir.name
        for partition_dir in sorted(house_dir.iterdir(), reverse=True):
            if not partition_dir.is_dir():
                continue
            # ingested_at = fecha de la particion, no el reloj: con now_iso()
            # Silver no era reproducible byte a byte sobre el mismo Bronze.
            match = _PARTITION_RE.match(partition_dir.name)
            ingested_at = f"{match.group(1)}T00:00:00+00:00" if match else None
            for file_path in sorted(partition_dir.glob("*.jsonl"), key=_file_order):
                if file_path.name in NON_LOT_FILES:
                    continue
                with open(file_path, encoding="utf-8") as handle:
                    for line in handle:
                        line = line.strip()
                        if not line:
                            continue
                        stats["lines"] += 1
                        # Un scraper matado deja la ultima linea a medias. Sin
                        # este try, esa linea abortaba toda la corrida.
                        try:
                            record = json.loads(line)
                        except ValueError:
                            record = None
                        if not isinstance(record, dict):
                            source = str(file_path.relative_to(ROOT))
                            stats["malformed"][source] = stats["malformed"].get(source, 0) + 1
                            continue
                        if not record.get("lot_url"):
                            continue
                        yield normalize_lot(
                            record, house_slug, str(file_path.relative_to(ROOT)), ingested_at
                        )


def main() -> None:
    SILVER_ROOT.mkdir(parents=True, exist_ok=True)
    lots_path = SILVER_ROOT / "lots.jsonl"
    auctions_path = SILVER_ROOT / "auctions.jsonl"

    dedupe_keys: set[str] = set()
    seen_auctions: set[str] = set()

    stats: dict = {}
    # Escritura atomica: antes se abrian (y vaciaban) los dos ficheros ANTES de
    # leer Bronze, asi que un fallo a mitad dejaba un Silver truncado que las
    # etapas siguientes leian como si fuera completo.
    with atomic_write(lots_path, "w", encoding="utf-8") as lots_out, atomic_write(
        auctions_path, "w", encoding="utf-8"
    ) as auctions_out:
        for row in iter_bronze_rows(stats):
            dedupe_key = row["dedupe_key"]
            if dedupe_key in dedupe_keys:
                continue
            dedupe_keys.add(dedupe_key)
            lots_out.write(json.dumps(row, ensure_ascii=False) + "\n")

            auction_key = f"{row.get('house_slug')}|{row.get('auction_id')}"
            if auction_key not in seen_auctions:
                seen_auctions.add(auction_key)
                auctions_out.write(
                    json.dumps(
                        {
                            "house_slug": row.get("house_slug"),
                            "auction_id": row.get("auction_id"),
                            "auction_title": row.get("auction_title"),
                            "auction_start_date": row.get("auction_start_date"),
                            "auction_end_date": row.get("auction_end_date"),
                            "auction_url": row.get("auction_url"),
                            "auction_info_url": row.get("auction_info_url"),
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )

        # Dentro del with: si se aborta, el Silver anterior queda intacto.
        malformed = sum(stats["malformed"].values())
        for source, count in sorted(stats["malformed"].items()):
            print(f"[silver] AVISO: {count:,} lineas rotas saltadas en {source}")
        if malformed:
            print(f"[silver] {malformed:,} lineas rotas de {stats['lines']:,} leidas")
        if malformed > stats["lines"] * MAX_MALFORMED_RATE:
            raise SystemExit(
                f"[silver] ABORTADO: {malformed:,} lineas rotas de {stats['lines']:,} "
                f"superan el {MAX_MALFORMED_RATE:.1%}. Bronze esta corrupto; Silver no se toca."
            )

    print(f"[silver] wrote: {lots_path}")
    print(f"[silver] wrote: {auctions_path}")


if __name__ == "__main__":
    main()

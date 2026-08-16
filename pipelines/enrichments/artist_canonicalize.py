#!/usr/bin/env python3
"""Enrichment: clave canonica de artista por lote.

La logica de plegado vive en pipelines/shared/artist_key.py, que es tambien la
que usa Silver (artist_resolve.py). Antes este fichero tenia su propia version
con un bug: aplicaba re.sub(r"[^a-z0-9\\s]", "") despues de .lower() sin
normalizacion Unicode, asi que BORRABA los acentos en vez de plegarlos
("Joan Miró" -> "artist_joan_mir") y solo colapsaba 15.199 nombres a 14.727.

Se mantiene el fichero de salida porque semantic_layer/sources.yaml lo declara,
pero la fuente de verdad de la identidad del artista es ahora
data/silver/lots.jsonl (campos artist_id / artist_fold).
"""

from __future__ import annotations

import json
from pathlib import Path

from pipelines.shared.artist_key import artist_fold

ROOT = Path(__file__).resolve().parents[2]
SILVER_LOTS = ROOT / "data" / "silver" / "lots.jsonl"
OUTPUT = ROOT / "data" / "enrichments" / "artist_canonicalized.jsonl"


def artist_key(name: str | None) -> str | None:
    """Clave canonica del nombre, o None si no hay clave utilizable."""
    fold = artist_fold(name)
    return fold.replace(" ", "_") if fold else None


def main() -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with open(SILVER_LOTS, encoding="utf-8") as source, open(OUTPUT, "w", encoding="utf-8") as target:
        for line in source:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            key = artist_key(row.get("artist_name"))
            payload = {
                "dedupe_key": row.get("dedupe_key"),
                "artist_name": row.get("artist_name"),
                "artist_id": f"artist_{key}" if key else None,
            }
            target.write(json.dumps(payload, ensure_ascii=False) + "\n")
    print(f"[enrichment] wrote: {OUTPUT}")


if __name__ == "__main__":
    main()

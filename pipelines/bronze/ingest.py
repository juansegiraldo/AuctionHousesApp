#!/usr/bin/env python3
"""Ingest per-house scraper output JSONL into Bronze layer."""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[2]
SCRAPING_HOUSES = ROOT / "scraping" / "houses"
BRONZE_ROOT = ROOT / "data" / "bronze"

# Restos de corridas de prueba que quedaron en el output de Bogota. NO son
# datos: son corridas de catalogo que nunca bajaron la pagina de detalle, asi
# que traen fecha, artista, medium, procedencia y estimacion a None. Silver
# dedupe por lot_url y gana el primero que aterriza, de modo que pisaban al
# fichero bueno y dejaban 67 lotes mutilados (los mismos 52 vendidos que caian
# al fallback estatico de FX). Los lotes completos ya estan en el fichero con
# el slug de la subasta, asi que descartarlos no pierde nada.
#
# Se exige que "test" sea un SEGMENTO del nombre (separado por _ - o .), nunca
# una subcadena: una subasta puede llamarse "arte-contest-2024" o
# "protesta-social" y esas si son datos.
_TEST_FILE_RE = re.compile(r"(?:^|[_\-.])test(?:$|[_\-.])", re.IGNORECASE)


def is_ingestable(filename: str) -> bool:
    """Decide si un fichero del output de una casa entra en Bronze."""
    if not filename.endswith(".jsonl"):
        return False
    return not _TEST_FILE_RE.search(filename)


def load_house_registry() -> list[dict]:
    registry_path = SCRAPING_HOUSES / "registry.json"
    with open(registry_path, encoding="utf-8") as handle:
        data = json.load(handle)
    return data.get("houses", [])


def main() -> None:
    partition = datetime.now().strftime("ingestion_date=%Y-%m-%d")
    BRONZE_ROOT.mkdir(parents=True, exist_ok=True)

    for house in load_house_registry():
        slug = house["slug"]
        source = ROOT / house["output_dir"]
        if not source.exists():
            continue
        target = BRONZE_ROOT / slug / partition
        target.mkdir(parents=True, exist_ok=True)
        skipped = 0
        for jsonl_file in source.glob("*.jsonl"):
            if not is_ingestable(jsonl_file.name):
                skipped += 1
                print(f"[bronze] {slug}: OMITIDO (fichero de prueba) {jsonl_file.name}")
                continue
            shutil.copy2(jsonl_file, target / jsonl_file.name)
            print(f"[bronze] {slug}: {jsonl_file.name} -> {target}")
        if skipped:
            print(f"[bronze] {slug}: {skipped} fichero(s) de prueba omitidos")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Ingest per-house scraper output JSONL into Bronze layer."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[2]
SCRAPING_HOUSES = ROOT / "scraping" / "houses"
BRONZE_ROOT = ROOT / "data" / "bronze"


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
        for jsonl_file in source.glob("*.jsonl"):
            shutil.copy2(jsonl_file, target / jsonl_file.name)
            print(f"[bronze] {slug}: {jsonl_file.name} -> {target}")


if __name__ == "__main__":
    main()

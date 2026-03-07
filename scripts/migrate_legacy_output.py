#!/usr/bin/env python3
"""Move legacy scraping/output JSONL files to house output directory."""

from __future__ import annotations

from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
LEGACY = ROOT / "scraping" / "output"
TARGET = ROOT / "scraping" / "houses" / "bogota_auctions" / "output"


def main() -> None:
    if not LEGACY.exists():
        print(f"Legacy folder not found: {LEGACY}")
        return
    TARGET.mkdir(parents=True, exist_ok=True)
    moved = 0
    for file_path in LEGACY.glob("*.jsonl"):
        destination = TARGET / file_path.name
        if destination.exists():
            continue
        shutil.move(str(file_path), str(destination))
        moved += 1
    print(f"Moved {moved} file(s) from {LEGACY} to {TARGET}")


if __name__ == "__main__":
    main()

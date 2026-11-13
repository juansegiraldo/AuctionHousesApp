"""Copia a Supabase Storage lo irreemplazable que NO es lote.

    python -m scripts.archive_to_storage

Los lotes ya viven en auction.raw_lots. Esto cubre lo que no se puede volver a
generar: el Excel curado de Lefebre y la investigacion web de artistas (horas de
consultas a Wikidata). Cada corrida sube a una carpeta con la fecha, asi un
fichero estropeado nunca pisa la copia buena anterior.
"""
from __future__ import annotations

import gzip
import urllib.request
from datetime import date
from pathlib import Path

from pipelines.bronze.load_raw import ROOT, call

FILES = [
    "FINALL.xlsx",
    "data/enrichments/artist_web_research.jsonl",
    "data/enrichments/artist_web_research_cache.jsonl",
    "data/enrichments/place_countries.json",
]
# ponytail: el plan free de Storage admite 50 MB por fichero; si un .gz lo supera
# hay que trocearlo. Hoy el mayor (la cache, 110 MB) comprime muy por debajo.
MAX_BYTES = 50 * 1024 * 1024


def main() -> None:
    folder = date.today().isoformat()
    for rel in FILES:
        path = ROOT / rel
        if not path.exists():
            raise SystemExit(f"Falta {rel}: no se archiva nada a medias, revisa por que no esta")
        data = gzip.compress(path.read_bytes())
        if len(data) > MAX_BYTES:
            raise SystemExit(f"{rel} comprimido pesa {len(data) / 1e6:.0f} MB, mas que el limite de 50 MB")
        dest = f"{folder}/{path.name}.gz"
        url = call("auction", {"op": "sign_upload", "path": dest})["signed_url"]
        req = urllib.request.Request(url, data=data, method="PUT",
                                     headers={"Content-Type": "application/gzip", "x-upsert": "true"})
        with urllib.request.urlopen(req, timeout=600) as resp:
            resp.read()
        print(f"{rel} -> {dest} ({len(data) / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()

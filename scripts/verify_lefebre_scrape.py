"""Verifica un scrape de Lefebre contra el total que declara la propia casa.

El API de Auction Mobility publica, por subasta, `total_hammer_price` y
`sold_lot_count` en el resumen. La suma de los precios de los lotes tiene que
cuadrar EXACTAMENTE con eso (comprobado en 14/14 subastas el 2026-08-16). Es un
oraculo gratis: detecta paginacion incompleta, lotes perdidos por un timeout y
errores de conversion de precio, sin depender de ninguna fuente externa.

    python scripts/verify_lefebre_scrape.py
    python scripts/verify_lefebre_scrape.py --slug subasta-34

Sale con codigo != 0 si algo no cuadra, para poder encadenarlo en CI.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scraping.houses.lefebre_subastas.house import HOUSE, lefebre_fetcher  # noqa: E402
from scraping.houses.lefebre_subastas.parsers import (  # noqa: E402
    BASE_URL,
    EXCEL_ONLY_AUCTIONS,
    HISTORIC_URL,
)

_VIEWVARS_RE = re.compile(r"viewVars\s*=\s*(\{.*?\});", re.S)


def resumenes() -> dict[str, dict]:
    """slug -> resumen de la subasta, leyendo viewVars de /auctions/past."""
    found: dict[str, dict] = {}
    for page in range(1, 6):
        url = HISTORIC_URL if page == 1 else f"{HISTORIC_URL}?page={page}"
        match = _VIEWVARS_RE.search(lefebre_fetcher(url, 30.0))
        if not match:
            break
        view_vars = json.loads(match.group(1))
        vistas = 0
        for key in ("auctions", "upcomingAuctions"):
            for row in (view_vars.get(key) or {}).get("result_page") or []:
                vistas += 1
                found.setdefault(row.get("_slug") or row["row_id"], row)
        if not vistas:
            break
    return found


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--slug", default=None, help="Verificar solo esta subasta")
    parser.add_argument("--output-dir", type=Path, default=HOUSE.output_dir)
    args = parser.parse_args()

    sys.stdout.reconfigure(encoding="utf-8")  # los titulos llevan acentos
    summaries = resumenes()

    print(f"{'subasta':32} {'lotes':>6} {'vend':>5} {'martillo COP':>18}  estado")
    print("-" * 78)

    fallos = revisadas = 0
    for path in sorted(args.output_dir.glob("*.jsonl")):
        slug = path.stem
        if args.slug and slug != args.slug:
            continue
        if slug in ("historic_all_lots", "auction_index"):
            continue

        lots = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
        if not lots:
            continue

        # Las del Excel no tienen contrapartida verificable: la web trae 890
        # lotes mas que el curador descarto a proposito.
        if lots[0].get("auction_url", "").startswith("excel://"):
            print(f"{slug:32} {len(lots):6} {'':5} {'':>18}  omitida (fuente Excel)")
            continue

        summary = summaries.get(slug)
        if not summary:
            print(f"{slug:32} {len(lots):6} {'':5} {'':>18}  SIN RESUMEN en la web")
            continue

        vendidos = [l for l in lots if l.get("price_sold")]
        suma = sum(l["price_sold"] for l in vendidos)
        esperado = float(summary.get("total_hammer_price") or 0)
        esperados_lotes = summary.get("lot_count")
        esperados_vend = summary.get("sold_lot_count")

        problemas = []
        if abs(suma - esperado) >= 1:
            problemas.append(f"martillo {suma:,.0f} != {esperado:,.0f}")
        if esperados_lotes is not None and len(lots) != esperados_lotes:
            problemas.append(f"lotes {len(lots)} != {esperados_lotes}")
        if esperados_vend is not None and len(vendidos) != esperados_vend:
            problemas.append(f"vendidos {len(vendidos)} != {esperados_vend}")

        revisadas += 1
        if problemas:
            fallos += 1
            print(f"{slug:32} {len(lots):6} {len(vendidos):5} {suma:18,.0f}  FALLO: {'; '.join(problemas)}")
        else:
            print(f"{slug:32} {len(lots):6} {len(vendidos):5} {suma:18,.0f}  OK")

    print("-" * 78)
    print(f"{revisadas} subastas verificadas, {fallos} con problemas")
    if fallos:
        print("\nUna subasta con menos lotes de los esperados suele ser un .jsonl parcial")
        print("de un timeout: borra su .jsonl y su checkpoint y vuelve a lanzarla.")
    return 1 if fallos else 0


if __name__ == "__main__":
    raise SystemExit(main())

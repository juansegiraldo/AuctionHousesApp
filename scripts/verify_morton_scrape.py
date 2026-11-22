"""Verifica un scrape de Morton contra el numero de lotes que declara cada subasta.

La pagina de cada subasta publica "N Results" (el total de su catalogo). Cada
fichero de output/ tiene que traer exactamente N lotes. Detecta lo que el resume
del runner no ve: un fichero se abre al empezar la subasta, asi que una corrida
cortada deja un fichero a medias que la siguiente da por hecho y salta.

Tambien cuenta, por subasta, cuantos lotes quedaron sin estado: antes de 2024 el
estado solo sale de la ficha del lote, y una ficha fallida lo deja en None.

    python scripts/verify_morton_scrape.py
    python scripts/verify_morton_scrape.py --auction 17078

Sale con codigo != 0 si algo no cuadra.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scraping.common import net  # noqa: E402
from scraping.houses.morton_subastas.house import HOUSE  # noqa: E402
from scraping.houses.morton_subastas.parsers import _page_html  # noqa: E402


def declared_total(auction_url: str) -> int | None:
    page = net.fetch_with_retry(auction_url, 2, 30.0, fetcher=HOUSE.fetcher, house_slug=HOUSE.slug)
    match = re.search(r"(\d[\d,]*)\s+Results", _page_html(page))
    return int(match.group(1).replace(",", "")) if match else None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--auction", default=None, help="Verificar solo este id de subasta")
    parser.add_argument("--output-dir", type=Path, default=HOUSE.output_dir)
    args = parser.parse_args()

    sys.stdout.reconfigure(encoding="utf-8")  # los titulos llevan acentos
    print(f"{'subasta':>8} {'fecha':10} {'web':>5} {'lotes':>6} {'vend':>5} {'sin est.':>8}  estado")
    print("-" * 64)

    fallos = revisadas = 0
    for path in sorted(args.output_dir.glob("*.jsonl"), key=lambda p: p.stem):
        if not path.stem.isdigit() or (args.auction and path.stem != args.auction):
            continue
        lots = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        if not lots:
            print(f"{path.stem:>8} {'':10} {'':>5} {0:6}  VACIO")
            fallos += 1
            continue
        revisadas += 1
        web = declared_total(lots[0]["auction_url"])
        sold = sum(1 for lot in lots if lot.get("status") == "VENDIDO")
        sin_estado = sum(1 for lot in lots if not lot.get("status"))
        ok = web == len(lots) and not sin_estado
        fallos += not ok
        estado = "ok" if ok else ("FALTAN LOTES" if web != len(lots) else "LOTES SIN ESTADO")
        fecha = (lots[0].get("auction_start_date") or "")[:10]
        print(f"{path.stem:>8} {fecha:10} {web if web is not None else '?':>5} {len(lots):6} {sold:5} {sin_estado:8}  {estado}")

    print("-" * 64)
    print(f"{revisadas} subastas revisadas, {fallos} con problemas")
    return 1 if fallos else 0


if __name__ == "__main__":
    raise SystemExit(main())

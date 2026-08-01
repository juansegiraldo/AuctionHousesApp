#!/usr/bin/env python3
"""Enrichment: normaliza precios a EUR respetando la moneda de cada lote.

Antes este fichero aplicaba una tasa COP->USD fija a TODAS las filas, incluidas
las de Duran que ya venian en EUR (se dividian por 4000). Ahora lee
row["currency"] y usa la tabla unica de pipelines/config/fx.yaml.

Ejecutar como modulo desde la raiz:  python -m pipelines.enrichments.currency_normalize
"""

from __future__ import annotations

import json
from pathlib import Path

from pipelines.shared.fx import fx_as_of, to_eur

ROOT = Path(__file__).resolve().parents[2]
SILVER_LOTS = ROOT / "data" / "silver" / "lots.jsonl"
OUTPUT = ROOT / "data" / "enrichments" / "currency_normalized.jsonl"


def main() -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    fx_source = f"static_fx_{fx_as_of()}"
    rows = 0
    missing_rate = 0

    with open(SILVER_LOTS, encoding="utf-8") as source, open(
        OUTPUT, "w", encoding="utf-8"
    ) as target:
        for line in source:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            currency = row.get("currency")
            price_sold = row.get("price_sold")
            price_sold_eur = to_eur(price_sold, currency)
            if price_sold is not None and price_sold_eur is None:
                missing_rate += 1

            payload = {
                "dedupe_key": row.get("dedupe_key"),
                "currency": currency,
                "price_sold_eur": price_sold_eur,
                "price_estimate_min_eur": to_eur(row.get("price_estimate_min"), currency),
                "price_estimate_max_eur": to_eur(row.get("price_estimate_max"), currency),
                "fx_source": fx_source,
            }
            target.write(json.dumps(payload, ensure_ascii=False) + "\n")
            rows += 1

    print(f"[enrichment] wrote: {OUTPUT} ({rows:,} filas)")
    if missing_rate:
        print(f"[enrichment] AVISO: {missing_rate:,} precios sin tasa de cambio en fx.yaml")


if __name__ == "__main__":
    main()

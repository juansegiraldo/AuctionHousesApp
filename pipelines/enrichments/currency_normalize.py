#!/usr/bin/env python3
"""Enrichment: normaliza precios a EUR respetando la moneda de cada lote.

Antes este fichero aplicaba una tasa COP->USD fija a TODAS las filas, incluidas
las de Duran que ya venian en EUR (se dividian por 4000). Ahora lee
row["currency"] y usa la tabla unica de pipelines/config/fx.yaml.

La tasa es ademas la del MES de la subasta (fx_history.yaml), no la de hoy:
fx_source lo deja por lote ("monthly_2019-06" / "static_2026-08-01").

Ejecutar como modulo desde la raiz:  python -m pipelines.enrichments.currency_normalize
"""

from __future__ import annotations

import json
from pathlib import Path

from pipelines.shared.fx import fx_as_of, to_eur_at
from pipelines.shared.schema import extract_month

ROOT = Path(__file__).resolve().parents[2]
SILVER_LOTS = ROOT / "data" / "silver" / "lots.jsonl"
OUTPUT = ROOT / "data" / "enrichments" / "currency_normalized.jsonl"


def main() -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    rows = 0
    missing_rate = 0
    fallback = 0

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
            # Tasa del mes de la subasta, no la de hoy.
            month, _ = extract_month(
                row.get("auction_start_date"), row.get("auction_id") or ""
            )
            price_sold_eur, fx_method = to_eur_at(price_sold, currency, month)
            if price_sold is not None and price_sold_eur is None:
                missing_rate += 1
            if fx_method == "fallback_static":
                fallback += 1

            payload = {
                "dedupe_key": row.get("dedupe_key"),
                "currency": currency,
                "price_sold_eur": price_sold_eur,
                "price_estimate_min_eur": to_eur_at(
                    row.get("price_estimate_min"), currency, month
                )[0],
                "price_estimate_max_eur": to_eur_at(
                    row.get("price_estimate_max"), currency, month
                )[0],
                "fx_source": (
                    f"monthly_{month}"
                    if fx_method == "monthly" and month
                    else f"static_{fx_as_of()}"
                ),
            }
            target.write(json.dumps(payload, ensure_ascii=False) + "\n")
            rows += 1

    print(f"[enrichment] wrote: {OUTPUT} ({rows:,} filas)")
    if missing_rate:
        print(f"[enrichment] AVISO: {missing_rate:,} precios sin tasa de cambio en fx.yaml")
    if fallback:
        print(f"[enrichment] {fallback:,} lotes sin fecha usable -> tasa estatica")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Build Gold analytics artifacts from Silver layer.

Reglas de esta capa (aprendidas a base de errores, no las rompas):

1. MONEDA. Cada casa cotiza en su propia moneda (Bogota en COP, Duran en EUR).
   Nunca se suman importes de monedas distintas. Se emiten siempre dos cifras:
   `revenue_native` (+ `currency`), que es exacta, y `revenue_eur`, que es
   aproximada porque usa una tasa estatica de pipelines/config/fx.yaml.
   Cualquier total que cruce casas debe sumar EUR, nunca nativo.

2. ANIO. Las casas guardan la fecha en formatos distintos, asi que el anio se
   extrae con pipelines.shared.schema.extract_year(), que ademas dice de donde
   lo saco (iso / text / auction_id / unknown).

3. VENDIDO. Se usa el estado explicito cuando la casa lo publica. "Tiene precio"
   solo se usa como aproximacion cuando no hay estado.

Ademas se emite data/gold/quality_flags.jsonl con los avisos que el informe
muestra al usuario, para que las salvedades sean visibles y no notas al pie.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from pipelines.shared.fx import fx_as_of, fx_note, rate_for, to_eur
from pipelines.shared.schema import UNKNOWN_YEAR, extract_year, is_sold

ROOT = Path(__file__).resolve().parents[2]
SILVER_ROOT = ROOT / "data" / "silver"
GOLD_ROOT = ROOT / "data" / "gold"


def _read_lots(lots_path: Path):
    """Itera el Silver decodificando cada linea."""
    with open(lots_path, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                yield json.loads(line)


def _write_jsonl(path: Path, rows) -> None:
    with open(path, "w", encoding="utf-8") as output:
        for row in rows:
            output.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"[gold] wrote: {path}")


def main() -> None:
    GOLD_ROOT.mkdir(parents=True, exist_ok=True)
    lots_path = SILVER_ROOT / "lots.jsonl"
    if not lots_path.exists():
        raise FileNotFoundError(f"Silver lots not found: {lots_path}")

    # --- Acumuladores (una sola pasada sobre Silver) -------------------------
    per_house: dict[str, dict] = defaultdict(
        lambda: {
            "lots_offered": 0,
            "lots_sold": 0,
            "revenue_native": 0.0,
            "revenue_eur": 0.0,
            "currencies": set(),
            "null_status": 0,
            "explicit_status": 0,
            "lot_numbers": defaultdict(set),
            "lots_without_number": 0,
        }
    )
    per_auction: dict[tuple[str, str], dict] = defaultdict(
        lambda: {
            "lots": 0,
            "sold": 0,
            "revenue_native": 0.0,
            "revenue_eur": 0.0,
            "currency": None,
            "auction_title": None,
            "auction_start_date": None,
        }
    )
    per_year: dict[str, dict] = defaultdict(
        lambda: {"lots_offered": 0, "lots_sold": 0, "revenue_eur": 0.0}
    )
    per_year_house: dict[tuple[str, str], dict] = defaultdict(
        lambda: {
            "lots_offered": 0,
            "lots_sold": 0,
            "revenue_native": 0.0,
            "revenue_eur": 0.0,
            "currency": None,
        }
    )
    year_source: dict[tuple[str, str], int] = defaultdict(int)
    unconvertible: dict[str, int] = defaultdict(int)
    # Venta directa permanente (p.ej. "tienda-online" de Duran): no es una
    # subasta, asi que no tiene fecha. Se contabiliza aparte para no
    # confundirla con lotes a los que si deberia haberse podido datar.
    non_auction_lots: dict[str, int] = defaultdict(int)

    for row in _read_lots(lots_path):
        house = row.get("house_slug", "unknown")
        currency = row.get("currency")
        status = row.get("status")
        price = row.get("price_sold")
        sold = is_sold(status, price)

        aid_raw = row.get("auction_id") or ""
        year, method = extract_year(row.get("auction_start_date"), aid_raw)
        year_source[(house, method)] += 1
        if method == "unknown" and ("tienda-online" in aid_raw or "venta-directa" in aid_raw):
            non_auction_lots[house] += 1

        # Importe convertido: None si la moneda no esta en fx.yaml.
        price_eur = to_eur(price, currency) if sold else None
        if sold and price is not None and price_eur is None:
            unconvertible[str(currency)] += 1

        h = per_house[house]
        h["lots_offered"] += 1
        if currency:
            h["currencies"].add(currency)
        if status is None:
            h["null_status"] += 1
        else:
            h["explicit_status"] += 1
        lot_number = row.get("lot_number")
        if lot_number is not None:
            h["lot_numbers"][row.get("auction_id") or ""].add(lot_number)
        else:
            # Sin numero de lote no se pueden buscar huecos de secuencia, que es
            # como se estima si la casa publica los no vendidos. Se cuenta aparte
            # porque lot_numbers solo guarda los que si lo traen.
            h["lots_without_number"] += 1

        aid = row.get("auction_id") or ""
        a = per_auction[(house, aid)]
        a["lots"] += 1
        if a["currency"] is None:
            a["currency"] = currency
        if a["auction_title"] is None:
            a["auction_title"] = row.get("auction_title")
        if a["auction_start_date"] is None:
            a["auction_start_date"] = row.get("auction_start_date")

        py = per_year[year]
        py["lots_offered"] += 1
        pyh = per_year_house[(year, house)]
        pyh["lots_offered"] += 1
        if pyh["currency"] is None:
            pyh["currency"] = currency

        if sold:
            h["lots_sold"] += 1
            a["sold"] += 1
            py["lots_sold"] += 1
            pyh["lots_sold"] += 1
            if price is not None:
                h["revenue_native"] += float(price)
                a["revenue_native"] += float(price)
                pyh["revenue_native"] += float(price)
            if price_eur is not None:
                h["revenue_eur"] += price_eur
                a["revenue_eur"] += price_eur
                py["revenue_eur"] += price_eur
                pyh["revenue_eur"] += price_eur

    # --- agg_house_metrics --------------------------------------------------
    house_rows = []
    for house, m in sorted(per_house.items()):
        currencies = sorted(m["currencies"])
        currency = currencies[0] if len(currencies) == 1 else "MIXED"
        lots_sold = m["lots_sold"]
        offered = m["lots_offered"] or 1
        house_rows.append(
            {
                "house_slug": house,
                "lots_offered": m["lots_offered"],
                "lots_sold": lots_sold,
                "sell_through_rate": lots_sold / offered,
                "currency": currency,
                "revenue_native": round(m["revenue_native"], 2),
                "revenue_eur": round(m["revenue_eur"], 2),
                "fx_rate_used": rate_for(currency),
                "avg_sold_price_native": (
                    round(m["revenue_native"] / lots_sold, 2) if lots_sold else None
                ),
                "avg_sold_price_eur": (
                    round(m["revenue_eur"] / lots_sold, 2) if lots_sold else None
                ),
            }
        )
    _write_jsonl(GOLD_ROOT / "agg_house_metrics.jsonl", house_rows)

    # --- agg_auction_metrics ------------------------------------------------
    auction_rows = []
    for (house, aid), m in sorted(per_auction.items()):
        lots = m["lots"] or 1
        auction_rows.append(
            {
                "house_slug": house,
                "auction_id": aid,
                "auction_title": m["auction_title"],
                "auction_start_date": m["auction_start_date"],
                "lots": m["lots"],
                "sold": m["sold"],
                "sell_through_pct": round(m["sold"] / lots * 100, 1),
                "currency": m["currency"],
                "revenue_native": round(m["revenue_native"], 2),
                "revenue_eur": round(m["revenue_eur"], 2),
            }
        )
    _write_jsonl(GOLD_ROOT / "agg_auction_metrics.jsonl", auction_rows)

    # --- agg_lots_by_year (cruza casas -> solo EUR tiene sentido) ------------
    def _year_key(y: str):
        return (y == UNKNOWN_YEAR, y)

    year_rows = []
    for year in sorted(per_year.keys(), key=_year_key):
        m = per_year[year]
        offered = m["lots_offered"] or 1
        year_rows.append(
            {
                "year": year,
                "lots_offered": m["lots_offered"],
                "lots_sold": m["lots_sold"],
                "sell_through_rate": round(m["lots_sold"] / offered, 4),
                "revenue_eur": round(m["revenue_eur"], 2),
            }
        )
    _write_jsonl(GOLD_ROOT / "agg_lots_by_year.jsonl", year_rows)

    # --- agg_lots_by_year_by_house (una sola casa -> nativo tambien vale) ----
    year_house_rows = []
    for (year, house) in sorted(per_year_house.keys(), key=lambda k: (_year_key(k[0]), k[1])):
        m = per_year_house[(year, house)]
        offered = m["lots_offered"] or 1
        year_house_rows.append(
            {
                "year": year,
                "house_slug": house,
                "lots_offered": m["lots_offered"],
                "lots_sold": m["lots_sold"],
                "sell_through_rate": round(m["lots_sold"] / offered, 4),
                "currency": m["currency"],
                "revenue_native": round(m["revenue_native"], 2),
                "revenue_eur": round(m["revenue_eur"], 2),
            }
        )
    _write_jsonl(GOLD_ROOT / "agg_lots_by_year_by_house.jsonl", year_house_rows)

    # --- quality_flags: las salvedades que el informe debe mostrar -----------
    flags = [
        {
            "level": "info",
            "code": "fx_static",
            "message": fx_note(),
            "fx_as_of": fx_as_of(),
        }
    ]

    for house, m in sorted(per_house.items()):
        # Lotes ausentes de la secuencia: senal de que la casa no publica
        # todos los lotes (tipicamente oculta los no vendidos).
        expected = sum(max(nums) for nums in m["lot_numbers"].values() if nums)
        present = sum(len(nums) for nums in m["lot_numbers"].values())
        missing = expected - present
        if m["null_status"]:
            flags.append(
                {
                    "level": "warn",
                    "code": "status_inferred",
                    "house_slug": house,
                    "count": m["null_status"],
                    "message": (
                        f"{m['null_status']:,} lotes de {house} sin estado explicito; "
                        "se infiere vendido por la presencia de precio."
                    ),
                }
            )
        if missing > 0 and m["null_status"] > 0:
            flags.append(
                {
                    "level": "critical",
                    "code": "sell_through_not_comparable",
                    "house_slug": house,
                    "count": missing,
                    "message": (
                        f"Tasa de venta de {house} NO comparable con otras casas: "
                        f"faltan ~{missing:,} numeros de lote de las secuencias, "
                        "indicio de que la fuente solo publica lotes vendidos."
                    ),
                }
            )

    for (house, method), count in sorted(year_source.items()):
        if method == "auction_id":
            flags.append(
                {
                    "level": "warn",
                    "code": "year_inferred",
                    "house_slug": house,
                    "count": count,
                    "message": (
                        f"{count:,} lotes de {house} con anio inferido del identificador "
                        "de subasta, no de una fecha real."
                    ),
                }
            )
        elif method == "unknown":
            # La venta directa permanente no tiene fecha por naturaleza; se
            # separa para que el aviso refleje solo lo realmente problematico.
            direct = non_auction_lots.get(house, 0)
            datable = count - direct
            if datable > 0:
                flags.append(
                    {
                        "level": "warn",
                        "code": "year_unknown",
                        "house_slug": house,
                        "count": datable,
                        "message": (
                            f"{datable:,} lotes de {house} en subastas sin fecha en el "
                            "titulo -> agrupados como 'unknown'."
                        ),
                    }
                )
            if direct > 0:
                flags.append(
                    {
                        "level": "info",
                        "code": "non_auction_lots",
                        "house_slug": house,
                        "count": direct,
                        "message": (
                            f"{direct:,} lotes de {house} son venta directa permanente "
                            "(tienda online), no subastas: sin fecha por naturaleza."
                        ),
                    }
                )

    # Zorrilla se scrapea desde LiveAuctioneers, que normaliza los importes a USD
    # en origen. La casa remata en Montevideo y pudo cotizar en UYU: ese importe
    # NO existe en la fuente. Se avisa para que nadie lea los USD como moneda de
    # martillo original. Ver scraping/houses/zorrilla_subastas/parsers.py.
    # OJO: per_house es un defaultdict; usar 'in' y no .get() para no crear la clave.
    if "zorrilla_subastas" in per_house:
        flags.append(
            {
                "level": "warn",
                "code": "currency_normalized_at_source",
                "house_slug": "zorrilla_subastas",
                "count": per_house["zorrilla_subastas"]["lots_offered"],
                "message": (
                    "Los importes de zorrilla_subastas vienen en USD normalizados por "
                    "el agregador (LiveAuctioneers), no en la moneda de martillo. "
                    "La casa opera en Montevideo y pudo rematar en UYU; ese dato no "
                    "esta publicado en la fuente."
                ),
            }
        )

    # Lefebre no se scrapea: sale de una hoja de calculo curada a mano en 2024
    # (FINALL.xlsx). No se actualiza sola y su cobertura es la que se transcribio,
    # no la que publico la casa. Ver scraping/houses/lefebre_subastas/README.md.
    # OJO: per_house es un defaultdict; usar 'in' y no .get() para no crear la clave.
    if "lefebre_subastas" in per_house:
        flags.append(
            {
                "level": "warn",
                "code": "source_is_manual_dataset",
                "house_slug": "lefebre_subastas",
                "count": per_house["lefebre_subastas"]["lots_offered"],
                "message": (
                    "Los lotes de lefebre_subastas vienen de un Excel curado a mano "
                    "en 2024, no de un scraper: el dato esta congelado en esa fecha "
                    "y la cobertura depende de lo que se transcribio."
                ),
            }
        )
        # Solo 4 de las 15 subastas traen numero de lote real; en el resto la
        # hoja guarda el numero de fila. Sin numeracion no se pueden detectar
        # huecos de secuencia, que es como se estima el sesgo de tasa de venta.
        without_number = per_house["lefebre_subastas"]["lots_without_number"]
        if without_number:
            flags.append(
                {
                    "level": "warn",
                    "code": "partial_lot_numbers",
                    "house_slug": "lefebre_subastas",
                    "count": without_number,
                    "message": (
                        f"{without_number:,} lotes de lefebre_subastas no tienen numero "
                        "de lote en la fuente: en esas subastas no se puede comprobar "
                        "si faltan lotes por huecos en la secuencia."
                    ),
                }
            )

    for currency, count in sorted(unconvertible.items()):
        flags.append(
            {
                "level": "critical",
                "code": "fx_missing_rate",
                "count": count,
                "message": (
                    f"{count:,} lotes vendidos en '{currency}' sin tasa en fx.yaml: "
                    "excluidos de los totales en EUR."
                ),
            }
        )

    _write_jsonl(GOLD_ROOT / "quality_flags.jsonl", flags)


if __name__ == "__main__":
    main()

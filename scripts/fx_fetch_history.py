#!/usr/bin/env python3
"""Descarga el historico de tasas y escribe pipelines/config/fx_history.yaml.

Se ejecuta A MANO y rara vez. NO forma parte de run_all.ps1: los pipelines no
tocan la red, leen siempre el YAML versionado en git.

Dos fuentes, porque el BCE NO publica el peso colombiano (la serie
D.COP.EUR.SP00.A devuelve 404). El puente es:

    COP->EUR = (1 / TRM_COP_USD) x (1 / EURUSD_BCE)

usando en cada lado la fuente canonica de esa moneda.

Ejecutar desde la raiz:  python -m scripts.fx_fetch_history
"""

from __future__ import annotations

import json
import urllib.request
from collections import defaultdict
from pathlib import Path
from typing import Dict

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "pipelines" / "config" / "fx_history.yaml"

# Un anio de margen antes del primer lote (2014) para que ningun mes real
# quede fuera de rango.
START = "2013-01-01"

ECB_URL = (
    "https://data-api.ecb.europa.eu/service/data/EXR/D.USD.EUR.SP00.A"
    "?startPeriod={start}&format=csvdata"
)
TRM_URL = (
    "https://www.datos.gov.co/resource/32sa-8pi3.json"
    "?$limit=50000&$where=vigenciadesde>='{start}T00:00:00'"
    "&$order=vigenciadesde%20ASC"
)
# Sin User-Agent el BCE responde 403.
HEADERS = {"User-Agent": "AuctionHousesApp/1.0 (fx history fetch)"}


def _fetch(url: str) -> str:
    request = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(request, timeout=120) as response:
        return response.read().decode("utf-8")


def parse_ecb_csv(text: str) -> Dict[str, float]:
    """CSV del BCE -> {fecha ISO: EUR/USD}. TIME_PERIOD y OBS_VALUE son las
    columnas 7 y 8 (indices 6 y 7)."""
    daily: Dict[str, float] = {}
    for line in text.splitlines():
        parts = line.split(",")
        if len(parts) < 8 or parts[6] == "TIME_PERIOD":
            continue
        try:
            daily[parts[6]] = float(parts[7])
        except ValueError:
            # Dias sin cotizacion (festivos) vienen vacios: se omiten.
            continue
    return daily


def parse_trm_json(text: str) -> Dict[str, float]:
    """JSON de datos.gov.co -> {fecha ISO: COP por USD}."""
    daily: Dict[str, float] = {}
    for row in json.loads(text):
        date = (row.get("vigenciadesde") or "")[:10]
        try:
            daily[date] = float(row["valor"])
        except (KeyError, TypeError, ValueError):
            continue
    return daily


def monthly_average(daily: Dict[str, float]) -> Dict[str, float]:
    """Media mensual. Es la granularidad mas fina que soportan las tres casas:
    Duran solo publica mes y anio ("Enero 2014")."""
    buckets: Dict[str, list] = defaultdict(list)
    for date, value in daily.items():
        buckets[date[:7]].append(value)
    return {month: sum(vals) / len(vals) for month, vals in sorted(buckets.items())}


def build_rates(
    eurusd_monthly: Dict[str, float],
    trm_monthly: Dict[str, float],
) -> Dict[str, Dict[str, float]]:
    """Compone las tasas hacia EUR.

    Un mes que falte en cualquiera de las dos series se omite en COP en vez de
    rellenarse: la misma disciplina que to_eur() devolviendo None.
    """
    usd = {m: round(1 / v, 8) for m, v in eurusd_monthly.items() if v}
    cop = {
        m: round((1 / trm) * (1 / eurusd_monthly[m]), 10)
        for m, trm in trm_monthly.items()
        if trm and eurusd_monthly.get(m)
    }
    return {"USD": usd, "COP": cop}


def render_yaml(rates: Dict[str, Dict[str, float]], generated_at: str) -> str:
    lines = [
        "# Tasas de cambio MENSUALES hacia EUR. Generado por",
        "# scripts/fx_fetch_history.py -- no editar a mano.",
        "#",
        "# El BCE no publica COP (D.COP.EUR.SP00.A da 404), asi que el peso se",
        "# compone puenteando por el dolar: COP->EUR = (1/TRM) x (1/EURUSD).",
        "#",
        "# Lo lee unicamente pipelines/shared/fx.py.",
        "",
        "base_currency: EUR",
        f'generated_at: "{generated_at}"',
        "sources:",
        '  USD: "ECB SDW EXR D.USD.EUR.SP00.A (media mensual)"',
        '  COP: "TRM Superfinanciera datos.gov.co 32sa-8pi3 x ECB EUR/USD (media mensual)"',
        "rates_to_eur:",
    ]
    for currency in ("USD", "COP"):
        lines.append(f"  {currency}:")
        for month, rate in sorted(rates[currency].items()):
            lines.append(f'    "{month}": {rate}')
    return "\n".join(lines) + "\n"


def main() -> None:
    import datetime

    print(f"[fx] descargando BCE EUR/USD desde {START} ...")
    eurusd = monthly_average(parse_ecb_csv(_fetch(ECB_URL.format(start=START))))
    print(f"[fx]   {len(eurusd)} meses")

    print(f"[fx] descargando TRM COP/USD desde {START} ...")
    trm = monthly_average(parse_trm_json(_fetch(TRM_URL.format(start=START))))
    print(f"[fx]   {len(trm)} meses")

    rates = build_rates(eurusd, trm)
    generated_at = datetime.date.today().isoformat()
    OUTPUT.write_text(render_yaml(rates, generated_at), encoding="utf-8")
    print(f"[fx] escrito {OUTPUT}")
    print(f"[fx]   USD: {len(rates['USD'])} meses | COP: {len(rates['COP'])} meses")


if __name__ == "__main__":
    main()

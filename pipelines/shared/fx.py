"""Conversion de monedas a EUR desde una fuente unica de tasas.

Las tasas viven en pipelines/config/fx.yaml. Este modulo es el unico punto de
lectura, para que gold y los enrichments no puedan divergir.

Regla de diseno: una moneda desconocida devuelve None, nunca 1.0. Un fallo debe
ser visible aguas abajo, no disfrazarse de euros.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

ROOT = Path(__file__).resolve().parents[2]
FX_CONFIG = ROOT / "pipelines" / "config" / "fx.yaml"
FX_HISTORY = ROOT / "pipelines" / "config" / "fx_history.yaml"


@lru_cache(maxsize=1)
def load_fx() -> Dict[str, Any]:
    """Carga fx.yaml (cacheado: se lee una sola vez por proceso)."""
    with open(FX_CONFIG, encoding="utf-8") as handle:
        return yaml.safe_load(handle)


@lru_cache(maxsize=1)
def load_fx_history() -> Dict[str, Any]:
    """Carga fx_history.yaml (cacheado). Lo genera scripts/fx_fetch_history.py."""
    with open(FX_HISTORY, encoding="utf-8") as handle:
        return yaml.safe_load(handle)


@lru_cache(maxsize=1)
def _history_months() -> Dict[str, list]:
    """Meses disponibles por moneda, ordenados. Cacheado para no reordenar en
    cada lote (son 60.709)."""
    rates = load_fx_history().get("rates_to_eur", {})
    return {cur: sorted(months) for cur, months in rates.items()}


def fx_history_range() -> tuple[Optional[str], Optional[str]]:
    """Primer y ultimo mes cubiertos por el historico."""
    months = _history_months().get("USD") or []
    return (months[0], months[-1]) if months else (None, None)


def rate_for_month(currency: Optional[str], when: Optional[str]) -> Optional[float]:
    """Tasa hacia EUR para una moneda en un mes "YYYY-MM".

    EUR no consulta el historico: siempre 1.0.

    Un mes fuera de rango se sujeta al mes mas cercano disponible (no a la tasa
    estatica): sigue siendo un dato real de mercado.
    """
    if not currency or not when:
        return None
    cur = currency.upper()
    if cur == "EUR":
        return 1.0
    months = _history_months().get(cur)
    if not months:
        return None
    key = when if when in set(months) else (months[0] if when < months[0] else months[-1])
    return load_fx_history()["rates_to_eur"][cur].get(key)


def rate_for(currency: Optional[str]) -> Optional[float]:
    """Tasa hacia EUR para una moneda, o None si no esta definida."""
    if not currency:
        return None
    return load_fx().get("rates_to_eur", {}).get(currency.upper())


def to_eur(amount: Optional[float], currency: Optional[str]) -> Optional[float]:
    """Convierte un importe a EUR. Devuelve None si falta el importe o la tasa."""
    if amount is None:
        return None
    rate = rate_for(currency)
    if rate is None:
        return None
    return round(float(amount) * rate, 2)


def to_eur_at(
    amount: Optional[float],
    currency: Optional[str],
    when: Optional[str],
) -> tuple[Optional[float], str]:
    """Convierte a EUR con la tasa del mes de la subasta.

    Devuelve (importe, method) con method en:
      "monthly"          -> tasa del mes (o del mes mas cercano del historico)
      "fallback_static"  -> sin mes utilizable: tasa estatica de fx.yaml
      "unavailable"      -> moneda sin tasa: importe None

    El fallback es por FECHA ausente, NO por moneda ausente: una moneda
    desconocida sigue devolviendo None, nunca 1.0. Son dos fallos distintos y
    solo uno tiene respuesta razonable.

    Devolver el metodo junto al importe es el patron de extract_year(), para
    que el informe pueda contar cuantos lotes usaron el fallback.
    """
    if rate_for(currency) is None and (not currency or currency.upper() != "EUR"):
        return None, "unavailable"

    # EUR nunca se convierte: tasa 1.0 en cualquier mes. Sin este atajo, un lote
    # de Duran sin fecha usable se marcaria "fallback_static" y engordaria el
    # contador de fallback del informe con lotes que NO son aproximados --
    # Duran son 40.442 lotes, asi que dominaria el recuento.
    is_eur = bool(currency) and currency.upper() == "EUR"
    if is_eur:
        return (None if amount is None else round(float(amount), 2)), "monthly"

    if amount is None:
        return None, "monthly" if when else "fallback_static"

    rate = rate_for_month(currency, when)
    if rate is not None:
        return round(float(amount) * rate, 2), "monthly"

    return to_eur(amount, currency), "fallback_static"


def fx_as_of() -> str:
    return str(load_fx().get("as_of", "desconocida"))


def fx_note(fallback_lots: Optional[int] = None) -> str:
    """Texto de descargo para mostrar en el informe."""
    first, last = fx_history_range()
    note = (
        f"Conversion a EUR con la tasa media del MES de cada subasta "
        f"({first} a {last}). Fuentes: BCE (EUR/USD) y TRM de la "
        "Superfinanciera de Colombia (USD/COP). "
        "Sirve para comparar casas entre si, no para valoracion contable."
    )
    if fallback_lots:
        note += (
            f" {fallback_lots:,} lotes sin fecha utilizable se convirtieron con "
            f"la tasa estatica de {fx_as_of()}."
        )
    return note

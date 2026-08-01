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


@lru_cache(maxsize=1)
def load_fx() -> Dict[str, Any]:
    """Carga fx.yaml (cacheado: se lee una sola vez por proceso)."""
    with open(FX_CONFIG, encoding="utf-8") as handle:
        return yaml.safe_load(handle)


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


def fx_as_of() -> str:
    return str(load_fx().get("as_of", "desconocida"))


def fx_note() -> str:
    """Texto de descargo para mostrar en el informe."""
    return (
        f"Conversion a EUR con tasa estatica de {fx_as_of()}. "
        "No usa tasas historicas por fecha de subasta. "
        "Sirve para comparar casas entre si, no para valoracion contable."
    )

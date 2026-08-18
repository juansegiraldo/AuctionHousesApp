"""Shared schema helpers for Silver and Gold pipeline stages."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

# Cada casa guarda la fecha en un formato distinto:
#   Bogota -> ISO ("2024-06-07T19:00")
#   Duran  -> texto en espaniol ("Julio 2014")
# Por eso extract_year() prueba varias estrategias en orden.
_YEAR_RE = re.compile(r"(?:19|20)\d{2}")

# Duran escribe el mes en texto y en espaniol ("Julio 2014"). El anio se acepta
# solo como 19xx/20xx, igual que en extract_year: la propia web de Duran tiene
# el typo "subasta-541-marzo-2107", y preferimos un mes desconocido a uno
# fabricado.
_MONTHS_ES = {
    "enero": "01", "febrero": "02", "marzo": "03", "abril": "04",
    "mayo": "05", "junio": "06", "julio": "07", "agosto": "08",
    "septiembre": "09", "setiembre": "09", "octubre": "10",
    "noviembre": "11", "diciembre": "12",
}
_MONTH_TEXT_RE = re.compile(
    r"(" + "|".join(_MONTHS_ES) + r")[\s\-_]+((?:19|20)\d{2})",
    re.IGNORECASE,
)
_ISO_MONTH_RE = re.compile(r"^((?:19|20)\d{2})-(0[1-9]|1[0-2])")

UNKNOWN_YEAR = "unknown"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def extract_year(
    auction_start_date: Optional[str],
    auction_id: Optional[str] = None,
) -> Tuple[str, str]:
    """Extrae el anio de una subasta.

    Devuelve (year, method) donde method es uno de:
      "iso"        -> fecha ISO estandar (Bogota)
      "text"       -> texto con anio embebido, p.ej. "Julio 2014" (Duran)
      "auction_id" -> inferido del identificador, p.ej. "subasta-504-enero-2014_504-001"
      "unknown"    -> no hay anio recuperable

    Se devuelve el metodo para que el informe pueda avisar cuando un anio fue
    inferido en vez de leido de una fecha real.
    """
    date_str = auction_start_date or ""

    # 1. ISO: los primeros 4 caracteres ya son el anio.
    if len(date_str) >= 4 and date_str[:4].isdigit():
        return date_str[:4], "iso"

    # 2. Texto libre con un anio dentro ("Julio 2014", "Febrero 2015").
    match = _YEAR_RE.search(date_str)
    if match:
        return match.group(0), "text"

    # 3. Ultimo recurso: el slug de la subasta suele llevar el anio.
    if auction_id:
        match = _YEAR_RE.search(auction_id)
        if match:
            return match.group(0), "auction_id"

    return UNKNOWN_YEAR, "unknown"


def extract_month(
    auction_start_date: Optional[str],
    auction_id: Optional[str] = None,
) -> Tuple[Optional[str], str]:
    """Extrae el mes de una subasta como "YYYY-MM".

    Devuelve (month, method) con method en:
      "iso"        -> fecha ISO estandar (Bogota, Zorrilla)
      "text"       -> texto en espaniol, p.ej. "Julio 2014" (Duran)
      "auction_id" -> inferido del slug, p.ej. "subasta-504-enero-2014_504-001"
      "unknown"    -> no hay mes recuperable; el llamante decide el fallback

    Es la hermana de extract_year(). Existe porque la conversion a EUR usa la
    tasa del mes de la subasta: aplicar la tasa de hoy a un lote de 2014
    infravalora ~62% las ventas en COP.
    """
    date_str = auction_start_date or ""

    # 1. ISO: "2022-03-03T20:00" -> "2022-03".
    match = _ISO_MONTH_RE.match(date_str)
    if match:
        return f"{match.group(1)}-{match.group(2)}", "iso"

    # 2. Texto libre en espaniol ("Julio 2014").
    match = _MONTH_TEXT_RE.search(date_str)
    if match:
        return f"{match.group(2)}-{_MONTHS_ES[match.group(1).lower()]}", "text"

    # 3. Ultimo recurso: el slug de la subasta.
    if auction_id:
        match = _MONTH_TEXT_RE.search(auction_id)
        if match:
            return f"{match.group(2)}-{_MONTHS_ES[match.group(1).lower()]}", "auction_id"

    return None, "unknown"


def is_sold(status: Optional[str], price_sold: Optional[float]) -> bool:
    """Determina si un lote se vendio.

    Prioriza el estado explicito cuando existe. Solo si la casa no publica
    estado se recurre a "tiene precio" como aproximacion.

    Ojo: Bogota no publica los lotes NO VENDIDO, asi que su tasa de venta no es
    comparable con la de Duran. Eso se avisa en el informe, no se corrige aqui.
    """
    if status is not None:
        return status.strip().upper() == "VENDIDO"
    return price_sold is not None


def normalize_lot(record: Dict[str, Any], house_slug: str, source_file: str) -> Dict[str, Any]:
    """Normalize a lot record into a Silver-compatible shape."""
    normalized = dict(record)
    normalized["house_slug"] = house_slug
    normalized["ingested_at"] = now_iso()
    normalized["source_file"] = source_file
    normalized["dedupe_key"] = f"{house_slug}|{normalized.get('lot_url', '')}"
    return normalized

"""Shared schema helpers for Silver and Gold pipeline stages."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def normalize_lot(record: Dict[str, Any], house_slug: str, source_file: str) -> Dict[str, Any]:
    """Normalize a lot record into a Silver-compatible shape."""
    normalized = dict(record)
    normalized["house_slug"] = house_slug
    normalized["ingested_at"] = now_iso()
    normalized["source_file"] = source_file
    normalized["dedupe_key"] = f"{house_slug}|{normalized.get('lot_url', '')}"
    return normalized

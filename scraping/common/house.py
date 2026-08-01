"""Per-house configuration contract for the multi-house scraper framework.

A house is fully described by one frozen ``House`` instance (its ``HOUSE`` global in
``scraping/houses/<slug>/house.py``). The shared engine (``runner.py``) is parameterized
by this object, so adding a house means writing ``parsers.py`` + this small config — no
orchestration, retry, resume, checkpoint, or JSONL code per house.

Importing this module must NOT trigger any network access. It does import ``net`` for the
default fetcher, which only re-exports scrapling fetchers (no calls at import time).
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Any, Callable, Optional

from scraping.common.models import AuctionMeta
from scraping.common.net import FetchFn, default_fetcher

# discover(first_page, meta, *, fetch, post, get_session, delay, max_lots,
#          max_retries, timeout_seconds, log) -> list[dict]   (see discovery.py)
DiscoverFn = Callable[..., list[dict]]
# accept_lot(category, fallback_text) -> keep?   (mirrors the legacy is_target_category)
AcceptFn = Callable[[Optional[str], Optional[str]], bool]
# build_meta(auction_url, supplied_meta, first_page, house) -> AuctionMeta
BuildMetaFn = Callable[[str, Optional[AuctionMeta], Any, "House"], AuctionMeta]


@dataclass(frozen=True)
class House:
    """Everything the shared engine needs to scrape one auction house."""

    slug: str                  # MUST equal the registry.json slug
    name: str                  # auction_house_name on AuctionMeta / LotItem
    currency: str              # "COP" | "EUR" | "UYU" ... (replaces the literal in lot builders)
    base_url: str
    historic_url: str
    output_dir: Path           # MUST match the registry.json output_dir
    parsers: ModuleType        # the house's parsers.py module object
    discover: DiscoverFn       # a closure from a factory in discovery.py
    accept_lot: Optional[AcceptFn] = None      # None = accept every lot
    build_meta: Optional[BuildMetaFn] = None   # None = default_build_meta
    fetcher: FetchFn = default_fetcher         # how to download a page (net.py)
    default_delay: float = 1.0
    default_retries: int = 2
    default_timeout: float = 20.0
    historic_delay: float = 1.5
    max_ajax_pages: int = 200

    REQUIRED_PARSER_FUNCS = (
        "_auction_id_from_url",
        "parse_historic_page",
        "parse_auction_page",
        "parse_lot_page",
        "get_auction_title_from_page",
    )

    def __post_init__(self) -> None:
        missing = [
            name for name in self.REQUIRED_PARSER_FUNCS if not hasattr(self.parsers, name)
        ]
        if missing:
            raise AttributeError(
                f"House '{self.slug}' parsers module is missing required functions: {missing}"
            )


def default_build_meta(
    auction_url: str,
    supplied_meta: Optional[AuctionMeta],
    first_page: Any,
    house: "House",
) -> AuctionMeta:
    """Build/repair AuctionMeta from the first page.

    Title comes from the house's get_auction_title_from_page (falling back to the slug).
    Start date is read via an hasattr-guarded optional hook (Duran has it; Bogota does not).
    If a meta was supplied (historic run), it is updated rather than rebuilt.
    """
    parsers = house.parsers
    auction_id = parsers._auction_id_from_url(auction_url)
    title = parsers.get_auction_title_from_page(first_page) or auction_id
    start_date = None
    if hasattr(parsers, "get_auction_start_date_from_page"):
        start_date = parsers.get_auction_start_date_from_page(first_page)

    if supplied_meta is not None:
        update = {"auction_id": auction_id, "auction_title": title or supplied_meta.auction_title, "auction_url": auction_url}
        if start_date and not supplied_meta.auction_start_date:
            update["auction_start_date"] = start_date
        return supplied_meta.model_copy(update=update)

    return AuctionMeta(
        auction_id=auction_id,
        auction_title=title,
        auction_start_date=start_date,
        auction_url=auction_url,
        auction_house_name=house.name,
    )


def load_house(slug: str) -> House:
    """Import scraping.houses.<slug>.house and return its HOUSE instance."""
    module = importlib.import_module(f"scraping.houses.{slug}.house")
    return module.HOUSE

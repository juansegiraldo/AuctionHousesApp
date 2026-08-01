"""Lot-discovery strategies — the one place AJAX-vs-HTML structurally diverges.

Each factory returns a ``discover`` closure with the documented keyword signature::

    discover(first_page, meta, *, fetch, post, get_session,
             delay, max_lots, max_retries, timeout_seconds, log) -> list[dict]

It returns the full list of raw preview dicts (paginated, NOT yet deduped — the engine
dedupes). The engine never branches on house type; it just calls ``house.discover(...)``.

A third discovery mechanism (JSON API, Selenium "load more", ...) is a third factory here,
with no change to the engine. The keyword signature can later be promoted to a
``typing.Protocol`` with zero call-site churn.
"""

from __future__ import annotations

import time
from typing import Any, Callable

from scraping.common.house import DiscoverFn


def html_pagination_discovery(get_page_urls: Callable, parse_auction_page: Callable) -> DiscoverFn:
    """Static HTML pagination (Bogota-style): follow pagination links, parse each page.

    ``get_page_urls(first_page, base_auction_url)`` returns every page URL (incl. the base);
    ``parse_auction_page(page, meta)`` returns preview dicts for one page.
    """

    def discover(
        first_page: Any,
        meta: Any,
        *,
        fetch: Callable[[str], Any],
        post: Callable | None = None,
        get_session: Callable | None = None,
        delay: float = 1.0,
        max_lots: int | None = None,
        max_retries: int = 2,
        timeout_seconds: float = 20.0,
        log: Callable | None = None,
    ) -> list[dict]:
        previews: list[dict] = list(parse_auction_page(first_page, meta))
        base = meta.auction_url
        for page_url in get_page_urls(first_page, base):
            if page_url in {base, base.split("?")[0]}:
                continue
            time.sleep(delay)
            previews.extend(parse_auction_page(fetch(page_url), meta))
        return previews

    return discover


def ajax_infinite_scroll_discovery(
    extract_config: Callable,
    parse_auction_page: Callable,
    category_from_payload: Callable | None = None,
    *,
    html_fallback: Callable | None = None,
    page_size: int = 48,
    max_pages_cap: int = 200,
) -> DiscoverFn:
    """AJAX infinite scroll (Duran-style): prime a session, POST page/actualPage in a loop.

    Lifted as one block from Duran's scrape_auction discovery path: extract the AJAX url +
    form payload, prime a requests.Session to refresh the token, POST incremental pages,
    stop after 2 stagnant pages (no new lot_url), stamp a forced category from the filter
    payload. If there is no AJAX config and ``html_fallback`` (a get_page_urls callable) is
    given, fall through to static pagination.
    """

    def _tag(previews: list[dict], forced: str | None) -> None:
        if forced:
            for preview in previews:
                preview["category"] = preview.get("category") or forced

    def discover(
        first_page: Any,
        meta: Any,
        *,
        fetch: Callable[[str], Any],
        post: Callable,
        get_session: Callable,
        delay: float = 1.0,
        max_lots: int | None = None,
        max_retries: int = 2,
        timeout_seconds: float = 20.0,
        log: Callable | None = None,
    ) -> list[dict]:
        previews: list[dict] = list(parse_auction_page(first_page, meta))
        ajax_url, payload = extract_config(first_page)
        forced = category_from_payload(payload) if category_from_payload else None
        _tag(previews, forced)

        if not (ajax_url and payload):
            if html_fallback is not None:
                base = meta.auction_url
                for page_url in html_fallback(first_page, base):
                    if page_url in {base, base.split("?")[0]}:
                        continue
                    time.sleep(delay)
                    previews.extend(parse_auction_page(fetch(page_url), meta))
            return previews

        session = get_session()
        # Prime cookies/session state and refresh payload/token from this same session.
        primed = session.get(meta.auction_url, timeout=timeout_seconds)
        primed.raise_for_status()
        session_url, session_payload = extract_config(primed.text)
        if session_url:
            ajax_url = session_url
        if session_payload:
            payload = session_payload
            if category_from_payload:
                forced = category_from_payload(payload) or forced

        if max_lots is not None:
            max_pages = max(1, (max_lots // page_size) + 5)
        else:
            max_pages = max_pages_cap

        seen_before = len({p.get("lot_url") for p in previews if p.get("lot_url")})
        stagnant_pages = 0
        for page_number in range(1, max_pages + 1):
            body = dict(payload)
            body["page"] = str(page_number)
            body["actualPage"] = str(page_number)
            html = post(session, ajax_url, body)
            page_previews = list(parse_auction_page(html, meta))
            _tag(page_previews, forced)
            previews.extend(page_previews)
            seen_now = len({p.get("lot_url") for p in previews if p.get("lot_url")})
            if not page_previews or seen_now == seen_before:
                stagnant_pages += 1
                if stagnant_pages >= 2:
                    break
            else:
                stagnant_pages = 0
            seen_before = seen_now
            time.sleep(delay)
        return previews

    return discover

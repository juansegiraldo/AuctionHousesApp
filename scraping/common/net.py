"""House-agnostic networking helpers shared by the multi-house scraper framework.

Lifted (near-verbatim) from the Duran scraper's retry/backoff/log helpers, but made
house-agnostic so every house reuses one implementation:

- the page fetcher is *injectable* (``House.fetcher``) so anti-bot / JS-heavy sites can
  swap ``Fetcher.get`` for ``StealthyFetcher.fetch`` without touching the engine;
- ``log_event`` takes ``house_slug`` as a parameter instead of a module global, keeping
  the structured-log shape (``house_slug`` field) identical to the legacy houses.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Callable

import requests
from scrapling import Fetcher, StealthyFetcher

log = logging.getLogger(__name__)

# A fetcher takes (url, timeout_seconds) and returns a page object exposing ``.css(...)``
# (scrapling Selector) — both Fetcher.get and StealthyFetcher.fetch satisfy this.
FetchFn = Callable[[str, float], Any]

RATE_LIMIT_EXTRA_RETRIES = 3  # extra retries when we get HTTP 429


def default_fetcher(url: str, timeout_seconds: float) -> Any:
    """Plain curl_cffi-backed fetch — what Bogota/Duran use today. No JS, no Cloudflare."""
    return Fetcher.get(url, timeout=timeout_seconds)


def stealthy_fetcher(url: str, timeout_seconds: float) -> Any:
    """Headless-browser fetch for anti-bot / JS-rendered sites (e.g. Zorrilla).

    Playwright timeouts are in milliseconds, so seconds are converted here.
    """
    return StealthyFetcher.fetch(
        url,
        timeout=int(timeout_seconds * 1000),
        solve_cloudflare=True,
        load_dom=True,
    )


def log_event(event: str, *, house_slug: str, **fields: Any) -> None:
    """Emit a structured JSON log line. Shape matches the legacy per-house log_event."""
    payload = {"event": event, "house_slug": house_slug, **fields}
    log.info(json.dumps(payload, ensure_ascii=False))


def fetch_with_retry(
    url: str,
    max_retries: int,
    timeout_seconds: float,
    *,
    fetcher: FetchFn = default_fetcher,
    house_slug: str = "",
    sleep: Callable[[float], None] = time.sleep,
) -> Any:
    """GET ``url`` via ``fetcher`` with exponential backoff. Raises after the limit."""
    last_error = None
    for attempt in range(max_retries + 1):
        try:
            return fetcher(url, timeout_seconds)
        except Exception as exc:  # pragma: no cover - network failures
            last_error = exc
            if attempt >= max_retries:
                break
            backoff = min(8.0, 1.0 * (2**attempt))
            log_event(
                "retry_fetch",
                house_slug=house_slug,
                url=url,
                attempt=attempt + 1,
                backoff=backoff,
                error_type=type(exc).__name__,
            )
            sleep(backoff)
    raise RuntimeError(f"Failed to fetch {url}: {last_error}")


def post_with_retry(
    session: requests.Session,
    url: str,
    data: dict[str, str],
    max_retries: int,
    timeout_seconds: float,
    *,
    house_slug: str = "",
    sleep: Callable[[float], None] = time.sleep,
) -> str:
    """POST ``data`` to ``url`` with backoff and HTTP 429 / Retry-After handling."""
    last_error = None
    effective_max = max_retries + 1
    max_attempts = max_retries + 1 + RATE_LIMIT_EXTRA_RETRIES
    for attempt in range(max_attempts):
        try:
            response = session.post(url, data=data, timeout=timeout_seconds)
            response.raise_for_status()
            return response.text
        except requests.HTTPError as exc:
            last_error = exc
            if exc.response is not None and exc.response.status_code == 429:
                effective_max = max_retries + 1 + RATE_LIMIT_EXTRA_RETRIES
            if attempt >= effective_max - 1:
                break
            # 429 Too Many Requests: use longer backoff and respect Retry-After.
            if exc.response is not None and exc.response.status_code == 429:
                retry_after = exc.response.headers.get("Retry-After")
                if retry_after and retry_after.isdigit():
                    backoff = min(120.0, float(retry_after))
                else:
                    backoff = 20.0
                log_event(
                    "retry_post",
                    house_slug=house_slug,
                    url=url,
                    attempt=attempt + 1,
                    backoff=backoff,
                    error_type="HTTPError",
                    status_code=429,
                )
            else:
                backoff = min(8.0, 1.0 * (2**attempt))
                log_event(
                    "retry_post",
                    house_slug=house_slug,
                    url=url,
                    attempt=attempt + 1,
                    backoff=backoff,
                    error_type=type(exc).__name__,
                )
            sleep(backoff)
        except Exception as exc:  # pragma: no cover - network failures
            last_error = exc
            if attempt >= max_retries:
                break
            backoff = min(8.0, 1.0 * (2**attempt))
            log_event(
                "retry_post",
                house_slug=house_slug,
                url=url,
                attempt=attempt + 1,
                backoff=backoff,
                error_type=type(exc).__name__,
            )
            sleep(backoff)
    raise RuntimeError(f"Failed to post {url}: {last_error}")

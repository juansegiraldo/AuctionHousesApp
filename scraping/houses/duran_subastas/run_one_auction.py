#!/usr/bin/env python3
"""Phase 1: scrape one Duran auction with category filtering and retries."""

from __future__ import annotations

import argparse
import json
import logging
import time
from pathlib import Path
from typing import Callable

import orjson
import requests
from scrapling import Fetcher

from scraping.common.models import AuctionMeta, LotItem
from scraping.houses.duran_subastas.parsers import (
    TARGET_CATEGORIES,
    _auction_id_from_url,
    category_from_filter_payload,
    category_from_text,
    extract_infinite_scroll_config,
    get_auction_start_date_from_page,
    get_auction_page_urls,
    get_auction_title_from_page,
    parse_auction_page,
    parse_lot_page,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

HOUSE_SLUG = "duran_subastas"
HOUSE_NAME = "Duran Arte y Subastas"
HOUSE_DIR = Path(__file__).resolve().parent
DEFAULT_OUTPUT_DIR = HOUSE_DIR / "output"


def log_event(event: str, **fields) -> None:
    payload = {"event": event, "house_slug": HOUSE_SLUG, **fields}
    log.info(json.dumps(payload, ensure_ascii=False))


def fetch_with_retry(
    url: str,
    max_retries: int,
    timeout_seconds: float,
    sleep: Callable[[float], None] = time.sleep,
):
    last_error = None
    for attempt in range(max_retries + 1):
        try:
            return Fetcher.get(url, timeout=timeout_seconds)
        except Exception as exc:  # pragma: no cover - network failures
            last_error = exc
            if attempt >= max_retries:
                break
            backoff = min(8.0, 1.0 * (2**attempt))
            log_event("retry_fetch", url=url, attempt=attempt + 1, backoff=backoff, error_type=type(exc).__name__)
            sleep(backoff)
    raise RuntimeError(f"Failed to fetch {url}: {last_error}")


RATE_LIMIT_EXTRA_RETRIES = 3  # extra retries when we get 429


def post_with_retry(
    session: requests.Session,
    url: str,
    data: dict[str, str],
    max_retries: int,
    timeout_seconds: float,
    sleep: Callable[[float], None] = time.sleep,
) -> str:
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
            # 429 Too Many Requests: use longer backoff and respect Retry-After
            if exc.response is not None and exc.response.status_code == 429:
                retry_after = exc.response.headers.get("Retry-After")
                if retry_after and retry_after.isdigit():
                    backoff = min(120.0, float(retry_after))
                else:
                    backoff = 20.0
                log_event(
                    "retry_post",
                    url=url,
                    attempt=attempt + 1,
                    backoff=backoff,
                    error_type="HTTPError",
                    status_code=429,
                )
            else:
                backoff = min(8.0, 1.0 * (2**attempt))
                log_event("retry_post", url=url, attempt=attempt + 1, backoff=backoff, error_type=type(exc).__name__)
            sleep(backoff)
        except Exception as exc:  # pragma: no cover - network failures
            last_error = exc
            if attempt >= max_retries:
                break
            backoff = min(8.0, 1.0 * (2**attempt))
            log_event("retry_post", url=url, attempt=attempt + 1, backoff=backoff, error_type=type(exc).__name__)
            sleep(backoff)
    raise RuntimeError(f"Failed to post {url}: {last_error}")


def is_target_category(category: str | None, fallback_text: str | None = None) -> bool:
    if category in TARGET_CATEGORIES:
        return True
    if fallback_text:
        return category_from_text(fallback_text) in TARGET_CATEGORIES
    return False


def _lot_from_preview(preview: dict, meta: AuctionMeta) -> LotItem:
    return LotItem(
        auction_id=meta.auction_id,
        auction_title=meta.auction_title,
        auction_start_date=meta.auction_start_date,
        auction_end_date=meta.auction_end_date,
        auction_house_name=meta.auction_house_name,
        auction_url=meta.auction_url,
        auction_info_url=meta.auction_info_url,
        lot_number=preview.get("lot_number"),
        lot_url=preview["lot_url"],
        lot_title=preview.get("lot_title"),
        lot_year=preview.get("lot_year"),
        image_url=preview.get("thumbnail_url"),
        price_estimate_min=preview.get("price_estimate_min"),
        price_estimate_max=preview.get("price_estimate_max"),
        price_sold=preview.get("price_sold"),
        status=preview.get("status"),
        currency="EUR",
    )


def _merge_lot(preview: dict, detail: dict, meta: AuctionMeta, lot_url: str) -> LotItem:
    return LotItem(
        auction_id=detail.get("auction_id", meta.auction_id),
        auction_title=detail.get("auction_title", meta.auction_title),
        auction_start_date=detail.get("auction_start_date", meta.auction_start_date),
        auction_end_date=detail.get("auction_end_date", meta.auction_end_date),
        auction_house_name=detail.get("auction_house_name", meta.auction_house_name),
        auction_url=detail.get("auction_url", meta.auction_url),
        auction_info_url=detail.get("auction_info_url", meta.auction_info_url),
        lot_number=detail.get("lot_number") or preview.get("lot_number"),
        lot_url=lot_url,
        lot_title=detail.get("lot_title") or preview.get("lot_title"),
        lot_year=detail.get("lot_year") or preview.get("lot_year"),
        image_url=detail.get("image_url") or preview.get("thumbnail_url"),
        price_estimate_min=detail.get("price_estimate_min") or preview.get("price_estimate_min"),
        price_estimate_max=detail.get("price_estimate_max") or preview.get("price_estimate_max"),
        price_sold=detail.get("price_sold") or preview.get("price_sold"),
        currency=detail.get("currency", "EUR"),
        artist_name=detail.get("artist_name"),
        artist_birth_year=detail.get("artist_birth_year"),
        artist_death_year=detail.get("artist_death_year"),
        artist_country=detail.get("artist_country"),
        artist_raw=detail.get("artist_raw"),
        description=detail.get("description"),
        medium=detail.get("medium"),
        dimensions=detail.get("dimensions"),
        provenance=detail.get("provenance"),
        status=detail.get("status") or preview.get("status"),
    )


def scrape_auction(
    auction_url: str,
    output_path: Path,
    delay: float = 1.0,
    skip_lot_detail: bool = False,
    auction_meta: AuctionMeta | None = None,
    max_lots_per_auction: int | None = None,
    max_retries: int = 2,
    timeout_seconds: float = 20.0,
) -> list[LotItem]:
    first_page = fetch_with_retry(auction_url, max_retries=max_retries, timeout_seconds=timeout_seconds)
    auction_title = get_auction_title_from_page(first_page) or _auction_id_from_url(auction_url)
    auction_start_date = get_auction_start_date_from_page(first_page)
    meta = auction_meta or AuctionMeta(
        auction_id=_auction_id_from_url(auction_url),
        auction_title=auction_title,
        auction_start_date=auction_start_date,
        auction_url=auction_url,
        auction_house_name=HOUSE_NAME,
    )
    if auction_meta and auction_start_date and not meta.auction_start_date:
        meta = meta.model_copy(update={"auction_start_date": auction_start_date})
    lot_previews: list[dict] = parse_auction_page(first_page, meta)
    ajax_url, ajax_payload = extract_infinite_scroll_config(first_page)
    forced_category = category_from_filter_payload(ajax_payload)
    if forced_category:
        for preview in lot_previews:
            preview["category"] = preview.get("category") or forced_category

    if ajax_url and ajax_payload:
        session = requests.Session()
        # Prime cookies/session state and refresh payload/token from this same session.
        session_first_page = session.get(auction_url, timeout=timeout_seconds)
        session_first_page.raise_for_status()
        session_ajax_url, session_ajax_payload = extract_infinite_scroll_config(session_first_page.text)
        if session_ajax_url:
            ajax_url = session_ajax_url
        if session_ajax_payload:
            ajax_payload = session_ajax_payload
            forced_category = category_from_filter_payload(ajax_payload) or forced_category
        if max_lots_per_auction is not None:
            max_pages = max(1, (max_lots_per_auction // 48) + 5)
        else:
            max_pages = 200
        seen_before = len({p.get("lot_url") for p in lot_previews if p.get("lot_url")})
        stagnant_pages = 0
        for page_number in range(1, max_pages + 1):
            payload = dict(ajax_payload)
            payload["page"] = str(page_number)
            payload["actualPage"] = str(page_number)
            html = post_with_retry(
                session,
                ajax_url,
                payload,
                max_retries=max_retries,
                timeout_seconds=timeout_seconds,
            )
            page_previews = parse_auction_page(html, meta)
            if forced_category:
                for preview in page_previews:
                    preview["category"] = preview.get("category") or forced_category
            lot_previews.extend(page_previews)
            seen_now = len({p.get("lot_url") for p in lot_previews if p.get("lot_url")})
            if not page_previews or seen_now == seen_before:
                stagnant_pages += 1
                if stagnant_pages >= 2:
                    break
            else:
                stagnant_pages = 0
            seen_before = seen_now
            time.sleep(delay)
    else:
        # Fallback path for pages where lots are directly embedded in links.
        all_page_urls = get_auction_page_urls(first_page, auction_url)
        for page_url in all_page_urls:
            if page_url == auction_url or page_url == auction_url.split("?")[0]:
                continue
            time.sleep(delay)
            page = fetch_with_retry(page_url, max_retries=max_retries, timeout_seconds=timeout_seconds)
            page_previews = parse_auction_page(page, meta)
            if forced_category:
                for preview in page_previews:
                    preview["category"] = preview.get("category") or forced_category
            lot_previews.extend(page_previews)

    deduped: list[dict] = []
    seen = set()
    for preview in lot_previews:
        lot_url = preview.get("lot_url")
        if not lot_url or lot_url in seen:
            continue
        seen.add(lot_url)
        preview_category = preview.get("category")
        if preview_category and preview_category not in TARGET_CATEGORIES:
            log_event(
                "lot_filtered_discovery",
                auction_id=meta.auction_id,
                lot_url=lot_url,
                category=preview_category,
                reason="category_excluded",
            )
            continue
        deduped.append(preview)

    if max_lots_per_auction is not None:
        deduped = deduped[:max_lots_per_auction]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    accepted: list[LotItem] = []

    with open(output_path, "wb") as out_file:
        for idx, preview in enumerate(deduped, 1):
            lot_url = preview["lot_url"]
            if skip_lot_detail:
                detail = {}
                lot_data = _lot_from_preview(preview, meta)
            else:
                time.sleep(delay)
                lot_page = fetch_with_retry(lot_url, max_retries=max_retries, timeout_seconds=timeout_seconds)
                detail = parse_lot_page(lot_page, meta)
                lot_data = _merge_lot(preview, detail, meta, lot_url)

            category = detail.get("category") or preview.get("category")
            if not is_target_category(category, fallback_text=f"{lot_data.lot_title or ''} {lot_data.description or ''}"):
                log_event(
                    "lot_filtered",
                    auction_id=meta.auction_id,
                    lot_url=lot_url,
                    reason="category_excluded",
                    category=category,
                )
                continue

            accepted.append(lot_data)
            out_file.write(orjson.dumps(lot_data.model_dump(), option=orjson.OPT_APPEND_NEWLINE))
            log_event("lot_persisted", auction_id=meta.auction_id, idx=idx, lot_url=lot_url, category=category)

    log_event("auction_done", auction_id=meta.auction_id, accepted_lots=len(accepted), output=str(output_path))
    return accepted


def main() -> None:
    parser = argparse.ArgumentParser(description="Scrape one Duran auction.")
    parser.add_argument("auction_url", help="Auction URL")
    parser.add_argument("-o", "--output", default=None, help="Output JSONL path")
    parser.add_argument("-d", "--delay", type=float, default=1.0, help="Delay between requests")
    parser.add_argument("--quick", action="store_true", help="Skip lot detail")
    parser.add_argument("--max-lots-per-auction", type=int, default=None)
    parser.add_argument("--max-retries", type=int, default=2)
    parser.add_argument("--timeout", type=float, default=20.0)
    args = parser.parse_args()

    output_path = Path(args.output) if args.output else (DEFAULT_OUTPUT_DIR / f"{_auction_id_from_url(args.auction_url)}.jsonl")
    scrape_auction(
        args.auction_url,
        output_path,
        delay=args.delay,
        skip_lot_detail=args.quick,
        max_lots_per_auction=args.max_lots_per_auction,
        max_retries=args.max_retries,
        timeout_seconds=args.timeout,
    )


if __name__ == "__main__":
    main()


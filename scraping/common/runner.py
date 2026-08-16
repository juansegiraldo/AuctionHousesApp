"""The single shared scraping engine, parameterized by a ``House``.

This holds the orchestration that was ~90% duplicated between houses: meta building,
lot-preview discovery (delegated to ``house.discover``), dedupe, the (lenient) per-lot
detail fetch, the currency-parameterized lot builders, JSONL writing, and the three
phase CLIs (one-auction / auction-list / historic) with resume + checkpoints + workers.

Per-lot error handling is LENIENT: a lot whose detail page fails to parse is logged and
skipped, the auction continues (chosen as the unified default for massive runs).

The ``run_*_cli`` helpers resolve ``scrape_auction`` / ``fetch_historic`` /
``DEFAULT_OUTPUT_DIR`` / ``_auction_id_from_url`` from the *shim module's* ``globals()``
at call time, so each house exposes its own module-level names and the
``python -m scraping.houses.<slug>.run_historic ...`` invocation stays identical.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import time
from pathlib import Path
from typing import Any, Callable

import orjson
import requests

from scraping.common import checkpoints, net
from scraping.common.house import House, default_build_meta
from scraping.common.models import AuctionMeta, LotItem


# ---------------------------------------------------------------------------
# Lot builders — formerly duplicated per house, now one copy each, currency-parameterized.
# ---------------------------------------------------------------------------

def _lot_from_preview(preview: dict, meta: AuctionMeta, currency: str) -> LotItem:
    """Construye el lote solo con el preview (ruta --quick / skip_lot_detail).

    Copia TAMBIEN los campos descriptivos (description, artist_*, medium,
    dimensions, provenance) cuando el preview los trae. Antes solo los copiaba
    _merge_lot, asi que una casa cuyo listado ya incluye la descripcion —
    Zorrilla via LiveAuctioneers— la perdia entera al correr con --quick: el
    parser la extraia y el engine la tiraba. Un `.get()` de mas aqui no cuesta
    nada y evita re-scrapear 11.000 lotes para recuperar un dato que ya estaba
    descargado.
    """
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
        image_url=preview.get("image_url") or preview.get("thumbnail_url"),
        price_estimate_min=preview.get("price_estimate_min"),
        price_estimate_max=preview.get("price_estimate_max"),
        price_sold=preview.get("price_sold"),
        status=preview.get("status"),
        currency=currency,
        artist_name=preview.get("artist_name"),
        artist_birth_year=preview.get("artist_birth_year"),
        artist_death_year=preview.get("artist_death_year"),
        artist_country=preview.get("artist_country"),
        artist_raw=preview.get("artist_raw"),
        description=preview.get("description"),
        medium=preview.get("medium"),
        dimensions=preview.get("dimensions"),
        provenance=preview.get("provenance"),
    )


def _merge_lot(preview: dict, detail: dict, meta: AuctionMeta, lot_url: str, currency: str) -> LotItem:
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
        currency=detail.get("currency", currency),
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


# ---------------------------------------------------------------------------
# Phase 1: scrape one auction.
# ---------------------------------------------------------------------------

def scrape_auction(
    house: House,
    auction_url: str,
    output_path: Path,
    *,
    delay: float | None = None,
    skip_lot_detail: bool = False,
    auction_meta: AuctionMeta | None = None,
    max_lots_per_auction: int | None = None,
    max_retries: int | None = None,
    timeout_seconds: float | None = None,
) -> list[LotItem]:
    delay = house.default_delay if delay is None else delay
    max_retries = house.default_retries if max_retries is None else max_retries
    timeout_seconds = house.default_timeout if timeout_seconds is None else timeout_seconds

    def log(event: str, **fields: Any) -> None:
        net.log_event(event, house_slug=house.slug, **fields)

    def fetch(url: str) -> Any:
        return net.fetch_with_retry(
            url, max_retries, timeout_seconds, fetcher=house.fetcher, house_slug=house.slug
        )

    def post(session: requests.Session, url: str, data: dict[str, str]) -> str:
        return net.post_with_retry(
            session, url, data, max_retries, timeout_seconds, house_slug=house.slug
        )

    first_page = fetch(auction_url)
    build_meta = house.build_meta or default_build_meta
    meta = build_meta(auction_url, auction_meta, first_page, house)

    previews = list(
        house.discover(
            first_page,
            meta,
            fetch=fetch,
            post=post,
            get_session=requests.Session,
            delay=delay,
            max_lots=max_lots_per_auction,
            max_retries=max_retries,
            timeout_seconds=timeout_seconds,
            log=log,
        )
    )

    # Dedupe by lot_url (preserve order); discovery-stage category filter.
    deduped: list[dict] = []
    seen: set[str] = set()
    for preview in previews:
        lot_url = preview.get("lot_url")
        if not lot_url or lot_url in seen:
            continue
        seen.add(lot_url)
        category = preview.get("category")
        if house.accept_lot and category and not house.accept_lot(category, None):
            log("lot_filtered_discovery", auction_id=meta.auction_id, lot_url=lot_url, category=category)
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
                detail: dict = {}
                lot = _lot_from_preview(preview, meta, house.currency)
            else:
                time.sleep(delay)
                try:
                    detail = house.parsers.parse_lot_page(fetch(lot_url), meta)
                except Exception as exc:  # lenient: skip a bad lot, keep the auction going
                    log("lot_detail_failed", auction_id=meta.auction_id, lot_url=lot_url, error=str(exc))
                    detail = {}
                lot = _merge_lot(preview, detail, meta, lot_url, house.currency)

            if house.accept_lot:
                category = detail.get("category") or preview.get("category")
                fallback_text = f"{lot.lot_title or ''} {lot.description or ''}"
                if not house.accept_lot(category, fallback_text):
                    log("lot_filtered", auction_id=meta.auction_id, lot_url=lot_url, category=category)
                    continue

            accepted.append(lot)
            out_file.write(orjson.dumps(lot.model_dump(), option=orjson.OPT_APPEND_NEWLINE))
            log("lot_persisted", auction_id=meta.auction_id, idx=idx, lot_url=lot_url)

    log("auction_done", auction_id=meta.auction_id, accepted_lots=len(accepted), output=str(output_path))
    return accepted


# ---------------------------------------------------------------------------
# CLI helpers. They read house-bound names from the shim module's globals().
# ---------------------------------------------------------------------------

def _g(module_globals: dict, name: str) -> Any:
    try:
        return module_globals[name]
    except KeyError as exc:  # pragma: no cover - misconfigured shim
        raise RuntimeError(f"Runner CLI expected '{name}' in the shim module globals") from exc


def run_one_auction_cli(module_globals: dict) -> None:
    house: House = _g(module_globals, "HOUSE")
    scrape = _g(module_globals, "scrape_auction")
    default_output_dir: Path = _g(module_globals, "DEFAULT_OUTPUT_DIR")
    auction_id_from_url = house.parsers._auction_id_from_url

    parser = argparse.ArgumentParser(description=f"Scrape one {house.name} auction.")
    parser.add_argument("auction_url", help="Auction URL")
    parser.add_argument("-o", "--output", default=None, help="Output JSONL path")
    parser.add_argument("-d", "--delay", type=float, default=house.default_delay)
    parser.add_argument("--quick", action="store_true", help="Skip lot detail")
    parser.add_argument("--max-lots-per-auction", type=int, default=None)
    parser.add_argument("--max-retries", type=int, default=house.default_retries)
    parser.add_argument("--timeout", type=float, default=house.default_timeout)
    args = parser.parse_args()

    output_path = (
        Path(args.output)
        if args.output
        else default_output_dir / f"{auction_id_from_url(args.auction_url)}.jsonl"
    )
    lots = scrape(
        args.auction_url,
        output_path,
        delay=args.delay,
        skip_lot_detail=args.quick,
        max_lots_per_auction=args.max_lots_per_auction,
        max_retries=args.max_retries,
        timeout_seconds=args.timeout,
    )
    print(f"\nDone. {len(lots)} lots scraped -> {output_path}")


def run_auction_list_cli(module_globals: dict) -> None:
    house: House = _g(module_globals, "HOUSE")
    scrape = _g(module_globals, "scrape_auction")
    default_output_dir: Path = _g(module_globals, "DEFAULT_OUTPUT_DIR")
    auction_id_from_url = house.parsers._auction_id_from_url

    parser = argparse.ArgumentParser(description=f"Scrape multiple {house.name} auctions.")
    parser.add_argument("urls", nargs="*", help="Auction URLs")
    parser.add_argument("-f", "--file", default=None, help="One URL per line")
    parser.add_argument("-o", "--output", default=None, help="Merged output file")
    parser.add_argument("-d", "--delay", type=float, default=house.default_delay)
    parser.add_argument("--quick", action="store_true")
    parser.add_argument("--max-lots-per-auction", type=int, default=None)
    parser.add_argument("--max-retries", type=int, default=house.default_retries)
    parser.add_argument("--timeout", type=float, default=house.default_timeout)
    args = parser.parse_args()

    urls = list(args.urls)
    if args.file:
        with open(args.file, encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if line and not line.startswith("#"):
                    urls.append(line)
    if not urls:
        parser.error("No auction URLs provided.")

    default_output_dir.mkdir(parents=True, exist_ok=True)
    merged_path = Path(args.output) if args.output else None
    total_lots = 0
    for index, auction_url in enumerate(urls, 1):
        out = default_output_dir / f"{auction_id_from_url(auction_url)}.jsonl"
        lots = scrape(
            auction_url,
            out,
            delay=args.delay,
            skip_lot_detail=args.quick,
            max_lots_per_auction=args.max_lots_per_auction,
            max_retries=args.max_retries,
            timeout_seconds=args.timeout,
        )
        total_lots += len(lots)
        if index < len(urls):
            time.sleep(args.delay * 2)

    if merged_path and len(urls) > 1:
        merged_path.parent.mkdir(parents=True, exist_ok=True)
        with open(merged_path, "wb") as out_handle:
            for auction_url in urls:
                src = default_output_dir / f"{auction_id_from_url(auction_url)}.jsonl"
                if src.exists():
                    with open(src, "rb") as in_handle:
                        out_handle.write(in_handle.read())
    print(f"Done. {total_lots} lots scraped in {len(urls)} auctions.")


def run_historic_cli(module_globals: dict) -> None:
    house: House = _g(module_globals, "HOUSE")
    scrape = _g(module_globals, "scrape_auction")
    fetch_historic = _g(module_globals, "fetch_historic")
    default_output_dir: Path = _g(module_globals, "DEFAULT_OUTPUT_DIR")
    auction_id_from_url = house.parsers._auction_id_from_url

    parser = argparse.ArgumentParser(description=f"Scrape {house.name} historic auctions.")
    parser.add_argument("--url", default=house.historic_url)
    parser.add_argument("-o", "--output", default=None, help="Merged output")
    parser.add_argument("-d", "--delay", type=float, default=house.historic_delay)
    parser.add_argument("--list-only", action="store_true")
    parser.add_argument("--start-from", default=None)
    parser.add_argument("--quick", action="store_true")
    parser.add_argument("--max-auctions", type=int, default=None)
    parser.add_argument("--max-lots-per-auction", type=int, default=None)
    parser.add_argument("--max-retries", type=int, default=house.default_retries)
    parser.add_argument("--timeout", type=float, default=house.default_timeout)
    parser.add_argument("--workers", type=int, default=1, help="Parallel auctions to scrape")
    parser.add_argument(
        "--auction-timeout",
        type=float,
        default=None,
        help="Per-auction timeout in seconds when workers > 1 (default: 600)",
    )
    args = parser.parse_args()
    workers = max(1, args.workers)
    auction_timeout = args.auction_timeout if args.auction_timeout is not None else (600.0 if workers > 1 else None)

    default_output_dir.mkdir(parents=True, exist_ok=True)
    checkpoint_dir = default_output_dir / "checkpoints"
    merged_path = Path(args.output) if args.output else (default_output_dir / "historic_all_lots.jsonl")

    def output_path_for(auction: AuctionMeta) -> Path:
        return default_output_dir / f"{auction_id_from_url(auction.auction_url)}.jsonl"

    auctions = fetch_historic(args.url, max_retries=args.max_retries, timeout_seconds=args.timeout)
    checkpoints.save_auction_index(auctions, default_output_dir / "auction_index.jsonl")

    if args.start_from:
        for idx, auction in enumerate(auctions):
            if args.start_from in auction.auction_id or args.start_from in auction.auction_url:
                auctions = auctions[idx:]
                break
    if args.max_auctions is not None:
        auctions = auctions[: args.max_auctions]

    if args.list_only:
        for auction in auctions:
            print(f"{auction.auction_id} -> {auction.auction_url}")
        return

    def _log(event: str, **fields: Any) -> None:
        net.log_event(event, house_slug=house.slug, **fields)

    total_lots = 0
    if workers == 1:
        for auction in auctions:
            auction_id = auction_id_from_url(auction.auction_url)
            individual_path = output_path_for(auction)
            if individual_path.exists():
                checkpoints.write_checkpoint(
                    checkpoint_dir, auction_id,
                    {"status": "skipped_existing", "auction_id": auction_id, "output": str(individual_path)},
                )
                continue
            try:
                lots = scrape(
                    auction.auction_url,
                    individual_path,
                    delay=args.delay,
                    skip_lot_detail=args.quick,
                    auction_meta=auction,
                    max_lots_per_auction=args.max_lots_per_auction,
                    max_retries=args.max_retries,
                    timeout_seconds=args.timeout,
                )
                checkpoints.write_checkpoint(
                    checkpoint_dir, auction_id,
                    {"status": "done", "auction_id": auction_id, "accepted_lots": len(lots)},
                )
            except Exception as exc:  # pragma: no cover - network dependent
                checkpoints.write_checkpoint(
                    checkpoint_dir, auction_id,
                    {"status": "failed", "auction_id": auction_id, "error_type": type(exc).__name__, "error": str(exc)},
                )
                _log("auction_failed", auction_id=auction_id, error_type=type(exc).__name__, message=str(exc))
                continue
            time.sleep(args.delay * 2)
    else:
        if workers > 16:
            _log("worker_warning", workers=workers, message="High worker count may trigger HTTP 419")
        existing: list[tuple[str, Path]] = []
        pending: list[tuple[AuctionMeta, Path]] = []
        for auction in auctions:
            auction_id = auction_id_from_url(auction.auction_url)
            individual_path = output_path_for(auction)
            if individual_path.exists():
                existing.append((auction_id, individual_path))
            else:
                pending.append((auction, individual_path))
        for auction_id, individual_path in existing:
            checkpoints.write_checkpoint(
                checkpoint_dir, auction_id,
                {"status": "skipped_existing", "auction_id": auction_id, "output": str(individual_path)},
            )

        def _scrape_pending(auction: AuctionMeta, output_path: Path) -> int:
            lots = scrape(
                auction.auction_url,
                output_path,
                delay=args.delay,
                skip_lot_detail=args.quick,
                auction_meta=auction,
                max_lots_per_auction=args.max_lots_per_auction,
                max_retries=args.max_retries,
                timeout_seconds=args.timeout,
            )
            return len(lots)

        futures: dict[concurrent.futures.Future, AuctionMeta] = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
            for auction, output_path in pending:
                futures[pool.submit(_scrape_pending, auction, output_path)] = auction
            for future, auction in futures.items():
                auction_id = auction_id_from_url(auction.auction_url)
                try:
                    accepted = future.result(timeout=auction_timeout) if auction_timeout is not None else future.result()
                    checkpoints.write_checkpoint(
                        checkpoint_dir, auction_id,
                        {"status": "done", "auction_id": auction_id, "accepted_lots": accepted},
                    )
                except concurrent.futures.TimeoutError:
                    checkpoints.write_checkpoint(
                        checkpoint_dir, auction_id,
                        {"status": "failed", "auction_id": auction_id, "error_type": "TimeoutError",
                         "error": "auction_timeout", "timeout_seconds": auction_timeout},
                    )
                    _log("auction_failed", auction_id=auction_id, error_type="TimeoutError", message="auction_timeout")
                    future.cancel()
                except Exception as exc:  # pragma: no cover - network dependent
                    checkpoints.write_checkpoint(
                        checkpoint_dir, auction_id,
                        {"status": "failed", "auction_id": auction_id, "error_type": type(exc).__name__, "error": str(exc)},
                    )
                    _log("auction_failed", auction_id=auction_id, error_type=type(exc).__name__, message=str(exc))
                    continue
        _log("parallel_done", workers=workers, pending=len(pending), skipped_existing=len(existing))

    merged_count = checkpoints.merge_outputs(auctions, output_path_for, merged_path)
    _log("historic_done", total_lots=merged_count, merged_output=str(merged_path))

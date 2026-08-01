"""Tests for the shared engine: scrape_auction (dedupe, lenient detail, filter, fetcher)."""

from pathlib import Path
from types import ModuleType, SimpleNamespace

import orjson

from scraping.common import runner
from scraping.common.house import House


def _make_parsers(*, lot_detail=None, raise_on_detail=False):
    """Build a fake parsers module the engine can drive.

    Discovery is injected separately, so parsers only needs the required functions the
    engine itself calls: _auction_id_from_url, get_auction_title_from_page, parse_lot_page.
    parse_historic_page / parse_auction_page exist only to satisfy the House contract.
    """
    mod = ModuleType("fake_parsers")
    mod._auction_id_from_url = lambda url: url.rstrip("/").split("/")[-1]
    mod.get_auction_title_from_page = lambda page: "Test Auction"
    mod.parse_historic_page = lambda page: []
    mod.parse_auction_page = lambda page, meta=None: []

    def parse_lot_page(page, meta=None):
        if raise_on_detail:
            raise ValueError("bad lot page")
        return dict(lot_detail or {})

    mod.parse_lot_page = parse_lot_page
    return mod


def _make_house(tmp_path, parsers, *, accept_lot=None, fetcher=None, discover=None):
    used = {"fetched": []}

    def default_discover(first_page, meta, *, fetch, post, get_session, delay,
                         max_lots, max_retries, timeout_seconds, log):
        # two distinct lots + one duplicate
        return [
            {"lot_url": "http://h/lot/1", "lot_title": "One", "category": "pintura"},
            {"lot_url": "http://h/lot/2", "lot_title": "Two", "category": "joyas"},
            {"lot_url": "http://h/lot/1", "lot_title": "Dup", "category": "pintura"},
        ]

    def spy_fetcher(url, timeout_seconds):
        used["fetched"].append(url)
        return f"<page {url}>"

    house = House(
        slug="testhouse", name="Test House", currency="UYU",
        base_url="http://h", historic_url="http://h/historic",
        output_dir=tmp_path / "output",
        parsers=parsers,
        discover=discover or default_discover,
        accept_lot=accept_lot,
        fetcher=fetcher or spy_fetcher,
        default_delay=0, default_retries=0, default_timeout=1,
    )
    return house, used


def _read_jsonl(path):
    return [orjson.loads(line) for line in path.read_bytes().splitlines() if line.strip()]


def test_scrape_auction_dedupes_and_sets_currency(tmp_path):
    parsers = _make_parsers(lot_detail={"artist_name": "Picasso", "price_sold": 100})
    house, used = _make_house(tmp_path, parsers)
    out = tmp_path / "out.jsonl"

    lots = runner.scrape_auction(house, "http://h/auction/7", out)

    assert len(lots) == 2  # duplicate lot/1 collapsed
    rows = _read_jsonl(out)
    assert {r["lot_url"] for r in rows} == {"http://h/lot/1", "http://h/lot/2"}
    assert all(r["currency"] == "UYU" for r in rows)
    assert all(r["artist_name"] == "Picasso" for r in rows)
    assert all(r["auction_house_name"] == "Test House" for r in rows)


def test_scrape_auction_lenient_on_detail_error(tmp_path):
    # parse_lot_page raises for every lot; lots must still be written (from preview).
    parsers = _make_parsers(raise_on_detail=True)
    house, used = _make_house(tmp_path, parsers)
    out = tmp_path / "out.jsonl"

    lots = runner.scrape_auction(house, "http://h/auction/7", out)

    assert len(lots) == 2  # not aborted by the failing detail pages
    rows = _read_jsonl(out)
    assert {r["lot_title"] for r in rows} == {"One", "Two"}  # from preview


def test_accept_lot_none_keeps_everything(tmp_path):
    parsers = _make_parsers(lot_detail={})
    house, _ = _make_house(tmp_path, parsers, accept_lot=None)
    out = tmp_path / "out.jsonl"
    lots = runner.scrape_auction(house, "http://h/auction/7", out)
    assert len(lots) == 2


def test_accept_lot_filters_by_category(tmp_path):
    parsers = _make_parsers(lot_detail={})

    def only_pintura(category, fallback_text):
        return category == "pintura"

    house, _ = _make_house(tmp_path, parsers, accept_lot=only_pintura)
    out = tmp_path / "out.jsonl"
    lots = runner.scrape_auction(house, "http://h/auction/7", out)
    # lot/2 (joyas) filtered at discovery stage; only lot/1 (pintura) survives
    assert len(lots) == 1
    assert lots[0].lot_url == "http://h/lot/1"


def test_scrape_auction_uses_house_fetcher(tmp_path):
    parsers = _make_parsers(lot_detail={})
    house, used = _make_house(tmp_path, parsers)
    out = tmp_path / "out.jsonl"
    runner.scrape_auction(house, "http://h/auction/7", out)
    # the injected spy fetcher saw the first page + each (deduped) lot detail page
    assert "http://h/auction/7" in used["fetched"]
    assert "http://h/lot/1" in used["fetched"]
    assert "http://h/lot/2" in used["fetched"]


def test_skip_lot_detail_does_not_fetch_lots(tmp_path):
    parsers = _make_parsers(raise_on_detail=True)  # would raise if called
    house, used = _make_house(tmp_path, parsers)
    out = tmp_path / "out.jsonl"
    lots = runner.scrape_auction(house, "http://h/auction/7", out, skip_lot_detail=True)
    assert len(lots) == 2
    assert used["fetched"] == ["http://h/auction/7"]  # only the first page

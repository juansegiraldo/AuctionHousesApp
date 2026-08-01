"""Tests for the discovery strategies (HTML pagination + AJAX infinite scroll)."""

from types import SimpleNamespace

from scraping.common.discovery import ajax_infinite_scroll_discovery, html_pagination_discovery

META = SimpleNamespace(auction_url="http://h/auction/1")


def _previews(*urls):
    return [{"lot_url": u} for u in urls]


# ---------------- HTML pagination ----------------

def test_html_pagination_walks_all_pages():
    pages = {
        "FIRST": _previews("l1", "l2"),
        "http://h/auction/1?page=2": _previews("l3"),
    }

    def parse_auction_page(page, meta):
        return pages[page]

    def get_page_urls(first_page, base):
        return [base, "http://h/auction/1?page=2"]  # base is skipped

    def fetch(url):
        return url

    discover = html_pagination_discovery(get_page_urls, parse_auction_page)
    out = discover("FIRST", META, fetch=fetch, delay=0)
    assert {p["lot_url"] for p in out} == {"l1", "l2", "l3"}


# ---------------- AJAX infinite scroll ----------------

class _FakeSession:
    def get(self, url, timeout):
        return SimpleNamespace(text="PRIMED", raise_for_status=lambda: None)


def test_ajax_stops_after_stagnant_pages():
    # Page 1 returns new lots; pages 2 and 3 return the same (stagnant) -> stop.
    ajax_pages = {
        "1": _previews("a1", "a2"),
        "2": [],
        "3": [],
    }

    def parse_auction_page(page, meta):
        if page == "FIRST" or page == "PRIMED":
            return []
        return ajax_pages.get(page, [])

    def extract_config(page):
        return ("http://h/ajax", {"token": "t"})

    posts = []

    def post(session, url, body):
        posts.append(body["page"])
        return body["page"]  # the page number string is what parse_auction_page keys on

    discover = ajax_infinite_scroll_discovery(extract_config, parse_auction_page)
    out = discover(
        "FIRST", META, fetch=lambda u: u, post=post, get_session=_FakeSession,
        delay=0, max_lots=None,
    )
    assert {p["lot_url"] for p in out} == {"a1", "a2"}
    # stops after 2 stagnant pages: posts pages 1, 2, 3
    assert posts == ["1", "2", "3"]


def test_ajax_falls_back_to_html_when_no_config():
    def parse_auction_page(page, meta):
        return {"FIRST": _previews("f1"), "http://h/auction/1?page=2": _previews("f2")}[page]

    def extract_config(page):
        return (None, {})  # no AJAX config -> fallback

    def get_page_urls(first_page, base):
        return [base, "http://h/auction/1?page=2"]

    discover = ajax_infinite_scroll_discovery(
        extract_config, parse_auction_page, html_fallback=get_page_urls
    )
    out = discover(
        "FIRST", META, fetch=lambda u: u, post=None, get_session=_FakeSession, delay=0,
    )
    assert {p["lot_url"] for p in out} == {"f1", "f2"}

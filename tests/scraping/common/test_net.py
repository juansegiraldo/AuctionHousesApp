"""Tests for the shared networking helpers (retry/backoff, 429 handling, injectable fetcher)."""

import pytest
import requests

from scraping.common import net


def test_fetch_with_retry_recovers_after_failures():
    calls = {"n": 0}

    def flaky_fetcher(url, timeout_seconds):
        calls["n"] += 1
        if calls["n"] < 3:
            raise ConnectionError("boom")
        return f"page:{url}"

    result = net.fetch_with_retry(
        "http://x/y", max_retries=3, timeout_seconds=5.0,
        fetcher=flaky_fetcher, sleep=lambda _: None,
    )
    assert result == "page:http://x/y"
    assert calls["n"] == 3


def test_fetch_with_retry_raises_after_limit():
    def always_fail(url, timeout_seconds):
        raise ConnectionError("nope")

    with pytest.raises(RuntimeError):
        net.fetch_with_retry(
            "http://x/y", max_retries=2, timeout_seconds=5.0,
            fetcher=always_fail, sleep=lambda _: None,
        )


def test_fetch_with_retry_uses_injected_fetcher():
    seen = {}

    def custom_fetcher(url, timeout_seconds):
        seen["url"] = url
        seen["timeout"] = timeout_seconds
        return "ok"

    out = net.fetch_with_retry(
        "http://z", max_retries=0, timeout_seconds=12.5,
        fetcher=custom_fetcher, sleep=lambda _: None,
    )
    assert out == "ok"
    assert seen == {"url": "http://z", "timeout": 12.5}


class _FakeResponse:
    def __init__(self, status_code, text="", headers=None):
        self.status_code = status_code
        self.text = text
        self.headers = headers or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            err = requests.HTTPError(f"{self.status_code}")
            err.response = self
            raise err


class _FakeSession:
    def __init__(self, responses):
        self._responses = list(responses)
        self.posts = 0

    def post(self, url, data, timeout):
        self.posts += 1
        return self._responses.pop(0)


def test_post_with_retry_respects_retry_after_on_429():
    slept = []
    session = _FakeSession([
        _FakeResponse(429, headers={"Retry-After": "7"}),
        _FakeResponse(200, text="<html>ok</html>"),
    ])
    out = net.post_with_retry(
        session, "http://api", {"page": "1"}, max_retries=2, timeout_seconds=5.0,
        sleep=slept.append,
    )
    assert out == "<html>ok</html>"
    assert session.posts == 2
    assert slept == [7.0]  # honored Retry-After

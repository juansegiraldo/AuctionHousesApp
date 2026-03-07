import pytest

from scraping.houses.duran_subastas import run_one_auction


def test_fetch_with_retry_recovers(monkeypatch):
    attempts = {"n": 0}

    class DummyResponse:
        html_content = "<html></html>"

    def fake_get(*args, **kwargs):
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise RuntimeError("transient")
        return DummyResponse()

    monkeypatch.setattr(run_one_auction.Fetcher, "get", fake_get)
    response = run_one_auction.fetch_with_retry("https://example.com", max_retries=3, timeout_seconds=1, sleep=lambda _: None)
    assert isinstance(response, DummyResponse)
    assert attempts["n"] == 3


def test_fetch_with_retry_raises_after_limit(monkeypatch):
    def always_fail(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(run_one_auction.Fetcher, "get", always_fail)
    with pytest.raises(RuntimeError):
        run_one_auction.fetch_with_retry("https://example.com", max_retries=1, timeout_seconds=1, sleep=lambda _: None)


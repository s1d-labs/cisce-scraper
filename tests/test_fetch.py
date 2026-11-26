"""Tests for the surgical fetch upgrade: fast Scrapling path, challenge detection, solve-only-on-challenge.

No network: backends are monkeypatched. Saved pages come from tests/pages/.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import crawl  # noqa: E402

PAGES = Path(__file__).parent / "pages"


class Hub:
    def __init__(self):
        self.counts, self.blocked = {}, 0

    def metric(self, name, value=1):
        self.counts[name] = self.counts.get(name, 0) + value

    def error(self, n=1):
        self.metric("errors", n)

    def block(self, n=1):
        self.blocked += n


def saved(name):
    return (PAGES / name).read_text(encoding="utf-8")


def test_a_listing_page_with_a_cloudflare_script_is_not_a_challenge():
    """The real locate.cisce.org pages carry challenge-platform but have school cards; they must use the fast path."""
    page = "<html><script src='/cdn-cgi/challenge-platform/h/b/x.js'></script>" + saved("result-isc-india-p1.html") + "</html>"
    assert not crawl.is_challenge(page)


def test_the_saved_challenge_page_is_detected():
    assert crawl.is_challenge(saved("cloudflare-challenge.html"))


def test_fast_get_reads_the_scrapling_body(monkeypatch):
    """Scrapling 0.5 has an empty str(page.text); the body is in page.body."""
    class Page:
        status = 200
        body = b"<div class='school-card'>x</div>"
        encoding = "utf-8"

    class Fetcher:
        @staticmethod
        def get(url, **kw):
            assert kw["impersonate"] == "chrome"
            return Page()

    monkeypatch.setitem(sys.modules, "scrapling", object())
    monkeypatch.setitem(sys.modules, "scrapling.fetchers", type("m", (), {"Fetcher": Fetcher})())
    assert crawl.fast_get("https://locate.cisce.org/?page=1") == (200, "<div class='school-card'>x</div>")


def test_fast_get_returns_none_when_scrapling_is_missing(monkeypatch):
    monkeypatch.setitem(sys.modules, "scrapling", None)
    assert crawl.fast_get("https://locate.cisce.org/") is None


def test_solve_challenge_is_only_called_for_a_challenge(monkeypatch):
    """The main loop calls solve_challenge on a 403 or a real challenge, never on a good page."""
    calls = []
    monkeypatch.setattr(crawl, "fast_get", lambda url: (200, saved("result-isc-india-p1.html")))
    monkeypatch.setattr(crawl, "solve_challenge", lambda url, hub: (calls.append(url) or ("challenge", "")))
    monkeypatch.setattr(crawl, "stop_flag", lambda: type("E", (), {"is_set": lambda self: False})())
    # No network and no hub: check the decision in isolation through a tiny replay of the loop's condition.
    class Item:
        payload = {"url": "u"}
        key = "k"

    url = Item.payload["url"]
    status, page = crawl.fast_get(url)
    if status == 403 or crawl.is_challenge(page):
        crawl.solve_challenge(url, Hub())
    assert calls == [] and status == 200


def test_solve_challenge_counts_its_request(monkeypatch):
    class Page:
        status = 200
        body = b"<html>real page</html>"
        encoding = "utf-8"

    class StealthyFetcher:
        @staticmethod
        def fetch(url, **kw):
            assert kw["solve_cloudflare"] is True
            return Page()

    monkeypatch.setitem(sys.modules, "scrapling", object())
    monkeypatch.setitem(sys.modules, "scrapling.fetchers", type("m", (), {"StealthyFetcher": StealthyFetcher})())
    hub = Hub()
    assert crawl.solve_challenge("https://nopecha.com/demo/cloudflare", hub) == (200, "<html>real page</html>")
    assert hub.counts["n_http"] == 1 and "t_http_s" in hub.counts

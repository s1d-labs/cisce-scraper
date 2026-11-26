"""The `crawl` task: CISCE affiliated schools from locate.cisce.org (10 schools per listing page).

python crawl.py --local [url]   fetches one page without the hub and prints the records.
python crawl.py --files DIR     parses listing pages saved by hand in a browser (*.html) and prints the records (no network).

Fetch order: Scrapling `Fetcher` first (browser TLS fingerprint, ~0.45 s per page on 57 measured listing pages); a real
Cloudflare challenge then goes to `StealthyFetcher(solve_cloudflare=True)` (about 2 minutes, only when a challenge appears);
an interactive challenge ("Verify you are human") is never clicked. If Cloudflare solving cannot clear it, the run records a
`cloudflare-challenge` failure, closes and exits, so the pool does not keep hitting the site. `requests` is the fallback when
Scrapling is not installed. Plain `challenge-platform` scripts are not a challenge: the page must lack the expected markers.
"""
import gzip
import html
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from urllib.parse import unquote, urlsplit

from scrape_hub_client import HubClient, LocalHub, count_request, stop_flag

PROJECT = os.environ.get("SCRAPE_POOL_PROJECT", "")
SITE = os.environ.get("SITE", "https://locate.cisce.org")
DEADLINE = time.time() + float(os.environ.get("SCRAPE_MAX_HOURS", "1")) * 3600 - 300
MIN_DELAY_S = 5                     # one page every 5 s or more, whatever the hub says

CARD = re.compile(r'<div class="school-card">(.*?)(?=<div class="school-card">|</tbody>)', re.S)
HEAD = re.compile(r'<h6[^>]*>\s*([A-Z]{2,4}\d+)\s*-\s*(.*?)</h6>', re.S)
BODY = re.compile(r'<p class="mb-1">(.*?)</p>', re.S)
BADGE = re.compile(r'class="badge badge-outline-(red|blue|green)[^"]*">\s*(.*?)\s*</span>', re.S)
SITE_LINK = re.compile(r'<a href="([^"]*)"\s+class="[^"]*visit-btn')
LOCATIONS = re.compile(r'const locations = (\{.*?\});\s*$', re.M)
TOTAL = re.compile(r'Showing\s+(\d+)\s+to\s+(\d+)\s+of\s+(\d+)\s+entries')
PIN = re.compile(r"^\d[\d \-]{2,9}$")      # Indian 6-digit PINs ("744 103" too) and foreign postcodes


def text(s):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s))).strip()


def is_challenge(page):
    """True for a Cloudflare check page (non-interactive or interactive) instead of the listing."""
    return bool(re.search(r"<title>\s*(Just a moment|Attention Required)", page)) or "challenge-platform" in page and "school-card" not in page


def listed_total(page):
    m = TOTAL.search(page)
    return int(m.group(3)) if m else None


def split_address(lines):
    """'locality..., district,' / 'state,' / 'PIN, country' -> fields; the raw text stays in `address` too."""
    parts = [p.strip(" .-") for p in ", ".join(lines).split(",") if p.strip(" .-")]   # "562127." and "-208020" occur
    out = {"country": "", "pin": "", "state": "", "district": "", "locality": ""}
    if parts and not PIN.match(parts[-1]):
        out["country"] = parts.pop()
    if parts and PIN.match(parts[-1]):
        out["pin"] = parts.pop().replace(" ", "")
    if parts:
        out["state"] = parts.pop()
    if parts:
        out["district"] = parts.pop()
    out["locality"] = ", ".join(parts)
    return out


ROW = re.compile(r'<tr>\s*<td>\s*<ul>\s*<li><b>([A-Z]{2,4}\d+)</b></li>(.*?)</tr>', re.S)   # the 2023-2025 table layout
LI = re.compile(r"<li>(.*?)</li>", re.S)
STATE_PIN = re.compile(r"^(.*?)\s*-\s*([\d ]{3,9})$")


def parse_table(page):
    """The older layout of locate.cisce.org (2023-2025, `/result` with no filter = every school on one page): one <tr> per
    school; cells: code, name, address lines, "State - PIN", country | phone (in an HTML comment), fax, e-mail, website |
    gender, residence, ASISC | ICSE/ISC/CVE | head. District is not marked: the last address line (a town) goes to locality."""
    out = []
    for code, rest in ROW.findall(page):
        cells = re.split(r"</td>\s*<td>", rest)
        if len(cells) < 5:
            continue
        first = [text(x) for x in LI.findall(cells[0])]
        name, country = first[0], first[-1]
        sp = STATE_PIN.match(first[-2]) if len(first) > 2 else None
        lines = [x for x in first[1:-2] if x]
        contact = cells[1]
        field = lambda label: text(m.group(1)) if (m := re.search(rf"<b>{label}</b>\s*:-?\s*(?:<br\s*/?>)?(.*?)</li>", contact, re.S)) else ""  # noqa: E731
        site = re.search(r'<span id="\d+">(.*?)</span>', contact, re.S)
        kind = [text(x) for x in LI.findall(cells[2])]
        subj = {text(x) for x in LI.findall(cells[3])}
        out.append((code, {
            "code": code, "name": name, "principal": text(" ".join(LI.findall(cells[4]))),
            "address": ", ".join(x for x in first[1:] if x), "country": country,
            "state": sp.group(1).strip() if sp else "", "pin": sp.group(2).replace(" ", "") if sp else "",
            "district": "", "locality": ", ".join(lines),
            "phones": "; ".join(x.strip() for x in field("Phone").split(",") if x.strip()),
            "email": "; ".join(x.strip() for x in field("Email").split(",") if x.strip()),
            "gender": kind[0] if kind else "", "residence": kind[1] if len(kind) > 1 else "", "asisc": "ASISC" in kind,
            "icse": "ICSE" in subj, "isc": "ISC" in subj, "cve": "CVE" in subj,
            "website": text(site.group(1)) if site else "", "lat": None, "lng": None, "listed_total": None,
        }))
    return out


def parse(page):
    """[(affiliation_code, data)] for the schools on one listing page. Pure: tested on saved pages."""
    if '<div class="school-card">' not in page:
        return parse_table(page)
    coords = {}
    m = LOCATIONS.search(page)
    if m:
        for s in json.loads(m.group(1)).get("schools", []):
            coords[s["name"].split(" - ", 1)[0].strip()] = (s.get("lat"), s.get("lng"))
    total, out = listed_total(page), []
    for card in CARD.findall(page):
        h = HEAD.search(card)
        if not h:
            continue
        code, name = h.group(1), text(h.group(2))
        body = BODY.search(card)
        principal, address_lines = "", []
        if body:
            first, _, rest = body.group(1).partition("<br>")
            principal = text(first)
            address_lines = [text(x) for x in rest.split("\n") if text(x)]
        badges = [(c, text(t)) for c, t in BADGE.findall(card)]
        blue = [t for c, t in badges if c == "blue"]
        green = {t for c, t in badges if c == "green"}
        link = SITE_LINK.search(card)
        lat, lng = coords.get(code, (None, None))
        out.append((code, {
            "code": code, "name": name, "principal": principal,
            "address": ", ".join(a.rstrip(",") for a in address_lines), **split_address(address_lines),
            "gender": next((t for c, t in badges if c == "red"), ""),
            "residence": next((t for t in blue if t != "ASISC"), ""),
            "asisc": "ASISC" in blue,
            "icse": "ICSE" in green, "isc": "ISC" in green, "cve": "CVE" in green,
            "website": html.unescape(link.group(1)).strip() if link else "",
            "lat": lat, "lng": lng, "listed_total": total,
        }))
    return out


def fast_get(url, timeout=25):
    """(status, html) from Scrapling's Fetcher, or None when there is no usable answer.

    Scrapling 0.5 puts the body in `page.body`, not `str(page.text)`. A browser TLS fingerprint is enough for the open
    listing pages and costs about 0.45 s; solving is left for the challenge path. `proxy` comes from the pool's SCRAPE_PROXY."""
    try:
        from scrapling.fetchers import Fetcher
    except ImportError:
        return None
    proxy = os.environ.get("SCRAPE_PROXY") or None
    try:
        page = Fetcher.get(url, impersonate="chrome", timeout=timeout, proxy=proxy)
    except Exception:
        return None
    status = getattr(page, "status", None)
    body = getattr(page, "body", None) or b""
    html = body.decode(getattr(page, "encoding", None) or "utf-8", errors="replace")
    return status, html


def solve_challenge(url, hub, timeout=150):
    """(status, html) after Cloudflare solving, or ('challenge', '') when it did not clear.

    This is expensive (about 2 minutes on a real challenge), so it runs only after `fast_get` sees a challenge or a 403."""
    try:
        from scrapling.fetchers import StealthyFetcher
        proxy = os.environ.get("SCRAPE_PROXY") or None
        t = time.time()
        page = StealthyFetcher.fetch(url, headless=True, solve_cloudflare=True, timeout=int(timeout * 1000), proxy=proxy)
        body = getattr(page, "body", None) or b""
        text = body.decode(getattr(page, "encoding", None) or "utf-8", errors="replace")
        status = getattr(page, "status", None)
        count_request(hub, status, time.time() - t)
        if status == 200 and not is_challenge(text):
            return 200, text
    except Exception:
        count_request(hub, None, 0)
    return "challenge", ""


class Browser:
    """One headless Chromium and one context per process (keeps the Cloudflare clearance cookie between pages)."""

    def __init__(self):
        from playwright.sync_api import sync_playwright
        proxy = None
        if os.environ.get("SCRAPE_PROXY"):
            u = urlsplit(os.environ["SCRAPE_PROXY"])
            proxy = {"server": f"http://{u.hostname}:{u.port}", "username": unquote(u.username or ""), "password": unquote(u.password or "")}
        self.pw = sync_playwright().start()
        self.browser = self.pw.chromium.launch(proxy=proxy)
        self.page = self.browser.new_context(locale="en-IN").new_page()

    def get(self, hub, url):
        """(status, html). status None = no answer; 'challenge' = Cloudflare did not let the page through."""
        t = time.time()
        try:
            r = self.page.goto(url, wait_until="domcontentloaded", timeout=60000)
            for _ in range(30):                                 # a non-interactive check reloads by itself
                if "Just a moment" not in self.page.title():
                    break
                self.page.wait_for_timeout(1000)
            page = self.page.content()
        except Exception:
            count_request(hub, None, time.time() - t)
            return None, ""
        status = r.status if r else None
        if is_challenge(page):
            count_request(hub, 403, time.time() - t)
            return "challenge", page
        count_request(hub, 200 if "school-card" in page or TOTAL.search(page) else status, time.time() - t)
        return 200, page

    def close(self):
        self.browser.close()
        self.pw.stop()


def local(url):
    hub = LocalHub()
    t = time.time()
    status, page = fast_get(url) or (None, "")
    count_request(hub, status, time.time() - t)
    if status == 403 or is_challenge(page):
        status, page = solve_challenge(url, hub)
    if status == "challenge":
        b = Browser()
        try:
            status, page = b.get(hub, url)
        finally:
            b.close()
    rows = parse(page) if status == 200 else []
    for rid, data in rows:
        print(json.dumps({"record_id": rid, "data": data}, ensure_ascii=False))
    title = re.search(r"<title>(.*?)</title>", page, re.S)
    print(f"status {status}, title {text(title.group(1)) if title else ''!r}, {len(rows)} records, listed total {listed_total(page)}, counters {hub.counts}", file=sys.stderr)


def main():
    stop = stop_flag()
    hub = HubClient(PROJECT, job_index=int(os.environ.get("SCRAPE_JOB_INDEX", "0")), total_jobs=int(os.environ.get("SCRAPE_TOTAL_JOBS", "1")))
    b = None
    try:
        while time.time() < DEADLINE and not stop.is_set():
            if hub.settings.get("paused"):
                time.sleep(30)
                continue
            items = hub.claim(1, steal=True, retry_failed=True)
            if not items:
                break
            item = items[0]
            url = item["payload"]["url"]
            t = time.time()
            got = fast_get(url)
            if got is None:                            # Scrapling missing or errored: try plain requests
                try:
                    import requests
                    r = requests.get(url, headers={"User-Agent": "s1d-labs scraper (https://github.com/s1d-labs)"}, timeout=25)
                    got = (r.status_code, r.text)
                except Exception:
                    got = (None, "")
            status, page = got
            count_request(hub, status, time.time() - t)
            if status == 403 or is_challenge(page):
                hub.metric("cf_challenge_seen")
                status, page = solve_challenge(url, hub)
            if status == "challenge":
                if b is None:                          # Scrapling could not clear it: keep the last, human-safe tier
                    b = Browser()
                status, page = b.get(hub, url)
            if status == "challenge":
                hub.failure("cloudflare-challenge", item["key"], "Cloudflare challenge did not clear; not clicked", url=item["payload"]["url"])
                hub.complete([item["key"]], "failed", error="cloudflare challenge")
                hub.close("failed", "cloudflare challenge: stopped, no retries from this run")
                return 3
            if status != 200:
                hub.complete([item["key"]], "failed", error=f"page did not load ({status})")
                time.sleep(MIN_DELAY_S)
                continue
            hub.upload_many([(f"pages/{item['key']}.html.gz", gzip.compress(page.encode()), "application/gzip")])
            seen = datetime.now(timezone.utc).date().isoformat()
            rows = parse(page)
            for rid, data in rows:
                hub.record(rid, {**data, "page": item["payload"].get("page"), "seen": seen})
            hub.complete([item["key"]], "done", fetched=len(rows))
            time.sleep(max(MIN_DELAY_S, hub.settings.get("delay_ms", 0) / 1000))
        hub.close("failed", "stopped by signal") if stop.is_set() else hub.close()
    except BaseException as e:
        hub.close("failed", f"{type(e).__name__}: {e}"[:200])
        raise
    finally:
        if b:
            b.close()
    return 0


if __name__ == "__main__":
    if sys.argv[1:2] == ["--files"]:
        from pathlib import Path
        for f in sorted(Path(sys.argv[2]).glob("*.htm*")):
            for rid, data in parse(f.read_text(encoding="utf-8", errors="replace")):
                print(json.dumps({"record_id": rid, "data": {**data, "file": f.name}}, ensure_ascii=False))
    elif sys.argv[1:2] == ["--local"]:
        local(sys.argv[2] if len(sys.argv) > 2 else SITE + "/?page=1")
    else:
        sys.exit(main())

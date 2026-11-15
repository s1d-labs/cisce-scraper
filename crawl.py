"""The `crawl` task: CISCE affiliated schools from locate.cisce.org (10 schools per listing page).

python crawl.py --local [url]   fetches one page without the hub and prints the records.

The site is behind Cloudflare: plain HTTP gets 403, so pages load in headless Chromium (Playwright). A non-interactive check
clears by itself in a few seconds. An interactive challenge ("Verify you are human") is never clicked: the task records a
`cloudflare-challenge` failure, closes the run and exits, so the pool does not keep hitting the site.
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
    parts = [p.strip() for p in ", ".join(lines).split(",") if p.strip()]
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


def parse(page):
    """[(affiliation_code, data)] for the schools on one listing page. Pure: tested on saved pages."""
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
    hub, b = LocalHub(), Browser()
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
        b = Browser()
        while time.time() < DEADLINE and not stop.is_set():
            if hub.settings.get("paused"):
                time.sleep(30)
                continue
            items = hub.claim(1, steal=True, retry_failed=True)
            if not items:
                break
            item = items[0]
            status, page = b.get(hub, item["payload"]["url"])
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
    if sys.argv[1:2] == ["--local"]:
        local(sys.argv[2] if len(sys.argv) > 2 else SITE + "/?page=1")
    else:
        sys.exit(main())

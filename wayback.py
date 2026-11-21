"""CISCE school lists from Wayback Machine copies of the old official locator (www.cisce.org/locate-search.aspx, 2015-2022).

The old locator listed every affiliated school on one page when no filter was set. The Internet Archive holds 148 such copies.
python wayback.py <out_dir>   downloads the copies listed in sources/wayback-full-lists.txt (the last of each year), writes
                              <out_dir>/wayback_<ts>.jsonl
python wayback.py --task      the pool's `history` task (projects cisce-scraper-wayback and cisce-scraper-locator-cache)
"""
import gzip
import html
import json
import os
import re
import sys
import time
import urllib.request

ROW = re.compile(r"<tr>\s*<td[^>]*>\s*<strong>([A-Z]{2,4}\d{3,4})</strong>(.*?)</tr>", re.S)
CONTACT = re.compile(r"\[(O|F|E|M|Domain)\]\s*([^<]*)")
PIN = re.compile(r"^(.*?)[-\s]*(\d{3}\s?\d{3})\s*$")


def text(s):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s))).strip()


def parse_old(page):
    """[(code, data)] from one copy of the old locator. Pure: tested on a saved excerpt."""
    out = []
    for code, rest in ROW.findall(page):
        # rest = the end of the code cell (name, address), then the cells: contacts, categories, affiliation, head
        first, *cells = rest.split("<td")
        cells = [c.split(">", 1)[-1] for c in cells] + ["", "", "", ""]
        _, name, addr = (first.split("<p", 1)[0].split("<br />", 2) + ["", ""])[:3]
        lines = [text(x) for x in addr.split("\n") if text(x)]
        district, pin = "", ""
        if lines:
            m = PIN.match(lines[-1])
            district, pin = (m.group(1).strip(), m.group(2).replace(" ", "")) if m else (lines[-1], "")
        contacts = {}
        for k, v in CONTACT.findall(cells[0]):
            if v.strip():
                contacts.setdefault(k, []).append(v.strip())
        cat = [c for c in (text(x) for x in cells[1].split("</div>")) if c]
        aff = text(cells[2]).split()
        out.append((code, {
            "code": code, "name": text(name).rstrip(","), "address": ", ".join(lines[:-1]), "district": district, "pin": pin,
            "phones": contacts.get("O", []) + contacts.get("M", []), "fax": contacts.get("F", []), "email": contacts.get("E", []),
            "domain": contacts.get("Domain", []),
            "gender": cat[0] if cat else "", "residence": cat[1] if len(cat) > 2 else "", "status": cat[-1] if len(cat) > 1 else "",
            "icse": "ICSE" in aff, "isc": "ISC" in aff, "cve": "CVE" in aff,
            "head": text(cells[3]),
        }))
    return out


def sources():
    """Queue items of the `history` task: the Wayback full lists and the cached locate.cisce.org pages (files in sources/)."""
    base = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sources")
    wb = [line.split() for line in open(f"{base}/wayback-full-lists.txt") if line.strip()]
    cache = [line.strip() for line in open(f"{base}/locator-2026-10-20-magesh-xseed.txt") if line.strip()]
    dev = [line.split() for line in open(f"{base}/devlocate-wayback.txt") if line.strip()]
    full = [line.split() for line in open(f"{base}/locator-wayback.txt") if line.strip()]
    return {
        "wayback": [{"key": ts, "payload": {"url": f"https://web.archive.org/web/{ts}id_/{url}", "kind": "old", "expected": 2500,
                                             "date": f"{ts[:4]}-{ts[4:6]}-{ts[6:8]}", "source": "web.archive.org copy of " + url}}
                    for ts, url in wb] + [
            # devlocate.cisce.org (a copy of the locator, now 403 for visitors): Wayback copies of its listing pages, 2026
            {"key": f"dev-{ts}-{url.rsplit('=', 1)[-1] if '=' in url else '1'}", "payload": {
                "url": f"https://web.archive.org/web/{ts}id_/{url}", "kind": "new", "expected": 10,
                "date": f"{ts[:4]}-{ts[4:6]}-{ts[6:8]}", "source": "web.archive.org copy of " + url}} for ts, url in dev] + [
            # locate.cisce.org/result with no filter: every school on one page (found 2026-11-17; 3,221 schools on 2025-11-02)
            {"key": f"locator-{ts}" + (f"-{url.rsplit('=', 1)[1]}" if "page=" in url else ""), "payload": {
                "url": f"https://web.archive.org/web/{ts}id_/{url}", "kind": "new", "expected": 10 if "page=" in url else 3200,
                "date": f"{ts[:4]}-{ts[4:6]}-{ts[6:8]}", "source": "web.archive.org copy of " + url}} for ts, url in full],
        "locator-cache": [{"key": u.rsplit("/", 1)[1].split(".")[0][:16], "payload": {
            "url": u, "kind": "new", "expected": 10, "date": "2026-10-20",
            "source": "locate.cisce.org page cached by github.com/magesh-xseed/milestones"}} for u in cache],
    }


def task():
    """Pool task: fetch one source page per item, parse it, store records `<date>:<code>` (history, one row per list)."""
    import requests
    from scrape_hub_client import HubClient, stop_flag, timed_get
    import crawl
    stop = stop_flag()
    deadline = time.time() + float(os.environ.get("SCRAPE_MAX_HOURS", "1")) * 3600 - 300
    hub = HubClient(os.environ["SCRAPE_POOL_PROJECT"], job_index=int(os.environ.get("SCRAPE_JOB_INDEX", "0")),
                    total_jobs=int(os.environ.get("SCRAPE_TOTAL_JOBS", "1")))
    s = requests.Session()
    try:
        while time.time() < deadline and not stop.is_set():
            if hub.settings.get("paused"):
                time.sleep(30)
                continue
            items = hub.claim(1, steal=True, retry_failed=True)
            if not items:
                break
            key, p = items[0]["key"], items[0]["payload"]
            r = timed_get(hub, s, p["url"], timeout=300)
            if r is None or r.status_code != 200:
                hub.complete([key], "failed", error=f"HTTP {r.status_code if r is not None else 'no answer'}")
                continue
            body = r.content
            page = (gzip.decompress(body) if body[:2] == b"\x1f\x8b" else body).decode("utf-8", "replace")
            rows = parse_old(page) if p["kind"] == "old" else ([] if crawl.is_challenge(page) else crawl.parse(page))
            for code, d in rows:
                hub.record(f"{p['date']}:{code}", {**d, "snapshot": p["date"], "source": p["source"]})
            hub.complete([key], "done" if rows else "failed", fetched=len(rows), **({} if rows else {"error": "no schools on the page"}))
            time.sleep(max(2, hub.settings.get("delay_ms", 0) / 1000))
        hub.close("failed", "stopped by signal") if stop.is_set() else hub.close()
    except BaseException as e:
        hub.close("failed", f"{type(e).__name__}: {e}"[:200])
        raise


def main(out):
    """Local: download the Wayback full lists in sources/ and write <out>/wayback_<ts>.jsonl (input of link/merge.py)."""
    for item in sources()["wayback"]:
        page = urllib.request.urlopen(item["payload"]["url"], timeout=300).read().decode("utf-8", "replace")
        rows = parse_old(page)
        with open(f"{out}/wayback_{item['key']}.jsonl", "w") as f:
            for code, d in rows:
                f.write(json.dumps({**d, "snapshot": item["key"]}, ensure_ascii=False) + "\n")
        print(item["key"], len(rows), "schools", flush=True)
        time.sleep(5)


if __name__ == "__main__":
    task() if sys.argv[1:2] == ["--task"] else main(sys.argv[1])

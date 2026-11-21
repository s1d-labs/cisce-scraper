"""Weekly watch: new Wayback copies (HTTP 200) of locate.cisce.org listing pages.

locate.cisce.org shows a Cloudflare check to every automated route, so new data comes from the Internet Archive:
- `locate.cisce.org/result` with no filter = every school on one page (3,221 schools on 2025-11-02);
- `locate.cisce.org/?page=N` = one listing page of 10 schools.
New copies are added to sources/locator-wayback.txt ("<timestamp> <url>"); the next setup run seeds them into
cisce-scraper-wayback. A failed CDX request is not an error: the watch says so and tries again next week.

    python watch.py            add new copies to sources/locator-wayback.txt, print how many
    python watch.py --dry-run  only print them
"""
import json
import os
import re
import sys
import time
import urllib.request
from pathlib import Path

FILE = Path(__file__).parent / "sources" / "locator-wayback.txt"
CDX = ("https://web.archive.org/cdx/search/cdx?url=locate.cisce.org/&matchType=prefix&output=json"
       "&fl=timestamp,original,statuscode,length&filter=statuscode:200&from={since}")
WANTED = re.compile(r"^https?://locate\.cisce\.org(?::\d+)?/(result/?|\?page=\d+)$")


def wanted(rows, have):
    """New (timestamp, url) pairs of full lists and listing pages, not yet in the file. Pure: tested in self_check()."""
    out = []
    for ts, url, status, *_ in rows:
        url = url.replace("http://", "https://").replace(":80/", "/")
        if status == "200" and WANTED.match(url) and (ts, url) not in have:
            out.append((ts, url))
    return sorted(set(out))


def fetch(since, tries=3):
    for i in range(tries):
        try:
            req = urllib.request.Request(CDX.format(since=since), headers={"User-Agent": "s1d-labs cisce-scraper weekly watch"})
            with urllib.request.urlopen(req, timeout=120) as r:
                rows = json.load(r)
            return rows[1:] if rows else []
        except Exception as e:                         # 504 and 429 happen: wait and try again, then give up for this week
            print(f"CDX try {i + 1}: {e}")
            time.sleep(60 * (i + 1))
    return None


def self_check():
    rows = [["20251102210937", "https://locate.cisce.org/result", "200"], ["20261201000000", "http://locate.cisce.org:80/result", "200"],
            ["20261201000001", "https://locate.cisce.org/?page=7", "200"], ["20261201000002", "https://locate.cisce.org/css/app.css", "200"],
            ["20261201000003", "https://locate.cisce.org/result?_token=x&state=1", "200"]]
    got = wanted(rows, {("20251102210937", "https://locate.cisce.org/result")})
    assert got == [("20261201000000", "https://locate.cisce.org/result"), ("20261201000001", "https://locate.cisce.org/?page=7")], got


def main():
    self_check()
    lines = [line.split() for line in FILE.read_text().splitlines() if line.strip()]
    have = {(ts, url) for ts, url in lines}
    since = max(ts for ts, _ in lines)[:8] if lines else "2023"
    rows = fetch(since)
    if rows is None:
        print("::warning::Wayback CDX did not answer; no change this week")
        return 0
    new = wanted(rows, have)
    for ts, url in new:
        print("new:", ts, url)
    if new and "--dry-run" not in sys.argv:
        with open(FILE, "a") as f:
            f.writelines(f"{ts} {url}\n" for ts, url in new)
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as f:
            f.write(f"new={len(new)}\n")
    print(len(new), "new copies")
    return 0


if __name__ == "__main__":
    sys.exit(main())

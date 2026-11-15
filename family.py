"""What this family scrapes: CISCE affiliated schools (locate.cisce.org).

The queue holds one item per listing page per month (`<YYYY-MM>-p<n>`): the daily Setup run seeds the new month's keys, so the
whole list is read again each month. Records are upserts by affiliation code; `seen` tells when a school was last listed.
"""
import json
from datetime import datetime, timezone
from pathlib import Path

FAMILY = json.loads((Path(__file__).parent / "scrape.json").read_text())["family"]
SITE = "https://locate.cisce.org"
# Paused (0 pages): on 2026-11-16 Cloudflare showed an interactive challenge to the box, to proxy in-07 and to a GitHub runner.
# The task never clicks it. Set 3 for a pilot when trideep says so, then 340 (336 pages + growth) after a clean pilot.
PAGES = 0
MONTH = datetime.now(timezone.utc).strftime("%Y-%m")

PROJECTS = [
    {
        "name": f"{FAMILY}-schools",
        "title": "CISCE affiliated schools (locate.cisce.org)",
        "task": "crawl",
        "target": "locate.cisce.org",
        "env": {"SITE": SITE},
        "probe": None,          # Cloudflare answers 403 to the hub's plain-HTTP probe: a probe would hold the work forever
        "unit_label": "page", "record_label": "school",
        "items": [{"key": f"{MONTH}-p{n}", "payload": {"url": f"{SITE}/?page={n}", "page": n, "expected": 10}}
                  for n in range(1, PAGES + 1)],
    },
]

PROBES = []

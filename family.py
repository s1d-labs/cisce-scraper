"""What this family scrapes: CISCE affiliated schools (locate.cisce.org).

The queue holds one item per listing page per month (`<YYYY-MM>-p<n>`): the daily Setup run seeds the new month's keys, so the
whole list is read again each month. Records are upserts by affiliation code; `seen` tells when a school was last listed.
"""
import json
import sys
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

sys.path.insert(0, str(Path(__file__).parent))
from wayback import sources  # noqa: E402

HISTORY = sources()
PROJECTS += [
    {
        # full lists of the old official locator (www.cisce.org/locate-search.aspx), Wayback copies 2015-2022; record id <date>:<code>
        "name": f"{FAMILY}-wayback", "title": "CISCE affiliated schools: official lists 2015-2022 (Wayback Machine)",
        "task": "history", "target": "web.archive.org", "env": {}, "probe": None, "unit_label": "list", "record_label": "school-year",
        "max_workers": 1, "delay_ms": 5000, "items": HISTORY["wayback"],
    },
    {
        # locate.cisce.org pages of 2026-10-20 from the public raw cache of github.com/magesh-xseed/milestones (pinned commit)
        "name": f"{FAMILY}-locator-cache", "title": "CISCE affiliated schools: locate.cisce.org pages of 2026-10-20 (magesh-xseed cache)",
        "task": "history", "target": "raw.githubusercontent.com", "env": {}, "probe": None, "unit_label": "page", "record_label": "school",
        "max_workers": 2, "delay_ms": 2000, "items": HISTORY["locator-cache"],
    },
]

import frc  # noqa: E402

# Gujarat Fee Regulation Committee school list (all boards, with UDISE codes): first pool run with 5 pages, then frc.PAGES.
FRC_PAGES = 5
PROJECTS += [
    {
        "name": f"{FAMILY}-frc-gujarat", "title": "Gujarat FRC school list (frcgujarat.org): UDISE code, board, medium",
        "task": "history", "target": "frcgujarat.org", "env": {}, "probe": None, "unit_label": "page", "record_label": "school",
        "max_workers": 1, "delay_ms": 3000, "items": frc.items(FRC_PAGES),
    },
]

PROBES = []

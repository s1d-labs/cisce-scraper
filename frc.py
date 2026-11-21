"""Gujarat Fee Regulation Committee (frcgujarat.org): the public school list. 10 schools per page, about 1,563 pages.
Each row: FRC id, school name, UDISE code (11 digits), district, block, medium, board (GSEB, GSHSEB, CBSE, ICSE / CISCE, IB,
"Cambrige"), application types, fee status. The fee orders of each school are on a detail page (not read yet).
"""
import json
import re
from datetime import datetime, timezone

SITE = "https://frcgujarat.org"
# shortcut: a fixed page count (1,563 pages on 2026-11-21) plus growth; pages after the end are empty and count as done.
PAGES = 1600
ROWS = re.compile(r"var jsonModel=(\[.*?\]);?\s*$", re.M)
KEEP = ["Id", "SchoolName", "SchoolCode", "SchoolAddress", "DistrictName", "BlockName", "Medium", "Board", "SchoolType",
        "ApplicationTypes", "FeeStatus"]


def parse(page):
    """[("<frc id>:<medium>:<board>", row)] for one list page; [] for a page after the end; None when the page has no list (an error page)."""
    m = ROWS.search(page)
    if not m:
        return None
    out = []
    for r in json.loads(m.group(1)):
        d = {k: (r.get(k) or "").strip() if isinstance(r.get(k), str) else r.get(k) for k in KEEP}
        out.append((f"{d['Id']}:{d['Medium']}:{d['Board']}", d))   # one school can have two media (two rows, one FRC id)
    return out


def items(pages=PAGES):
    """Queue items: one per list page per month (`<YYYY-MM>-p<n>`), so the daily setup re-reads the list each month."""
    month = datetime.now(timezone.utc).strftime("%Y-%m")
    return [{"key": f"{month}-p{n:04d}", "payload": {"url": f"{SITE}/Home/SearchSchool?page={n}", "kind": "frc", "date": month,
                                                    "source": "frcgujarat.org school list", "expected": 10}}
            for n in range(1, pages + 1)]

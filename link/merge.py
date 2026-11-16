"""One row per CISCE affiliation code from every source we have (newest source first for each field).

python link/merge.py <dir>
  reads  <dir>/wayback_<ts>.jsonl      old official locator, Wayback copies (wayback.py), full lists 2015-2022
         <dir>/locator/*              locate.cisce.org listing pages of LOCATOR_DATE (magesh-xseed/milestones raw cache)
         <dir>/locator-<date>-<src>/* more listing pages, e.g. locator-2026-07-23-devlocate-wayback, locator-2026-11-20-saved-by-hand
                                      (.html, .gz, or cisce-pages-*.json bundles from saver.js)
         <dir>/cisce_2018.csv          github.com/deedy/cisce_schools_data (code, name, address, pin, state)
         <dir>/pincodes.csv            optional: pincode, district (udise db, directory.pincodes) for rows with no district
         <dir>/cisce_2021.csv          github.com/Nitish-Kumar-kushwaha/list-of-all-CISCE-schools-in-India (code, name_and_place, phone)
  writes <dir>/cisce_all.csv           one row per code
         <dir>/cisce_presence.csv      code, source, date: which list showed the code when
`locator_date` is the date of the locator pages (default 2026-10-20, the magesh-xseed fetch); set LOCATOR_DATE to change it.
"""
import collections
import csv
import glob
import gzip
import json
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import crawl  # noqa: E402

LOCATOR_DATE = os.environ.get("LOCATOR_DATE", "2026-10-20")
FIELDS = ["code", "name", "state", "district", "locality", "address", "pin", "country", "gender", "residence", "status", "icse", "isc",
          "cve", "head", "phones", "email", "website", "lat", "lng", "first_seen", "last_seen", "on_locator_2026", "n_sources", "sources"]
HISTORY = ["name", "district", "pin", "status", "gender", "residence", "icse", "isc", "cve"]   # per list row in cisce_presence
STATE_FIX = {"Dubai (U.A.E.)": "Dubai", "Tamilnadu": "Tamil Nadu", "Chattisgarh": "Chhattisgarh", "New Delhi": "Delhi", "Orissa": "Odisha", "Pondicherry": "Puducherry"}
FOREIGN = {"DUBAI": "United Arab Emirates", "SHARJAH": "United Arab Emirates", "INDONESIA": "Indonesia", "SINGAPORE": "Singapore",
           "THAILAND": "Thailand"}


def prefix(code):
    return re.sub(r"\d", "", code)


def read_page(path):
    b = open(path, "rb").read()
    return (gzip.decompress(b) if b[:2] == b"\x1f\x8b" else b).decode("utf-8", "replace")


def merge(d):
    presence, rows = [], collections.defaultdict(dict)       # rows[code][source_date] = data in a common shape

    def add(code, date, source, data):
        presence.append({"code": code, "source": source, "date": date, **{k: data.get(k, "") for k in HISTORY}})
        rows[code][date] = {k: v for k, v in data.items() if v not in ("", None, [], False)}

    for f in sorted(glob.glob(f"{d}/wayback_*.jsonl")):
        ts = re.search(r"wayback_(\d{8})", f).group(1)
        date = f"{ts[:4]}-{ts[4:6]}-{ts[6:8]}"
        for line in open(f):
            r = json.loads(line)
            add(r["code"], date, "wayback-cisce.org", {**r, "phones": "; ".join(r["phones"]), "email": "; ".join(r["email"]),
                                                        "website": "; ".join(r["domain"])})
    for folder in sorted(glob.glob(f"{d}/locator*/")):       # locator/ (LOCATOR_DATE) or locator-<YYYY-MM-DD>[-<source>]/
        m = re.search(r"locator-(\d{4}-\d{2}-\d{2})(?:-(.+?))?/$", folder)
        date, source = (m.group(1), m.group(2) or "locate.cisce.org") if m else (LOCATOR_DATE, "locate.cisce.org")
        for f in sorted(glob.glob(f"{folder}*")):
            # cisce-pages-*.json: pages saved by saver.js (github.com/insightLegion/cisce-locator-saver), {"page-0001.html": html}
            pages = json.load(open(f, encoding="utf-8")).values() if f.endswith(".json") else [read_page(f)]
            for page in pages:
                if crawl.is_challenge(page):
                    continue
                for code, r in crawl.parse(page):
                    add(code, date, source, {**r, "head": r["principal"]})
    state18 = {}
    if os.path.exists(f"{d}/cisce_2018.csv"):
        for r in csv.DictReader(open(f"{d}/cisce_2018.csv")):
            state18[r["code"]] = r["state"]
            add(r["code"], "2018-12-31", "github-deedy-2018", {"name": r["name"], "address": r["address"], "pin": r["pin"],
                                                                  "country": FOREIGN.get(r["state"], "India")})
    name21 = {}
    if os.path.exists(f"{d}/cisce_2021.csv"):
        for r in csv.DictReader(open(f"{d}/cisce_2021.csv")):
            name21[r["code"]] = r["name_and_place"]                 # name and place in one text: used only when no name is known
            add(r["code"], "2021-08-30", "github-nitish-2021", {"phones": r["phone"]})

    pin_district = {}                         # <dir>/pincodes.csv (pincode, district): UDISE+ directory.pincodes, optional
    if os.path.exists(f"{d}/pincodes.csv"):
        pin_district = {r["pincode"]: r["district"].title() for r in csv.DictReader(open(f"{d}/pincodes.csv")) if r["district"]}

    # state for rows without one: the 2018 list, else the most common state of the code prefix
    pref = collections.defaultdict(collections.Counter)
    for code, by_date in rows.items():
        for r in by_date.values():
            if r.get("state"):
                pref[prefix(code)][r["state"].title()] += 1
    for code, s in state18.items():
        pref[prefix(code)][s.title()] += 1

    out = []
    for code, by_date in sorted(rows.items()):
        dates = sorted(by_date)
        row = {}
        for dt in dates:                                     # oldest first, so newer values overwrite older ones
            row.update(by_date[dt])
        if not row.get("state"):
            s = state18.get(code)
            row["state"] = s.title() if s else (pref[prefix(code)].most_common(1)[0][0] if pref[prefix(code)] else "")
        row["state"] = STATE_FIX.get(row["state"], row["state"])
        row["country"] = row.get("country") or FOREIGN.get(row["state"].upper(), "India")
        row["name"] = row.get("name") or name21.get(code, "")
        if not row.get("district") and row.get("pin") in pin_district:     # the 2025 table layout has no district field
            row["district"] = pin_district[row["pin"]]
        out.append({**{k: row.get(k, "") for k in FIELDS}, "code": code, "first_seen": dates[0], "last_seen": dates[-1],
                    "on_locator_2026": LOCATOR_DATE in by_date, "n_sources": len(dates)})
    by_code = collections.defaultdict(set)
    for p in presence:
        by_code[p["code"]].add(p["source"])
    for r in out:
        r["sources"] = "; ".join(sorted(by_code[r["code"]]))
    return out, presence


def write(path, rows, fields):
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader(), w.writerows(rows)


def self_check():
    import tempfile
    t = tempfile.mkdtemp()
    with open(f"{t}/wayback_20200101000000.jsonl", "w") as f:
        f.write(json.dumps({"code": "AB001", "name": "Old Name", "phones": ["1"], "email": [], "domain": [], "pin": "111111"}) + "\n")
    with open(f"{t}/wayback_20220101000000.jsonl", "w") as f:
        f.write(json.dumps({"code": "AB001", "name": "New Name", "phones": [], "email": ["a@b"], "domain": [], "pin": ""}) + "\n")
    rows, pres = merge(t)
    r = rows[0]
    assert (r["name"], r["pin"], r["phones"], r["email"], r["first_seen"], r["last_seen"]) == ("New Name", "111111", "1", "a@b", "2020-01-01", "2022-01-01")
    assert len(pres) == 2 and not r["on_locator_2026"] and [p["name"] for p in pres] == ["Old Name", "New Name"]
    page = open(os.path.join(os.path.dirname(__file__), "..", "tests", "pages", "result-isc-india-p1.html"), encoding="utf-8").read()
    os.makedirs(f"{t}/locator-2026-11-20-saved-by-hand")
    json.dump({"page-0001.html": page}, open(f"{t}/locator-2026-11-20-saved-by-hand/cisce-pages-0001-0001.json", "w"))
    rows, pres = merge(t)
    assert len(rows) == 11 and {p["source"] for p in pres} >= {"saved-by-hand"}


if __name__ == "__main__":
    self_check()
    rows, presence = merge(sys.argv[1])
    write(f"{sys.argv[1]}/cisce_all.csv", rows, FIELDS)
    write(f"{sys.argv[1]}/cisce_presence.csv", presence, ["code", "source", "date", *HISTORY])
    print(len(rows), "codes;", sum(r["on_locator_2026"] for r in rows), "on the 2026 locator pages;",
          collections.Counter(r["last_seen"] for r in rows).most_common(6))

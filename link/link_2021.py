"""Second linking pass for the 2021 CISCE list, which has no PIN: code prefix -> state (from the 2018 list), then the UDISE name
(>= 8 characters, without an "ICSE" suffix) must start the 2021 "name + place" text and share a word with the UDISE district,
locality or block. Each code and UDISE school once. A 25-link sample read correct on 2026-11-16.

python link/link_2021.py <dir>   reads cisce_2018.csv, cisce_2021.csv, udise_cisce.csv, cisce_udise_link.csv; writes link_2021.csv
"""
import collections
import csv
import re
import sys

import link as L


def run(d):
    pref = collections.defaultdict(collections.Counter)
    for r in csv.DictReader(open(f"{d}/cisce_2018.csv")):
        pref[re.sub(r"\d", "", r["code"])][L.state(r["state"])] += 1
    udise = list(csv.DictReader(open(f"{d}/udise_cisce.csv")))
    done = list(csv.DictReader(open(f"{d}/cisce_udise_link.csv")))
    used_c, used_u = {x["code"] for x in done}, {x["udise"] for x in done}
    by_state = collections.defaultdict(list)
    for u in udise:
        if u["udise"] not in used_u:
            by_state[L.state(u["state"])].append(u)
    cands = []
    for r in csv.DictReader(open(f"{d}/cisce_2021.csv")):
        if r["code"] in used_c:
            continue
        p = pref[re.sub(r"\d", "", r["code"])]
        st = p.most_common(1)[0][0] if p else None
        states = ["ANDHRA PRADESH", "TELANGANA"] if st == "ANDHRA PRADESH" else [st]   # AP codes predate Telangana
        k, w = L.key(r["name_and_place"]), L.words(r["name_and_place"])
        for s in states:
            for u in by_state.get(s, []):
                uk = L.key(u["name"]).split("ICSE")[0]
                place = L.words(" ".join(u[f] or "" for f in ("district", "locality", "block")))
                if len(uk) >= 8 and k.startswith(uk) and place & w:
                    cands.append((len(uk), r["code"], u["udise"]))
    used, out = set(), []
    for _, code, ud in sorted(cands, reverse=True):
        if code not in used and ud not in used:
            used |= {code, ud}
            out.append({"code": code, "udise": ud, "method": "state+nameprefix+place", "score": 1.0})
    with open(f"{d}/link_2021.csv", "w", newline="") as f:
        wr = csv.DictWriter(f, fieldnames=["code", "udise", "method", "score"])
        wr.writeheader(), wr.writerows(out)
    print("2021 links:", len(out))


if __name__ == "__main__":
    run(sys.argv[1])

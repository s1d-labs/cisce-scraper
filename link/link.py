"""Link CISCE school lists to UDISE+. Run on a team box; writes CSVs for ws_trideep.cisce_scraper.

python link/link.py <dir> [udise_all.csv]   reads <dir>/udise_cisce.csv, cisce.csv (code, name, address, pin, state, district)
                            writes <dir>/cisce_udise_link.csv

Method (kept in the `method` column):
  pin+name     same PIN, normalised names equal or similarity >= 0.85
  pin+prefix   same PIN, the UDISE name starts with the CISCE name (UDISE adds the place)
  pin+contains same PIN, every distinctive CISCE name word is in the UDISE name
  pin+fuzzy    same PIN, similarity >= 0.6 and at least 2 shared name words that are not generic
  dist+name    same state and district, normalised names equal and unique in that district on both sides (PIN differs)
Each UDISE school links to one CISCE school at most (best score first).
"""
import csv
import difflib
import re
import sys
from collections import defaultdict

GENERIC = set("THE SCHOOL SCHOOLS PUBLIC HIGH HIGHER SECONDARY SENIOR SR SEC ENGLISH MEDIUM EM CONVENT ACADEMY VIDYALAYA "
              "INTERNATIONAL INTL AND OF CO ED HR SECY RESIDENTIAL DAY BOARDING GIRLS BOYS ST SAINT MISSION MODEL COLLEGE INTER JUNIOR JR PU "
              "EDUCATION EDUCATIONAL CENTRE CENTER INSTITUTE NATIONAL PRY PRIMARY HS HSS EMHS MHSS ICSE ISC".split())
STATE_FIX = {"TAMIL NADU": "TAMILNADU", "CHATTISGARH": "CHHATTISGARH", "ANDAMAN AND NICOBAR ISLANDS": "ANDAMAN & NICOBAR ISLANDS",
             "JAMMU AND KASHMIR": "JAMMU & KASHMIR", "NCT OF DELHI": "DELHI", "ORISSA": "ODISHA"}


def norm(name):
    s = re.sub(r"[^A-Z0-9 ]", " ", (name or "").upper().replace("'", "").replace("\u2019", "").replace(".", " ").replace("&", " AND "))
    return " ".join("SAINT" if w in ("ST", "SNT", "STS") else w for w in s.split())


def key(name):
    return re.sub(r"[^A-Z0-9]", "", norm(name))


def words(name):
    return {w for w in norm(name).split() if w not in GENERIC and len(w) > 1}


def state(s):
    s = norm(s)
    return STATE_FIX.get(s, s)


def score(a, b):
    if key(a) == key(b):
        return 1.0
    return difflib.SequenceMatcher(None, key(a), key(b)).ratio()


def link(cisce, udise):
    by_pin, by_dist = defaultdict(list), defaultdict(list)
    for u in udise:
        by_pin[(u["pincode"] or "").strip()].append(u)
        by_dist[(state(u["state"]), norm(u["district"]))].append(u)
    cands, cisce_names = [], defaultdict(int)
    for c in cisce:
        cisce_names[(state(c["state"]), norm(c["district"]), key(c["name"]))] += 1
    for c in cisce:
        for u in by_pin.get(c["pin"], []) if c["pin"] else []:
            sc = score(c["name"], u["name"])
            shared = len(words(c["name"]) & words(u["name"]))
            cw, uw = words(c["name"]), words(u["name"])
            if sc == 1.0 or (sc >= 0.85 and cw & uw):           # "Gems Public School" ~ "SL Public School" is 0.87: need a shared word
                cands.append((sc + 1, c["code"], u["udise"], "pin+name", round(sc, 3)))
            elif key(u["name"]).startswith(key(c["name"])) and len(key(c["name"])) >= 6:
                cands.append((1.8, c["code"], u["udise"], "pin+prefix", round(sc, 3)))
            elif cw and cw <= uw:
                cands.append((1.5 + sc / 10, c["code"], u["udise"], "pin+contains", round(sc, 3)))
            elif sc >= 0.6 and shared >= 2:
                cands.append((sc, c["code"], u["udise"], "pin+fuzzy", round(sc, 3)))
        same = [u for u in by_dist.get((state(c["state"]), norm(c["district"])), []) if key(c["name"]) == key(u["name"])]
        if len(same) == 1 and cisce_names[(state(c["state"]), norm(c["district"]), key(c["name"]))] == 1:   # unique on both sides
            cands.append((0.5, c["code"], same[0]["udise"], "dist+name", 1.0))
    used_c, used_u, out = set(), set(), []
    for _, code, ud, method, sc in sorted(cands, reverse=True):
        if code in used_c or ud in used_u:
            continue
        used_c.add(code), used_u.add(ud)
        out.append({"code": code, "udise": ud, "method": method, "score": sc})
    return out


def stems(name, place=""):
    """Distinctive words without a plural/possessive S and without place words (DEWAS in 'Pratibha Global School Dewas')."""
    return {w.rstrip("S") for w in words(name)} - {w.rstrip("S") for w in norm(place).split()}


def link_pin_unique(cisce, udise):
    """Last pass: a PIN with exactly one unlinked code and one unlinked UDISE ICSE school. Names there are often misspelt or
    shortened (ST MARRY'S COVENT, AGAAPE MISSION): accept a shared distinctive word or a close spelling (score >= 0.8).
    94 links read on 2026-11-17: 93 right; the wrong one (B V M vs TANDON INTERNATIONAL) is now refused."""
    pc, pu = defaultdict(list), defaultdict(list)
    for c in cisce:
        pc[c["pin"]].append(c)
    for u in udise:
        pu[(u["pincode"] or "").strip()].append(u)
    out = []
    for pin, cs in pc.items():
        if pin and len(cs) == 1 and len(pu.get(pin, [])) == 1:
            c, u = cs[0], pu[pin][0]
            place = " ".join([c.get("district", ""), c.get("locality", ""), c.get("state", ""), u.get("district", ""), u.get("block", "")])
            sc = score(c["name"], u["name"])
            dk = [re.sub(r"[^A-Z0-9]", "", " ".join(w for w in norm(n).split() if w not in GENERIC)) for n in (c["name"], u["name"])]
            close = sc >= 0.8 and difflib.SequenceMatcher(None, *dk).ratio() >= 0.3   # not only "INTERNATIONAL SCHOOL" in common
            if close or stems(c["name"], place) & stems(u["name"], place):
                out.append({"code": c["code"], "udise": u["udise"], "method": "pin-unique", "score": round(sc, 3)})
    return out


def self_check():
    assert key("St. George's Grammar School") == key("SAINT GEORGES GRAMMAR SCHOOL")
    assert key("St.Anne's School") == key("ST ANNES SCHOOL") and key("R.V.S. School") == key("RVS SCHOOL")
    assert state("Tamil Nadu") == "TAMILNADU"
    u = [{"udise": "1", "name": "LOYOLA PUBLIC SCHOOL", "pincode": "522005", "state": "ANDHRA PRADESH", "district": "GUNTUR"},
         {"udise": "2", "name": "LOYOLA HIGH SCHOOL", "pincode": "522005", "state": "ANDHRA PRADESH", "district": "GUNTUR"}]
    c = [{"code": "AP003", "name": "Loyola Public School", "pin": "522005", "state": "Andhra Pradesh", "district": "Guntur"}]
    assert link(c, u) == [{"code": "AP003", "udise": "1", "method": "pin+name", "score": 1.0}]
    pc = lambda code, name, pin, dist: {"code": code, "name": name, "pin": pin, "district": dist, "state": "", "locality": ""}  # noqa: E731
    pu = lambda ud, name, pin, dist: {"udise": ud, "name": name, "pincode": pin, "district": dist, "block": ""}  # noqa: E731
    got = link_pin_unique([pc("PU051", "St. Xavier's High School", "1", "X"), pc("MP042", "Pratibha Global School Dewas", "2", "Dewas"),
                           pc("MA218", "R. J. International", "3", "Y"), pc("PU133", "B V M International School", "5", "V"), pc("A1", "A School", "4", "Z"), pc("A2", "B School", "4", "Z")],
                          [pu("u1", "ST. XAVIER SR SEC SCHOOL", "1", "X"), pu("u2", "ESCORT JUNIOR COLLEGE DEWAS", "2", "DEWAS"),
                           pu("u3", "PODAR INTERNATIONAL SCHOOL", "3", "Y"), pu("u5", "TANDON INTERNATIONAL SCHOOL", "5", "V"), pu("u4", "A SCHOOL", "4", "Z")])
    assert [x["code"] for x in got] == ["PU051"], got


def write(path, rows):
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]) if rows else ["empty"])
        w.writeheader(), w.writerows(rows)


if __name__ == "__main__":
    self_check()
    d = sys.argv[1]
    udise = list(csv.DictReader(open(f"{d}/udise_cisce.csv")))
    cisce = list(csv.DictReader(open(f"{d}/cisce.csv")))
    links = link(cisce, udise)
    done = {x["code"] for x in links} | {x["udise"] for x in links}
    links += link_pin_unique([c for c in cisce if c["code"] not in done], [u for u in udise if u["udise"] not in done])
    if len(sys.argv) > 2:                   # second pass: all UDISE schools at the PINs still unmatched (board field may be wrong)
        done = {x["code"] for x in links} | {x["udise"] for x in links}
        rest = [c for c in cisce if c["code"] not in done]
        pins = {c["pin"] for c in rest}
        more = [u for u in csv.DictReader(open(sys.argv[2])) if u["pincode"] in pins and u["udise"] not in done]
        # contains / fuzzy across all boards gave wrong links in a 40-link sample: keep only name and prefix matches there
        links += [{**x, "method": x["method"] + "/any-board"} for x in link(rest, more) if x["method"] in ("pin+name", "pin+prefix")]
    write(f"{d}/cisce_udise_link.csv", links)
    india = [c for c in cisce if c.get("country", "India") in ("India", "")]
    print(f"CISCE {len(cisce)} (India {len(india)}), UDISE CISCE {len(udise)}, linked {len(links)}",
          {m: sum(1 for x in links if x["method"] == m) for m in sorted({x["method"] for x in links})})

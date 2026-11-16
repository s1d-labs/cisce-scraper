"""CISCE school lists from Wayback Machine copies of the old official locator (www.cisce.org/locate-search.aspx, 2015-2022).

The old locator listed every affiliated school on one page when no filter was set. The Internet Archive holds 148 such copies.
python wayback.py <out_dir> [timestamps...]   downloads the copies (one per year by default), writes <out_dir>/wayback_<ts>.jsonl
"""
import html
import json
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


def snapshots():
    """[(timestamp, url)] of full-list copies (> 1 MB) in the Wayback CDX index."""
    cdx = "https://web.archive.org/cdx/search/cdx?url=cisce.org/locate-search.aspx&matchType=prefix&fl=timestamp,original,statuscode,length"
    rows = [line.split() for line in urllib.request.urlopen(cdx, timeout=120).read().decode().splitlines()]
    return [(r[0], r[1]) for r in rows if len(r) == 4 and r[2] == "200" and int(r[3]) > 1_000_000]


def main(out, wanted):
    snaps = snapshots()
    if not wanted:                              # default: the last copy of each year
        last = {}
        for ts, url in snaps:
            last[ts[:4]] = max(last.get(ts[:4], ("", "")), (ts, url))
        wanted = [ts for ts, _ in last.values()]
    for ts, url in snaps:
        if ts not in wanted:
            continue
        page = urllib.request.urlopen(f"https://web.archive.org/web/{ts}id_/{url}", timeout=300).read().decode("utf-8", "replace")
        rows = parse_old(page)
        with open(f"{out}/wayback_{ts}.jsonl", "w") as f:
            for code, d in rows:
                f.write(json.dumps({**d, "snapshot": ts}, ensure_ascii=False) + "\n")
        print(ts, len(rows), "schools", flush=True)
        time.sleep(5)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2:])

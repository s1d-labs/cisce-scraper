"""High Court orders with CISCE as a party (team data: hub project court-judgments-hc; PDFs in the open S3 bucket
indian-high-court-judgments): tag each order by topic and link school petitioners to CISCE codes.

    python link/hc_orders.py <dir> <dir>/cisce_all.csv      reads <dir>/orders.tsv and <dir>/pdf/, writes <dir>/hc_orders.csv

<dir>/orders.tsv: psql -d scrape_hub -At -F$'\t' -c "<EXPORT>"; the PDFs: see s3_key(). The output has no person names: for a
person petitioner the party column says "person". A name match is a candidate, not a fact; equal names give all codes ("UP208|UP426").
"""
EXPORT = ("select record_id, data->>'court', data->>'decision_date', data->>'src_court', data->>'pdf_link', data->>'petitioner', "
          "data->>'respondent', data->>'title', data->>'disposal_nature' from records where project='court-judgments-hc' and "
          "(data->>'title' ilike '%school certificate%' or data->>'title' ilike '%cisce%' or data->>'title' ilike '%c.i.s.c.e%' "
          "or data->>'title' ilike '%I.C.S.E%')")


def s3_key(date, src_court, pdf_link):
    """s3://indian-high-court-judgments/data/pdf/year=<year>/court=<src_court>/bench=<bench>/<file> (aws s3 cp --no-sign-request)."""
    parts = pdf_link.split("/")
    return f"s3://indian-high-court-judgments/data/pdf/year={date[:4]}/court={src_court}/bench={parts[2] if len(parts) > 3 else ''}/{parts[-1]}"

import csv
import re
import subprocess
import sys
from pathlib import Path

H = Path(sys.argv[1])
sys.path.insert(0, str(Path(__file__).parent))
from link import score  # noqa: E402

TOPICS = [("disaffiliation", r"dis-?affiliat|withdraw\w* (of )?(the )?affiliation|de-?affiliat|cancel\w* (of )?(the )?affiliation"),
          ("NOC / recognition", r"no objection certificate|\bN\.?O\.?C\b|recogni[sz]"),
          ("affiliation", r"affiliat"),
          ("fees", r"\bfees?\b"),
          ("teacher / service", r"terminat|salary|service|dismiss\w* from|teacher"),
          ("result / marks / exam", r"re-?evaluat|marks|result|examination|answer (script|sheet)|grace"),
          ("admission / board change", r"admission|migrat|transfer certificate|change of board")]
COURT_STATES = {"kerala": {"Kerala"}, "calcutta": {"West Bengal", "Andaman and Nicobar Islands"}, "allahabad": {"Uttar Pradesh"},
                "bombay": {"Maharashtra", "Goa"}, "madras": {"Tamil Nadu", "Puducherry"}, "orissa": {"Odisha"},
                "uttarakhand": {"Uttarakhand"}, "telangana": {"Telangana", "Andhra Pradesh"}, "andhra": {"Andhra Pradesh"},
                "punjab": {"Punjab", "Haryana", "Chandigarh"}, "chhattisgarh": {"Chhattisgarh"}, "jharkhand": {"Jharkhand"},
                "karnataka": {"Karnataka"}, "patna": {"Bihar"}, "gauhati": {"Assam", "Arunachal Pradesh", "Nagaland"},
                "sikkim": {"Sikkim"}, "madhya": {"Madhya Pradesh"}, "rajasthan": {"Rajasthan"}, "gujarat": {"Gujarat"},
                "himachal": {"Himachal Pradesh"}, "meghalaya": {"Meghalaya"}, "tripura": {"Tripura"}, "manipur": {"Manipur"},
                "jammu": {"Jammu and Kashmir", "Ladakh"}}
SCHOOL = re.compile(r"SCHOOL|ACADEMY|SOCIETY|TRUST|CONVENT|VIDYALAYA|EDUCATION|COLLEGE|MISSION|INSTITUT|ASSOCIATION", re.I)
CODE = re.compile(r"\b([A-Z]{2,3}\d{3})\b")

codes = list(csv.DictReader(open(Path(sys.argv[2]))))          # cisce_all.csv
known = {c["code"] for c in codes}
out = []
for r in csv.reader(open(H / "orders.tsv"), delimiter="\t"):
    rid, court, date, src, link, pet, resp, title, disposal = (r + [""] * 9)[:9]
    pdf = H / "pdf" / link.split("/")[-1]
    text = subprocess.run(["pdftotext", "-layout", str(pdf), "-"], capture_output=True, text=True).stdout if pdf.exists() else ""
    low = text.lower()
    topics = [name for name, pat in TOPICS if re.search(pat, low, re.I)]
    topic = topics[0] if topics else ("no text" if not text else "other")
    school_party = bool(SCHOOL.search(pet or title.split(" Vs ")[0]))
    found = sorted({c for c in CODE.findall(text) if c in known})
    match = ""
    if school_party and not found:                               # name match: petitioner against CISCE names; ties give all codes
        states = next((s for k, s in COURT_STATES.items() if k in court.lower()), None)   # None: Delhi, CISCE's seat, any state
        scored = sorted(((score(c["name"], pet), c["code"]) for c in codes if not states or c["state"] in states), reverse=True)
        if scored and scored[0][0] >= 0.75:
            match = "|".join(sorted(code for sc, code in scored if sc >= scored[0][0] - 0.02))
    out.append({"record_id": rid, "court": court, "date": date, "topic": topic, "all_topics": "; ".join(topics),
                "party": "school/trust/society" if school_party else "person", "school_party_name": pet if school_party else "",
                "codes_in_text": " ".join(found), "name_match": match, "disposal": disposal, "pdf": link, "has_text": bool(text.strip())})
assert s3_key("2018-07-06", "9_13", "court/cnrorders/cisdb_16012018/orders/X_1.pdf").endswith("/bench=cisdb_16012018/X_1.pdf")
with open(H / "hc_orders.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(out[0]))
    w.writeheader(), w.writerows(out)
import collections  # noqa: E402
print(len(out), "orders;", sum(o["has_text"] for o in out), "with text")
print(collections.Counter(o["topic"] for o in out).most_common())
print(collections.Counter((o["party"], o["topic"]) for o in out if o["party"] != "person").most_common())
print("with codes:", [(o["codes_in_text"] or o["name_match"], o["topic"], o["date"]) for o in out if o["codes_in_text"] or o["name_match"]])

"""Parsing tests on saved pages: fast, no network.

result-isc-india-p1.html: locate.cisce.org/result?country=India&affiliation=ISC, page 1, saved 2026-09-15 (public test fixture of
github.com/Ayushmaan06/school). cloudflare-challenge.html: the interactive check page, saved from the box on 2026-11-16.
"""
from pathlib import Path

import crawl

PAGES = Path(__file__).parent / "pages"


def test_result_page_gives_ten_schools():
    page = (PAGES / "result-isc-india-p1.html").read_text(encoding="utf-8")
    rows = crawl.parse(page)
    assert len(rows) == 10 and len({r for r, _ in rows}) == 10
    code, s = rows[0]
    assert code == "AN001" and s["name"] == "Don Bosco School" and s["principal"] == "Fr. BHARATHRAJA C"
    assert (s["locality"], s["district"], s["state"], s["pin"], s["country"]) == ("PORT BLAIR", "South Andaman", "Andaman and Nicobar Islands", "744103", "India")
    assert (s["gender"], s["residence"], s["asisc"], s["icse"], s["isc"], s["cve"]) == ("Co-ed.", "Day", False, True, True, False)
    assert (s["lat"], s["lng"]) == (11.6324598, 92.6692593) and s["listed_total"] == 1928 and s["website"] == ""
    s = dict(rows)["AP003"]
    assert s["asisc"] and s["residence"] == "Day/Residential" and s["website"] == "https://www.loyolapublicschool.org"
    assert s["pin"] == "522005" and s["state"] == "Andhra Pradesh"
    assert dict(rows)["AP006"]["name"] == "St. George's Grammar School"
    assert all(d["lat"] for _, d in rows)


def test_challenge_page_is_detected_and_gives_nothing():
    page = (PAGES / "cloudflare-challenge.html").read_text(encoding="utf-8")
    assert crawl.is_challenge(page) and crawl.parse(page) == []
    assert not crawl.is_challenge((PAGES / "result-isc-india-p1.html").read_text(encoding="utf-8"))


def test_address_without_district():
    a = crawl.split_address(["Dubai,", "Dubai,", "00000, United Arab Emirates"])
    assert a["country"] == "United Arab Emirates" and a["state"] == "Dubai" and a["pin"] == "00000"

"""Parsing tests on saved pages: fast, no network.

result-isc-india-p1.html: locate.cisce.org/result?country=India&affiliation=ISC, page 1, saved 2026-09-15 (public test fixture of
github.com/Ayushmaan06/school). cloudflare-challenge.html: the interactive check page, saved from the box on 2026-11-16.
wayback-locate-search-2022-excerpt.html: the old locator (www.cisce.org/locate-search.aspx), Wayback copy of 2022-04-19, 3 rows.
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


def test_pin_with_stray_punctuation():
    a = crawl.split_address(["Kanpur, Kanpur Nagar,", "Uttar Pradesh,", "-208020, India"])
    assert (a["pin"], a["state"], a["district"]) == ("208020", "Uttar Pradesh", "Kanpur Nagar")
    assert crawl.split_address(["SOLURU, Ramanagara,", "Karnataka,", "562127., India"])["pin"] == "562127"


def test_wayback_old_locator_rows():
    import wayback
    rows = dict(wayback.parse_old((PAGES / "wayback-locate-search-2022-excerpt.html").read_text(encoding="utf-8")))
    assert list(rows) == ["AN001", "AP001", "AP002"]
    s = rows["AP001"]
    assert (s["name"], s["district"], s["pin"], s["address"]) == ("Paramjyoti Public School", "East Godavari", "533201", "Near Red Bridge, Amalapuram")
    assert (s["gender"], s["residence"], s["status"], s["icse"], s["isc"]) == ("Co-ed.", "D/R", "Permanent", True, False)
    assert s["phones"] == ["8019030155", "08856-238726"] and s["email"] == ["head@ap001cisce.org"] and s["head"] == "Mrs. Mercy Nelson Panga"
    assert rows["AN001"]["status"] == "Provisional" and rows["AN001"]["isc"]


def test_locator_table_layout_2025():
    """locate.cisce.org/result of 2025-11-02 (Wayback): the older table layout, every school on one page."""
    rows = dict(crawl.parse((PAGES / "locate-result-table-2025-excerpt.html").read_text(encoding="utf-8")))
    assert sorted(rows) == ["AN001", "AP001", "DU001", "PU100"]
    r = rows["PU100"]
    assert (r["name"], r["state"], r["pin"], r["country"], r["residence"]) == ("International Fateh Academy", "Punjab", "143115", "India", "Day/Boarding")
    assert r["icse"] and r["isc"] and not r["cve"] and r["website"] == "fatehacademy.com"
    assert r["phones"] == "9888774026; 9501108834" and r["email"].startswith("Head.PU100@")
    assert rows["DU001"]["country"] == "United Arab Emirates"


def test_frc_gujarat_list_page():
    import frc
    rows = dict(frc.parse((PAGES / "frc-gujarat-p1.html").read_text(encoding="utf-8")))
    r = rows["20771:English:GSHSEB"]
    assert len(rows) == 10 and r["SchoolCode"] == "24221531164" and r["SchoolName"] == "AADARSH MISSION SCHOOL(ENG MED)"
    assert "54487:Gujarati:GSHSEB" in rows and "54487:English:GSHSEB" in rows      # one school, two media
    assert frc.parse("<html>error</html>") is None and frc.parse("var jsonModel=[];\n") == []

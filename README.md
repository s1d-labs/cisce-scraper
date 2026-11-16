# cisce-scraper

The list of CISCE affiliated schools for the s1d-labs scrape pool, from every public source we found.

## Projects (scrape hub)

| Project | Task | Source | State |
|---|---|---|---|
| `cisce-scraper-schools` | `crawl` | [locate.cisce.org](https://locate.cisce.org/), the official locator, 10 schools per page | paused: Cloudflare shows an interactive check to automated browsers (`family.py` `PAGES = 0`) |
| `cisce-scraper-wayback` | `history` | full lists of the old official locator (www.cisce.org/locate-search.aspx), Wayback Machine copies 2015-2022; locate.cisce.org/result of 2025-11-02 (every school on one page); devlocate.cisce.org pages of 2026 | 11 lists + 1 full list + 51 pages |
| `cisce-scraper-locator-cache` | `history` | locate.cisce.org pages of 2026-10-20 from a public raw cache (see credits) | 169 pages |

Record id: the affiliation code (`crawl`), or `<date>:<code>` (`history`, one record per list).

## Merge and links

`link/merge.py` gives one row per affiliation code from all sources; `link/link.py` links codes to UDISE+;
`link/load.sh` loads the result into a team workspace database. See the docstrings.

## Credits

- [Internet Archive Wayback Machine](https://web.archive.org/): copies of www.cisce.org/locate-search.aspx, 2015-2022; the copy of
  locate.cisce.org/result of 2025-11-02 (3,221 schools on one page); copies of devlocate.cisce.org pages, 2026.
- [magesh-xseed/milestones](https://github.com/magesh-xseed/milestones): raw cache of locate.cisce.org pages, fetched 2026-10-20.
- [deedy/cisce_schools_data](https://github.com/deedy/cisce_schools_data): CISCE school list of 2018 (2,341 schools).
- [Nitish-Kumar-kushwaha/list-of-all-CISCE-schools-in-India](https://github.com/Nitish-Kumar-kushwaha/list-of-all-CISCE-schools-in-India): list of 2021.
- [Ayushmaan06/school](https://github.com/Ayushmaan06/school): a saved locate.cisce.org result page, used as a test fixture.
- [Baalaaji1/ICSE-Schools-data](https://github.com/Baalaaji1/ICSE-Schools-data): list of 2019 (not used: the Wayback copies of 2019 hold the same list).

## Check

```
pip install -r requirements.txt pytest "scrape-hub-client @ git+https://github.com/s1d-labs/runner@sdk-stable#subdirectory=sdk"
python -m playwright install chromium
python -m pytest tests -q                         # parsing, no network
scrape-check --items 2 --project cisce-scraper-locator-cache
python crawl.py --files DIR                       # listing pages saved by hand in a browser
```

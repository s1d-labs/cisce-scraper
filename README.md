# cisce-scraper

The list of CISCE affiliated schools from [locate.cisce.org](https://locate.cisce.org/), for the s1d-labs scrape pool.

- Project `cisce-scraper-schools`: one queue item per listing page and month (`<YYYY-MM>-p<n>`), 10 schools per page.
- Record id: the CISCE affiliation code (for example `AN001`). Fields: name, principal, address, locality, district, state, PIN,
  country, ICSE / ISC / CVE, gender, residence type, ASISC member, website, coordinates, `listed_total`, `page`, `seen`.
- The site is behind Cloudflare. The task uses headless Chromium (Playwright). It does not click a challenge: on an interactive
  challenge it records a `cloudflare-challenge` failure and stops.

## Check

```
pip install -r requirements.txt pytest "scrape-hub-client @ git+https://github.com/s1d-labs/runner@sdk-stable#subdirectory=sdk"
python -m playwright install chromium
python -m pytest tests -q                         # parsing, no network
python crawl.py --local "https://locate.cisce.org/?page=1"
```

The **check** workflow runs the tests, a reachability step from the GitHub runner, and `scrape-check --items 2` when the runner
gets through.

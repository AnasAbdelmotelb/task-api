# polite-scraper

FlyRank Internship · Backend Track · Week 5 · Assignment A9: **The polite scraper**.

> **Location:** this folder is the `scraper/` part of my internship repo
> [`task-api`](https://github.com/AnasAbdelmotelb/task-api), as the brief asks. The same
> project, with its full stage-by-stage commit history (Stage 0 to Stage 6), is also published
> on its own at [`polite-scraper`](https://github.com/AnasAbdelmotelb/polite-scraper). The
> scraper's User-Agent points at that standalone repo. All commands below are run from inside
> `task-api/scraper/`, and the scraper is independent of the FastAPI app in the repo root.

A small, polite scraping pipeline. It downloads the first three catalogue pages of
[Books to Scrape](https://books.toscrape.com/) and visits all 60 book pages. It turns
messy HTML into clean, schema-checked JSON, survives a broken page without crashing, and
ends every run with an honest report.

```
fetch -> extract -> normalize -> validate -> store -> report
```

## Quick start (under 5 minutes)

Lane: **Python 3.10+** with Requests, Beautiful Soup and Pydantic. Everything is free and
needs no account.

```bash
git clone https://github.com/AnasAbdelmotelb/task-api.git
cd task-api/scraper                  # everything below runs from this folder
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt

python -m src.main                   # the one command: robots check, 3 pages, 60 books, report
```

The user-agent names this repo (`CONTACT_URL` in `src/config.py`). If you fork the repo,
point it at your fork, either by editing that line or by setting
`SCRAPER_CONTACT_URL=https://github.com/<you>/polite-scraper`. The scraper refuses to make
any request while the contact URL is still a placeholder.

Outputs:

| File | What it holds |
|---|---|
| `output/books.json` | the validated records (60 on a clean run) |
| `output/errors.json` | records that failed the schema, each with its reasons (`[]` when none) |
| `output/run-report.json` | the honest numbers for this run |
| `cache/` | saved HTML, so reruns don't hit the site (git-ignored) |

Other commands:

```bash
python -m src.main --inject-broken-url   # Stage 5 drill: adds one made-up book URL
python -m pytest -q                      # 57 offline tests; none touch the real site
```

## Target classification

| Question | Answer |
|---|---|
| Which site? | `https://books.toscrape.com/`, part of the ToScrape sandbox (`https://toscrape.com/`) |
| Why this site? | On 2026-10-12 I read what `https://toscrape.com/` says about itself: it is a "Web Scraping Sandbox", and Books to Scrape is *"A fictional bookstore that desperately wants to be scraped. It's a safe place for beginners learning web scraping"*. That statement on their page is my permission. The saved check is `evidence/toscrape-sandbox-check.txt`. |
| How much? | Only the **first 3 catalogue pages** (`catalogue/page-1.html` to `page-3.html`) and the **60 book pages** they link to. That is 63 page requests plus one `robots.txt` request. |
| What data? | Per book: title, product URL, price, availability text, rating text, description, plus provenance (source page and fetch time). No personal data. |
| Why is that appropriate? | It is a public practice sandbox made for this exercise, the scope is tiny, and every request is slow, cached and clearly identified. |

**robots.txt check:** `https://books.toscrape.com/robots.txt` was requested once on
2026-10-12 at 17:01:05 UTC. Result: **no robots file found (HTTP 404)**.
A missing robots file is not permission, just a missing file. The permission comes from the
sandbox statement above. The scraper still checks the file on every run. It caches the
result, obeys any `Disallow` rules it finds, and stops if the file cannot be read (5xx or
network error), as RFC 9309 says.

I will not reuse this code on another site without checking its rules and terms first.

## Politeness rules

| Rule | How |
|---|---|
| Honest identity | `User-Agent: FlyRankInternship-A9/1.0 (+<repo URL>)` on every request |
| Slow | at least **1.0 s** between real requests (the brief asks for 0.5 s or more); cached pages need no wait |
| Never hang | **10 s** timeout on every request |
| Only 200 is a page | any other status is a failed fetch, not HTML to parse |
| Cache | every page is saved under `cache/`, so reruns read from disk |
| Scope lock | only `books.toscrape.com` can be requested, and only 3 catalogue pages |
| Retries | **one** retry after 3 s for timeouts, connection errors and 5xx. **Never** for 404 (gone) or 403 (the site said no) |
| No concurrency | one request at a time |

## Record schema

Defined once in `src/models.py` (Pydantic `BookRecord`) and exported as JSON Schema in
`schema/book-record.schema.json`. Extra fields are rejected.

| Field | Type | Rule |
|---|---|---|
| `title` | string | required, not empty |
| `product_url` | string | required; absolute `https://books.toscrape.com/...`; the **canonical identity** (duplicates count once) |
| `price_text` | string | required; raw value as scraped, e.g. `"£51.77"` |
| `price_gbp` | number | required, ≥ 0; parsed from `price_text` with `Decimal` (2 dp). Text without a `£` amount is rejected, never guessed |
| `availability_text` | string | required, e.g. `"In stock (22 available)"` |
| `rating_text` | enum | `One` / `Two` / `Three` / `Four` / `Five` |
| `description` | string or `null` | optional; `null` when the page has none (never invented) |
| `source_page` | string | catalogue page the book was found on (provenance) |
| `fetched_at` | string | ISO-8601 UTC time the HTML was really downloaded (provenance) |

A record that fails goes to `output/errors.json` with its reasons. It never enters
`books.json`. `books.json` is rewritten atomically on every run and de-duplicated by
`product_url`, so a rerun gives the same 60 records, not 120.

## How it works

| File | Job |
|---|---|
| `src/config.py` | target, scope and politeness settings in one place |
| `src/fetcher.py` | `PoliteFetcher`: user-agent, timeout, delay, status check, cache, single retry, robots.txt |
| `src/parser.py` | pure HTML to raw-record functions. Selectors aim at `article.product_page div.product_main`, not "the first price on the page" |
| `src/models.py` | price normalization and the Pydantic schema |
| `src/storage.py` | atomic JSON writes, de-duplication |
| `src/main.py` | the pipeline and `run-report.json` |
| `tests/` | offline tests; `tests/fake_site.py` imitates the site so nothing hits the network |

Design decisions:

- **Decimal, not float, for parsing.** `Decimal("51.77")` is exact. It is converted to a
  JSON number only at the end, because the brief wants a number that programs can sort.
- **Pagination follows the site's own `next` link**, so no book URLs are hardcoded.
- **Each page fails on its own.** Fetch and parse errors are recorded in the report and the
  loop moves on.
- **The cache stores `fetched_at`** next to each page, so provenance stays true on reruns.

## Real run report

This is the report from the first real run against the live site on 2026-10-12, with an
empty cache. It is copied unchanged from `evidence/run-report-first-run.json`:

```json
{
  "started_at": "2026-10-12T17:01:03Z",
  "finished_at": "2026-10-12T17:02:29Z",
  "duration_seconds": 85.48,
  "user_agent": "FlyRankInternship-A9/1.0 (+https://github.com/AnasAbdelmotelb/polite-scraper)",
  "delay_seconds": 1.0,
  "timeout_seconds": 10,
  "robots_txt": {
    "url": "https://books.toscrape.com/robots.txt",
    "status": 404,
    "checked_at": "2026-10-12T17:01:05Z",
    "result": "no robots file found"
  },
  "catalogue_pages": 3,
  "discovered_urls": 60,
  "unique_urls": 60,
  "injected_broken_url": null,
  "detail_pages_attempted": 60,
  "detail_pages_parsed": 60,
  "pages_fetched": 64,
  "cache_hits": 0,
  "retries": 0,
  "valid_records": 60,
  "invalid_records": 0,
  "duplicates_removed": 0,
  "failed_pages": 0,
  "failures": []
}
```

What the four real runs showed (full terminal output is in `evidence/`):

| Run | Command | Result |
|---|---|---|
| 1 · first run | `python -m src.main` | 3 catalogue pages, 60 discovered / 60 unique URLs, **60 valid, 0 invalid, 0 failed**, 64 real requests (robots + 3 + 60), 85.5 s |
| 2 · rerun | `python -m src.main` | **64 cache hits, 0 requests**, 60 records. `books.json` is byte-identical to run 1 (same SHA-256), so reruns don't duplicate |
| 3 · broken-page drill | `python -m src.main --inject-broken-url` | the made-up URL failed with **HTTP 404 after 1 attempt (no retry)**. The run finished, `books.json` still had **60** records, and the report showed **`failed_pages: 1`** |
| 4 · final clean run | `python -m src.main` | 60 valid, `failed_pages: 0`. This is the committed `output/run-report.json` |

Checks on the real `output/books.json` (`evidence/verify-books.txt`): 60 records, 60 unique
`product_url`s, 20 per catalogue page, every `price_gbp` a number that matches its
`price_text` (range £12.84 to £57.31), every URL `https://`, and all 60 re-validated against
`BookRecord`. `errors.json` is `[]`.

Pacing (`evidence/pacing-check.txt`): the 64 real requests have 64 distinct timestamps over
83 s. No two requests ever happened in the same second.

**Why no browser?** The book data is already in the HTML the server sends (ToScrape lists
Books to Scrape as "Requires JavaScript ✘"), so a headless browser would only add cost
(time, memory, a bigger dependency) for nothing.

## Evidence

| File | What it shows |
|---|---|
| `evidence/toscrape-sandbox-check.txt` | the site's own sandbox statement, fetched once |
| `evidence/run1-first-real-run.txt` | first real run: `FETCH` lines, robots result, 3/60/60 counts, a sample raw record |
| `evidence/run-report-first-run.json` | that run's report (pasted above) |
| `evidence/run2-rerun-cache.txt` | rerun: `CACHE HIT` for all 64 pages, `pages_fetched=0` |
| `evidence/run3-broken-url.txt`, `evidence/run-report-broken-url.json` | the broken-page drill |
| `evidence/run4-final-clean.txt` | the final clean run that produced the committed outputs |
| `evidence/verify-books.txt` | count, uniqueness, numeric prices, schema re-validation |
| `evidence/pacing-check.txt` | request spacing from the cached fetch timestamps |
| `evidence/pytest-result.txt` | test result on the same machine |

## Tests

```bash
python -m pytest -q
```

57 tests cover price normalization (valid and invalid strings), relative to absolute URLs,
next-link handling, duplicate URLs, a missing description, a malformed fixture, garbage
HTML, schema rejections, user-agent / timeout / delay / cache behaviour, the retry rules
(5xx and timeouts once, 404 and 403 never), robots.txt handling, and end-to-end runs
against a fake site. Those runs check idempotency, a broken URL, a 500 on one book, an
invalid record and a failed catalogue page.

## Limitations

- **Scope is fixed** to the first 3 catalogue pages of one sandbox site. That is deliberate.
- **The cache never expires.** A changed price on the site is not seen until `cache/` is
  deleted. That is fine for a sandbox, but a real job would need a cache lifetime or
  conditional requests.
- **Retries are basic**: one retry after a fixed wait, with no backoff and no `Retry-After`
  handling (that is next week's A16).
- If a catalogue page fails, the pages after it can't be discovered, because the next link
  lives on that page. The run reports it and continues with what it has.
- **Descriptions are stored exactly as the site serves them.** On the live site, the
  description paragraph often contains a cut-off teaser followed by the full text and
  "...more" (for example `…love th It's hard to imagine…`). That text really is in the HTML,
  so I keep it verbatim rather than guessing which part is "right". None of the first 60
  books lacks a description; the `null` case is covered by a test fixture.
- `price_gbp` is a JSON float. That is fine for display and sorting, but money maths should
  re-parse `price_text` with `Decimal`.

## Ethics note

I used Books to Scrape because it is a practice site for learning web scraping. I limited the project to the first three catalogue pages and the 60 books listed there. The robots.txt request returned HTTP 404, and I recorded that result without treating it as permission to scrape any website without restrictions.

My scraper identifies itself through the repository URL in its User-Agent, waits at least one second between requests, uses timeouts, and caches pages to avoid unnecessary repeat requests. It retries eligible temporary errors once and logs and skips a 404 without retrying.

Before using this scraper on another website, I would check its rules and terms first. I would prefer an official API when available and would not bypass logins, paywalls, or access restrictions.

"""Polite scraper for the Books to Scrape practice sandbox (FlyRank W5 · A9).

Pipeline: robots check -> discover 3 catalogue pages -> fetch + extract 60 book pages
-> normalize -> validate -> store -> report.

    python -m src.main                      # normal run
    python -m src.main --inject-broken-url  # Stage 5 drill: one made-up URL is added
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from . import config
from .fetcher import PoliteFetcher, utc_now_iso
from .models import normalize_and_validate
from .parser import book_cache_name, parse_book, parse_catalogue, unique_in_order
from .storage import dedupe_by_url, write_json


def discover(fetcher: PoliteFetcher, failures: list, max_pages: int = config.MAX_CATALOGUE_PAGES):
    """Return (pages_ok, list of (book_url, source_page)) for the first `max_pages` pages."""
    found: list[tuple[str, str]] = []
    page_url: str | None = config.START_URL
    pages_ok = 0
    for page_no in range(1, max_pages + 1):
        if page_url is None:
            break
        result = fetcher.get(page_url, f"catalogue-page-{page_no}.html")
        if not result.ok:
            failures.append(_failure(page_url, "catalogue", result.status, result.error, result.attempts))
            break  # without this page we cannot know where the next one is
        try:
            urls, next_url = parse_catalogue(result.text, page_url)
        except Exception as exc:  # a broken page is logged, never fatal
            failures.append(_failure(page_url, "catalogue", 200, f"parse error: {exc}", result.attempts))
            break
        pages_ok += 1
        found.extend((u, page_url) for u in urls)
        page_url = next_url  # let the site tell us where page N+1 is
    return pages_ok, found


def _failure(url, kind, status, error, attempts):
    return {"url": url, "kind": kind, "status": status, "error": error, "attempts": attempts}


def run(fetcher: PoliteFetcher, output_dir: str | Path = config.OUTPUT_DIR,
        inject_broken_url: bool = False) -> dict:
    started_at, t0 = utc_now_iso(), time.monotonic()
    out = Path(output_dir)
    failures: list[dict] = []

    robots = fetcher.check_robots()
    detail = f"HTTP {robots['status']}" if robots["status"] is not None else robots.get("error")
    print(f"ROBOTS {robots['url']}: {robots['result']} ({detail})")

    pages_ok = discovered = 0
    unique: list[str] = []
    raw_records: list[dict] = []
    if robots["result"] == "unreachable":
        failures.append(_failure(robots["url"], "robots", robots["status"], robots.get("error"), 1))
        print("robots.txt could not be read: stopping without scraping (RFC 9309).")
    else:
        pages_ok, found = discover(fetcher, failures)
        discovered = len(found)
        unique = unique_in_order([u for u, _ in found])
        print(f"catalogue_pages={pages_ok} discovered={discovered} unique_urls={len(unique)}")

        source_of: dict[str, str] = {}
        for url, src in found:
            source_of.setdefault(url, src)
        if inject_broken_url:
            print(f"DRILL: adding made-up URL {config.BROKEN_URL}")
            unique.append(config.BROKEN_URL)
            source_of[config.BROKEN_URL] = config.START_URL

        for url in unique:  # each page on its own: one bad page never stops the run
            if not fetcher.allowed_by_robots(url):
                failures.append(_failure(url, "detail", None, "disallowed by robots.txt", 0))
                continue
            result = fetcher.get(url, book_cache_name(url))
            if not result.ok:
                failures.append(_failure(url, "detail", result.status, result.error, result.attempts))
                continue
            try:
                raw_records.append(parse_book(result.text, url, source_of[url], result.fetched_at))
            except Exception as exc:
                failures.append(_failure(url, "detail", 200, f"parse error: {exc}", result.attempts))
        print(f"detail_pages={len(raw_records)}")
        if raw_records:
            print("sample raw record:")
            print(json.dumps(raw_records[0], indent=2, ensure_ascii=False))

    valid, errors = [], []
    for raw in raw_records:
        record, reasons = normalize_and_validate(raw)
        if record is None:
            errors.append({"product_url": raw.get("product_url"), "reasons": reasons, "raw": raw})
        else:
            valid.append(record.model_dump())
    valid, duplicates = dedupe_by_url(valid)

    if valid:
        write_json(out / "books.json", valid)  # overwrite, never append: reruns stay at 60
    else:
        print("no valid records this run: books.json left untouched")
    write_json(out / "errors.json", errors)

    report = {
        "started_at": started_at,
        "finished_at": utc_now_iso(),
        "duration_seconds": round(time.monotonic() - t0, 2),
        "user_agent": fetcher.user_agent,
        "delay_seconds": fetcher.delay,
        "timeout_seconds": fetcher.timeout,
        "robots_txt": robots,
        "catalogue_pages": pages_ok,
        "discovered_urls": discovered,
        "unique_urls": len(set(unique) - {config.BROKEN_URL}) if inject_broken_url else len(unique),
        "injected_broken_url": config.BROKEN_URL if inject_broken_url else None,
        "detail_pages_attempted": len(unique),
        "detail_pages_parsed": len(raw_records),
        "pages_fetched": fetcher.network_requests,
        "cache_hits": fetcher.cache_hits,
        "retries": fetcher.retries,
        "valid_records": len(valid),
        "invalid_records": len(errors),
        "duplicates_removed": duplicates,
        "failed_pages": len(failures),
        "failures": failures,
    }
    write_json(out / "run-report.json", report)
    print(
        f"REPORT valid={report['valid_records']} invalid={report['invalid_records']} "
        f"failed_pages={report['failed_pages']} pages_fetched={report['pages_fetched']} "
        f"cache_hits={report['cache_hits']} retries={report['retries']} "
        f"duration={report['duration_seconds']}s -> {out / 'run-report.json'}"
    )
    return report


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Polite Books to Scrape scraper (FlyRank A9)")
    ap.add_argument("--inject-broken-url", action="store_true",
                    help="add one made-up book URL to prove a broken page is skipped")
    ap.add_argument("--output-dir", default=config.OUTPUT_DIR)
    ap.add_argument("--cache-dir", default=config.CACHE_DIR)
    args = ap.parse_args(argv)

    if config.contact_url_is_placeholder():
        print("Refusing to run: set SCRAPER_CONTACT_URL (or edit src/config.py) so the "
              "user-agent honestly points at your repo.")
        return 2
    print(f"USER-AGENT {config.USER_AGENT} | delay={config.REQUEST_DELAY_SECONDS}s "
          f"timeout={config.TIMEOUT_SECONDS}s")
    report = run(PoliteFetcher(cache_dir=args.cache_dir), args.output_dir, args.inject_broken_url)
    return 0 if report["valid_records"] > 0 else 1


if __name__ == "__main__":
    sys.exit(main())

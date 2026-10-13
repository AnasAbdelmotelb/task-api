"""End-to-end runs against the offline fake site: no real network traffic."""

import json

from src import config, main
from src.fetcher import PoliteFetcher
from tests.fake_site import FakeResponse, FakeSession, fake_site_routes


def run_once(tmp_path, routes=None, inject=False):
    session = FakeSession(routes or fake_site_routes())
    fetcher = PoliteFetcher(cache_dir=tmp_path / "cache", session=session,
                            sleep=lambda s: None, log=lambda m: None)
    report = main.run(fetcher, tmp_path / "output", inject_broken_url=inject)
    books = json.loads((tmp_path / "output" / "books.json").read_text(encoding="utf-8"))
    errors = json.loads((tmp_path / "output" / "errors.json").read_text(encoding="utf-8"))
    return report, books, errors, session


def test_clean_run_gives_exactly_60_valid_unique_records(tmp_path):
    report, books, errors, session = run_once(tmp_path)
    assert report["catalogue_pages"] == 3  # page 4 exists on the fake site but is not visited
    assert report["discovered_urls"] == 60 and report["unique_urls"] == 60
    assert len(books) == 60 and len({b["product_url"] for b in books}) == 60
    assert all(isinstance(b["price_gbp"], float) for b in books)
    assert all(b["product_url"].startswith("https://") for b in books)
    assert errors == [] and report["failed_pages"] == 0
    assert not any("page-4" in c["url"] for c in session.calls)
    assert len(session.calls) == 64  # robots + 3 catalogue + 60 books


def test_rerun_is_idempotent_and_served_from_cache(tmp_path):
    _, first, _, _ = run_once(tmp_path)
    report, second, _, session = run_once(tmp_path)
    assert second == first and len(second) == 60
    assert session.calls == [] and report["cache_hits"] == 64 and report["pages_fetched"] == 0


def test_broken_url_is_skipped_and_reported(tmp_path):
    report, books, _, _ = run_once(tmp_path, inject=True)
    assert len(books) == 60
    assert report["failed_pages"] == 1
    assert report["failures"][0]["url"] == config.BROKEN_URL
    assert report["failures"][0]["status"] == 404 and report["failures"][0]["attempts"] == 1


def test_server_error_on_one_book_does_not_kill_the_run(tmp_path):
    routes = fake_site_routes()
    bad = "https://books.toscrape.com/catalogue/fake-book-5_996/index.html"
    routes[bad] = FakeResponse(500, "boom")
    report, books, _, session = run_once(tmp_path, routes)
    assert len(books) == 59 and report["failed_pages"] == 1 and report["retries"] == 1
    assert sum(c["url"] == bad for c in session.calls) == 2  # tried once more, then gave up


def test_malformed_book_goes_to_errors_json_not_books_json(tmp_path):
    routes = fake_site_routes()
    bad = "https://books.toscrape.com/catalogue/fake-book-2_999/index.html"
    routes[bad] = FakeResponse(200, "<html><body><article class='product_page'>"
                                    "<div class='product_main'><h1>X</h1>"
                                    "<p class='price_color'>free!</p></div></article>")
    report, books, errors, _ = run_once(tmp_path, routes)
    assert len(books) == 59 and report["invalid_records"] == 1
    assert errors[0]["product_url"] == bad and errors[0]["reasons"]
    assert bad not in {b["product_url"] for b in books}


def test_catalogue_failure_is_reported_without_crashing(tmp_path):
    routes = fake_site_routes()
    routes["https://books.toscrape.com/catalogue/page-2.html"] = FakeResponse(503, "")
    report, books, _, _ = run_once(tmp_path, routes)
    assert report["catalogue_pages"] == 1 and len(books) == 20
    assert report["failures"][0]["kind"] == "catalogue"


def test_report_has_required_fields(tmp_path):
    report, _, _, _ = run_once(tmp_path)
    for key in ["started_at", "duration_seconds", "pages_fetched", "cache_hits",
                "valid_records", "invalid_records", "failed_pages"]:
        assert key in report


def test_cli_refuses_to_run_with_placeholder_contact(monkeypatch, capsys):
    monkeypatch.setattr(config, "CONTACT_URL", "https://github.com/YOUR-GITHUB-USERNAME/polite-scraper")
    assert main.main([]) == 2
    assert "Refusing to run" in capsys.readouterr().out

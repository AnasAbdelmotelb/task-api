import json
from pathlib import Path

from src.models import BookRecord, normalize_and_validate
from src.parser import parse_book
from src.storage import dedupe_by_url, write_json

GOOD = {
    "title": "A Light in the Attic",
    "product_url": "https://books.toscrape.com/catalogue/a-light-in-the-attic_1000/index.html",
    "price_text": "£51.77",
    "availability_text": "In stock (22 available)",
    "rating_text": "Three",
    "description": None,
    "source_page": "https://books.toscrape.com/catalogue/page-1.html",
    "fetched_at": "2026-10-12T10:00:00Z",
}


def test_good_raw_record_validates_with_numeric_price():
    record, reasons = normalize_and_validate(GOOD)
    assert reasons == []
    assert record.price_gbp == 51.77 and isinstance(record.price_gbp, float)
    assert record.price_text == "£51.77"  # raw kept beside clean
    assert record.description is None


def _reasons(**changes):
    record, reasons = normalize_and_validate({**GOOD, **changes})
    assert record is None
    return " | ".join(reasons)


def test_missing_title_is_rejected():
    assert "title" in _reasons(title=None)


def test_relative_or_http_or_foreign_urls_are_rejected():
    assert "product_url" in _reasons(product_url="a-light_1000/index.html")
    assert "product_url" in _reasons(product_url="http://books.toscrape.com/catalogue/x/index.html")
    assert "product_url" in _reasons(product_url="https://evil.example/catalogue/x/index.html")


def test_bad_price_and_rating_and_timestamp_are_rejected():
    assert "price_gbp" in _reasons(price_text="Price on request")
    assert "rating_text" in _reasons(rating_text="Seven")
    assert "fetched_at" in _reasons(fetched_at="yesterday")
    assert "fetched_at" in _reasons(fetched_at="2026-10-12T10:00:00")  # no timezone


def test_empty_description_string_and_extra_fields_are_rejected():
    assert "description" in _reasons(description="")
    assert "surprise" in _reasons(surprise="field")


def test_malformed_fixture_ends_up_with_reasons(fixture_html):
    raw = parse_book(fixture_html("book_malformed.html"), GOOD["product_url"],
                     GOOD["source_page"], GOOD["fetched_at"])
    record, reasons = normalize_and_validate(raw)
    assert record is None and reasons  # goes to errors.json, never books.json


def test_dedupe_keeps_first_record_per_canonical_url():
    other = {**GOOD, "product_url": GOOD["product_url"].replace("1000", "999")}
    records, removed = dedupe_by_url([GOOD, other, dict(GOOD)])
    assert len(records) == 2 and removed == 1


def test_write_json_is_valid_json_and_overwrites(tmp_path: Path):
    path = tmp_path / "out" / "books.json"
    write_json(path, [GOOD, GOOD])
    write_json(path, [GOOD])
    assert json.loads(path.read_text(encoding="utf-8")) == [GOOD]
    assert not list(path.parent.glob("*.tmp"))


def test_schema_marks_description_optional_and_others_required():
    schema = BookRecord.model_json_schema()
    assert "description" not in schema["required"]
    assert {"title", "product_url", "price_gbp", "source_page", "fetched_at"} <= set(schema["required"])

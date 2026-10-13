from src.parser import (book_cache_name, clean_text, parse_book, parse_catalogue,
                        unique_in_order)

PAGE1 = "https://books.toscrape.com/catalogue/page-1.html"
BOOK = "https://books.toscrape.com/catalogue/a-light-in-the-attic_1000/index.html"
T = "2026-10-12T10:00:00Z"


def test_catalogue_links_become_absolute_and_next_link_is_followed(fixture_html):
    urls, next_url = parse_catalogue(fixture_html("catalogue_page.html"), PAGE1)
    assert urls[0] == BOOK
    assert all(u.startswith("https://books.toscrape.com/catalogue/") for u in urls)
    assert next_url == "https://books.toscrape.com/catalogue/page-2.html"


def test_parent_relative_links_resolve_with_urljoin():
    html = '<article class="product_pod"><h3><a href="../../../a-book_1/index.html">x</a></h3></article>'
    urls, _ = parse_catalogue(html, "https://books.toscrape.com/catalogue/category/books/poetry_23/index.html")
    assert urls == ["https://books.toscrape.com/catalogue/a-book_1/index.html"]


def test_last_page_has_no_next_link(fixture_html):
    _, next_url = parse_catalogue(fixture_html("catalogue_last_page.html"), PAGE1)
    assert next_url is None


def test_duplicate_urls_are_removed_in_order(fixture_html):
    urls, _ = parse_catalogue(fixture_html("catalogue_page.html"), PAGE1)
    assert len(urls) == 3  # the card without a link is ignored
    assert unique_in_order(urls) == [BOOK, "https://books.toscrape.com/catalogue/tipping-the-velvet_999/index.html"]


def test_full_book_page_gives_all_eight_raw_fields(fixture_html):
    raw = parse_book(fixture_html("book_full.html"), BOOK, PAGE1, T)
    assert list(raw) == ["title", "product_url", "price_text", "availability_text",
                         "rating_text", "description", "source_page", "fetched_at"]
    assert raw["title"] == "A Light in the Attic"
    assert raw["price_text"] == "£51.77"  # not the £1.00 decoy outside product_main
    assert raw["availability_text"] == "In stock (22 available)"
    assert raw["rating_text"] == "Three"
    assert raw["description"].startswith("It's hard to imagine a world without A Light in the Attic. This")
    assert "&amp;" not in raw["description"] and "  " not in raw["description"]
    assert (raw["source_page"], raw["fetched_at"]) == (PAGE1, T)


def test_missing_description_is_null_not_invented(fixture_html):
    raw = parse_book(fixture_html("book_no_description.html"), BOOK, PAGE1, T)
    assert raw["description"] is None
    assert raw["title"] == "Alice in Wonderland (Alice's Adventures in Wonderland #1)"
    assert raw["price_text"] == "£55.53"
    assert len(raw) == 8  # key still present


def test_malformed_page_yields_nones_instead_of_crashing(fixture_html):
    raw = parse_book(fixture_html("book_malformed.html"), BOOK, PAGE1, T)
    assert raw["title"] is None
    assert raw["availability_text"] is None
    assert raw["rating_text"] is None  # "Seven" is not a rating word
    assert raw["description"] is None
    assert raw["price_text"] == "Price on request"  # kept raw; validation rejects it later


def test_garbage_html_does_not_crash():
    raw = parse_book("<<<not html at all", BOOK, PAGE1, T)
    assert raw["title"] is None and raw["product_url"] == BOOK
    assert parse_catalogue("", PAGE1) == ([], None)


def test_clean_text_and_cache_names():
    assert clean_text("  a \n\t b  ") == "a b"
    assert clean_text("   ") is None
    assert book_cache_name(BOOK) == "books/a-light-in-the-attic_1000.html"

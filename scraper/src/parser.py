"""HTML extraction. Pure functions: HTML string in, Python values out, with no network access.

Selectors are aimed at the product area of the page, never at "the first thing that
looks like a price" in the whole document.
"""

from __future__ import annotations

from urllib.parse import urljoin

from bs4 import BeautifulSoup


def clean_text(value: str | None) -> str | None:
    """Collapse runs of whitespace; return None for empty text."""
    if value is None:
        return None
    text = " ".join(value.split())
    return text or None


def parse_catalogue(html: str, page_url: str) -> tuple[list[str], str | None]:
    """Return (absolute book URLs on this page, absolute next-page URL or None)."""
    soup = BeautifulSoup(html, "html.parser")
    book_urls = []
    for link in soup.select("article.product_pod h3 a[href]"):
        book_urls.append(urljoin(page_url, link["href"]))  # never glue strings together
    next_link = soup.select_one("ul.pager li.next a[href]")
    next_url = urljoin(page_url, next_link["href"]) if next_link else None
    return book_urls, next_url


def unique_in_order(urls: list[str]) -> list[str]:
    """Drop duplicate URLs, keeping first-seen order."""
    return list(dict.fromkeys(urls))


RATING_WORDS = {"One", "Two", "Three", "Four", "Five"}


def parse_book(html: str, product_url: str, source_page: str, fetched_at: str) -> dict:
    """Extract the eight raw fields from one book page.

    Missing values become None. Nothing is invented; validation decides later
    whether the record is good enough to store.
    """
    soup = BeautifulSoup(html, "html.parser")
    main = soup.select_one("article.product_page div.product_main")

    title = price_text = availability_text = rating_text = None
    if main is not None:
        h1 = main.find("h1")
        title = clean_text(h1.get_text()) if h1 else None
        price = main.select_one("p.price_color")
        price_text = clean_text(price.get_text()) if price else None
        avail = main.select_one("p.availability")
        availability_text = clean_text(avail.get_text()) if avail else None
        stars = main.select_one("p.star-rating")
        if stars is not None:
            words = [c for c in stars.get("class", []) if c in RATING_WORDS]
            rating_text = words[0] if words else None

    description = None
    header = soup.select_one("article.product_page #product_description")
    if header is not None:
        para = header.find_next_sibling("p")
        description = clean_text(para.get_text()) if para else None

    return {
        "title": title,
        "product_url": product_url,
        "price_text": price_text,
        "availability_text": availability_text,
        "rating_text": rating_text,
        "description": description,
        "source_page": source_page,
        "fetched_at": fetched_at,
    }


def book_cache_name(product_url: str) -> str:
    """'.../catalogue/a-light-in-the-attic_1000/index.html' -> 'books/a-light-in-the-attic_1000.html'."""
    parts = [p for p in product_url.split("/") if p]
    slug = parts[-2] if len(parts) >= 2 and parts[-1] == "index.html" else parts[-1]
    safe = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in slug)
    return f"books/{safe}.html"

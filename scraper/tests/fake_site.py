"""A tiny offline imitation of Books to Scrape, used by tests so they never hit the real site.

The HTML is hand-written to mirror the real page structure (product_pod cards, a
`li.next` pager, a `product_main` block, `#product_description` followed by a <p>), with
some mess added on purpose: extra whitespace, HTML entities, a decoy price outside the
product area, and a few books without a description.
"""

from __future__ import annotations

import requests

CATALOGUE = "https://books.toscrape.com/catalogue/"
RATINGS = ["One", "Two", "Three", "Four", "Five"]


def make_books(n_pages: int = 4, per_page: int = 20) -> list[dict]:
    books = []
    for i in range(n_pages * per_page):
        slug = f"fake-book-{i + 1}_{1000 - i}"
        books.append({
            "slug": slug,
            "url": f"{CATALOGUE}{slug}/index.html",
            "title": f"Fake Book {i + 1} & Friends",
            "price": f"£{10 + i}.{i % 100:02d}",
            "stock": f"In stock ({(i % 22) + 1} available)",
            "rating": RATINGS[i % 5],
            # every 7th book has no description, like some real books
            "description": None if i % 7 == 3 else f"  Description of book {i + 1}.\n  It has   messy   spacing. ",
        })
    return books


def catalogue_html(page: int, books: list[dict], has_next: bool) -> str:
    cards = "".join(
        f"""
        <li class="col-xs-6 col-sm-4 col-md-3 col-lg-3">
          <article class="product_pod">
            <div class="image_container"><a href="{b['slug']}/index.html"><img src="x.jpg" alt="x"></a></div>
            <p class="star-rating {b['rating']}"></p>
            <h3><a href="{b['slug']}/index.html" title="{b['title'].replace('&', '&amp;')}">{b['title'][:10].replace('&', '&amp;')}...</a></h3>
            <div class="product_price"><p class="price_color">{b['price']}</p></div>
          </article>
        </li>"""
        for b in books
    )
    nxt = f'<li class="next"><a href="page-{page + 1}.html">next</a></li>' if has_next else ""
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8"><title>All products</title></head>
<body><div class="page_inner"><section>
<div class="alert alert-warning">Warning! This is a demo website for web scraping purposes.</div>
<ol class="row">{cards}</ol>
<ul class="pager"><li class="current">Page {page} of 4</li>{nxt}</ul>
</section></div></body></html>"""


def book_html(b: dict) -> str:
    desc = (
        f'<div id="product_description" class="sub-header"><h2>Product Description</h2></div>\n<p>{b["description"]}</p>'
        if b["description"] is not None else ""
    )
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8"><title>{b['title'].replace('&', '&amp;')}</title></head>
<body>
<div class="promo"><p class="price_color">£0.99</p></div>
<article class="product_page">
  <div class="row">
    <div class="col-sm-6 product_main">
      <h1>  {b['title'].replace('&', '&amp;')}  </h1>
      <p class="price_color">{b['price']}</p>
      <p class="instock availability">
          <i class="icon-ok"></i>

          {b['stock']}

      </p>
      <p class="star-rating {b['rating']}"><i class="icon-star"></i></p>
    </div>
  </div>
  {desc}
  <div class="sub-header"><h2>Product Information</h2></div>
  <table class="table table-striped"><tr><th>Price (excl. tax)</th><td>{b['price']}</td></tr></table>
</article>
</body></html>"""


class FakeResponse:
    def __init__(self, status_code: int, body: str | bytes = b""):
        self.status_code = status_code
        self.content = body.encode("utf-8") if isinstance(body, str) else body


class FakeSession:
    """Stands in for requests.Session. `routes` maps URL -> FakeResponse, an exception,
    or a list of those (consumed one per call). Unknown URLs return 404."""

    def __init__(self, routes: dict | None = None):
        self.routes = routes or {}
        self.calls: list[dict] = []

    def get(self, url, headers=None, timeout=None):
        self.calls.append({"url": url, "headers": headers or {}, "timeout": timeout})
        route = self.routes.get(url, FakeResponse(404, "not found"))
        if isinstance(route, list):
            route = route.pop(0) if len(route) > 1 else route[0]
        if isinstance(route, Exception):
            raise route
        return route


def fake_site_routes(n_pages: int = 4) -> dict:
    """Routes for a 4-page fake catalogue (so 'stop after 3' is actually tested)."""
    books = make_books(n_pages)
    routes = {"https://books.toscrape.com/robots.txt": FakeResponse(404, "Not Found")}
    for p in range(1, n_pages + 1):
        chunk = books[(p - 1) * 20: p * 20]
        routes[f"{CATALOGUE}page-{p}.html"] = FakeResponse(200, catalogue_html(p, chunk, p < n_pages))
    for b in books:
        routes[b["url"]] = FakeResponse(200, book_html(b))
    return routes


__all__ = ["FakeResponse", "FakeSession", "fake_site_routes", "make_books", "requests"]

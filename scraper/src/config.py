"""All politeness and scope settings live here, so they are easy to read and review."""

import os

BASE_URL = "https://books.toscrape.com/"
START_URL = "https://books.toscrape.com/catalogue/page-1.html"
ALLOWED_HOST = "books.toscrape.com"  # the scraper refuses to request any other host
MAX_CATALOGUE_PAGES = 3
ROBOTS_URL = "https://books.toscrape.com/robots.txt"
# Made-up URL for the Stage 5 failure drill (--inject-broken-url). Expected: HTTP 404, no retry.
BROKEN_URL = "https://books.toscrape.com/catalogue/flyrank-a9-this-book-does-not-exist_0/index.html"

# Honest identification. Set SCRAPER_CONTACT_URL, or edit the default, to point at YOUR repo.
CONTACT_URL = os.environ.get(
    "SCRAPER_CONTACT_URL", "https://github.com/AnasAbdelmotelb/polite-scraper"
)
USER_AGENT = f"FlyRankInternship-A9/1.0 (+{CONTACT_URL})"

REQUEST_DELAY_SECONDS = 1.0  # brief requires >= 0.5 s; 1 s is gentler
TIMEOUT_SECONDS = 10  # never wait forever
RETRY_WAIT_SECONDS = 3.0  # one retry, only for timeouts / connection errors / 5xx

CACHE_DIR = "cache"
OUTPUT_DIR = "output"


def contact_url_is_placeholder() -> bool:
    return "YOUR-GITHUB-USERNAME" in CONTACT_URL

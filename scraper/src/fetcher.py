"""Polite HTTP fetching with an on-disk cache.

Rules: honest user-agent, timeout, status check, a delay between real requests,
and a cache so the site sees each page only once.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import requests

from . import config


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class FetchResult:
    url: str
    ok: bool
    status: int | None = None
    text: str | None = None
    from_cache: bool = False
    fetched_at: str | None = None
    size: int = 0
    error: str | None = None
    attempts: int = 0


class PoliteFetcher:
    def __init__(
        self,
        cache_dir: str | Path = config.CACHE_DIR,
        session=None,
        user_agent: str = config.USER_AGENT,
        delay: float = config.REQUEST_DELAY_SECONDS,
        timeout: float = config.TIMEOUT_SECONDS,
        retry_wait: float = config.RETRY_WAIT_SECONDS,
        allowed_host: str = config.ALLOWED_HOST,
        sleep=time.sleep,
        clock=time.monotonic,
        log=print,
    ):
        self.cache_dir = Path(cache_dir)
        self.session = session or requests.Session()
        self.user_agent = user_agent
        self.delay = delay
        self.timeout = timeout
        self.retry_wait = retry_wait
        self.allowed_host = allowed_host
        self._sleep = sleep
        self._clock = clock
        self._log = log
        self._last_request_at: float | None = None
        self.network_requests = 0
        self.cache_hits = 0
        self.retries = 0

    # ---- cache -------------------------------------------------------------
    def _paths(self, cache_name: str) -> tuple[Path, Path]:
        html = self.cache_dir / cache_name
        return html, html.with_name(html.name + ".meta.json")

    def _read_cache(self, url: str, cache_name: str) -> FetchResult | None:
        html_path, meta_path = self._paths(cache_name)
        if not (html_path.exists() and meta_path.exists()):
            return None
        body = html_path.read_bytes()
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        self.cache_hits += 1
        self._log(f"CACHE HIT {url} ({len(body)} bytes)")
        return FetchResult(
            url=url, ok=True, status=meta.get("status", 200),
            text=body.decode("utf-8", errors="replace"), from_cache=True,
            fetched_at=meta["fetched_at"], size=len(body),
        )

    def _write_cache(self, url: str, cache_name: str, body: bytes, fetched_at: str) -> None:
        html_path, meta_path = self._paths(cache_name)
        html_path.parent.mkdir(parents=True, exist_ok=True)
        html_path.write_bytes(body)
        meta_path.write_text(
            json.dumps({"url": url, "status": 200, "fetched_at": fetched_at, "bytes": len(body)}),
            encoding="utf-8",
        )

    # ---- politeness --------------------------------------------------------
    def _wait_turn(self) -> None:
        """Sleep so there are at least `delay` seconds between the END of the previous
        real request and the start of the next one (a slow response doesn't eat the gap)."""
        if self._last_request_at is not None:
            remaining = self.delay - (self._clock() - self._last_request_at)
            if remaining > 0:
                self._sleep(remaining)

    # ---- public API --------------------------------------------------------
    def get(self, url: str, cache_name: str) -> FetchResult:
        if urlparse(url).hostname != self.allowed_host:
            return FetchResult(url=url, ok=False, error=f"host not allowed: {urlparse(url).hostname}")

        cached = self._read_cache(url, cache_name)
        if cached:
            return cached

        result = self._request_once(url)
        if result.retryable:  # timeout, connection error or 5xx: wait a moment, try ONCE more
            self.retries += 1
            self._log(f"RETRY {url} after {result.error} (waiting {self.retry_wait}s)")
            self._sleep(self.retry_wait)
            result = self._request_once(url)
            result.attempts = 2
        else:
            result.attempts = 1

        if not result.ok:
            self._log(f"FAIL {url} ({result.error}, attempts={result.attempts})")
            return result.to_public()
        self._write_cache(url, cache_name, result.body, result.fetched_at)
        self._log(f"FETCH {url} (HTTP 200, {result.size} bytes)")
        return result.to_public()

    # ---- robots.txt -------------------------------------------------------
    def check_robots(self, robots_url: str = config.ROBOTS_URL) -> dict:
        """Request robots.txt once (the result is cached) and return what happened.

        Outcomes, following RFC 9309:
          200        -> parse the rules; each URL is checked with can_fetch()
          4xx        -> "no robots file found"; no robot rules apply. That is NOT permission:
                        our permission is the sandbox's own statement (see README)
          5xx/error  -> "unreachable": stop, because the rules cannot be read
        """
        cache_path = self.cache_dir / "robots-check.json"
        if cache_path.exists():
            info = json.loads(cache_path.read_text(encoding="utf-8"))
            self.cache_hits += 1
            self._log(f"CACHE HIT {robots_url} (robots result: {info['result']})")
        else:
            attempt = self._request_once(robots_url)
            info = {"url": robots_url, "status": attempt.status, "checked_at": utc_now_iso()}
            if attempt.ok:
                info["result"] = "found"
                info["text"] = attempt.body.decode("utf-8", errors="replace")
            elif attempt.status is not None and 400 <= attempt.status < 500:
                info["result"] = "no robots file found"
            else:
                info["result"] = "unreachable"
                info["error"] = attempt.error
            if info["result"] != "unreachable":  # never cache a transient failure
                cache_path.parent.mkdir(parents=True, exist_ok=True)
                cache_path.write_text(json.dumps(info, indent=2), encoding="utf-8")
            self._log(f"FETCH {robots_url} ({attempt.error or 'HTTP ' + str(attempt.status)})")

        parser = None
        if info["result"] == "found":
            parser = RobotFileParser()
            parser.parse(info["text"].splitlines())
        self._robots = parser
        return {k: v for k, v in info.items() if k != "text"}

    def allowed_by_robots(self, url: str) -> bool:
        parser = getattr(self, "_robots", None)
        return True if parser is None else parser.can_fetch(self.user_agent, url)

    def _request_once(self, url: str) -> "_Attempt":
        self._wait_turn()
        self.network_requests += 1
        fetched_at = utc_now_iso()
        try:
            resp = self.session.get(
                url, headers={"User-Agent": self.user_agent}, timeout=self.timeout
            )
        except (requests.Timeout, requests.ConnectionError) as exc:
            return _Attempt(url, ok=False, retryable=True, error=type(exc).__name__)
        except requests.RequestException as exc:
            return _Attempt(url, ok=False, retryable=False, error=type(exc).__name__)
        finally:
            self._last_request_at = self._clock()

        if resp.status_code != 200:  # only 200 means "here is your page"
            # 5xx may be temporary; 4xx (404 gone, 403 "no") will not change by asking again
            return _Attempt(url, ok=False, status=resp.status_code,
                            retryable=resp.status_code >= 500, error=f"HTTP {resp.status_code}")
        body = resp.content or b""
        return _Attempt(url, ok=True, status=200, body=body, fetched_at=fetched_at)


@dataclass
class _Attempt:
    url: str
    ok: bool
    retryable: bool = False
    status: int | None = None
    body: bytes = b""
    fetched_at: str | None = None
    error: str | None = None
    attempts: int = 1

    @property
    def size(self) -> int:
        return len(self.body)

    def to_public(self) -> FetchResult:
        return FetchResult(
            url=self.url, ok=self.ok, status=self.status,
            text=self.body.decode("utf-8", errors="replace") if self.ok else None,
            fetched_at=self.fetched_at, size=self.size, error=self.error,
            attempts=self.attempts,
        )

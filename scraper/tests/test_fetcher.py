import requests

from src.fetcher import PoliteFetcher
from tests.fake_site import FakeResponse, FakeSession

URL = "https://books.toscrape.com/catalogue/page-1.html"


class Clock:
    def __init__(self):
        self.now = 0.0
        self.sleeps = []

    def time(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


def make(tmp_path, routes, clock=None):
    clock = clock or Clock()
    session = FakeSession(routes)
    logs = []
    f = PoliteFetcher(cache_dir=tmp_path, session=session, user_agent="TestBot/1.0 (+https://example.org)",
                      delay=1.0, timeout=7, retry_wait=3.0, sleep=clock.sleep, clock=clock.time,
                      log=logs.append)
    return f, session, clock, logs


def test_sends_user_agent_and_timeout_then_caches(tmp_path):
    f, s, _, logs = make(tmp_path, {URL: FakeResponse(200, "<html>ok £</html>")})
    first = f.get(URL, "catalogue-page-1.html")
    second = f.get(URL, "catalogue-page-1.html")
    assert first.ok and not first.from_cache and second.from_cache
    assert second.text == first.text and "£" in second.text
    assert second.fetched_at == first.fetched_at  # provenance survives the cache
    assert len(s.calls) == 1
    assert s.calls[0]["headers"]["User-Agent"] == "TestBot/1.0 (+https://example.org)"
    assert s.calls[0]["timeout"] == 7
    assert logs[0].startswith("FETCH") and logs[1].startswith("CACHE HIT")
    assert (tmp_path / "catalogue-page-1.html").exists()


def test_waits_between_real_requests_but_not_for_cache(tmp_path):
    routes = {URL: FakeResponse(200, "a"), URL + "?2": FakeResponse(200, "b")}
    f, _, clock, _ = make(tmp_path, routes)
    f.get(URL, "a.html")
    f.get(URL, "a.html")          # cache hit: no wait
    f.get(URL + "?2", "b.html")   # real request: waits 1 s
    assert clock.sleeps == [1.0]
    assert all(s >= 0.5 for s in clock.sleeps)


def test_404_is_a_failure_and_not_retried_or_cached(tmp_path):
    f, s, _, _ = make(tmp_path, {URL: FakeResponse(404, "nope")})
    r = f.get(URL, "x.html")
    assert not r.ok and r.status == 404 and r.attempts == 1 and r.text is None
    assert len(s.calls) == 1 and f.retries == 0
    assert not (tmp_path / "x.html").exists()


def test_403_is_not_retried(tmp_path):
    f, s, _, _ = make(tmp_path, {URL: FakeResponse(403, "go away")})
    assert not f.get(URL, "x.html").ok
    assert len(s.calls) == 1


def test_5xx_is_retried_once_then_succeeds(tmp_path):
    f, s, clock, _ = make(tmp_path, {URL: [FakeResponse(503, ""), FakeResponse(200, "fine")]})
    r = f.get(URL, "x.html")
    assert r.ok and r.attempts == 2 and len(s.calls) == 2 and f.retries == 1
    assert 3.0 in clock.sleeps


def test_5xx_twice_gives_up_after_one_retry(tmp_path):
    f, s, _, _ = make(tmp_path, {URL: FakeResponse(500, "")})
    r = f.get(URL, "x.html")
    assert not r.ok and r.status == 500 and r.attempts == 2 and len(s.calls) == 2


def test_timeout_is_retried_once(tmp_path):
    f, s, _, _ = make(tmp_path, {URL: [requests.Timeout("slow"), requests.Timeout("slow")]})
    r = f.get(URL, "x.html")
    assert not r.ok and "Timeout" in r.error and len(s.calls) == 2


def test_other_hosts_are_never_requested(tmp_path):
    f, s, _, _ = make(tmp_path, {})
    r = f.get("https://example.com/", "x.html")
    assert not r.ok and "host not allowed" in r.error and s.calls == []


def test_robots_missing_is_recorded_once(tmp_path):
    robots = "https://books.toscrape.com/robots.txt"
    f, s, _, _ = make(tmp_path, {robots: FakeResponse(404, "")})
    assert f.check_robots()["result"] == "no robots file found"
    assert f.check_robots()["result"] == "no robots file found"
    assert len(s.calls) == 1 and f.allowed_by_robots(URL)


def test_robots_rules_are_obeyed(tmp_path):
    robots = "https://books.toscrape.com/robots.txt"
    f, _, _, _ = make(tmp_path, {robots: FakeResponse(200, "User-agent: *\nDisallow: /catalogue/private/\n")})
    assert f.check_robots()["result"] == "found"
    assert f.allowed_by_robots(URL)
    assert not f.allowed_by_robots("https://books.toscrape.com/catalogue/private/x.html")


def test_robots_server_error_means_unreachable(tmp_path):
    f, _, _, _ = make(tmp_path, {"https://books.toscrape.com/robots.txt": FakeResponse(503, "")})
    assert f.check_robots()["result"] == "unreachable"


def test_delay_counts_from_end_of_a_slow_response(tmp_path):
    clock = Clock()

    class SlowSession(FakeSession):
        def get(self, url, headers=None, timeout=None):
            clock.now += 5.0  # the server takes 5 s to answer
            return super().get(url, headers, timeout)

    f = PoliteFetcher(cache_dir=tmp_path, session=SlowSession({URL: FakeResponse(200, "a"),
                                                                URL + "?2": FakeResponse(200, "b")}),
                      delay=1.0, sleep=clock.sleep, clock=clock.time, log=lambda m: None)
    f.get(URL, "a.html")
    f.get(URL + "?2", "b.html")
    assert clock.sleeps == [1.0]  # still waits a full second after the slow reply

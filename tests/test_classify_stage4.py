"""Stage 4: timeout, retry policy, cost logging, kill switch."""
import json
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime

import httpx
import openai
import pytest

from src.llm import calls
from src.llm.calls import MAX_RETRIES, parse_retry_after
from src.llm.schema import PROMPT_VERSION
from conftest import VALID_ANSWER_JSON

URL = "/tasks/classify"
REQUEST = httpx.Request("POST", "http://llm.test/v1/chat/completions")


def status_error(cls, status, headers=None):
    response = httpx.Response(status, headers=headers or {}, request=REQUEST)
    return cls(f"HTTP {status}", response=response, body=None)


def timeout():
    return openai.APITimeoutError(request=REQUEST)


@pytest.fixture
def waits(monkeypatch):
    """Record the waits instead of sleeping; fixed jitter of 0.25s."""
    recorded = []
    monkeypatch.setattr(calls, "sleep", recorded.append)
    monkeypatch.setattr(calls, "jitter", lambda: 0.25)
    return recorded


def log_lines(capsys, event=None):
    lines = [json.loads(line) for line in capsys.readouterr().out.splitlines() if line.startswith("{")]
    return [line for line in lines if event is None or line["event"] == event]


# ---------- what is retried ----------

@pytest.mark.parametrize(
    "error",
    [
        timeout(),
        status_error(openai.RateLimitError, 429),
        status_error(openai.InternalServerError, 500),
        status_error(openai.InternalServerError, 503),
    ],
    ids=["timeout", "429", "500", "503"],
)
def test_retryable_failure_then_success(api, fake_llm, waits, error):
    fake_llm.script(error, VALID_ANSWER_JSON)

    res = api.post(URL, json={"text": "Send the invoice to the client"})

    assert res.status_code == 200
    assert len(fake_llm.calls) == 2
    assert waits == [1.25]


def test_backoff_is_1_2_4_seconds_plus_jitter_then_gives_up(api, fake_llm, waits):
    fake_llm.script(status_error(openai.InternalServerError, 500))

    res = api.post(URL, json={"text": "Buy milk"})

    assert res.status_code == 502
    assert "HTTP 500" in res.json()["error"]
    assert len(fake_llm.calls) == 1 + MAX_RETRIES == 4
    assert waits == [1.25, 2.25, 4.25]


def test_repeated_timeouts_return_504(api, fake_llm, waits):
    fake_llm.script(timeout())

    res = api.post(URL, json={"text": "Buy milk"})

    assert res.status_code == 504
    assert "did not answer in time" in res.json()["error"]
    assert len(fake_llm.calls) == 4


@pytest.mark.parametrize(
    "cls, status",
    [
        (openai.BadRequestError, 400),
        (openai.AuthenticationError, 401),
        (openai.PermissionDeniedError, 403),
        (openai.NotFoundError, 404),
    ],
)
def test_client_errors_are_never_retried(api, fake_llm, waits, capsys, cls, status):
    fake_llm.script(status_error(cls, status))

    res = api.post(URL, json={"text": "Buy milk"})

    assert res.status_code == 502
    assert f"HTTP {status}" in res.json()["error"]
    assert "Not retried" in res.json()["error"]
    assert len(fake_llm.calls) == 1
    assert waits == []
    call_lines = log_lines(capsys, "llm_call")
    assert len(call_lines) == 1 and call_lines[0]["retry_in_s"] is None


def test_401_message_points_at_the_key_without_showing_it(api, fake_llm, waits, monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "sk-test-not-a-real-key")
    fake_llm.script(status_error(openai.AuthenticationError, 401))

    res = api.post(URL, json={"text": "Buy milk"})

    assert "LLM_API_KEY" in res.json()["error"]
    assert "sk-test-not-a-real-key" not in res.text


def test_connection_error_is_not_retried(api, fake_llm, waits):
    fake_llm.script(openai.APIConnectionError(request=REQUEST))

    res = api.post(URL, json={"text": "Buy milk"})

    assert res.status_code == 503
    assert len(fake_llm.calls) == 1
    assert waits == []


# ---------- Retry-After ----------

def test_retry_after_seconds_is_obeyed_instead_of_backoff(api, fake_llm, waits):
    fake_llm.script(status_error(openai.RateLimitError, 429, {"Retry-After": "7"}), VALID_ANSWER_JSON)

    assert api.post(URL, json={"text": "Buy milk"}).status_code == 200
    assert waits == [7.0]


def test_retry_after_http_date_is_obeyed(api, fake_llm, waits):
    when = format_datetime(datetime.now(timezone.utc) + timedelta(seconds=10), usegmt=True)
    fake_llm.script(status_error(openai.RateLimitError, 429, {"Retry-After": when}), VALID_ANSWER_JSON)

    assert api.post(URL, json={"text": "Buy milk"}).status_code == 200
    assert len(waits) == 1 and 8.0 <= waits[0] <= 10.0


def test_retry_after_too_long_gives_up_with_503_and_header(api, fake_llm, waits):
    fake_llm.script(status_error(openai.RateLimitError, 429, {"Retry-After": "3600"}))

    res = api.post(URL, json={"text": "Buy milk"})

    assert res.status_code == 503
    assert res.headers["Retry-After"] == "3600"
    assert len(fake_llm.calls) == 1
    assert waits == []


@pytest.mark.parametrize(
    "value, expected",
    [("5", 5.0), ("0", 0.0), ("1.5", 1.5), ("", None), (None, None), ("soon", None)],
)
def test_parse_retry_after_seconds(value, expected):
    assert parse_retry_after(value) == expected


def test_parse_retry_after_http_date():
    now = datetime(2026, 10, 15, 12, 0, 0, tzinfo=timezone.utc)

    assert parse_retry_after("Thu, 15 Oct 2026 12:00:30 GMT", now=now) == 30.0
    assert parse_retry_after("Thu, 15 Oct 2026 11:00:00 GMT", now=now) == 0.0


# ---------- retries and repair together stay bounded ----------

def test_repair_call_has_its_own_retries_and_total_calls_are_bounded(api, fake_llm, waits):
    fake_llm.script("not json", timeout(), timeout(), timeout(), timeout())

    res = api.post(URL, json={"text": "Buy milk"})

    assert res.status_code == 504
    assert len(fake_llm.calls) == 1 + 4  # first answer, then the repair with 3 retries


# ---------- cost log ----------

def test_one_log_line_per_call_with_version_model_tokens_duration_repairs(api, fake_llm, capsys):
    fake_llm.script("not json", VALID_ANSWER_JSON)

    api.post(URL, json={"text": "Buy milk"})

    call_lines = log_lines(capsys, "llm_call")
    assert [line["call"] for line in call_lines] == ["initial", "repair"]
    for line in call_lines:
        assert line["prompt_version"] == PROMPT_VERSION
        assert line["model"] == "fake-model"
        assert line["input_tokens"] == 120 and line["output_tokens"] == 30
        assert isinstance(line["duration_ms"], int)
        assert line["outcome"] == "ok"
    assert [line["repair_count"] for line in call_lines] == [0, 1]


def test_request_summary_totals_tokens_and_calls(api, fake_llm, capsys):
    fake_llm.script("not json", VALID_ANSWER_JSON)

    api.post(URL, json={"text": "Buy milk"})

    (summary,) = log_lines(capsys, "llm_request")
    assert summary["outcome"] == "repaired"
    assert summary["model_calls"] == 2
    assert summary["repair_count"] == 1
    assert summary["input_tokens"] == 240 and summary["output_tokens"] == 60


def test_failed_attempts_are_logged_with_their_outcome(api, fake_llm, waits, capsys):
    fake_llm.script(status_error(openai.RateLimitError, 429), VALID_ANSWER_JSON)

    api.post(URL, json={"text": "Buy milk"})

    first, second = log_lines(capsys, "llm_call")
    assert first["outcome"] == "http_429" and first["retry_in_s"] == 1.25
    assert second["outcome"] == "ok" and second["attempt"] == 2


def test_logs_never_contain_the_task_text_or_the_key(api, fake_llm, monkeypatch, capsys):
    monkeypatch.setenv("LLM_API_KEY", "sk-test-not-a-real-key")
    fake_llm.script("not json", VALID_ANSWER_JSON)

    api.post(URL, json={"text": "Private task text 12345"})

    out = capsys.readouterr().out
    assert "Private task text 12345" not in out
    assert "sk-test-not-a-real-key" not in out


# ---------- kill switch and stub: zero model calls in the logs ----------

@pytest.mark.parametrize("env, outcome", [({"LLM_ENABLED": "false"}, "disabled"), ({"LLM_STUB": "1"}, "stub")])
def test_kill_switch_and_stub_log_zero_model_calls(api, fake_llm, monkeypatch, capsys, env, outcome):
    for name, value in env.items():
        monkeypatch.setenv(name, value)

    res = api.post(URL, json={"text": "Buy milk"})

    assert res.status_code == 200
    assert fake_llm.calls == []
    lines = log_lines(capsys)
    assert [line for line in lines if line["event"] == "llm_call"] == []
    (summary,) = [line for line in lines if line["event"] == "llm_request"]
    assert summary["outcome"] == outcome and summary["model_calls"] == 0

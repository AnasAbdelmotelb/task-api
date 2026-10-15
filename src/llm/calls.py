"""One model call with the retry policy and a cost log line per attempt.

Retried: timeouts, 429 and 5xx, with exponential backoff and jitter
(1s, 2s, 4s, each plus up to 0.5s), at most MAX_RETRIES times. A
Retry-After header is obeyed instead of the backoff. Never retried:
400, 401, 403 or any other 4xx, and connection errors.
"""
import json
import math
import os
import random
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import List, Optional

import openai

from src.llm.client import LLMClient, LLMResult
from src.llm.schema import PROMPT_VERSION


MAX_RETRIES = 3
BASE_DELAY_SECONDS = 1.0
MAX_JITTER_SECONDS = 0.5
MAX_RETRY_AFTER_SECONDS = 20.0

# Indirection so tests can run the policy without waiting.
sleep = time.sleep
jitter = lambda: random.uniform(0, MAX_JITTER_SECONDS)  # noqa: E731


class LLMCallError(Exception):
    """A model call failed for good. Carries the HTTP status our API returns."""

    def __init__(self, status_code: int, message: str, retry_after: Optional[float] = None):
        super().__init__(message)
        self.status_code = status_code
        self.message = message
        self.retry_after = retry_after


@dataclass
class RequestStats:
    """Totals for one /tasks/classify request, for the summary log line."""

    model: str
    model_calls: int = 0
    repair_count: int = 0
    input_tokens: int = 0
    output_tokens: int = 0


def log_event(event: dict) -> None:
    """One structured line on stdout. Never contains keys, prompts or user text."""
    print(json.dumps(event), file=sys.stdout, flush=True)


def parse_retry_after(value: Optional[str], now: Optional[datetime] = None) -> Optional[float]:
    """Seconds to wait from a Retry-After header: delta-seconds or an HTTP date."""
    if not value:
        return None
    value = value.strip()
    try:
        return max(0.0, float(value))
    except ValueError:
        pass
    try:
        when = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    now = now or datetime.now(timezone.utc)
    return max(0.0, (when - now).total_seconds())


def backoff_delay(retry_number: int) -> float:
    """1s, 2s, 4s ... plus jitter, for retry 1, 2, 3 ..."""
    return BASE_DELAY_SECONDS * 2 ** (retry_number - 1) + jitter()


def _outcome(exc: Exception) -> str:
    if isinstance(exc, openai.APITimeoutError):
        return "timeout"
    if isinstance(exc, openai.APIStatusError):
        return f"http_{exc.status_code}"
    return "connection_error"


def _is_retryable(exc: Exception) -> bool:
    if isinstance(exc, openai.APITimeoutError):
        return True
    if isinstance(exc, openai.APIStatusError):
        return exc.status_code == 429 or exc.status_code >= 500
    return False


def _retry_after(exc: Exception) -> Optional[float]:
    response = getattr(exc, "response", None)
    if response is None:
        return None
    return parse_retry_after(response.headers.get("retry-after"))


def _final_error(exc: Exception, attempts: int, retry_after: Optional[float]) -> LLMCallError:
    tries = f"{attempts} attempt{'s' if attempts > 1 else ''}"
    if isinstance(exc, openai.APITimeoutError):
        return LLMCallError(504, f"The model did not answer in time ({tries}).")
    if isinstance(exc, openai.APIStatusError):
        status = exc.status_code
        if status in (401, 403):
            return LLMCallError(
                502,
                f"The LLM provider rejected the credentials (HTTP {status}). "
                "Check LLM_API_KEY. Not retried.",
            )
        if status == 429:
            return LLMCallError(
                503, f"The LLM provider's rate limit was reached (HTTP 429, {tries}).",
                retry_after=retry_after,
            )
        if status >= 500:
            return LLMCallError(502, f"The LLM provider failed (HTTP {status}, {tries}).")
        return LLMCallError(
            502, f"The LLM provider rejected the request (HTTP {status}). Not retried."
        )
    return LLMCallError(503, "Could not reach the LLM provider. Check LLM_BASE_URL.")


def call_model(
    client: LLMClient, messages: List[dict], *, call: str, stats: RequestStats
) -> LLMResult:
    """Call the model with the retry policy; log one line per attempt."""
    attempt = 0
    while True:
        attempt += 1
        stats.model_calls += 1
        started = time.monotonic()
        line = {
            "event": "llm_call",
            "prompt_version": PROMPT_VERSION,
            "model": stats.model,
            "call": call,
            "attempt": attempt,
            "repair_count": stats.repair_count,
        }
        try:
            result = client.complete(messages)
        except openai.APIError as exc:
            retry_after = _retry_after(exc)
            retryable = _is_retryable(exc) and attempt <= MAX_RETRIES
            if retry_after is not None and retry_after > MAX_RETRY_AFTER_SECONDS:
                retryable = False
            delay = (retry_after if retry_after is not None else backoff_delay(attempt)) if retryable else None
            log_event({
                **line,
                "outcome": _outcome(exc),
                "duration_ms": round((time.monotonic() - started) * 1000),
                "retry_in_s": round(delay, 2) if delay is not None else None,
            })
            if not retryable:
                raise _final_error(exc, attempt, retry_after) from None
            sleep(delay)
            continue

        stats.model = result.model or stats.model
        stats.input_tokens += result.input_tokens or 0
        stats.output_tokens += result.output_tokens or 0
        log_event({
            **line,
            "model": stats.model,
            "outcome": "ok",
            "input_tokens": result.input_tokens,
            "output_tokens": result.output_tokens,
            "duration_ms": round((time.monotonic() - started) * 1000),
        })
        return result


def configured_model() -> str:
    return os.getenv("LLM_MODEL", "").strip()


def retry_after_header(seconds: Optional[float]) -> Optional[str]:
    return str(math.ceil(seconds)) if seconds is not None else None

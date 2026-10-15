"""Decides how a classify request is answered: kill switch, stub, or model."""
import time
from typing import Optional, Tuple

from src.llm.calls import RequestStats, call_model, configured_model, log_event
from src.llm.client import LLMClient, LLMNotConfiguredError
from src.llm.parsing import AnswerRejected, parse_answer
from src.llm.prompt import build_messages, build_repair_messages
from src.llm.quarantine import quarantine
from src.llm.schema import (
    PROMPT_VERSION,
    Category,
    ClassifyResponse,
    ModelAnswer,
    Priority,
)
from src.llm.settings import llm_enabled, stub_mode


STUB_ANSWER = ModelAnswer(
    category=Category.work,
    priority=Priority.normal,
    confidence=0.9,
    reason="Stub answer: LLM_STUB=1 is set, so no model was called.",
)

DISABLED_ANSWER = ModelAnswer(
    category=Category.other,
    priority=Priority.normal,
    confidence=0.0,
    reason="Automatic classification is switched off; please review manually.",
)


class ModelAnswerRejected(Exception):
    """Both the first answer and the one repair failed validation."""


def classify_text(
    text: str, client: Optional[LLMClient]
) -> Tuple[ClassifyResponse, str]:
    """Return the response and its source: "disabled", "stub" or "model"."""
    if not llm_enabled():
        _log_request("disabled", RequestStats(model=""), 0.0)
        return ClassifyResponse.from_answer(DISABLED_ANSWER), "disabled"

    if stub_mode():
        _log_request("stub", RequestStats(model=""), 0.0)
        return ClassifyResponse.from_answer(STUB_ANSWER), "stub"

    if client is None:
        raise LLMNotConfiguredError("No LLM client is available")

    stats = RequestStats(model=configured_model())
    started = time.monotonic()
    outcome = "error"
    try:
        response = _classify_with_model(text, client, stats)
        outcome = "repaired" if stats.repair_count else "ok"
        return response, "model"
    except ModelAnswerRejected:
        outcome = "quarantined"
        raise
    finally:
        _log_request(outcome, stats, time.monotonic() - started)


def _classify_with_model(text: str, client: LLMClient, stats: RequestStats) -> ClassifyResponse:
    messages = build_messages(text)
    first = call_model(client, messages, call="initial", stats=stats)
    try:
        return ClassifyResponse.from_answer(parse_answer(first.text))
    except AnswerRejected as exc:
        first_error = str(exc)

    # Repair once, and only once.
    stats.repair_count = 1
    repair_messages = build_repair_messages(messages, first.text, first_error)
    second = call_model(client, repair_messages, call="repair", stats=stats)
    try:
        return ClassifyResponse.from_answer(parse_answer(second.text))
    except AnswerRejected as exc:
        second_error = str(exc)

    quarantine(
        text=text,
        prompt_version=PROMPT_VERSION,
        model=stats.model,
        attempts=[
            {"raw": first.text, "error": first_error},
            {"raw": second.text, "error": second_error},
        ],
    )
    raise ModelAnswerRejected(second_error)


def _log_request(outcome: str, stats: RequestStats, seconds: float) -> None:
    log_event({
        "event": "llm_request",
        "prompt_version": PROMPT_VERSION,
        "model": stats.model,
        "outcome": outcome,
        "model_calls": stats.model_calls,
        "repair_count": stats.repair_count,
        "input_tokens": stats.input_tokens,
        "output_tokens": stats.output_tokens,
        "duration_ms": round(seconds * 1000),
    })

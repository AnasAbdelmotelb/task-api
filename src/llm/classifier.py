"""Decides how a classify request is answered: kill switch, stub, or model."""
import os
from typing import Optional, Tuple

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
        return ClassifyResponse.from_answer(DISABLED_ANSWER), "disabled"

    if stub_mode():
        return ClassifyResponse.from_answer(STUB_ANSWER), "stub"

    if client is None:
        raise LLMNotConfiguredError("No LLM client is available")

    messages = build_messages(text)
    first = client.complete(messages)
    try:
        return ClassifyResponse.from_answer(parse_answer(first.text)), "model"
    except AnswerRejected as exc:
        first_error = str(exc)

    # Repair once, and only once.
    second = client.complete(build_repair_messages(messages, first.text, first_error))
    try:
        return ClassifyResponse.from_answer(parse_answer(second.text)), "model"
    except AnswerRejected as exc:
        second_error = str(exc)

    quarantine(
        text=text,
        prompt_version=PROMPT_VERSION,
        model=second.model or os.getenv("LLM_MODEL", ""),
        attempts=[
            {"raw": first.text, "error": first_error},
            {"raw": second.text, "error": second_error},
        ],
    )
    raise ModelAnswerRejected(second_error)

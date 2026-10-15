"""Decides how a classify request is answered: kill switch, stub, or model."""
from typing import Optional, Tuple

from src.llm.client import LLMClient
from src.llm.schema import (
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


class ModelNotWiredError(Exception):
    """Raised until Stage 2 connects the real model call."""


def classify_text(
    text: str, client: Optional[LLMClient]
) -> Tuple[ClassifyResponse, str]:
    """Return the response and its source: "disabled", "stub" or "model"."""
    if not llm_enabled():
        return ClassifyResponse.from_answer(DISABLED_ANSWER), "disabled"

    if stub_mode():
        return ClassifyResponse.from_answer(STUB_ANSWER), "stub"

    raise ModelNotWiredError("The model call is added in Stage 2.")

"""Decides how a classify request is answered: kill switch, stub, or model."""
from typing import Optional, Tuple, Union

from src.llm.client import LLMClient, LLMNotConfiguredError
from src.llm.prompt import build_user_message, load_system_prompt
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


def classify_text(
    text: str, client: Optional[LLMClient]
) -> Tuple[Union[ClassifyResponse, str], str]:
    """Return the response and its source: "disabled", "stub" or "model"."""
    if not llm_enabled():
        return ClassifyResponse.from_answer(DISABLED_ANSWER), "disabled"

    if stub_mode():
        return ClassifyResponse.from_answer(STUB_ANSWER), "stub"

    if client is None:
        raise LLMNotConfiguredError("No LLM client is available")

    # Stage 2 (temporary, as the brief says): return the model's text as it
    # came back. Stage 3 parses and validates it and never returns raw text.
    return client.complete(load_system_prompt(), build_user_message(text)), "model"

"""Turns the model's raw text into a validated ModelAnswer, or says why not."""
import re

from pydantic import ValidationError

from src.llm.schema import ModelAnswer


FENCE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL | re.IGNORECASE)


class AnswerRejected(Exception):
    """The model's text could not be parsed or validated. The message is the reason."""


def extract_json_object(raw: str) -> str:
    """Strip a code fence and any text around the outermost {...} object."""
    text = raw.strip()
    fenced = FENCE.search(text)
    if fenced:
        text = fenced.group(1)

    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end < start:
        raise AnswerRejected("No JSON object was found in the answer")
    return text[start:end + 1]


def describe(error: ValidationError) -> str:
    """The validation errors as one line, without echoing the model's values."""
    parts = []
    for item in error.errors(include_url=False, include_input=False):
        field = ".".join(str(part) for part in item["loc"]) or "answer"
        parts.append(f"{field}: {item['msg']}")
    return "; ".join(parts)


def parse_answer(raw: str) -> ModelAnswer:
    candidate = extract_json_object(raw)
    try:
        return ModelAnswer.model_validate_json(candidate)
    except ValidationError as exc:
        raise AnswerRejected(describe(exc)) from None

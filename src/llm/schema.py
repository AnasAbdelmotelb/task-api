"""Request and response contracts for POST /tasks/classify (see JOB-CARD.md)."""
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator


PROMPT_VERSION = "classify-v1"
REVIEW_THRESHOLD = 0.5
MAX_TEXT_LENGTH = 500


class Category(str, Enum):
    work = "work"
    study = "study"
    personal = "personal"
    errand = "errand"
    other = "other"


class Priority(str, Enum):
    low = "low"
    normal = "normal"
    high = "high"


class ClassifyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=MAX_TEXT_LENGTH)

    @field_validator("text")
    @classmethod
    def text_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("text must not be blank")
        return value


class ModelAnswer(BaseModel):
    """The only shape the model is allowed to return."""

    model_config = ConfigDict(extra="forbid")

    category: Category
    priority: Priority
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str = Field(min_length=1, max_length=160)


class ClassifyResponse(ModelAnswer):
    """What the endpoint returns: the model's answer plus fields our code sets."""

    needs_review: bool
    prompt_version: str

    @classmethod
    def from_answer(cls, answer: ModelAnswer) -> "ClassifyResponse":
        return cls(
            **answer.model_dump(),
            needs_review=answer.confidence < REVIEW_THRESHOLD,
            prompt_version=PROMPT_VERSION,
        )

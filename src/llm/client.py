"""The model client. Tests replace get_llm_client with a fake."""
import os
from typing import Optional, Protocol

from openai import OpenAI


DEFAULT_TIMEOUT_SECONDS = 30.0
MAX_TIMEOUT_SECONDS = 60.0
MAX_OUTPUT_TOKENS = 200


class LLMClient(Protocol):
    def complete(self, system_prompt: str, user_content: str) -> str:
        """Send one request to the model and return its raw text."""
        ...


class LLMNotConfiguredError(Exception):
    """A required LLM_* variable is missing or invalid. Never includes values."""


def _timeout_seconds() -> float:
    raw = os.getenv("LLM_TIMEOUT_SECONDS", "").strip()
    if not raw:
        return DEFAULT_TIMEOUT_SECONDS
    try:
        value = float(raw)
    except ValueError:
        raise LLMNotConfiguredError("LLM_TIMEOUT_SECONDS must be a number")
    if not 0 < value <= MAX_TIMEOUT_SECONDS:
        raise LLMNotConfiguredError(
            f"LLM_TIMEOUT_SECONDS must be above 0 and at most {MAX_TIMEOUT_SECONDS:g}"
        )
    return value


class OpenAICompatClient:
    """Chat Completions client for any OpenAI-compatible provider.

    Nothing is read or connected until complete() is called, so stub mode,
    the kill switch, app startup and tests never touch the network.
    """

    def build(self) -> OpenAI:
        missing = [
            name for name in ("LLM_BASE_URL", "LLM_API_KEY", "LLM_MODEL")
            if not os.getenv(name, "").strip()
        ]
        if missing:
            raise LLMNotConfiguredError(f"Missing {', '.join(missing)}")

        return OpenAI(
            base_url=os.environ["LLM_BASE_URL"],
            api_key=os.environ["LLM_API_KEY"],
            timeout=_timeout_seconds(),  # the SDK default is 10 minutes
            max_retries=0,  # no silent SDK retries; our own policy comes in Stage 4
        )

    def complete(self, system_prompt: str, user_content: str) -> str:
        response = self.build().chat.completions.create(
            model=os.environ["LLM_MODEL"],
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            temperature=0,
            max_tokens=MAX_OUTPUT_TOKENS,
        )
        return response.choices[0].message.content or ""


def get_llm_client() -> Optional[LLMClient]:
    return OpenAICompatClient()

"""Loads the versioned system prompt and builds the user message."""
import json
from functools import lru_cache
from pathlib import Path

from src.llm.schema import PROMPT_VERSION


PROMPTS_DIR = Path(__file__).resolve().parents[2] / "prompts"


@lru_cache(maxsize=None)
def load_system_prompt(version: str = PROMPT_VERSION) -> str:
    return (PROMPTS_DIR / f"{version}.md").read_text(encoding="utf-8")


REPAIR_INSTRUCTION = (
    "Your previous answer was rejected for this reason: {error}. "
    "Return only corrected JSON matching the schema."
)


def build_user_message(text: str) -> str:
    """JSON-encode the task so its content cannot break out of its own quotes."""
    return json.dumps({"task_text": text}, ensure_ascii=False)


def build_messages(text: str) -> list:
    """The system prompt and the task as a separate user message."""
    return [
        {"role": "system", "content": load_system_prompt()},
        {"role": "user", "content": build_user_message(text)},
    ]


def build_repair_messages(messages: list, broken: str, error: str) -> list:
    """Same prompt, plus the rejected answer, plus the exact reason."""
    return messages + [
        {"role": "assistant", "content": broken},
        {"role": "user", "content": REPAIR_INSTRUCTION.format(error=error)},
    ]

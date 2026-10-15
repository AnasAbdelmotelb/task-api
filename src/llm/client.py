"""The model client seam. Tests replace get_llm_client with a fake."""
from typing import Optional, Protocol


class LLMClient(Protocol):
    def complete(self, system_prompt: str, user_content: str) -> str:
        """Send one request to the model and return its raw text."""
        ...


def get_llm_client() -> Optional[LLMClient]:
    # Stage 1: no real client yet. Stage 2 returns the OpenAI-compatible
    # client configured from LLM_BASE_URL, LLM_API_KEY and LLM_MODEL.
    return None

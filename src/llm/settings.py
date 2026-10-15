"""LLM feature flags, read from the environment on every request."""
import os


TRUE_VALUES = {"1", "true", "yes", "on"}


def _flag(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    return raw.strip().lower() in TRUE_VALUES


def llm_enabled() -> bool:
    """Kill switch. Unset means on; any value other than 1/true/yes/on means off."""
    return _flag("LLM_ENABLED", default=True)


def stub_mode() -> bool:
    """LLM_STUB=1 returns a fixed schema-valid answer without calling the model."""
    return _flag("LLM_STUB", default=False)

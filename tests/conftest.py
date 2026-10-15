"""Fixtures for the /tasks/classify tests.

The tests mount only the classify router on a bare FastAPI app, so they need
no Postgres, no Supabase and no model. Run from the repo root:

    python -m pytest -q tests
"""
import socket
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.llm.client import get_llm_client  # noqa: E402
from src.routes.classify import router  # noqa: E402


VALID_ANSWER_JSON = (
    '{"category": "work", "priority": "high", "confidence": 0.8, '
    '"reason": "Mentions a client deadline."}'
)


class FakeLLMClient:
    """Records every call; returns a valid answer if it is ever called."""

    def __init__(self):
        self.calls = []

    def complete(self, system_prompt: str, user_content: str) -> str:
        self.calls.append((system_prompt, user_content))
        return VALID_ANSWER_JSON


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """Fail any test that tries to open a network connection."""

    def blocked(*args, **kwargs):
        raise AssertionError("Network access is not allowed in tests")

    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(socket, "create_connection", blocked)


@pytest.fixture(autouse=True)
def clean_llm_env(monkeypatch):
    """Each test starts with the flags unset; tests set what they need."""
    for name in ("LLM_ENABLED", "LLM_STUB"):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def fake_llm():
    return FakeLLMClient()


@pytest.fixture
def api(fake_llm):
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_llm_client] = lambda: fake_llm
    return TestClient(app)

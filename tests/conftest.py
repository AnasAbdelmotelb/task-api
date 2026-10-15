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

from src.llm.client import LLMResult, get_llm_client  # noqa: E402
from src.routes.classify import router  # noqa: E402


VALID_ANSWER_JSON = (
    '{"category": "work", "priority": "high", "confidence": 0.8, '
    '"reason": "Mentions a client deadline."}'
)


class FakeLLMClient:
    """Records every call and plays back scripted replies.

    Each reply is the model's text, or an exception to raise. The last reply
    repeats once the script runs out.
    """

    def __init__(self, *replies):
        self.replies = list(replies) or [VALID_ANSWER_JSON]
        self.calls = []

    def script(self, *replies):
        self.replies = list(replies)

    def complete(self, messages):
        self.calls.append(messages)
        reply = self.replies[min(len(self.calls), len(self.replies)) - 1]
        if isinstance(reply, Exception):
            raise reply
        return LLMResult(text=reply, model="fake-model", input_tokens=120, output_tokens=30)


@pytest.fixture(autouse=True)
def quarantine_file(tmp_path, monkeypatch):
    """Quarantine lines go to a temp file, never to the repo's logs/."""
    path = tmp_path / "quarantine.jsonl"
    monkeypatch.setenv("LLM_QUARANTINE_PATH", str(path))
    return path


@pytest.fixture(autouse=True)
def no_network(request, monkeypatch):
    """Fail any test that tries to open a network connection.

    Only tests marked `live` (skipped unless LLM_LIVE=1) may connect.
    """
    if request.node.get_closest_marker("live"):
        return

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

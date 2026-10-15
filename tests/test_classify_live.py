"""Controlled live test against the model configured in .env.

Skipped unless LLM_LIVE=1. With Ollama running and llama3.2:3b pulled:

    LLM_LIVE=1 python -m pytest -q -s tests/test_classify_live.py

Each input is one model call (two if a repair is needed); pick one with -k report.
"""
import os

import pytest
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.llm.client import get_llm_client
from src.llm.schema import ClassifyResponse
from src.routes.classify import router

INPUTS = {
    "report": "Email the client the Q3 report by Friday",
    "errand": "Pick up the dry cleaning and post the parcel today",
    "vague": "maybe learn some Spanish at some point",
}

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(os.getenv("LLM_LIVE") != "1", reason="set LLM_LIVE=1 to call the real model"),
]


@pytest.mark.parametrize("text", INPUTS.values(), ids=INPUTS.keys())
def test_real_model_answers_through_the_endpoint(monkeypatch, text):
    load_dotenv()
    monkeypatch.delenv("LLM_STUB", raising=False)
    monkeypatch.delenv("LLM_ENABLED", raising=False)

    app = FastAPI()
    app.include_router(router)
    api = TestClient(app)

    res = api.post("/tasks/classify", json={"text": text})
    print(f"\nINPUT : {text}\nSTATUS: {res.status_code}\nBODY  : {res.text}")

    # A real model may still fail twice; then the contract is a clean 422.
    assert res.status_code in (200, 422)
    assert res.headers["content-type"] == "application/json"
    if res.status_code == 200:
        assert res.headers["X-Classify-Source"] == "model"
        ClassifyResponse.model_validate(res.json())

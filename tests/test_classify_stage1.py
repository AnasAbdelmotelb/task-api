"""Stage 1: input validation, output schema, stub mode and kill switch."""
import pytest
from pydantic import ValidationError

from src.llm.schema import (
    PROMPT_VERSION,
    ClassifyResponse,
    ModelAnswer,
)

URL = "/tasks/classify"
RESPONSE_FIELDS = {
    "category", "priority", "confidence", "reason", "needs_review", "prompt_version",
}


# ---------- input validation: 400 naming the field, no model call ----------

@pytest.mark.parametrize(
    "payload, field",
    [
        ({}, "text"),                          # missing
        ({"text": 123}, "text"),               # wrong type
        ({"text": None}, "text"),
        ({"text": ["buy milk"]}, "text"),
        ({"text": ""}, "text"),                # empty
        ({"text": "   "}, "text"),             # blank
        ({"text": "x" * 501}, "text"),         # too long
        ({"text": "ok", "extra": 1}, "extra"), # unknown field
    ],
)
def test_invalid_input_returns_400_naming_the_field(api, fake_llm, payload, field):
    res = api.post(URL, json=payload)

    assert res.status_code == 400
    body = res.json()
    assert body["error"] == "Invalid request data"
    assert body["field"] == field
    assert body["message"]
    assert fake_llm.calls == []


def test_missing_body_returns_400(api, fake_llm):
    res = api.post(URL)

    assert res.status_code == 400
    assert res.json()["field"] == "body"
    assert fake_llm.calls == []


def test_malformed_json_returns_400(api, fake_llm):
    res = api.post(URL, content="{not json", headers={"Content-Type": "application/json"})

    assert res.status_code == 400
    assert res.json()["field"] == "body"
    assert fake_llm.calls == []


def test_invalid_input_is_rejected_before_the_model_path(api, fake_llm):
    # LLM enabled and stub off: bad input must still be a 400, not reach the model.
    res = api.post(URL, json={"text": ""})

    assert res.status_code == 400
    assert fake_llm.calls == []


@pytest.mark.parametrize("text", ["x", "y" * 500])
def test_length_limits_are_inclusive(api, monkeypatch, text):
    monkeypatch.setenv("LLM_STUB", "1")

    assert api.post(URL, json={"text": text}).status_code == 200


# ---------- stub mode ----------

def test_stub_returns_schema_valid_answer_without_model_call(api, fake_llm, monkeypatch):
    monkeypatch.setenv("LLM_STUB", "1")

    res = api.post(URL, json={"text": "Email the client the Q3 report by Friday"})

    assert res.status_code == 200
    body = res.json()
    assert set(body) == RESPONSE_FIELDS
    ClassifyResponse.model_validate(body)
    assert body["category"] == "work"
    assert body["needs_review"] is False
    assert body["prompt_version"] == PROMPT_VERSION
    assert res.headers["X-Classify-Source"] == "stub"
    assert fake_llm.calls == []


def test_stub_is_deterministic(api, monkeypatch):
    monkeypatch.setenv("LLM_STUB", "1")

    first = api.post(URL, json={"text": "Buy milk"}).json()
    second = api.post(URL, json={"text": "Revise for the exam"}).json()

    assert first == second


# ---------- kill switch ----------

@pytest.mark.parametrize("value", ["false", "0", "off", "no", "FALSE", "garbage"])
def test_kill_switch_returns_fallback_without_model_call(api, fake_llm, monkeypatch, value):
    monkeypatch.setenv("LLM_ENABLED", value)

    res = api.post(URL, json={"text": "Book a dentist appointment"})

    assert res.status_code == 200
    body = res.json()
    assert set(body) == RESPONSE_FIELDS
    assert body["category"] == "other"
    assert body["confidence"] == 0.0
    assert body["needs_review"] is True
    assert res.headers["X-Classify-Source"] == "disabled"
    assert fake_llm.calls == []


def test_kill_switch_wins_over_stub(api, fake_llm, monkeypatch):
    monkeypatch.setenv("LLM_ENABLED", "false")
    monkeypatch.setenv("LLM_STUB", "1")

    res = api.post(URL, json={"text": "Buy milk"})

    assert res.headers["X-Classify-Source"] == "disabled"
    assert fake_llm.calls == []


@pytest.mark.parametrize("value", ["true", "1", "TRUE", "yes", ""])
def test_enabled_values_do_not_trigger_the_kill_switch(api, monkeypatch, value):
    monkeypatch.setenv("LLM_ENABLED", value)
    monkeypatch.setenv("LLM_STUB", "1")

    res = api.post(URL, json={"text": "Buy milk"})

    assert res.headers["X-Classify-Source"] == "stub"


# ---------- output schema ----------

def valid_answer(**overrides):
    data = {"category": "study", "priority": "low", "confidence": 0.7,
            "reason": "Mentions revising for an exam."}
    data.update(overrides)
    return data


def test_model_answer_accepts_a_valid_answer():
    answer = ModelAnswer.model_validate(valid_answer())

    assert answer.category.value == "study"


@pytest.mark.parametrize(
    "overrides",
    [
        {"category": "shopping"},     # not in the closed list
        {"category": "Work"},         # case matters
        {"priority": "urgent"},
        {"confidence": -0.1},
        {"confidence": 1.1},
        {"confidence": "high"},
        {"reason": ""},
        {"reason": "x" * 161},
        {"needs_review": True},       # the model may not set our fields
        {"summary": "extra field"},
    ],
)
def test_model_answer_rejects_invalid_values(overrides):
    with pytest.raises(ValidationError):
        ModelAnswer.model_validate(valid_answer(**overrides))


@pytest.mark.parametrize("missing", ["category", "priority", "confidence", "reason"])
def test_model_answer_requires_every_field(missing):
    data = valid_answer()
    del data[missing]

    with pytest.raises(ValidationError):
        ModelAnswer.model_validate(data)


@pytest.mark.parametrize(
    "confidence, needs_review",
    [(0.0, True), (0.49, True), (0.5, False), (1.0, False)],
)
def test_needs_review_is_computed_by_code(confidence, needs_review):
    answer = ModelAnswer.model_validate(valid_answer(confidence=confidence))

    response = ClassifyResponse.from_answer(answer)

    assert response.needs_review is needs_review
    assert response.prompt_version == PROMPT_VERSION
    assert set(response.model_dump()) == RESPONSE_FIELDS


def test_response_rejects_extra_fields():
    data = valid_answer(needs_review=False, prompt_version=PROMPT_VERSION, debug="x")

    with pytest.raises(ValidationError):
        ClassifyResponse.model_validate(data)

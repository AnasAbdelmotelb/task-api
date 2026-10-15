"""Stage 3: parse, validate, repair once, quarantine on failure."""
import json

import pytest

from src.llm.parsing import AnswerRejected, extract_json_object, parse_answer
from src.llm.prompt import REPAIR_INSTRUCTION
from src.llm.schema import PROMPT_VERSION
from conftest import VALID_ANSWER_JSON

URL = "/tasks/classify"
RESPONSE_FIELDS = {
    "category", "priority", "confidence", "reason", "needs_review", "prompt_version",
}
BAD_CATEGORY = (
    '{"category": "shopping", "priority": "low", "confidence": 0.9, "reason": "Buying things."}'
)


# ---------- parsing ----------

@pytest.mark.parametrize(
    "raw",
    [
        VALID_ANSWER_JSON,
        f"```json\n{VALID_ANSWER_JSON}\n```",
        f"```\n{VALID_ANSWER_JSON}\n```",
        f"Sure! Here's the JSON:\n{VALID_ANSWER_JSON}",
        f"Sure! Here's the JSON:\n```json\n{VALID_ANSWER_JSON}\n```\nHope that helps.",
        f"  {VALID_ANSWER_JSON}  \n",
    ],
)
def test_fences_and_chatter_are_stripped(raw):
    assert parse_answer(raw).category.value == "work"


@pytest.mark.parametrize("raw", ["", "Sure! It is a work task.", "[1, 2, 3]", "}{"])
def test_text_without_an_object_is_rejected(raw):
    with pytest.raises(AnswerRejected, match="No JSON object"):
        extract_json_object(raw)


@pytest.mark.parametrize(
    "raw, field",
    [
        (BAD_CATEGORY, "category"),
        ('{"category": "work", "priority": "asap", "confidence": 0.9, "reason": "x"}', "priority"),
        ('{"category": "work", "priority": "low", "confidence": 1.5, "reason": "x"}', "confidence"),
        ('{"category": "work", "priority": "low", "confidence": 0.9}', "reason"),
        ('{"category": "work", "priority": "low", "confidence": 0.9, "reason": "x", "note": 1}', "note"),
        ('{"category": "work", "priority": "low", "confidence": 0.9, "reason": "x",}', "answer"),
    ],
)
def test_invalid_answers_are_rejected_with_a_reason_naming_the_field(raw, field):
    with pytest.raises(AnswerRejected) as caught:
        parse_answer(raw)

    assert field in str(caught.value)


def test_rejection_reason_does_not_echo_the_models_values():
    with pytest.raises(AnswerRejected) as caught:
        parse_answer(BAD_CATEGORY)

    assert "shopping" not in str(caught.value)


# ---------- the endpoint: happy path, repair, give up ----------

def test_fenced_answer_returns_schema_shaped_json(api, fake_llm):
    fake_llm.script(f"```json\n{VALID_ANSWER_JSON}\n```")

    res = api.post(URL, json={"text": "Send the invoice to the client"})

    assert res.status_code == 200
    assert res.headers["content-type"] == "application/json"
    assert set(res.json()) == RESPONSE_FIELDS
    assert res.json()["prompt_version"] == PROMPT_VERSION
    assert len(fake_llm.calls) == 1


def test_needs_review_comes_from_confidence(api, fake_llm):
    fake_llm.script(
        '{"category": "other", "priority": "normal", "confidence": 0.3, "reason": "Too vague."}'
    )

    body = api.post(URL, json={"text": "sort out the thing"}).json()

    assert body["category"] == "other"
    assert body["needs_review"] is True


def test_one_repair_fixes_a_bad_answer(api, fake_llm, quarantine_file):
    fake_llm.script(BAD_CATEGORY, VALID_ANSWER_JSON)

    res = api.post(URL, json={"text": "Buy a new laptop for work"})

    assert res.status_code == 200
    assert res.json()["category"] == "work"
    assert len(fake_llm.calls) == 2
    assert not quarantine_file.exists()


def test_repair_call_sends_same_prompt_broken_answer_and_exact_error(api, fake_llm):
    fake_llm.script(BAD_CATEGORY, VALID_ANSWER_JSON)

    api.post(URL, json={"text": "Buy a new laptop for work"})

    first, repair = fake_llm.calls
    assert repair[:2] == first  # same system prompt and user message
    assert repair[2] == {"role": "assistant", "content": BAD_CATEGORY}
    assert repair[3]["role"] == "user"
    assert repair[3]["content"].startswith("Your previous answer was rejected for this reason: category:")
    assert repair[3]["content"].endswith("Return only corrected JSON matching the schema.")
    assert REPAIR_INSTRUCTION.split("{error}")[0] in repair[3]["content"]


@pytest.mark.parametrize("second", [BAD_CATEGORY, "I cannot help with that."])
def test_second_failure_returns_422_and_quarantines(api, fake_llm, quarantine_file, second):
    fake_llm.script("not json at all", second)

    res = api.post(URL, json={"text": "Plan the team offsite"})

    assert res.status_code == 422
    body = res.json()
    assert body["prompt_version"] == PROMPT_VERSION
    assert "quarantined" in body["error"]
    assert "not json at all" not in res.text and second not in res.text
    assert len(fake_llm.calls) == 2  # one repair, and only one

    lines = quarantine_file.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["input"] == "Plan the team offsite"
    assert record["prompt_version"] == PROMPT_VERSION
    assert record["model"] == "fake-model"
    assert [a["raw"] for a in record["attempts"]] == ["not json at all", second]
    assert all(a["error"] for a in record["attempts"])


def test_each_failed_request_adds_one_quarantine_line(api, fake_llm, quarantine_file):
    fake_llm.script("nope")

    for _ in range(3):
        assert api.post(URL, json={"text": "Buy milk"}).status_code == 422

    assert len(quarantine_file.read_text(encoding="utf-8").splitlines()) == 3


def test_unwritable_quarantine_does_not_crash(api, fake_llm, monkeypatch, tmp_path):
    blocker = tmp_path / "a-file"
    blocker.write_text("x")
    monkeypatch.setenv("LLM_QUARANTINE_PATH", str(blocker / "quarantine.jsonl"))
    fake_llm.script("nope")

    assert api.post(URL, json={"text": "Buy milk"}).status_code == 422


def test_raw_model_text_is_never_returned(api, fake_llm):
    secret_looking = "RAW-MODEL-TEXT-42"
    fake_llm.script(f"{secret_looking} {VALID_ANSWER_JSON} {secret_looking}")

    res = api.post(URL, json={"text": "Buy milk"})

    assert res.status_code == 200
    assert secret_looking not in res.text

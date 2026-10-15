"""Stage 5: the eval set is well formed and the scorer counts correctly."""
import json
from pathlib import Path

from evals.run_eval import report, score
from src.llm.schema import Category, Priority

CASES = json.loads((Path(__file__).resolve().parents[1] / "evals" / "cases.json").read_text())


def answer(category, priority="normal", confidence=0.9, needs_review=False):
    return 200, {
        "category": category, "priority": priority, "confidence": confidence,
        "reason": "x", "needs_review": needs_review, "prompt_version": "classify-v1",
    }


def test_eight_cases_with_allowed_labels_and_unique_ids():
    assert len(CASES) == 8
    assert len({case["id"] for case in CASES}) == 8
    for case in CASES:
        assert 1 <= len(case["text"]) <= 500
        assert case["expected"]["category"] in {c.value for c in Category}
        assert case["expected"]["priority"] in {p.value for p in Priority}


def test_includes_ambiguous_and_when_unsure_cases():
    kinds = [case["kind"] for case in CASES]

    assert "ambiguous" in kinds
    unsure = [case for case in CASES if case["kind"] == "unsure"]
    assert unsure and all(case["expected"]["category"] == "other" for case in unsure)


def test_score_counts_matches_and_lists_failures():
    answers = [answer(case["expected"]["category"], case["expected"]["priority"],
                      needs_review=case["expected"].get("needs_review", False))
               for case in CASES]
    answers[0] = answer("study")          # wrong category
    answers[7] = (422, {"error": "x"})    # failed request counts as a miss

    result = score(CASES, answers)

    assert result["category_matched"] == 6
    assert result["unsure_flagged"] == 1 and result["unsure_total"] == 2
    assert result["prompt_versions"] == ["classify-v1"]
    text = report(result)
    assert "category (key field): 6/8 (75.0%)" in text
    assert CASES[0]["id"] in text.splitlines()[-1]

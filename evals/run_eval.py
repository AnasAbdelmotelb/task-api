"""Run the hand-labelled cases through POST /tasks/classify and score them.

The key field is `category`. Priority and the when-unsure flag are reported
too. Start the API first (for example `docker compose up -d`), then:

    python evals/run_eval.py
    python evals/run_eval.py --base-url http://localhost:8000 --out evals/results.json

Each case is one request to the endpoint (one model call, two if repaired).
"""
import argparse
import json
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


HERE = Path(__file__).resolve().parent


def classify(base_url: str, text: str, timeout: float) -> tuple:
    """POST one case; return (HTTP status, parsed JSON body or None)."""
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}/tasks/classify",
        data=json.dumps({"text": text}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as exc:
        try:
            return exc.code, json.loads(exc.read())
        except ValueError:
            return exc.code, None


def score(cases: list, answers: list) -> dict:
    """Compare each answer with its label. `answers` is [(status, body), ...]."""
    rows = []
    for case, (status, body) in zip(cases, answers):
        expected = case["expected"]
        got = body if status == 200 and isinstance(body, dict) else {}
        row = {
            "id": case["id"],
            "kind": case["kind"],
            "status": status,
            "expected_category": expected["category"],
            "got_category": got.get("category"),
            "category_ok": got.get("category") == expected["category"],
            "expected_priority": expected["priority"],
            "got_priority": got.get("priority"),
            "priority_ok": got.get("priority") == expected["priority"],
            "confidence": got.get("confidence"),
            "needs_review": got.get("needs_review"),
        }
        if "needs_review" in expected:
            row["needs_review_ok"] = got.get("needs_review") == expected["needs_review"]
        rows.append(row)

    total = len(rows)
    unsure = [row for row in rows if "needs_review_ok" in row]
    return {
        "total": total,
        "category_matched": sum(row["category_ok"] for row in rows),
        "priority_matched": sum(row["priority_ok"] for row in rows),
        "unsure_flagged": sum(row["needs_review_ok"] for row in unsure),
        "unsure_total": len(unsure),
        "prompt_versions": sorted({
            body.get("prompt_version") for _, body in answers
            if isinstance(body, dict) and body.get("prompt_version")
        }),
        "rows": rows,
    }


def report(result: dict) -> str:
    lines = [f"{'case':28} {'kind':10} {'status':6} {'category want/got':24} {'priority want/got':18} conf"]
    for row in result["rows"]:
        mark = "ok  " if row["category_ok"] else "MISS"
        category = f"{row['expected_category']}/{row['got_category']}"
        priority = f"{row['expected_priority']}/{row['got_priority']}"
        lines.append(
            f"{row['id']:28} {row['kind']:10} {row['status']!s:6} "
            f"{mark} {category:19} {priority:18} {row['confidence']}"
        )
    total = result["total"]
    pct = 100 * result["category_matched"] / total if total else 0
    lines += [
        "",
        f"category (key field): {result['category_matched']}/{total} ({pct:.1f}%)",
        f"priority:             {result['priority_matched']}/{total}",
        f"when-unsure flagged:  {result['unsure_flagged']}/{result['unsure_total']} (needs_review true)",
        f"prompt version(s):    {', '.join(result['prompt_versions']) or 'n/a'}",
    ]
    failed = [row["id"] for row in result["rows"] if not row["category_ok"]]
    lines.append(f"failed:               {', '.join(failed) if failed else 'none'}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--cases", default=str(HERE / "cases.json"))
    parser.add_argument("--out", help="also write the full result as JSON here")
    parser.add_argument("--timeout", type=float, default=300.0, help="seconds per request")
    args = parser.parse_args()

    cases = json.loads(Path(args.cases).read_text(encoding="utf-8"))
    answers = [classify(args.base_url, case["text"], args.timeout) for case in cases]
    result = score(cases, answers)
    result["date"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    result["base_url"] = args.base_url

    print(report(result))
    if args.out:
        Path(args.out).write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())

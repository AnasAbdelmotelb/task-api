"""Keeps rejected model answers in logs/quarantine.jsonl instead of using them."""
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import List


DEFAULT_PATH = Path(__file__).resolve().parents[2] / "logs" / "quarantine.jsonl"


def quarantine_path() -> Path:
    return Path(os.getenv("LLM_QUARANTINE_PATH") or DEFAULT_PATH)


def quarantine(
    *, text: str, prompt_version: str, model: str, attempts: List[dict]
) -> None:
    """Append one line. A failure to write is reported, never raised."""
    record = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "prompt_version": prompt_version,
        "model": model,
        "input": text,
        "attempts": attempts,  # [{"raw": ..., "error": ...}, ...]
    }
    path = quarantine_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError as exc:
        print(f"quarantine write failed: {exc}", file=sys.stderr)

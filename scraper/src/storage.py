"""Writing JSON output safely: atomic writes so a crash never leaves half a file."""

from __future__ import annotations

import json
import os
from pathlib import Path


def write_json(path: str | Path, data) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, path)  # atomic on the same filesystem


def dedupe_by_url(records: list[dict]) -> tuple[list[dict], int]:
    """Keep the first record per product_url. Returns (records, duplicates_removed)."""
    seen: dict[str, dict] = {}
    for record in records:
        seen.setdefault(record["product_url"], record)
    return list(seen.values()), len(records) - len(seen)

"""Normalization and the record schema (Pydantic).

A raw record is untrusted text. It becomes a BookRecord only if it passes the schema;
otherwise it goes to errors.json together with the reason.
"""

from __future__ import annotations

import re
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Literal, Optional
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from . import config

_PRICE_RE = re.compile(r"^\d{1,7}(\.\d{1,2})?$")


def parse_price_gbp(price_text: str | None) -> Decimal:
    """'£51.77' -> Decimal('51.77').

    Accepts the pound sign, the common mis-decoded form 'Â£', surrounding spaces and
    thousands commas. Rejects anything that is not clearly a GBP amount, so a value is
    never guessed.
    """
    if price_text is None:
        raise ValueError("price_text is missing")
    text = price_text.strip().replace("Â£", "£")
    if not text.startswith("£"):
        raise ValueError(f"price_text {price_text!r} is not a GBP amount (no £ sign)")
    number = text[1:].strip().replace(",", "")
    if not _PRICE_RE.match(number):
        raise ValueError(f"price_text {price_text!r} is not a valid amount")
    try:
        return Decimal(number).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except InvalidOperation as exc:  # pragma: no cover - regex already guards this
        raise ValueError(f"price_text {price_text!r} is not a valid amount") from exc


def _is_site_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme == "https" and parsed.hostname == config.ALLOWED_HOST


class BookRecord(BaseModel):
    """The shape of one finished, trusted record in output/books.json."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    title: str = Field(min_length=1)
    product_url: str  # canonical identity of the record
    price_text: str = Field(min_length=1)  # raw value kept beside the clean one
    price_gbp: float = Field(ge=0, allow_inf_nan=False)
    availability_text: str = Field(min_length=1)
    rating_text: Literal["One", "Two", "Three", "Four", "Five"]
    description: Optional[str] = Field(default=None, min_length=1)
    source_page: str
    fetched_at: str

    @field_validator("product_url", "source_page")
    @classmethod
    def _absolute_https_site_url(cls, value: str) -> str:
        if not _is_site_url(value):
            raise ValueError(f"must be an absolute https://{config.ALLOWED_HOST}/ URL")
        return value

    @field_validator("fetched_at")
    @classmethod
    def _utc_timestamp(cls, value: str) -> str:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("must be an ISO-8601 timestamp") from exc
        if parsed.tzinfo is None:
            raise ValueError("must include a timezone (UTC 'Z')")
        return value


def normalize_and_validate(raw: dict) -> tuple[BookRecord | None, list[str]]:
    """Return (record, []) for a good raw record, or (None, reasons) for a bad one."""
    clean = dict(raw)
    try:
        clean["price_gbp"] = float(parse_price_gbp(raw.get("price_text")))
    except ValueError as exc:
        return None, [f"price_gbp: {exc}"]
    try:
        return BookRecord.model_validate(clean), []
    except ValidationError as exc:
        reasons = [
            f"{'.'.join(str(p) for p in err['loc']) or 'record'}: {err['msg']}"
            for err in exc.errors()
        ]
        return None, reasons

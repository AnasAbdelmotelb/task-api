from decimal import Decimal

import pytest

from src.models import parse_price_gbp


@pytest.mark.parametrize("text, expected", [
    ("£51.77", Decimal("51.77")),
    ("  £51.77 ", Decimal("51.77")),
    ("Â£51.77", Decimal("51.77")),       # UTF-8 pound sign mis-decoded as Latin-1
    ("£ 1,234.5", Decimal("1234.50")),
    ("£10", Decimal("10.00")),
    ("£0.00", Decimal("0.00")),
])
def test_valid_prices_become_exact_decimals(text, expected):
    assert parse_price_gbp(text) == expected


def test_float_conversion_keeps_two_decimals():
    assert float(parse_price_gbp("£51.77")) == 51.77


@pytest.mark.parametrize("text", [
    None, "", "£", "51.77", "$51.77", "€51.77", "Price on request",
    "£51.777", "£-5.00", "£5.00 £6.00", "£1e3", "£NaN",
])
def test_bad_prices_are_rejected_not_guessed(text):
    with pytest.raises(ValueError):
        parse_price_gbp(text)

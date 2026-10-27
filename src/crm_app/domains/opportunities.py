"""Pure rules for deals (decision P4-B, migration 0011).

Each value function returns the value as the database stores it, or raises
`InvalidValue`. Amounts are `Decimal`s parsed from decimal strings and are
never rounded: a value with more minor digits than its currency has is
refused (P4-B 2).
"""

from __future__ import annotations

import re
from decimal import Decimal

from crm_app.domains.records import InvalidValue, visible_text

TITLE_MAX = 200
LOST_REASON_MAX = 500
AMOUNT_WHOLE_DIGITS = 12
IDLE_DAYS = 7

OPEN, WON, LOST = "open", "won", "lost"
OUTCOMES = (OPEN, WON, LOST)
# The allowed outcome changes (P4-B 5): open to won or lost, and back.
TRANSITIONS: frozenset[tuple[str, str]] = frozenset(
    {(OPEN, WON), (OPEN, LOST), (WON, OPEN), (LOST, OPEN)}
)

# ISO 4217 minor units of the currencies whose count is not 2 (fund and
# precious-metal codes are not workspace currencies; `domains.settings`).
_MINOR_DIGITS: dict[str, int] = {
    **dict.fromkeys(
        (
            "BIF",
            "CLP",
            "DJF",
            "GNF",
            "ISK",
            "JPY",
            "KMF",
            "KRW",
            "PYG",
            "RWF",
            "UGX",
            "VND",
            "VUV",
            "XAF",
            "XOF",
            "XPF",
        ),
        0,
    ),
    **dict.fromkeys(("BHD", "IQD", "JOD", "KWD", "LYD", "OMR", "TND"), 3),
}

_AMOUNT = re.compile(r"(0|[1-9][0-9]*)(?:\.([0-9]+))?")


def minor_digits(currency: str) -> int:
    """How many digits the currency has after the decimal point."""
    return _MINOR_DIGITS.get(currency, 2)


def amount(value: str, currency: str) -> Decimal:
    """A decimal string such as "12500.50": no sign, no exponent, no
    separators, at most 12 whole digits and at most the currency's minor
    digits."""
    match = _AMOUNT.fullmatch(value)
    if match is None:
        raise InvalidValue("must be a decimal number such as 1250.50")
    whole, fraction = match.group(1), match.group(2) or ""
    if len(whole) > AMOUNT_WHOLE_DIGITS:
        raise InvalidValue(f"must have at most {AMOUNT_WHOLE_DIGITS} digits before the point")
    if len(fraction) > minor_digits(currency):
        raise InvalidValue(f"must have at most {minor_digits(currency)} decimals in {currency}")
    return Decimal(value)


def amount_text(value: Decimal, currency: str) -> str:
    """A stored amount as the API shows it: exactly the currency's minor
    digits ("12500.50", "1500" in JPY)."""
    digits = minor_digits(currency)
    return f"{value:.{digits}f}"


def _text(value: str, maximum: int) -> str:
    if not visible_text(value):
        raise InvalidValue("must not contain control characters")
    trimmed = value.strip()
    if not trimmed:
        raise InvalidValue("is required")
    if len(trimmed) > maximum:
        raise InvalidValue(f"must be at most {maximum} characters")
    return trimmed


def title(value: str) -> str:
    """Trimmed, 1..200 characters, no control, format or separator characters."""
    return _text(value, TITLE_MAX)


def lost_reason(value: str) -> str:
    """Trimmed, 1..500 characters, no control, format or separator characters."""
    return _text(value, LOST_REASON_MAX)

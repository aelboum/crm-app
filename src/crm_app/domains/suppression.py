"""Pure rules for suppressions and consent (decision P7-B, migration 0017).

Each validating function returns the value as the database stores it, or
raises `InvalidValue`. A list of addresses is checked as a whole and its
refusal names positions, never the addresses.
"""

from __future__ import annotations

from collections.abc import Sequence

from crm_app.domains import records as record_rules
from crm_app.domains.forms import message
from crm_app.domains.records import InvalidValue

REASONS = ("unsubscribed", "bounced", "complained", "manual")
ORIGINS = ("manual", "consent_withdrawn")
NOTE_MAX = 500
ADD_MAX = 1000
MAX_ROWS = 100_000
SEARCH_MAX = 320
CONSENT_STATES = ("granted", "withdrawn", "none")


class InvalidAddresses(ValueError):
    """Addresses the list refuses, by their position in the request."""

    def __init__(self, positions: list[int]) -> None:
        super().__init__("invalid addresses")
        self.positions = positions


def addresses(raw: Sequence[str]) -> list[str]:
    """The addresses as stored (trimmed, lower-cased), without repeats, in
    the order given. Refuses an empty list, more than `ADD_MAX` and any
    entry that is not an email address."""
    if not raw:
        raise InvalidValue("is required")
    if len(raw) > ADD_MAX:
        raise InvalidValue(f"must be at most {ADD_MAX} addresses")
    stored: list[str] = []
    refused: list[int] = []
    for position, value in enumerate(raw):
        try:
            email = record_rules.email(value)
        except InvalidValue:
            refused.append(position)
            continue
        if email is None:
            refused.append(position)
        elif email not in stored:
            stored.append(email)
    if refused:
        raise InvalidAddresses(refused)
    return stored


def reason(value: str) -> str:
    if value not in REASONS:
        raise InvalidValue(f"must be one of {', '.join(REASONS)}")
    return value


def note(value: str | None) -> str | None:
    """An optional note: line breaks as LF, trimmed, 1..500 characters; blank is none."""
    return message(value, required=False)


def wording(value: str) -> str:
    """The exact wording a person agreed to (P7-B 4): required, 1..500 characters."""
    stored = message(value, required=True)
    if stored is None:
        raise InvalidValue("is required")
    return stored


def search(value: str | None) -> str | None:
    """A search term: trimmed and lower-cased; blank is none."""
    if value is None:
        return None
    trimmed = value.strip().lower()
    if len(trimmed) > SEARCH_MAX:
        raise InvalidValue(f"must be at most {SEARCH_MAX} characters")
    return trimmed or None


def may_send(*, suppressed: bool, consent: str, marketing: bool) -> bool:
    """The send rule (P7-B 6): never to a suppressed address; a marketing
    send also needs consent `granted`."""
    if suppressed:
        return False
    return not marketing or consent == "granted"

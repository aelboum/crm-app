"""Pure rules for tasks (decision P4-C, migration 0012).

Each function returns the value as the database stores it, or raises
`InvalidValue`.
"""

from __future__ import annotations

from crm_app.domains.records import InvalidValue, visible_text

TITLE_MAX = 200
PRIORITIES = ("high", "medium", "low")
DEFAULT_PRIORITY = "medium"


def title(value: str) -> str:
    """Trimmed, 1..200 characters, no control, format or separator characters."""
    if not visible_text(value):
        raise InvalidValue("must not contain control characters")
    trimmed = value.strip()
    if not trimmed:
        raise InvalidValue("is required")
    if len(trimmed) > TITLE_MAX:
        raise InvalidValue(f"must be at most {TITLE_MAX} characters")
    return trimmed

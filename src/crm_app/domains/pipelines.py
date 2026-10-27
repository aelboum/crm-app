"""Pure rules for pipelines and their stages (decision P4, migration 0010).

Each function returns the value as the database stores it, or raises
`InvalidValue`. Uniqueness of names, regardless of case, is the
database's.
"""

from __future__ import annotations

from crm_app.domains.records import InvalidValue, visible_text

PIPELINE_NAME_MAX = 60
STAGE_NAME_MAX = 40
MAX_STAGES = 15

DEFAULT_PIPELINE_NAME = "Sales"
# Name and probability of the default pipeline's stages, in order (P4 4A.2).
DEFAULT_STAGES: tuple[tuple[str, int], ...] = (
    ("Qualified", 20),
    ("Meeting", 40),
    ("Proposal", 60),
    ("Negotiation", 75),
)


def _name(value: str, maximum: int) -> str:
    if not visible_text(value):
        raise InvalidValue("must not contain control characters")
    trimmed = value.strip()
    if not trimmed:
        raise InvalidValue("is required")
    if len(trimmed) > maximum:
        raise InvalidValue(f"must be at most {maximum} characters")
    return trimmed


def pipeline_name(value: str) -> str:
    """Trimmed, 1..60 characters, no control, format or separator characters."""
    return _name(value, PIPELINE_NAME_MAX)


def stage_name(value: str) -> str:
    """Trimmed, 1..40 characters, no control, format or separator characters."""
    return _name(value, STAGE_NAME_MAX)


def probability(value: int) -> int:
    """A whole percentage, 0..100."""
    if isinstance(value, bool) or not 0 <= value <= 100:
        raise InvalidValue("must be a whole number from 0 to 100")
    return value

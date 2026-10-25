"""Pure rules for self-service signup (decision S-1): the workspace name and
the request fingerprint an idempotent replay is compared by. No database,
framework or configuration, so they are tested in isolation
(`tests/unit/test_signup_rules.py`).
"""

from __future__ import annotations

import hashlib
import unicodedata

NAME_MAX = 100


class InvalidWorkspaceNameError(ValueError):
    """The name is not acceptable; the message names the rule, never the value."""


def normalize_workspace_name(value: object) -> str:
    """The name as stored: NFC, inner whitespace collapsed, 1 to 100
    characters, no control, format or other non-printing characters."""
    if not isinstance(value, str):
        raise InvalidWorkspaceNameError("The workspace name must be text.")
    name = " ".join(unicodedata.normalize("NFC", value).split())
    if not name:
        raise InvalidWorkspaceNameError("The workspace name must not be empty.")
    if len(name) > NAME_MAX:
        raise InvalidWorkspaceNameError(f"The workspace name is longer than {NAME_MAX} characters.")
    if any(unicodedata.category(c).startswith("C") for c in name):
        raise InvalidWorkspaceNameError("The workspace name has a character that is not allowed.")
    return name


def request_fingerprint(name: str) -> str:
    """What a replay with the same `Idempotency-Key` must match: the
    normalized request. A hash, so the row never needs the name to compare."""
    return hashlib.sha256(name.encode("utf-8")).hexdigest()

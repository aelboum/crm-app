"""Pure rules for forms and their submissions (decision P7-A, migration 0013).

Each function returns the value as the database stores it, or raises
`InvalidValue`. Answer checks collect a code per field key, so a refusal
names the fields and the rules, never what the visitor typed.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from datetime import date
from typing import Any

from crm_app.domains import records as rules
from crm_app.domains.records import InvalidValue, visible_text

NAME_MAX = 120
LABEL_MAX = 100
OPTION_MAX = 100
OPTIONS_MAX = 20
FIELDS_MAX = 20
MESSAGE_MAX = 500
TEXTAREA_MAX = 5000
DEFAULT_THANK_YOU = "Thanks! We will be in touch soon."

STATUSES = ("draft", "published")
TYPES = ("text", "email", "phone", "textarea", "select", "date", "checkbox")
# Which contact field a form field may fill, and the field types allowed
# for it (P7-A 3).
TARGETS: dict[str, tuple[str, ...]] = {
    "first_name": ("text",),
    "last_name": ("text",),
    "email": ("email",),
    "phone": ("phone",),
    "job_title": ("text",),
    "city": ("text",),
}
# The longest answer a field takes: the contact column's limit for a target.
_TARGET_MAX = {
    "first_name": rules.NAME_MAX,
    "last_name": rules.NAME_MAX,
    "job_title": rules.JOB_TITLE_MAX,
    "city": rules.CITY_MAX,
}
_TEXT_MAX = 200
_KEY = re.compile(r"[a-z][a-z0-9_]{0,39}")
# All control characters but line feed (the migration's message checks).
_MESSAGE_CONTROL = re.compile(r"[\x00-\x09\x0b-\x1f\x7f]")


def _short(value: str, maximum: int) -> str:
    """Trimmed, 1..maximum characters, no control, format or separator characters."""
    if not visible_text(value):
        raise InvalidValue("must not contain control characters")
    trimmed = value.strip()
    if not trimmed:
        raise InvalidValue("is required")
    if len(trimmed) > maximum:
        raise InvalidValue(f"must be at most {maximum} characters")
    return trimmed


def name(value: str) -> str:
    return _short(value, NAME_MAX)


def _multiline(value: str, maximum: int) -> str | None:
    normalised = value.replace("\r\n", "\n").replace("\r", "\n").strip(" \n")
    if _MESSAGE_CONTROL.search(normalised):
        raise InvalidValue("must not contain control characters")
    if len(normalised) > maximum:
        raise InvalidValue(f"must be at most {maximum} characters")
    return normalised or None


def message(value: str | None, *, required: bool) -> str | None:
    """A thank-you message or consent wording: line breaks as LF, trimmed,
    1..500 characters, no control character other than LF. An optional
    message that is empty becomes `None`."""
    normalised = _multiline(value or "", MESSAGE_MAX)
    if normalised is None and required:
        raise InvalidValue("is required")
    return normalised


class FieldError(InvalidValue):
    """A field definition outside the rules: its position (-1 for the list
    itself) and the rule's code."""

    def __init__(self, index: int, code: str) -> None:
        super().__init__(f"field {index}: {code}")
        self.index = index
        self.code = code


def fields(raw: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """The field list as stored: 1..20 fields with unique keys; each target
    at most once and only on a field of a matching type; options only on a
    select, which needs 1..20 distinct ones."""
    if not 1 <= len(raw) <= FIELDS_MAX:
        raise FieldError(-1, "field_count")
    seen_keys: set[str] = set()
    seen_targets: set[str] = set()
    result: list[dict[str, Any]] = []
    for index, field in enumerate(raw):
        key = field.get("key")
        if not isinstance(key, str) or not _KEY.fullmatch(key):
            raise FieldError(index, "field_key")
        if key in seen_keys:
            raise FieldError(index, "duplicate_field_key")
        seen_keys.add(key)
        kind = field.get("type")
        if kind not in TYPES:
            raise FieldError(index, "field_type")
        try:
            label = _short(str(field.get("label") or ""), LABEL_MAX)
        except InvalidValue:
            raise FieldError(index, "field_label") from None
        target = field.get("target")
        if target is not None:
            if target not in TARGETS or kind not in TARGETS[target]:
                raise FieldError(index, "field_target")
            if target in seen_targets:
                raise FieldError(index, "duplicate_field_target")
            seen_targets.add(target)
        options = field.get("options")
        if kind == "select":
            options = _options(index, options)
        elif options is not None:
            raise FieldError(index, "field_options")
        result.append(
            {
                "key": key,
                "type": kind,
                "label": label,
                "required": bool(field.get("required", False)),
                "target": target,
                "options": options,
            }
        )
    return result


def _options(index: int, raw: object) -> list[str]:
    if not isinstance(raw, list) or not 1 <= len(raw) <= OPTIONS_MAX:
        raise FieldError(index, "field_options")
    options: list[str] = []
    for option in raw:
        try:
            value = _short(str(option), OPTION_MAX)
        except InvalidValue:
            raise FieldError(index, "field_options") from None
        if value in options:
            raise FieldError(index, "field_options")
        options.append(value)
    return options


def publish_refusal(stored: Sequence[Mapping[str, Any]]) -> str | None:
    """Why a form with these fields cannot be published, or `None`: it needs
    a required first-name field and an email or phone field (P7-A 3), so
    every submission can make a contact."""
    targets = {field["target"]: field for field in stored if field.get("target")}
    first = targets.get("first_name")
    if first is None or not first["required"]:
        return "first_name_field_required"
    if "email" not in targets and "phone" not in targets:
        return "email_or_phone_field_required"
    return None


def consent_refusal(stored: Sequence[Mapping[str, Any]], consent_text: str | None) -> str | None:
    """Consent is for the email channel (P7-A 7): wording needs an email field."""
    if consent_text is not None and not any(f.get("target") == "email" for f in stored):
        return "consent_needs_email_field"
    return None


class InvalidAnswers(InvalidValue):
    """Answers outside the form's rules: a code per field key."""

    def __init__(self, errors: Mapping[str, str]) -> None:
        super().__init__("invalid answers")
        self.errors = dict(errors)


def _answer(field: Mapping[str, Any], value: object) -> object:  # noqa: PLR0911, PLR0912 - one branch per type
    """One answer as stored, `None` when empty; raises `InvalidValue`."""
    kind = field["type"]
    if kind == "checkbox":
        if value is None:
            return None
        if not isinstance(value, bool):
            raise InvalidValue("must be true or false")
        return value or None
    if value is None:
        return None
    if not isinstance(value, str):
        raise InvalidValue("must be text")
    if kind == "email":
        return rules.email(value)
    if kind == "phone":
        return rules.phone(value)
    if kind == "textarea":
        return _multiline(value, TEXTAREA_MAX)
    if not value.strip():
        return None
    if kind == "select":
        if value not in field["options"]:
            raise InvalidValue("must be one of the options")
        return value
    if kind == "date":
        try:
            return date.fromisoformat(value.strip()).isoformat()
        except ValueError:
            raise InvalidValue("must be a date") from None
    return _short(value, _TARGET_MAX.get(field.get("target") or "", _TEXT_MAX))


def answers(stored: Sequence[Mapping[str, Any]], raw: Mapping[str, object]) -> dict[str, Any]:
    """The visitor's answers as stored, by field key, empty answers left out.
    Keys the form does not have are refused, as are missing required
    answers; a submission needs an email or a phone number (a contact
    needs one)."""
    errors: dict[str, str] = {}
    by_key = {field["key"]: field for field in stored}
    for key in raw:
        if key not in by_key:
            errors[str(key)[:40]] = "unknown_field"
    result: dict[str, Any] = {}
    for key, field in by_key.items():
        try:
            value = _answer(field, raw.get(key))
        except InvalidValue:
            errors[key] = "invalid"
            continue
        if value is None:
            if field["required"]:
                errors[key] = "required"
            continue
        result[key] = value
    if not errors:
        targets = {field.get("target"): key for key, field in by_key.items()}
        if not any(targets.get(name) in result for name in ("email", "phone")):
            for name in ("email", "phone"):
                if name in targets:
                    errors[targets[name]] = "email_or_phone_required"
    if errors:
        raise InvalidAnswers(errors)
    return result


def contact_values(stored: Sequence[Mapping[str, Any]], given: Mapping[str, Any]) -> dict[str, Any]:
    """The contact fields the answers fill, by target."""
    return {
        field["target"]: given[field["key"]]
        for field in stored
        if field.get("target") and field["key"] in given
    }

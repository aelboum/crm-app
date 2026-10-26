"""Custom field rules (decision P3-D; `crm_app.domains.custom_fields`):
definition keys, labels and options, and record values by type."""

from __future__ import annotations

import pytest

from crm_app.domains import custom_fields as rules
from crm_app.domains.records import InvalidValue
from tests.support import REPO_ROOT

MIGRATION = REPO_ROOT / "src" / "crm_app" / "migrations" / "versions" / "0008_custom_fields.py"


@pytest.mark.parametrize("key", ["carrier", "a", "seats_2", "x" * 40])
def test_keys_are_lower_case_machine_names(key: str) -> None:
    assert rules.key(key) == key


@pytest.mark.parametrize(
    "key", ["", "Carrier", "1st", "_x", "has-dash", "has space", "x" * 41, "é"]
)
def test_other_keys_are_refused(key: str) -> None:
    with pytest.raises(InvalidValue):
        rules.key(key)


def test_labels_are_trimmed_visible_and_short() -> None:
    assert rules.label("  Insurance carrier ") == "Insurance carrier"
    for refused in ("", "  ", "x" * 61, "a\nb", "a\u200bb"):
        with pytest.raises(InvalidValue):
            rules.label(refused)


def test_options_are_trimmed_distinct_and_bounded() -> None:
    assert rules.options([" Gold", "Silver "]) == ["Gold", "Silver"]
    for refused in ([], ["Gold", "gold"], [""], ["x" * 61], [str(n) for n in range(51)]):
        with pytest.raises(InvalidValue):
            rules.options(refused)


@pytest.mark.parametrize(
    ("field_type", "raw", "stored"),
    [
        ("text", "  Delta Dental ", "Delta Dental"),
        ("text", "   ", None),
        ("text", "张伟", "张伟"),
        ("number", 4, 4),
        ("number", 4.0, 4),
        ("number", -12.5, -12.5),
        ("number", 999_999_999_999_999, 999_999_999_999_999),
        ("date", "2026-02-28", "2026-02-28"),
        ("boolean", False, False),
        ("select", "Gold", "Gold"),
        ("text", None, None),
        ("select", None, None),
    ],
)
def test_values_are_stored_in_one_form(field_type: str, raw: object, stored: object) -> None:
    assert rules.value(field_type, ["Gold", "Silver"], raw) == stored


@pytest.mark.parametrize(
    ("field_type", "raw"),
    [
        ("text", 4),
        ("text", "x" * 501),
        ("text", "two\nlines"),
        ("number", "4"),
        ("number", True),
        ("number", float("nan")),
        ("number", float("inf")),
        ("number", 10**15),
        ("number", 0.1234567890123456),
        ("date", "2026-02-30"),
        ("date", "26-02-01"),
        ("date", "2026-02-01T10:00:00"),
        ("date", 20260201),
        ("boolean", "true"),
        ("boolean", 1),
        ("select", "gold"),
        ("select", "Bronze"),
        ("select", 1),
        ("currency", "4"),
    ],
)
def test_values_outside_their_type_are_refused(field_type: str, raw: object) -> None:
    with pytest.raises(InvalidValue):
        rules.value(field_type, ["Gold", "Silver"], raw)


def test_the_migration_checks_the_same_limits() -> None:
    migration = MIGRATION.read_text(encoding="utf-8")
    assert f"LABEL_MAX = {rules.LABEL_MAX}" in migration
    assert f"OPTIONS_MAX = {rules.OPTIONS_MAX}" in migration
    for name, names in (("FIELD_TYPES", rules.FIELD_TYPES), ("ENTITIES", rules.ENTITIES)):
        quoted = ", ".join(f'"{value}"' for value in names)
        assert f"{name} = ({quoted})" in migration

"""Form value rules (`crm_app.domains.forms`; decision P7-A)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import pytest

from crm_app.domains import forms as rules
from crm_app.domains import paging
from crm_app.domains.records import InvalidValue


def field(key: str, kind: str = "text", **extra: Any) -> dict[str, Any]:
    return {"key": key, "type": kind, "label": key.title(), **extra}


LEAD = [
    field("first", target="first_name", required=True),
    field("last", target="last_name"),
    field("email", "email", target="email"),
    field("phone", "phone", target="phone"),
    field("topic", "select", options=["Sales", "Support"]),
    field("when", "date"),
    field("note", "textarea"),
    field("agree", "checkbox"),
]


def test_names_and_messages_are_trimmed_and_bounded() -> None:
    assert rules.name("  Contact us ") == "Contact us"
    for bad in ("", " ", "x" * 121, "a\tb"):
        with pytest.raises(InvalidValue):
            rules.name(bad)
    assert rules.message(" Thanks!\r\nSee you. ", required=True) == "Thanks!\nSee you."
    assert rules.message("  ", required=False) is None
    for bad in ("", "x" * 501, "a\tb", "a\x00b"):
        with pytest.raises(InvalidValue):
            rules.message(bad, required=True)


def test_fields_are_normalised() -> None:
    stored = rules.fields(LEAD)
    assert stored[0] == {
        "key": "first",
        "type": "text",
        "label": "First",
        "required": True,
        "target": "first_name",
        "options": None,
    }
    assert stored[4]["options"] == ["Sales", "Support"]
    assert stored[1]["required"] is False


@pytest.mark.parametrize(
    ("raw", "code", "index"),
    [
        ([], "field_count", -1),
        ([field(f"f{i}") for i in range(21)], "field_count", -1),
        ([field("First")], "field_key", 0),
        ([field("a"), field("a")], "duplicate_field_key", 1),
        ([field("a", "rating")], "field_type", 0),
        ([field("a", label=" ")], "field_label", 0),
        ([field("a", "email", target="first_name")], "field_target", 0),
        ([field("a", target="company")], "field_target", 0),
        ([field("a", target="city"), field("b", target="city")], "duplicate_field_target", 1),
        ([field("a", "select")], "field_options", 0),
        ([field("a", "select", options=["x", "x"])], "field_options", 0),
        ([field("a", options=["x"])], "field_options", 0),
    ],
)
def test_field_lists_outside_the_rules_are_refused(
    raw: list[dict[str, Any]], code: str, index: int
) -> None:
    with pytest.raises(rules.FieldError) as caught:
        rules.fields(raw)
    assert (caught.value.code, caught.value.index) == (code, index)


def test_publishing_needs_a_required_first_name_and_an_email_or_phone() -> None:
    assert rules.publish_refusal(rules.fields(LEAD)) is None
    optional_first = [field("first", target="first_name"), field("e", "email", target="email")]
    assert rules.publish_refusal(rules.fields(optional_first)) == "first_name_field_required"
    no_contact = [field("first", target="first_name", required=True)]
    assert rules.publish_refusal(rules.fields(no_contact)) == "email_or_phone_field_required"
    phone_only = [*no_contact, field("p", "phone", target="phone")]
    assert rules.publish_refusal(rules.fields(phone_only)) is None


def test_consent_wording_needs_an_email_field() -> None:
    phone_only = rules.fields([field("p", "phone", target="phone")])
    assert rules.consent_refusal(phone_only, "Email me") == "consent_needs_email_field"
    assert rules.consent_refusal(phone_only, None) is None
    assert rules.consent_refusal(rules.fields(LEAD), "Email me") is None


def test_answers_are_normalised_and_empty_ones_left_out() -> None:
    stored = rules.fields(LEAD)
    given = rules.answers(
        stored,
        {
            "first": " Sam ",
            "last": "",
            "email": " Sam@Example.TEST ",
            "phone": None,
            "topic": "Sales",
            "when": "2026-11-02",
            "note": " Hello\r\nthere ",
            "agree": False,
        },
    )
    assert given == {
        "first": "Sam",
        "email": "sam@example.test",
        "topic": "Sales",
        "when": "2026-11-02",
        "note": "Hello\nthere",
    }
    assert rules.contact_values(stored, given) == {"first_name": "Sam", "email": "sam@example.test"}


def test_answer_refusals_name_keys_and_rules_only() -> None:
    stored = rules.fields(LEAD)
    with pytest.raises(rules.InvalidAnswers) as caught:
        rules.answers(
            stored,
            {
                "email": "not-an-email",
                "topic": "Other",
                "when": "02/11/2026",
                "agree": "yes",
                "extra": "x",
            },
        )
    assert caught.value.errors == {
        "extra": "unknown_field",
        "first": "required",
        "email": "invalid",
        "topic": "invalid",
        "when": "invalid",
        "agree": "invalid",
    }
    assert "not-an-email" not in str(caught.value)


def test_a_submission_needs_an_email_or_a_phone() -> None:
    stored = rules.fields(LEAD)
    with pytest.raises(rules.InvalidAnswers) as caught:
        rules.answers(stored, {"first": "Sam"})
    assert caught.value.errors == {
        "email": "email_or_phone_required",
        "phone": "email_or_phone_required",
    }
    assert rules.answers(stored, {"first": "Sam", "phone": "+31 20 123 4567"})["phone"] == (
        "+31 20 123 4567"
    )


def test_a_required_checkbox_must_be_ticked() -> None:
    stored = rules.fields(
        [
            field("first", target="first_name", required=True),
            field("email", "email", target="email", required=True),
            field("terms", "checkbox", required=True),
        ]
    )
    base = {"first": "Sam", "email": "sam@example.test"}
    with pytest.raises(rules.InvalidAnswers) as caught:
        rules.answers(stored, {**base, "terms": False})
    assert caught.value.errors == {"terms": "required"}
    assert rules.answers(stored, {**base, "terms": True})["terms"] is True


def test_text_answers_follow_the_target_columns_limits() -> None:
    stored = rules.fields(
        [field("city", target="city"), field("e", "email", target="email", required=True)]
    )
    with pytest.raises(rules.InvalidAnswers):
        rules.answers(stored, {"city": "x" * 101, "e": "a@b.test"})
    assert rules.answers(stored, {"city": "x" * 100, "e": "a@b.test"})["city"] == "x" * 100


def test_submission_cursors_round_trip() -> None:
    key = (datetime(2026, 10, 28, 9, 0, tzinfo=UTC), uuid.UUID(int=7))
    cursor = paging.encode("form_submission", "created_at", "desc", "f", key)
    assert paging.decode(cursor, "form_submission", "created_at", "desc", "f") == key

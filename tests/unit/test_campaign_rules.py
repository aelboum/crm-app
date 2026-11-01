"""Campaign rules (decision P7-C, `crm_app.domains.campaigns`)."""

from __future__ import annotations

import uuid

import pytest

from crm_app.domains import campaigns as rules
from crm_app.domains.records import STAGES, InvalidValue


def test_the_workflow_allows_only_its_steps() -> None:
    assert rules.after("validate", "draft") == "validated"
    assert rules.after("validate", "rejected") == "validated"
    assert rules.after("submit", "validated") == "awaiting_approval"
    assert rules.after("approve", "awaiting_approval") == "approved"
    assert rules.after("reject", "awaiting_approval") == "rejected"
    assert rules.after("queue", "approved") == "queued"
    for step, status in (
        ("approve", "draft"),
        ("approve", "validated"),
        ("queue", "awaiting_approval"),
        ("queue", "draft"),
        ("submit", "draft"),
        ("cancel", "queued"),
        ("cancel", "cancelled"),
    ):
        with pytest.raises(rules.StepRefused):
            rules.after(step, status)


def test_a_segment_needs_a_filter_or_an_explicit_all() -> None:
    assert rules.segment({"stages": ["lead"]}, STAGES).stages == ("lead",)
    assert rules.segment({"all_contacts": True}, STAGES).all_contacts is True
    for raw in (
        {},
        {"stages": []},
        {"stages": ["vip"]},
        {"stages": ["lead"], "all_contacts": True},
        {"tag_ids": ["not-a-uuid"]},
        {"tag_ids": [str(uuid.uuid4()) for _ in range(rules.FILTER_MAX + 1)]},
    ):
        with pytest.raises(InvalidValue):
            rules.segment(raw, STAGES)


def test_content_accepts_only_known_placeholders() -> None:
    assert rules.subject("Hi  {{first_name}} ") == "Hi {{first_name}}"
    assert rules.body("Hello {{ last_name }}\r\nBye") == "Hello {{ last_name }}\nBye"
    for bad in ("Hi {{email}}", "Hi {{first_name}", "Hi }} there", "{{__class__}}"):
        with pytest.raises(InvalidValue):
            rules.body(bad)
    with pytest.raises(InvalidValue):
        rules.subject("Bell\x07here")
    with pytest.raises(InvalidValue):
        rules.body("x" * (rules.BODY_MAX + 1))


def test_the_hash_changes_with_any_part_and_ignores_filter_order() -> None:
    one, two = uuid.uuid4(), uuid.uuid4()
    audience = rules.segment({"tag_ids": [str(one), str(two)]}, STAGES)
    same = rules.segment({"tag_ids": [str(two), str(one)]}, STAGES)
    base = rules.content_hash("N", "S", "B", audience)
    assert base == rules.content_hash("N", "S", "B", same)
    assert base != rules.content_hash("N", "S2", "B", audience)
    assert base != rules.content_hash("N", "S", "B2", audience)
    assert base != rules.content_hash("N", "S", "B", rules.segment({"all_contacts": True}, STAGES))


def test_rendering_is_literal_and_never_expands_values() -> None:
    text = rules.render("Hi {{first_name}} {{ last_name }}!", {"first_name": "{{last_name}}"})
    assert text == "Hi {{last_name}} !"
    assert rules.render("Hi {{first_name}}", {"first_name": "Ada\nBcc: x"}) == "Hi Ada Bcc: x"
    assert "Unsubscribe: https://u.test/x" in rules.footer("Acme", "https://u.test/x")


def test_eligibility_reasons() -> None:
    def reason(**kw: object) -> str | None:
        values = {"email": "a@b.c", "suppressed": False, "consent": "granted", "seen": False}
        values.update(kw)
        return rules.eligibility_reason(**values)  # type: ignore[arg-type]

    assert reason() is None
    assert reason(email=None) == "no_email"
    assert reason(seen=True) == "duplicate_email"
    assert reason(suppressed=True) == "suppressed"
    assert reason(consent="withdrawn") == "no_consent"
    assert reason(consent="none") == "no_consent"

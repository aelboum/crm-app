"""Automation definitions (decision P8-A, `crm_app.domains.automations`)."""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

import pytest

from crm_app.domains import automations as rules
from crm_app.domains.records import InvalidValue
from tests.support import PLACEHOLDER_SETTINGS, clean_environment, run_python

TAG = str(uuid.uuid4())
USER = str(uuid.uuid4())


def _base(**changes: Any) -> dict[str, Any]:
    return {
        "trigger": {"type": "contact_created", "sources": ["form"]},
        "condition": None,
        "yes": [{"type": "add_tag", "tag_id": TAG}],
        **changes,
    }


def test_a_definition_is_normalised_to_plain_data() -> None:
    given = rules.definition(
        _base(
            yes=[
                {"type": "create_task", "title": "  Call   back ", "due_minutes": 0},
                {"type": "wait", "minutes": 30},
                {"type": "wait_for_business_hours"},
                {"type": "assign_owner", "user_id": USER.upper()},
            ]
        )
    )
    assert given.as_json() == {
        "trigger": {"type": "contact_created", "sources": ["form"]},
        "condition": None,
        "yes": [
            {
                "type": "create_task",
                "title": "Call back",
                "priority": "medium",
                "due_minutes": 0,
                "assignee": "contact_owner",
            },
            {"type": "wait", "minutes": 30},
            {"type": "wait_for_business_hours"},
            {"type": "assign_owner", "user_id": USER},
        ],
        "no": [],
    }


@pytest.mark.parametrize(
    "changes",
    [
        {"trigger": {"type": "deal_won"}},
        {"trigger": {"type": "contact_created", "sources": ["import"]}},
        {"yes": [{"type": "eval", "code": "1+1"}]},
        {"yes": [{"type": "wait", "minutes": True}]},
        {"yes": [{"type": "wait", "minutes": 0}]},
        {"yes": [{"type": "wait", "minutes": rules.MINUTES_MAX + 1}]},
        {"yes": [{"type": "wait_for_business_hours", "minutes": 5}]},
        {"yes": [{"type": "add_tag", "tag_id": "not-an-id"}]},
        {"yes": [{"type": "add_tag", "tag_id": TAG, "extra": 1}]},
        {"yes": [{"type": "create_task", "title": "\u200b"}]},
        {"yes": [{"type": "create_task", "title": "T", "priority": "urgent"}]},
        {"yes": [{"type": "add_tag", "tag_id": TAG}] * (rules.MAX_ACTIONS + 1)},
        {"no": [{"type": "add_tag", "tag_id": TAG}]},
        {"condition": {"field": "custom_fields.x", "op": "in", "values": ["a"]}},
        {"condition": {"field": "source", "op": "matches", "values": [".*"]}},
        {"condition": {"field": "source", "op": "in", "values": []}},
        {"script": "x"},
        # P8-B
        {"trigger": {"type": "tag_added"}},
        {"trigger": {"type": "tag_added", "tag_id": "nope"}},
        {"trigger": {"type": "deal_stage_changed"}},
        {"trigger": {"type": "form_submitted", "sources": ["form"]}},
        {"trigger": {"type": "appointment_booked", "booking_page_id": TAG, "x": 1}},
        {"yes": [{"type": "set_lifecycle_stage", "stage": "royalty"}]},
        {"yes": [{"type": "remove_tag"}]},
        # P8-N
        {"yes": [{"type": "notify_member", "message": ""}]},
        {"yes": [{"type": "notify_member", "message": "\u200b"}]},
        {"yes": [{"type": "notify_member", "message": "x" * (rules.NOTICE_MAX + 1)}]},
        {"yes": [{"type": "notify_member", "message": "Hi", "recipient": "everyone"}]},
        {"yes": [{"type": "notify_member", "message": "Hi", "subject": "x"}]},
        # P8-C
        {"trigger": {"type": "campaign_sent", "campaign_id": "nope"}},
        {"trigger": {"type": "campaign_unsubscribed", "form_id": TAG}},
        {"trigger": {"type": "campaign_opened"}},
        # P8-F
        {"yes": [{"type": "set_custom_field", "value": "x"}]},
        {"yes": [{"type": "set_custom_field", "field_key": "Bad Key", "value": "x"}]},
        {"yes": [{"type": "set_custom_field", "field_key": "plan"}]},
        {"yes": [{"type": "set_custom_field", "field_key": "plan", "value": None}]},
        {"yes": [{"type": "set_custom_field", "field_key": "plan", "value": " "}]},
        {"yes": [{"type": "set_custom_field", "field_key": "plan", "value": "a\nb"}]},
        {"yes": [{"type": "set_custom_field", "field_key": "plan", "value": ["a"]}]},
        {"yes": [{"type": "set_custom_field", "field_key": "plan", "value": float("nan")}]},
        {"yes": [{"type": "set_custom_field", "field_key": "plan", "value": 10**15}]},
        {"yes": [{"type": "set_custom_field", "field_key": "plan", "value": "x" * 501}]},
        {"yes": [{"type": "set_custom_field", "field_key": "plan", "value": 1, "x": 1}]},
    ],
)
def test_anything_outside_the_rules_is_refused(changes: dict[str, Any]) -> None:
    with pytest.raises(InvalidValue):
        rules.definition(_base(**changes))


def test_event_triggers_match_their_type_and_their_record() -> None:
    other = str(uuid.uuid4())
    tagged = rules.definition(_base(trigger={"type": "tag_added", "tag_id": TAG.upper()}))
    assert tagged.as_json()["trigger"] == {"type": "tag_added", "tag_id": TAG}
    assert rules.matches(tagged, "tag_added", TAG)
    assert not rules.matches(tagged, "tag_added", other)
    assert not rules.matches(tagged, "form_submitted", TAG)
    assert not rules.triggered_by(tagged, "manual")
    any_form = rules.definition(_base(trigger={"type": "form_submitted"}))
    assert any_form.as_json()["trigger"] == {"type": "form_submitted", "form_id": None}
    assert rules.matches(any_form, "form_submitted", other)
    created = rules.definition(_base())
    assert not rules.matches(created, "contact_created", None)
    assert rules.referenced(tagged)[0] == {TAG}


def test_campaign_triggers_match_their_campaign_or_any() -> None:
    """P8-C: `campaign_sent` and `campaign_unsubscribed` take an optional
    campaign; one never matches the other's event."""
    campaign, other = str(uuid.uuid4()), str(uuid.uuid4())
    this_one = rules.definition(_base(trigger={"type": "campaign_sent", "campaign_id": campaign}))
    assert this_one.as_json()["trigger"] == {"type": "campaign_sent", "campaign_id": campaign}
    assert rules.matches(this_one, "campaign_sent", campaign)
    assert not rules.matches(this_one, "campaign_sent", other)
    assert not rules.matches(this_one, "campaign_unsubscribed", campaign)
    any_link = rules.definition(_base(trigger={"type": "campaign_unsubscribed"}))
    assert any_link.as_json()["trigger"] == {"type": "campaign_unsubscribed", "campaign_id": None}
    assert rules.matches(any_link, "campaign_unsubscribed", other)
    assert not rules.matches(any_link, "campaign_sent", other)


def test_the_new_actions_are_plain_data() -> None:
    given = rules.definition(
        _base(
            yes=[
                {"type": "remove_tag", "tag_id": TAG},
                {"type": "set_lifecycle_stage", "stage": "customer"},
            ]
        )
    )
    assert given.as_json()["yes"] == [
        {"type": "remove_tag", "tag_id": TAG},
        {"type": "set_lifecycle_stage", "stage": "customer"},
    ]
    assert rules.referenced(given)[0] == {TAG}


def test_imports_never_trigger_and_an_empty_source_list_means_any_other() -> None:
    any_source = rules.definition(_base(trigger={"type": "contact_created"}))
    assert rules.triggered_by(any_source, "manual")
    assert rules.triggered_by(any_source, "booking")
    assert not rules.triggered_by(any_source, "import")
    forms_only = rules.definition(_base())
    assert rules.triggered_by(forms_only, "form")
    assert not rules.triggered_by(forms_only, "manual")


def test_the_condition_picks_a_branch_from_stored_values() -> None:
    facts = rules.Facts(
        source="form", lifecycle_stage="lead", has_email=True, tag_ids=frozenset({TAG})
    )
    cases = [
        ({"field": "source", "op": "in", "values": ["form"]}, "yes"),
        ({"field": "source", "op": "not_in", "values": ["form"]}, "no"),
        ({"field": "lifecycle_stage", "op": "in", "values": ["customer"]}, "no"),
        ({"field": "email", "op": "present"}, "yes"),
        ({"field": "email", "op": "absent"}, "no"),
        ({"field": "tag", "op": "has", "values": [TAG]}, "yes"),
        ({"field": "tag", "op": "has_not", "values": [TAG]}, "no"),
        (None, "yes"),
    ]
    for condition, expected in cases:
        assert rules.branch_for(condition, facts) == expected, condition


def test_activation_needs_an_action_and_names_what_it_uses() -> None:
    with pytest.raises(InvalidValue):
        rules.activatable(rules.definition(_base(yes=[])))
    given = rules.definition(
        _base(
            condition={"field": "tag", "op": "has", "values": [TAG]},
            yes=[{"type": "assign_owner", "user_id": USER}],
            no=[{"type": "create_task", "title": "T", "assignee": "none"}],
        )
    )
    rules.activatable(given)
    assert rules.referenced(given) == ({TAG}, {USER})


def test_the_notify_action_is_plain_data_and_names_its_member() -> None:
    """P8-N: a fixed message, whitespace folded, to the contact's owner by
    default or to a named member, who must then be checked at activation."""
    given = rules.definition(
        _base(
            yes=[
                {"type": "notify_member", "message": "  Hot   lead "},
                {"type": "notify_member", "message": "Call", "recipient": USER.upper()},
            ]
        )
    )
    assert given.as_json()["yes"] == [
        {"type": "notify_member", "recipient": "contact_owner", "message": "Hot lead"},
        {"type": "notify_member", "recipient": USER, "message": "Call"},
    ]
    assert rules.referenced(given)[1] == {USER}


def test_the_custom_field_step_is_plain_data_and_names_its_field() -> None:
    """P8-F: a key and a fixed value, text trimmed, a whole float stored as
    an integer; activation checks the field, so the rule only shapes it."""
    given = rules.definition(
        _base(
            yes=[
                {"type": "set_custom_field", "field_key": "plan", "value": "  Gold "},
                {"type": "set_custom_field", "field_key": "score", "value": 5.0},
                {"type": "set_custom_field", "field_key": "vip", "value": False},
            ]
        )
    )
    assert given.as_json()["yes"] == [
        {"type": "set_custom_field", "field_key": "plan", "value": "Gold"},
        {"type": "set_custom_field", "field_key": "score", "value": 5},
        {"type": "set_custom_field", "field_key": "vip", "value": False},
    ]
    assert rules.field_values(given) == [("plan", "Gold"), ("score", 5), ("vip", False)]
    assert rules.referenced(given) == (set(), set())


def test_the_run_history_accepts_every_action(tmp_path: Path) -> None:
    """A step whose action the response model left out failed the whole
    run history (found with P8-F). The API module needs settings, so it is
    imported in a fresh interpreter."""
    probe = (
        "import json, typing\n"
        "from crm_app.api.automations import StepOut\n"
        "print('ACTIONS ' + json.dumps("
        "sorted(typing.get_args(StepOut.model_fields['action'].annotation))))\n"
    )
    result = run_python(probe, clean_environment(PLACEHOLDER_SETTINGS), tmp_path)
    assert result.returncode == 0, result.stderr
    line = next(x for x in result.stdout.splitlines() if x.startswith("ACTIONS "))
    assert json.loads(line.removeprefix("ACTIONS ")) == sorted(rules.ACTIONS)

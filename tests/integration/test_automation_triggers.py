"""Automation triggers and actions of decision P8-B.

Drives `automation_trigger_probe` in a fresh interpreter: a trigger that
needs its tag or stage refuses to be saved without it, and a named form,
booking page or stage must exist to activate; a tag added by a member
starts its automation, which sets the lifecycle stage and takes the tag
off; the same automation never runs twice for a contact; a deal moved into
a stage starts its automation (created in it, or moved elsewhere, does
not), and the tag that adds starts the next one, which then stops; a deal
without a contact moves without error; form and booking events start
only their own trigger's automations; another workspace's automations
never run for this workspace's contacts.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from tests.support import REPO_ROOT, run_module

pytestmark = pytest.mark.usefixtures("migrated")

Probe = dict[str, Any]


@pytest.fixture(scope="module")
def probe(integration_env: dict[str, str], tmp_path_factory: pytest.TempPathFactory) -> Probe:
    env = {
        **integration_env,
        "PYTHONPATH": str(REPO_ROOT),
        "RATE_LIMIT_REQUESTS_PER_WINDOW": "1000",
    }
    tmp = tmp_path_factory.mktemp("automation_triggers")
    result = run_module("tests.integration.automation_trigger_probe", [], env, tmp, timeout=600)
    assert result.returncode == 0, result.stderr
    line = next(x for x in result.stdout.splitlines() if x.startswith("RESULT "))
    return json.loads(line.removeprefix("RESULT "))


def test_triggers_and_actions_are_checked(probe: Probe) -> None:
    assert set(probe["refused"].values()) == {"invalid_automation"}
    assert probe["missing_subject"]["code"] == "invalid_automation"
    assert probe["trigger_stored"]["type"] == "tag_added"
    assert probe["activated"] == [200, 200, 200, 200]


def test_a_tag_added_starts_its_automation_once(probe: Probe) -> None:
    assert probe["tag_started"] == ["Hot to customer"]
    assert probe["tag_done"] is True
    assert probe["tag_again"] == 1


def test_a_deal_moved_into_the_stage_starts_a_chain_that_stops(probe: Probe) -> None:
    assert probe["deal_created_runs"] == 0
    assert probe["other_stage_runs"] == 0
    assert probe["stage_started"] == ["Won stage tags VIP"]
    assert probe["chain"] == ["Won stage tags VIP", "VIP becomes customer"]
    assert probe["chain_done"] is True
    assert probe["no_contact_move"] == 200


def test_form_and_booking_events_start_only_their_trigger(probe: Probe) -> None:
    # the any-form automation once; a second form for the same contact
    # adds nothing; no automation listens to bookings here
    assert probe["events"] == [1, 0, 0]


def test_an_automation_stops_acting_for_a_member_who_left(probe: Probe) -> None:
    outcome, run, stage = probe["departed"]
    assert outcome == "cancelled"
    assert run == {"status": "cancelled", "last_error": "not_active"}
    # the step never ran: the contact keeps its stage
    assert stage == "lead"


def test_other_workspaces_never_run_for_this_one(probe: Probe) -> None:
    assert probe["isolation"] == [1, 0]

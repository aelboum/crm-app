"""The automation notify action of decision P8-N.

Drives `automation_notify_probe` in a fresh interpreter: an empty message
and a recipient from another workspace are refused; a run notifies the
contact's owner and a named member in the app with the author's fixed
message, about the contact, with no member named as the actor; a retried
step notifies nobody twice; the recipient's list shows the note and the
contact's current name; a contact without an owner and a member who left
skip the step with a code and write nothing.
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
    tmp = tmp_path_factory.mktemp("automation_notify")
    result = run_module("tests.integration.automation_notify_probe", [], env, tmp, timeout=600)
    assert result.returncode == 0, result.stderr
    line = next(x for x in result.stdout.splitlines() if x.startswith("RESULT "))
    return json.loads(line.removeprefix("RESULT "))


def test_a_bad_message_or_a_foreign_recipient_is_refused(probe: Probe) -> None:
    assert probe["refused"] == [422, "invalid_automation"]


def test_the_owner_and_a_named_member_are_notified_with_the_message(probe: Probe) -> None:
    assert probe["activated"] == 200
    assert probe["stored"] == [
        {"type": "notify_member", "recipient": "contact_owner", "message": "New lead, call today"},
        {"type": "notify_member", "recipient": probe["member_id"], "message": "FYI"},
    ]
    assert probe["status"] == "completed"
    assert probe["notices"] == [
        [probe["member_id"], "automation_notice", "contact", "FYI", None],
        [probe["owner_id"], "automation_notice", "contact", "New lead, call today", None],
    ]


def test_a_retried_step_notifies_nobody_twice(probe: Probe) -> None:
    assert probe["after_retry"] == 2


def test_the_recipient_sees_the_note_and_the_contact(probe: Probe) -> None:
    assert probe["listed"] == [
        {
            "kind": "automation_notice",
            "subject_type": "contact",
            "subject_label": "Ann Lee",
            "note": "FYI",
            "actor_user_id": None,
        }
    ]


def test_no_owner_or_a_departed_member_skips_the_step(probe: Probe) -> None:
    steps, notes = probe["no_owner"]
    assert steps[0] == [0, "notify_member", "skipped", "no_owner"]
    assert notes == ["FYI"]
    gone_steps, gone_count = probe["member_gone"]
    assert gone_steps == [[0, "notify_member", "skipped", "member_gone"]]
    assert gone_count == 0

"""Appointment reminders (decision P5-D).

Drives `reminder_probe` in a fresh interpreter: reminders are off by
default; only members who may update the workspace turn them on, with an
allowed lead time; a run queues one transactional email per due
appointment (pending or confirmed, made before the reminder time, not yet
started) and records why others were skipped; a second run reminds nobody
twice; another workspace is untouched; the email holds no internal note;
a rescheduled appointment is reminded again; a member may send one now at
most once an hour, never for a cancelled appointment or a contact without
an address; readers see the status but cannot send; turning reminders off
removes the workspace from the run.
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
    env.pop("EMAIL_SENDING_ENABLED", None)
    tmp = tmp_path_factory.mktemp("reminders")
    result = run_module("tests.integration.reminder_probe", [], env, tmp, timeout=600)
    assert result.returncode == 0, result.stderr
    line = next(x for x in result.stdout.splitlines() if x.startswith("RESULT "))
    return json.loads(line.removeprefix("RESULT "))


def test_reminders_are_off_until_an_administrator_chooses_a_lead_time(probe: Probe) -> None:
    assert probe["off"] == 0
    # a member may not; 45 minutes is not allowed; the owner may
    assert probe["setting"] == [403, 422, 200, 1440]


def test_a_run_reminds_each_due_appointment_once_and_says_why_not(probe: Probe) -> None:
    assert probe["runs"] == [1, 3, 0, 0]
    assert probe["outcomes"] == {
        "due": [["automatic", "queued", None]],
        "no_email": [["automatic", "skipped", "no_email"]],
        "archived": [["automatic", "skipped", "contact_archived"]],
        "nobody": [["automatic", "skipped", "no_contact"]],
        "just_booked": [],
        "later": [],
        "cancelled": [],
    }
    assert probe["other_workspace"] == 0


def test_the_email_is_transactional_and_holds_no_internal_note(probe: Probe) -> None:
    purpose, to, subject_ok, greets, leaks_note, status = probe["email"]
    assert (purpose, to, subject_ok, greets, leaks_note) == (
        "appointment_reminder",
        "ada@customer.example.org",
        True,
        True,
        False,
    )
    # queued only: sending is off in tests
    assert status == "queued"


def test_a_rescheduled_appointment_is_reminded_again(probe: Probe) -> None:
    assert probe["rescheduled"] == 1
    lead, items, next_at, later_has_next, problem = probe["status"]
    assert (lead, items, next_at, later_has_next, problem) == (1440, 2, None, True, "no_email")


def test_a_member_may_send_one_now_at_most_once_an_hour(probe: Probe) -> None:
    assert probe["manual"] == [
        201,
        "manual",
        "reminder_too_soon",
        {"code": "reminder_unavailable", "reason": "no_email"},
        "not_open",
        403,
        404,
        404,
    ]


def test_turning_reminders_off_removes_the_workspace_from_the_run(probe: Probe) -> None:
    assert probe["registry_after_off"] == 0

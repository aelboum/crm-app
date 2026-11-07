"""Hosts' in-app appointment reminders (decision N-2).

Drives `member_reminder_probe` in a fresh interpreter: making an
appointment registers its workspace; a run notifies the host once, 30
minutes before the start, never earlier, never twice (also for two runs at
once); an appointment made a few minutes ahead or cancelled is not
reminded of; a rescheduled one is reminded of again; nobody else and no
other workspace sees it; the registry row goes once every appointment has
started, and the purge removes it.
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
    tmp = tmp_path_factory.mktemp("member_reminders")
    result = run_module("tests.integration.member_reminder_probe", [], env, tmp, timeout=600)
    assert result.returncode == 0, result.stderr
    line = next(x for x in result.stdout.splitlines() if x.startswith("RESULT "))
    return json.loads(line.removeprefix("RESULT "))


def test_making_an_appointment_registers_its_workspace(probe: Probe) -> None:
    assert probe["registered"] is True


def test_the_host_is_reminded_once_within_the_lead_time(probe: Probe) -> None:
    early, due, again = probe["runs"]
    assert early == 0
    assert due == 1
    assert again == 0
    assert {"subject_id": probe["later_id"], "actor": None} in probe["host_sees"]


def test_short_notice_and_cancelled_appointments_are_not_reminded_of(probe: Probe) -> None:
    assert probe["short_notice_run"] == 0
    assert probe["soon_or_dropped"] == []


def test_a_rescheduled_appointment_is_reminded_of_again(probe: Probe) -> None:
    assert probe["moved_status"] == 200
    assert probe["after_move"] == 1
    assert probe["host_count_after_move"] == 2


def test_two_runs_at_once_remind_once(probe: Probe) -> None:
    assert probe["race"] == [1, 1]


def test_nobody_else_and_no_other_workspace_sees_it(probe: Probe) -> None:
    assert probe["owner_sees"] == []
    assert probe["other_workspace"] == []
    assert probe["other_run"] == 1
    assert probe["other_after"] == 1


def test_the_registry_is_cleared_and_purged(probe: Probe) -> None:
    assert probe["left_after"] == []
    assert probe["forgotten"] is True

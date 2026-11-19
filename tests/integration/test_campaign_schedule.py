"""Scheduled campaigns (decision P7-SC).

Drives `campaign_schedule_probe` in a fresh interpreter: only approvers
schedule, with a version, an approved campaign, a time with its offset from
5 minutes to 90 days ahead, and only where queuing is available; the
maintenance run starts a campaign once it is due, as the member who
scheduled it; editing drops the schedule; unscheduling keeps the approval;
queuing at once replaces a schedule. Nothing is sent: a rehearsal workspace.
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
    for name in ("EMAIL_SENDING_ENABLED", "EMAIL_CAMPAIGN_SENDING_ENABLED", "EMAIL_PARENT_DOMAIN"):
        env.pop(name, None)
    tmp = tmp_path_factory.mktemp("campaign-schedule")
    result = run_module("tests.integration.campaign_schedule_probe", [], env, tmp, timeout=600)
    assert result.returncode == 0, result.stderr
    line = next(x for x in result.stdout.splitlines() if x.startswith("RESULT "))
    return json.loads(line.removeprefix("RESULT "))


def test_scheduling_is_refused_unless_every_condition_holds(probe: Probe) -> None:
    # A Member; no If-Match; in the past; beyond 90 days; no offset; a draft;
    # another workspace; unscheduling what is not scheduled.
    assert probe["refused"] == [
        403,
        428,
        "schedule: from 5 minutes to 90 days ahead",
        "invalid_campaign",
        422,
        "campaign_state",
        404,
        409,
    ]
    assert probe["unavailable"] == "campaign_sending_unavailable"


def test_a_scheduled_campaign_starts_only_when_due(probe: Probe) -> None:
    assert probe["scheduled"] == ["approved", True, 5]
    assert probe["row_due"] is True
    # Not due: nothing processed, still approved, the row waits.
    assert probe["early"] == [0, "approved", True]
    # Due: queued and processed (a rehearsal), the time cleared, the row gone.
    assert probe["due"] == [1, "completed", None, True]
    assert probe["audit"] == ["crm_app.campaign.queued:true", "crm_app.campaign.scheduled:-"]


def test_editing_unscheduling_or_queuing_now_replaces_the_schedule(probe: Probe) -> None:
    # The edit returns it to draft without a time; the run drops the row.
    assert probe["edited"] == ["draft", None, 0, "draft", True]
    assert probe["unscheduled"] == ["approved", None, True]
    # Queuing at once: no time, and the queue row is due now.
    assert probe["queued_now"] == ["queued", None, True]

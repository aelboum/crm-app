"""The campaign report (decision P10-C, `crm_app.reports.campaigns`).

Drives `report_campaign_probe` in a fresh interpreter: campaigns queued in
the period are listed newest first with recipients by outcome and
unsubscribes; one queued in the period before is counted for comparison
only; older ones, drafts and another workspace's campaigns are never
counted; a non-member and another workspace's Owner get 404; a period
that ends before it starts is refused.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from tests.support import REPO_ROOT, run_module

pytestmark = pytest.mark.usefixtures("migrated")

Probe = dict[str, Any]
REHEARSED = {
    "waiting": 0,
    "sent": 0,
    "delivered": 0,
    "bounced": 0,
    "complained": 0,
    "suppressed": 0,
    "not_sent": 0,
    "unknown": 0,
    "rehearsed": 2,
}


@pytest.fixture(scope="module")
def probe(integration_env: dict[str, str], tmp_path_factory: pytest.TempPathFactory) -> Probe:
    env = {
        **integration_env,
        "PYTHONPATH": str(REPO_ROOT),
        "RATE_LIMIT_REQUESTS_PER_WINDOW": "1000",
    }
    tmp = tmp_path_factory.mktemp("report_campaigns")
    result = run_module("tests.integration.report_campaign_probe", [], env, tmp, timeout=600)
    assert result.returncode == 0, result.stderr
    line = next(x for x in result.stdout.splitlines() if x.startswith("RESULT "))
    return json.loads(line.removeprefix("RESULT "))


def test_campaigns_queued_in_the_period_are_listed_newest_first(probe: Probe) -> None:
    report = probe["report"]
    assert report["capped"] is False
    assert report["period"]["days"] == 10
    assert report["campaigns"] == 2
    assert report["campaigns_before"] == 1
    assert report["recipients"] == 4
    assert report["outcomes"] == {**REHEARSED, "rehearsed": 4}
    assert report["unsubscribed"] == 1
    rows = [
        [row["campaign_id"], row["name"], row["status"], row["recipients"], row["unsubscribed"]]
        for row in report["items"]
    ]
    assert rows == [
        [probe["ids"]["latest"], "Latest", "completed", 2, 1],
        [probe["ids"]["earlier"], "Earlier", "completed", 2, 0],
    ]
    assert all(row["outcomes"] == REHEARSED for row in report["items"])


def test_only_the_workspaces_own_campaigns_and_members_count(probe: Probe) -> None:
    assert probe["other_workspace"] == 1
    assert probe["cross"] == 404
    assert probe["outsider"] == 404


def test_a_period_that_ends_before_it_starts_is_refused(probe: Probe) -> None:
    assert probe["bad_period"] == 422

"""Campaigns (decision P7-C).

Drives `campaign_probe` in a fresh interpreter: drafting by members,
refused content and segments, the validate → submit → approve workflow
with versions, approval only by Owners and Admins, an edit withdrawing an
approval, rejection with a note, an estimate that excludes contacts without
consent, suppressed or without an address; queuing refused while campaign
sending is unavailable and in production, and refused when the approval no
longer matches; recipients added once and emails sent from the campaign
subdomain; one-click unsubscribing that suppresses the address and
withdraws consent, with no visible difference for unknown tokens; other
workspaces see nothing; audit entries carry no campaign text.
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
    tmp = tmp_path_factory.mktemp("campaigns")
    result = run_module("tests.integration.campaign_probe", [], env, tmp, timeout=600)
    assert result.returncode == 0, result.stderr
    line = next(x for x in result.stdout.splitlines() if x.startswith("RESULT "))
    return json.loads(line.removeprefix("RESULT "))


def test_members_draft_and_bad_content_or_access_is_refused(probe: Probe) -> None:
    assert probe["created"] == [201, "draft", False]
    # unknown placeholder, empty segment, all_contacts with filters, reader,
    # another workspace's owner, an outsider
    assert probe["refused"] == [422, 422, 422, 403, 404, 404]
    assert probe["no_version"] == 428


def test_the_estimate_counts_only_contacts_who_may_receive_it(probe: Probe) -> None:
    status, estimate = probe["validated"]
    assert status == "validated"
    assert estimate == {
        "eligible": 1,
        "excluded": {"no_consent": 1, "suppressed": 1, "no_email": 1},
    }


def test_approval_follows_the_workflow_and_needs_an_approver(probe: Probe) -> None:
    assert probe["early_approve"]["detail"]["code"] == "campaign_state"
    assert probe["submitted"] == "awaiting_approval"
    assert probe["member_approve"] == 403
    assert probe["stale_approve"] == 409
    assert probe["approved"] == ["approved", True]


def test_an_edit_withdraws_the_approval(probe: Probe) -> None:
    assert probe["edited"] == ["draft", False, None]
    assert probe["approve_after_edit"]["code"] == "campaign_state"
    assert probe["rejected"] == ["rejected", "Shorten it"]
    assert probe["reapproved"] == ["approved", True]


def test_nothing_can_be_queued_while_sending_is_unavailable(probe: Probe) -> None:
    assert probe["queue_unavailable"] == [{"code": "campaign_sending_unavailable"}, 403]
    assert probe["listed"] == [1, False]
    assert probe["production"] is False


def test_a_changed_approval_is_refused_and_recipients_are_added_once(probe: Probe) -> None:
    assert probe["outdated"] == {"code": "approval_outdated"}
    assert probe["queued"] == "queued"
    assert probe["processed"] == ["completed", 1, 0]
    assert probe["recipients"] == 1
    assert probe["rendered"] == [True, True]
    assert probe["sent"] == "sent"
    assert probe["sender"] == "news@campaigns.example.test"


def test_unsubscribing_suppresses_and_withdraws_consent(probe: Probe) -> None:
    assert probe["unsubscribe"] == [204, 204, 204, 204, 204]
    assert probe["after_unsubscribe"] == [1, 1, "unsubscribed"]
    assert probe["late_send"] == [True, "suppressed"]


def test_cancelled_campaigns_are_final(probe: Probe) -> None:
    assert probe["cancel"] == ["cancelled", 409, 409]


def test_other_workspaces_see_nothing_and_audit_holds_no_text(probe: Probe) -> None:
    assert probe["isolation"] == [0, 404, 404]
    assert probe["audit_text"] == 0
    assert probe["audit_steps"] == 2

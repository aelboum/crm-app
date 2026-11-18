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
    # One https List-Unsubscribe address, One-Click asked, the body's token
    # (decision E-H1); the Message-ID it went with is kept.
    assert probe["headers"] == [1, True, True, True]
    assert probe["message_id_stored"] is True


def test_unsubscribing_suppresses_and_withdraws_consent(probe: Probe) -> None:
    assert probe["unsubscribe"] == [204, 204, 204, 204, 204]
    assert probe["after_unsubscribe"] == [1, 1, "unsubscribed"]
    link = ["system", True, "public_link", "crm_app.unsubscribe_link", "unavailable"]
    assert probe["unsubscribe_audit"] == [
        ["crm_app.contact.consent_withdrawn", *link],
        ["crm_app.suppression.added", *link],
    ]
    assert probe["late_send"] == [True, "suppressed"]


def test_cancelled_campaigns_are_final(probe: Probe) -> None:
    assert probe["cancel"] == ["cancelled", 409, 409]


def test_other_workspaces_see_nothing_and_audit_holds_no_text(probe: Probe) -> None:
    assert probe["isolation"] == [0, 404, 404]
    assert probe["audit_text"] == 0
    assert probe["audit_steps"] == 2


def test_the_maintenance_run_sends_queued_campaigns_in_batches(probe: Probe) -> None:
    """Decision P7-S: queuing records the campaign; each run adds at most a
    batch of recipients as the sending component, on behalf of the member
    who queued it, and the row goes once the campaign is finished."""
    # Workspace a's campaign, processed directly, leaves the queue.
    assert probe["queue_drained"] >= 1
    assert probe["queue_recorded"] == ["queued", 1]
    runs = probe["queue_runs"]
    # [campaigns processed, finished, waiting, emails] (+ status, queue rows)
    assert runs["no_https"] == [0, 0, 1, 0]
    assert runs["first"] == [1, 0, 0, 2, "processing", 1]
    assert runs["second"] == [1, 1, 0, 1, "completed", 0]
    assert runs["stale"] == [0, 1, 0, 0]
    assert probe["queue_recipients"] == 3
    assert probe["queue_emails_in_b"] is True
    owner = probe["queue_audit"]
    assert owner[0] == ["crm_app.campaign.completed", "system", "crm_app.campaign_send", True]
    assert owner[1][0] == "crm_app.campaign.queued"
    assert owner[1][1] == "user"


def test_a_named_workspace_rehearses_campaigns_and_nothing_is_sent(probe: Probe) -> None:
    """Decision P7-R: with sending unavailable, a workspace named in
    CAMPAIGN_REHEARSAL_WORKSPACES queues and processes a campaign; every
    email is closed as failed (rehearsal) and stays unsent even once
    sending is switched on. Another workspace still cannot queue."""
    r = probe["rehearsal"]
    assert r["listed"] == [False, True, False]
    assert r["queued"] == [200, "queued"]
    assert r["campaign"] == "completed"
    assert r["emails"] == [["failed", "rehearsal", 3]]
    assert r["run"][0] >= 1
    assert r["audit"] == "true"
    assert r["later"] == ["failed", 0]
    assert probe["rehearsal_other_workspace"] == {"code": "campaign_sending_unavailable"}

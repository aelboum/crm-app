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


def test_a_campaign_is_previewed_for_one_contact(probe: Probe) -> None:
    """Decision P7-PV: the contact's values and the footer with a stand-in
    link; whether they are in the audience and may receive it; a
    Read-only member may preview; an unknown contact or another workspace
    is a 404 and the contact is required."""
    preview = probe["preview"]
    assert preview["ada"] == ["News for Ada", True, True, "eligible", None]
    # Grace has no consent, Mal is suppressed, Cust is not a lead.
    assert preview["others"] == [
        ["excluded", "no_consent"],
        ["excluded", "suppressed"],
        ["outside", None],
    ]
    assert preview["refused"] == ["contact_not_found", 404, 422]


def test_a_deleted_tag_in_the_audience_is_reported_not_dropped(probe: Probe) -> None:
    """Decision P7-ST: the segment keeps the deleted tag (the audience never
    widens by itself), reads report it, and the audience check refuses
    with its own rule."""
    stale = probe["stale_tag"]
    assert stale["before"] == []
    assert stale["after"] is True
    assert stale["listed"] is True
    assert stale["segment_kept"] is True
    assert stale["validate"] == {
        "code": "invalid_campaign",
        "rule": "segment: a tag in the audience was deleted",
    }


def test_only_a_campaign_never_queued_may_be_deleted(probe: Probe) -> None:
    """P7-DL: those who manage campaigns delete a draft with its version;
    Read-only members are refused, another workspace sees a 404, and a
    campaign that was sent stays (it is archived instead). Audited."""
    deleted = probe["deleted"]
    assert deleted["refused"] == [403, 404, 428, 409]
    status, code, detail = deleted["finished"]
    assert status in ("completed", "partially_completed", "failed")
    assert (code, detail) == (
        409,
        {"code": "campaign_state", "rule": f"delete: not from {status}"},
    )
    assert deleted["still_there"] == 200
    assert deleted["gone"] == [204, 404]
    assert deleted["audit"] == 1


def test_deleted_tags_are_removed_only_on_request(probe: Probe) -> None:
    """P7-ST follow-up: removing the deleted tags is an edit for those who
    manage campaigns (a draft again, the other filters kept); refused when
    they are the only filter or none was deleted; another workspace sees a
    404; the audit counts the tags removed."""
    removed = probe["stale_removed"]
    assert removed["only_deleted"] == {
        "code": "invalid_campaign",
        "rule": "segment: only deleted tags choose this audience; edit the audience",
    }
    assert removed["refused"] == [403, 404, 409]
    assert removed["cleaned"] == [200, "draft", [], ["lead"], []]
    assert removed["again"] == {
        "code": "invalid_campaign",
        "rule": "segment: no tag in the audience was deleted",
    }
    assert removed["audit"] == 1


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


def test_only_finished_campaigns_are_archived_and_hidden_from_the_list(probe: Probe) -> None:
    """Decision P7-AR: archiving needs `campaign:manage` and a version, is
    refused for a draft, another workspace sees a 404, and an archived
    campaign keeps its results and comes back when unarchived."""
    archive = probe["archive"]
    # Read-only member; other workspace; no If-Match; a draft; not archived.
    assert archive["refused"] == [403, 404, 428, "campaign_state", 409]
    assert archive["archived"] == ["cancelled", True, 3]
    # Not in the default list; in the archived list, which holds nothing else here.
    assert archive["hidden"] == [False, True, False]
    assert archive["again"] == 409
    assert archive["report"] == 200
    assert archive["restored"] == [None, True]
    assert archive["audit"] == 2


def test_the_list_is_searched_filtered_and_paged_newest_first(probe: Probe) -> None:
    """Decision P7-CL: `search` matches part of the name ignoring case,
    `status` keeps one state, pages follow `next_cursor`, a cursor is
    refused with other filters, and other workspaces' campaigns never show."""
    paging = probe["paging"]
    assert paging["first"] == [["ZEBRA three", "Zebra two"], 3]
    assert paging["rest"] == [["Zebra one"], None]
    assert paging["cancelled"] == [True, True]
    # A literal "%" matches no name: it is not a wildcard.
    assert paging["drafts"] == 0
    assert paging["refused"] == ["invalid_cursor", "invalid_search", 422, 422]
    assert paging["other"] == 0


def test_the_list_is_ordered_by_name_or_last_update(probe: Probe) -> None:
    """Decision P7-SO: `order=name` sorts A to Z ignoring case and pages on;
    `order=updated_at` puts the last edited first; a cursor from another
    order and an unknown order are refused."""
    ordering = probe["ordering"]
    assert ordering["name"] == ["Zebra one", "ZEBRA three", "Zebra two"]
    assert ordering["name_last"] is None
    assert ordering["updated"] == "Zebra uno"
    assert ordering["refused"] == ["invalid_cursor", 422]


def test_results_are_exported_as_csv_for_owners_and_admins(probe: Probe) -> None:
    """Decision P7-RX: each recipient's address and outcome, as the contact
    export does it; Members and Read-only members are refused, another
    workspace sees a 404, and the audit holds the row count only."""
    csv = probe["results_csv"]
    assert csv["owner"] == [200, "text/csv; charset=utf-8", True, "no-store"]
    assert csv["header"] == "email,contact_id,outcome,added_at,unsubscribed_at"
    # Ada's email was accepted by the provider, then she unsubscribed.
    assert csv["row"] == ["ada@example.test", True, "sent", True]
    assert csv["rows"] == 1
    assert csv["refused"] == [403, 403, 404, 404]
    assert csv["audit"] == "1"


def test_a_campaign_is_duplicated_into_a_new_draft(probe: Probe) -> None:
    """Decision P7-DU: the copy has the subject, body and audience, none of
    the estimate or approval; any state may be copied; refused for
    Read-only members and other workspaces."""
    dup = probe["duplicate"]
    assert dup["copy"] == [
        201,
        '"1"',
        "draft",
        "Autumn news (copy)",
        True,
        True,
        True,
        None,
        False,
        True,
    ]
    assert dup["source_status"] == "completed"
    assert dup["named"] == [201, "Winter news"]
    assert dup["long"] == [120, True]
    assert dup["refused"] == [403, 404, "invalid_campaign", 422]
    assert dup["audit"] == 2


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


def test_a_campaign_report_counts_outcomes_for_its_workspace_only(probe: Probe) -> None:
    """Decision P7-RP: every role reads a campaign's results, counted from
    stored rows; another workspace gets 404 even with the id."""
    status, report = probe["report_rehearsal"]
    assert (status, report["status"], report["recipients"]) == (200, "completed", 3)
    assert report["outcomes"]["rehearsed"] == 3
    assert sum(report["outcomes"].values()) == 3
    assert report["unsubscribed"] == 0
    assert probe["report_cross"] == 404
    assert probe["report_missing"] == 404
    status, empty = probe["report_draft"]
    assert (status, empty["recipients"], empty["unsubscribed"]) == (200, 0, 0)
    assert set(empty["outcomes"].values()) == {0}
    # Workspace a's campaign: one email accepted by the provider (not
    # delivery), and its recipient then used the unsubscribe link.
    status, sent = probe["report_sent"]
    assert (status, sent["recipients"], sent["unsubscribed"]) == (200, 1, 1)
    assert {k: v for k, v in sent["outcomes"].items() if v} == {"sent": 1}

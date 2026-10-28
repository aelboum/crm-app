"""Suppression and consent routes (decision P7-B, slice 7B;
`crm_app.api.suppression`).

Drives `suppression_route_probe` in a fresh interpreter and checks the
audit log directly. Covers: the roles (Owner, Admin and Member read the
list; Owner and Admin add and remove; Members record and withdraw
consent); tenant isolation on every route; adding (normalised, deduplicated,
refusals by position that never echo an address); the list (newest first,
search, paging); a contact's email status; recording consent with its
wording; withdrawing it, which suppresses the address and keeps an earlier
reason; consent that never lifts a suppression; removing; and audit
entries without addresses, wording or notes.
"""

from __future__ import annotations

import json
from typing import Any

import psycopg
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
    tmp = tmp_path_factory.mktemp("suppression")
    result = run_module("tests.integration.suppression_route_probe", [], env, tmp, timeout=600)
    assert result.returncode == 0, result.stderr
    line = next(x for x in result.stdout.splitlines() if x.startswith("RESULT "))
    return json.loads(line.removeprefix("RESULT "))


def test_members_read_the_list_and_owners_and_admins_change_it(probe: Probe) -> None:
    assert probe["read"] == {
        "owner": 200,
        "admin": 200,
        "member": 200,
        "reader": 403,
        "other_owner": 404,
    }
    assert probe["add"] == {
        "owner": 201,
        "admin": 201,
        "member": 403,
        "reader": 403,
        "other_owner": 404,
    }
    assert probe["remove"] == {"member": 403, "admin": 204, "again": 404}


def test_addresses_are_added_once_and_refused_by_position(probe: Probe) -> None:
    assert probe["first"] == [201, {"added": 2, "already_suppressed": 0}]
    assert probe["again"] == [201, {"added": 1, "already_suppressed": 1}]
    status, body, echoed = probe["refused"]
    assert (status, body["detail"]) == (422, {"code": "invalid_emails", "positions": [1]})
    assert echoed is False
    assert probe["invalid"] == {"empty": 422, "too_many": 422, "reason": 422, "note": 422}


def test_the_list_is_newest_first_searchable_and_paged(probe: Probe) -> None:
    status, page = probe["listed"]
    assert status == 200
    emails = [item["email"] for item in page["items"]]
    assert emails[0] == "new@example.test"
    assert {"ada@example.test", "sam@example.test", "owner@example.test"} <= set(emails)
    ada = next(item for item in page["items"] if item["email"] == "ada@example.test")
    assert (ada["reason"], ada["origin"], ada["note"]) == (
        "bounced",
        "manual",
        "From the old newsletter tool.",
    )
    assert ada["created_by_user_id"] == probe["admin_id"]
    assert [item["email"] for item in probe["search"]] == ["ada@example.test"]
    first, second = probe["paging"]
    assert len(first) == 2
    assert not set(first) & set(second)
    assert (probe["bad_cursor"], probe["wrong_cursor"]) == (400, 400)


def test_consent_is_recorded_with_its_wording_by_a_member(probe: Probe) -> None:
    assert probe["status_before"] == {
        "has_email": True,
        "consent": "none",
        "suppression": None,
        "marketing_allowed": False,
    }
    assert probe["record_rights"] == {
        "reader": 403,
        "blank": 422,
        "no_email": {"detail": {"code": "contact_has_no_email"}},
    }
    assert probe["recorded"] == [
        200,
        {"has_email": True, "consent": "granted", "suppression": None, "marketing_allowed": True},
    ]


def test_withdrawing_consent_suppresses_the_address(probe: Probe) -> None:
    status, body = probe["withdrawn"]
    assert status == 200
    assert body["consent"] == "withdrawn"
    assert body["suppression"]["reason"] == "unsubscribed"
    assert body["marketing_allowed"] is False
    [carol] = probe["carol_listed"]
    assert (carol["email"], carol["reason"], carol["origin"]) == (
        "carol@example.test",
        "unsubscribed",
        "consent_withdrawn",
    )
    assert carol["created_by_user_id"] == probe["member_id"]
    # An address already on the list keeps its first reason.
    [sam] = probe["sam_listed"]
    assert (sam["reason"], sam["origin"]) == ("bounced", "manual")
    # Without an address there is nothing to suppress.
    assert probe["nomail_withdrawn"] == {
        "has_email": False,
        "consent": "withdrawn",
        "suppression": None,
        "marketing_allowed": False,
    }


def test_consent_never_lifts_a_suppression_but_removing_it_does(probe: Probe) -> None:
    regranted = probe["regranted"]
    assert regranted["consent"] == "granted"
    assert regranted["suppression"] is not None
    assert regranted["marketing_allowed"] is False
    assert probe["status_after_remove"] == {
        "has_email": True,
        "consent": "granted",
        "suppression": None,
        "marketing_allowed": True,
    }


def test_the_history_keeps_every_record(probe: Probe) -> None:
    history = probe["history"]
    assert [(r["status"], r["method"], r["wording"]) for r in history] == [
        ("granted", "manual", "Yes again."),
        ("withdrawn", "manual", "Asked by phone."),
        ("granted", "manual", "Yes, email me about offers."),
    ]
    assert {r["recorded_by_user_id"] for r in history} == {probe["member_id"]}


def test_another_workspace_cannot_reach_the_list_or_the_status(probe: Probe) -> None:
    assert probe["foreign"] == {
        "list": 404,
        "remove": 404,
        "remove_via_b": 404,
        "status": 404,
        "status_via_b": 404,
        "withdraw_via_b": 404,
        "b_list": 0,
    }


def test_changes_are_audited_without_addresses_or_wording(
    probe: Probe, owner_connection: psycopg.Connection
) -> None:
    rows = owner_connection.execute(
        "SELECT action, metadata FROM core.audit_log WHERE tenant_id = %s"
        " AND resource_type = 'crm_app.suppression' ORDER BY created_at",
        (probe["workspace"],),
    ).fetchall()
    actions = [action for action, _ in rows]
    assert actions.count("crm_app.suppression.removed") == 1
    added = [meta for action, meta in rows if action == "crm_app.suppression.added"]
    assert {"count": 2, "reason": "bounced"} in added
    assert {"count": 1, "reason": "unsubscribed"} in added
    contact_rows = owner_connection.execute(
        "SELECT action, metadata FROM core.audit_log WHERE tenant_id = %s"
        " AND resource_type = 'crm_app.contact' AND resource_id = %s"
        " AND action LIKE 'crm_app.contact.consent%%' ORDER BY created_at",
        (probe["workspace"], probe["carol"]),
    ).fetchall()
    assert [action for action, _ in contact_rows] == [
        "crm_app.contact.consent_recorded",
        "crm_app.contact.consent_withdrawn",
        "crm_app.contact.consent_recorded",
    ]
    assert {json.dumps(meta) for _, meta in contact_rows} == {'{"channel": "email"}'}
    text = json.dumps([meta for _, meta in rows])
    assert "@" not in text
    assert "newsletter" not in text

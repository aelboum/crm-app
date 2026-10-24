"""Invitations end to end (`PHASE2-PLAN.md` §8.2, §13 "Invitations";
decisions Q4, Q5, P2-F).

Drives `invitation_probe` in a fresh interpreter, then checks the audit
trail and the intent table directly. Covers who may invite and see
invitations, the Owner rule, manual-mode links (Q4), validation and
duplicates, acceptance bound to the invited verified email and used once,
the bare membership awaiting its role and its confirmation by an Admin
(Q5), revocation, email mode with SaaS-OS's fake provider including a
failed send, and that no token reaches a log, an audit entry, the intent
table or a listing.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import psycopg
import pytest
from psycopg import errors

from tests.integration.test_crm_tables import (
    _as_workspace,
    _visible,
    _workspace,
    env,  # noqa: F401 (fixture)
    runtime,  # noqa: F401 (fixture)
)
from tests.support import REPO_ROOT, run_module

pytestmark = pytest.mark.usefixtures("migrated")

Probe = dict[str, Any]


@pytest.fixture(scope="module")
def ran(integration_env: dict[str, str], tmp_path_factory: pytest.TempPathFactory) -> Probe:
    probe_env = {
        **integration_env,
        "PYTHONPATH": str(REPO_ROOT),
        # The probe creates and accepts many invitations within a minute; the
        # per-route and per-person limits are raised for this process only.
        "RATE_LIMIT_REQUESTS_PER_WINDOW": "1000",
    }
    cwd: Path = tmp_path_factory.mktemp("invitations")
    result = run_module("tests.integration.invitation_probe", [], probe_env, cwd, timeout=600)
    assert result.returncode == 0, result.stderr
    line = next(x for x in result.stdout.splitlines() if x.startswith("RESULT "))
    return {"probe": json.loads(line.removeprefix("RESULT ")), "stderr": result.stderr}


@pytest.fixture(scope="module")
def probe(ran: Probe) -> Probe:
    return ran["probe"]


def test_owners_and_admins_invite_and_see_invitations_and_nobody_else(probe: Probe) -> None:
    assert probe["create"] == {
        "Owner": 201,
        "Admin": 201,
        "Member": 403,
        "Read-only": 403,
        "outsider": 404,
        "other_owner": 404,
        "anonymous": 401,
    }
    assert probe["list"] == {
        "Owner": 200,
        "Admin": 200,
        "Member": 403,
        "Read-only": 403,
        "outsider": 404,
    }


def test_only_an_owner_invites_an_owner(probe: Probe) -> None:
    assert probe["owner_invites"] == {
        "admin_invites_owner": [403, {"code": "role_not_allowed"}],
        "owner_invites_owner": 201,
    }


def test_a_manual_invitation_returns_its_link_once_and_says_it_was_not_sent(probe: Probe) -> None:
    manual = probe["manual"]
    assert manual["status"] == 201
    assert manual["cache"] == "no-store"
    assert manual["link_path"] == f"/app/invite/{probe['workspace']}"
    assert manual["token_length"] >= 40
    invitation = manual["invitation"]
    assert invitation["email"] == probe["invitee_email"]  # trimmed and lower-cased
    assert (invitation["role"], invitation["delivery"], invitation["status"]) == (
        "Member",
        "manual",
        "pending",
    )
    listed = probe["listed"]
    assert (listed["role"], listed["delivery"], listed["status"]) == ("Member", "manual", "pending")
    assert "link" not in listed


def test_invitations_are_validated(probe: Probe) -> None:
    assert probe["validation"] == {
        "duplicate": [409, {"code": "duplicate_invitation"}],
        "bad_email": 422,
        "bad_role": 422,
        "extra_field": 422,
    }


def test_only_the_invited_verified_email_accepts_and_only_once(probe: Probe) -> None:
    assert probe["accept"] == {
        "anonymous": 401,
        "unverified_session": 404,
        "wrong_email": 404,
        "wrong_workspace": 404,
        "tampered": 404,
        "invitee": 200,
        "again": 404,
    }


def test_acceptance_gives_a_membership_awaiting_its_role(probe: Probe) -> None:
    after = probe["after_accept"]
    assert (after["member"]["status"], after["member"]["roles"]) == ("active", [])
    assert after["open_workspace"] == 403  # no role: no permission, fail closed
    assert probe["workspace"] in after["directory"]
    assert after["status_listed"] == "accepted"


def test_an_admin_confirms_the_role_and_nobody_else_can(probe: Probe) -> None:
    assert probe["confirm"] == {
        "by_member": 403,
        "by_invitee": 403,
        "by_admin": 200,
        "open_workspace": 200,
    }


def test_revocation(probe: Probe) -> None:
    assert probe["revoke"] == {
        "by_member": 403,
        "by_admin": "revoked",
        "again": 200,
        "accepted_one": 409,
        "unknown": 404,
        "other_workspace": 404,
    }


def test_email_mode_sends_through_the_provider_and_never_returns_the_link(probe: Probe) -> None:
    email = probe["email"]
    assert (email["status"], email["link_in_response"], email["delivery"]) == (201, None, "email")
    assert email["messages"] == 1
    assert email["link_in_body"] is True
    failure = probe["email_failure"]
    assert (failure["status"], failure["detail"]) == (502, {"code": "delivery_failed"})
    assert failure["status_listed"] == ["revoked"]  # nothing usable left behind


def test_no_token_reaches_logs_listings_or_audit(
    ran: Probe, owner_connection: psycopg.Connection
) -> None:
    probe = ran["probe"]
    secrets = probe["secrets"]
    assert len(secrets) >= 3
    audit = owner_connection.execute(
        "SELECT coalesce(string_agg(action || ' ' || metadata::text, ' '), '')"
        " FROM core.audit_log WHERE tenant_id = %s",
        (probe["workspace"],),
    ).fetchone()
    assert audit is not None
    intents = owner_connection.execute(
        "SELECT coalesce(string_agg(row_to_json(i)::text, ' '), '')"
        " FROM crm_app.invitation_intent i WHERE tenant_id = %s",
        (probe["workspace"],),
    ).fetchone()
    assert intents is not None
    for secret in secrets:
        assert secret not in ran["stderr"]
        assert secret not in probe["listing_text"]
        assert secret not in audit[0]
        assert secret not in intents[0]
    assert "crm_app.invitation.intent_recorded" in audit[0]
    assert probe["invitee_email"] not in intents[0]


# --- Row-level security, as the runtime role -----------------------------------


def test_intent_rows_are_visible_and_writable_only_in_their_own_workspace(
    env: dict[str, str],  # noqa: F811
    runtime: psycopg.Connection,  # noqa: F811
) -> None:
    a, b = _workspace(env)["tenant"], _workspace(env)["tenant"]
    insert = (
        "INSERT INTO crm_app.invitation_intent"
        " (tenant_id, invitation_id, role, invited_by_user_id, delivery)"
        " VALUES (%s, gen_random_uuid(), 'Member', gen_random_uuid(), 'manual')"
    )
    with _as_workspace(runtime, a):
        runtime.execute(insert, (a,))
    assert _visible(runtime, "invitation_intent") == 0
    with _as_workspace(runtime, b):
        assert _visible(runtime, "invitation_intent") == 0
    with _as_workspace(runtime, a):
        assert _visible(runtime, "invitation_intent") == 1
    with pytest.raises(errors.InsufficientPrivilege), _as_workspace(runtime, a):
        runtime.execute(insert, (b,))


@pytest.mark.parametrize(("column", "value"), [("role", "Superuser"), ("delivery", "sms")])
def test_the_intent_table_refuses_unknown_roles_and_deliveries(
    env: dict[str, str],  # noqa: F811
    owner_connection: psycopg.Connection,
    column: str,
    value: str,
) -> None:
    a = _workspace(env)["tenant"]
    row = {"role": "Member", "delivery": "manual", column: value}
    with pytest.raises(errors.CheckViolation):
        owner_connection.execute(
            "INSERT INTO crm_app.invitation_intent"
            " (tenant_id, invitation_id, role, invited_by_user_id, delivery)"
            " VALUES (%s, gen_random_uuid(), %s, gen_random_uuid(), %s)",
            (a, row["role"], row["delivery"]),
        )

"""Conversations (decision P6-C).

Drives `conversation_probe` in a fresh interpreter with sending off: a
thread with its first message; unread state per member; an email reply
queues one email (shown as queued, never as sent) and a retry with the same
`Idempotency-Key` queues none; notes queue nothing; refusals by rule;
assignment, closing and reopening with versions; Read-only members read
only; other workspaces and outsiders see nothing; deleting the contact
keeps the thread.
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
    env.pop("EMAIL_SENDING_ENABLED", None)
    tmp = tmp_path_factory.mktemp("conversations")
    result = run_module("tests.integration.conversation_probe", [], env, tmp, timeout=600)
    assert result.returncode == 0, result.stderr
    line = next(x for x in result.stdout.splitlines() if x.startswith("RESULT "))
    return json.loads(line.removeprefix("RESULT "))


def test_a_thread_starts_with_its_first_message(probe: Probe) -> None:
    assert probe["created"] == [201, "Your quote"]


def test_unread_means_a_message_by_someone_else_since_last_read(probe: Probe) -> None:
    assert probe["owner_unread"] == [True]
    assert probe["member_unread"] == [False]
    assert probe["mark_read"] == 204
    assert probe["owner_unread_after"] == [False]


def test_an_email_reply_is_queued_once_and_never_shown_as_sent(probe: Probe) -> None:
    assert probe["reply"] == [201, 201, "true", 422]
    assert probe["messages"] == [
        ["inbound", None],
        ["outbound", "queued"],
        ["note", None],
    ]
    emails = probe["emails"]
    assert len(emails) == 1
    assert emails[0]["purpose"] == "conversation_reply"
    assert emails[0]["to_email"] == "ada@example.test"
    assert emails[0]["subject"] == "Your quote"
    assert emails[0]["text_body"] == "Here it is.\nThanks!"
    assert emails[0]["status"] == "queued"


def test_refusals_name_the_rule_and_queue_nothing(probe: Probe) -> None:
    assert probe["outbound_on_other"]["detail"] == {
        "code": "invalid_conversation",
        "rule": "outbound: only on an email thread",
    }
    assert probe["no_email"][0] == 409
    assert probe["no_email"][1]["detail"]["code"] == "contact_has_no_email"
    assert probe["control"] == 422
    assert probe["unknown_contact"] == 422
    assert probe["after_refusals"] == 1


def test_assign_close_and_reopen(probe: Probe) -> None:
    assert probe["assigned"] == [200, probe["member"]]
    assert probe["stale"] == 409
    assert probe["outsider_assignee"] == 422
    assert probe["closed"] == "closed"
    assert probe["open_list_after_close"] == 0
    assert probe["closed_list"] == 1
    assert probe["assigned_mine"] == 1
    assert probe["unassigned_closed"] == 0
    assert probe["reopened"] == "open"
    assert probe["by_contact"] == 2


def test_read_only_members_read_but_change_nothing(probe: Probe) -> None:
    assert probe["reader_read"] == 200
    assert probe["reader_mark_read"] == 204
    assert probe["reader_reply"] == 403
    assert probe["reader_create"] == 403
    assert probe["reader_patch"] == 403


def test_other_workspaces_and_outsiders_see_nothing(probe: Probe) -> None:
    assert probe["other_owner_get"] == 404  # not a member: the workspace is hidden
    assert probe["other_tenant_path"] == 404
    assert probe["other_tenant_reply"] == 404
    assert probe["other_tenant_list"] == 0
    assert probe["outsider"] == 404
    assert probe["bad_status"] == 422


def test_deleting_the_contact_keeps_the_thread(probe: Probe) -> None:
    assert probe["contact_delete"] == 204
    assert probe["after_contact_delete"] == [None, 4]


def test_changes_are_audited_without_message_text(
    probe: Probe, owner_connection: psycopg.Connection
) -> None:
    rows = owner_connection.execute(
        "SELECT action, metadata::text FROM core.audit_log"
        " WHERE resource_type = 'crm_app.conversation' AND actor_user_id = %s",
        (probe["owner"],),
    ).fetchall()
    actions = {action for action, _ in rows}
    assert {
        "crm_app.conversation.message_added",
        "crm_app.conversation.updated",
        "crm_app.conversation.closed",
    } <= actions
    assert not any("Here it is" in meta or "Priced" in meta for _, meta in rows)

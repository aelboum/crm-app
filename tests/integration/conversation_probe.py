"""Drives conversations (decision P6-C) and prints one `RESULT <json>` line.

Run in a fresh interpreter by `tests/integration/test_conversations.py`.
Sending stays off, so an email reply is recorded as queued and none leaves
this machine. Seeds throwaway workspaces. Refuses to run unless
ENVIRONMENT=test.
"""

from __future__ import annotations

import json
import os
import secrets
import uuid
from typing import Any

from fastapi.testclient import TestClient
from saas_os.core.identity import issue_session
from saas_os.infra.db import tenant_session_scope
from sqlalchemy import text

from crm_app.app import create_app
from crm_app.roles import Role
from tests.integration.opportunity_route_probe import _member
from tests.integration.workspace_route_probe import _new_user, _new_workspace


def _emails(workspace: uuid.UUID) -> list[dict[str, Any]]:
    with tenant_session_scope(workspace) as session:
        return [
            dict(r._mapping)
            for r in session.execute(
                text(
                    "SELECT purpose, to_email, subject, text_body, status"
                    " FROM crm_app.email_message WHERE tenant_id = :t ORDER BY created_at"
                ),
                {"t": workspace},
            )
        ]


def main() -> None:  # noqa: PLR0915 - one scenario script, read top to bottom
    if os.environ.get("ENVIRONMENT") != "test":
        raise SystemExit("conversation_probe runs only with ENVIRONMENT=test")
    os.environ.pop("EMAIL_SENDING_ENABLED", None)
    a = _new_workspace("conversation-a")
    b = _new_workspace("conversation-b")
    member_id, member = _member(a, Role.MEMBER)
    _, reader = _member(a, Role.READ_ONLY)
    tokens = {
        "owner": issue_session(a.owner_id)[1],
        "member": member,
        "reader": reader,
        "other_owner": issue_session(b.owner_id)[1],
        "outsider": issue_session(_new_user())[1],
    }

    def auth(
        caller: str = "owner", version: int | None = None, key: str | None = None
    ) -> dict[str, str]:
        headers = {"Authorization": f"Bearer {tokens[caller]}"}
        if version is not None:
            headers["If-Match"] = f'"{version}"'
        if key is not None:
            headers["Idempotency-Key"] = key
        return headers

    base = f"/v1/workspaces/{a.id}"
    result: dict[str, Any] = {"owner": str(a.owner_id), "member": str(member_id)}
    with TestClient(create_app(), follow_redirects=False) as client:

        def contact(first: str, email: str | None) -> str:
            body: dict[str, Any] = {"first_name": first, "last_name": "Lovelace"}
            if email:
                body["email"] = email
            else:
                body["phone"] = "+31 20 123 4567"
            made = client.post(f"{base}/contacts", json=body, headers=auth())
            return str(made.json()["id"])

        def ids(path: str, caller: str = "owner") -> list[str]:
            return [i["id"] for i in client.get(path, headers=auth(caller)).json()["items"]]

        def unread(caller: str, conversation: str) -> list[bool]:
            items = client.get(f"{base}/conversations", headers=auth(caller)).json()["items"]
            return [i["unread"] for i in items if i["id"] == conversation]

        ada = contact("Ada", "ada@example.test")
        nomail = contact("Grace", None)
        thread = {
            "contact_id": ada,
            "channel": "email",
            "subject": "  Your   quote ",
            "kind": "inbound",
            "body": "Hi, can you send the quote?",
        }
        made = client.post(f"{base}/conversations", json=thread, headers=auth("member"))
        result["created"] = [made.status_code, made.json().get("subject")]
        conv = made.json()
        one = f"{base}/conversations/{conv['id']}"

        # Unread: the member logged it, so it is unread for the owner only.
        result["owner_unread"] = unread("owner", conv["id"])
        result["member_unread"] = unread("member", conv["id"])
        result["mark_read"] = client.post(f"{one}/read", headers=auth()).status_code
        result["owner_unread_after"] = unread("owner", conv["id"])

        # An email reply queues one email; a retry with the same key replays
        # without queuing another; a note queues nothing.
        key = f"reply-{secrets.token_hex(4)}"
        reply = {"kind": "outbound", "body": "Here it is.\nThanks!"}
        first = client.post(f"{one}/messages", json=reply, headers=auth(key=key))
        again = client.post(f"{one}/messages", json=reply, headers=auth(key=key))
        reused = client.post(
            f"{one}/messages", json={**reply, "body": "Other"}, headers=auth(key=key)
        )
        result["reply"] = [
            first.status_code,
            again.status_code,
            again.headers.get("Idempotent-Replayed"),
            reused.status_code,
        ]
        note = client.post(
            f"{one}/messages", json={"kind": "note", "body": "Priced at 2k"}, headers=auth()
        )
        thread_now = note.json()
        result["messages"] = [[m["kind"], m["delivery"]] for m in thread_now["messages"]]
        result["emails"] = _emails(a.id)

        # Refusals: outbound on a hand-logged thread, an email to a contact
        # without an address, control characters, an unknown contact.
        other = client.post(
            f"{base}/conversations",
            json={**thread, "channel": "other", "kind": "note", "body": "Met at the fair"},
            headers=auth(),
        ).json()
        result["outbound_on_other"] = client.post(
            f"{base}/conversations/{other['id']}/messages",
            json={"kind": "outbound", "body": "Hi"},
            headers=auth(),
        ).json()
        no_email = client.post(
            f"{base}/conversations",
            json={**thread, "contact_id": nomail, "kind": "outbound"},
            headers=auth(),
        )
        result["no_email"] = [no_email.status_code, no_email.json()]
        result["control"] = client.post(
            f"{one}/messages", json={"kind": "note", "body": "a\x07b"}, headers=auth()
        ).status_code
        result["unknown_contact"] = client.post(
            f"{base}/conversations",
            json={**thread, "contact_id": str(uuid.uuid4())},
            headers=auth(),
        ).status_code
        result["after_refusals"] = len(_emails(a.id))

        # Assign, close, reopen by a new inbound message; stale versions.
        version = thread_now["version"]
        assigned = client.patch(
            one, json={"assignee_user_id": str(member_id)}, headers=auth(version=version)
        )
        result["assigned"] = [assigned.status_code, assigned.json().get("assignee_user_id")]
        result["stale"] = client.patch(
            one, json={"status": "closed"}, headers=auth(version=version)
        ).status_code
        result["outsider_assignee"] = client.patch(
            one, json={"assignee_user_id": str(b.owner_id)}, headers=auth(version=version + 1)
        ).status_code
        closed = client.patch(one, json={"status": "closed"}, headers=auth(version=version + 1))
        result["closed"] = closed.json().get("status")
        result["open_list_after_close"] = ids(f"{base}/conversations").count(conv["id"])
        result["closed_list"] = ids(f"{base}/conversations?status=closed").count(conv["id"])
        result["assigned_mine"] = len(
            ids(f"{base}/conversations?status=closed&assigned=mine", "member")
        )
        result["unassigned_closed"] = len(
            ids(f"{base}/conversations?status=closed&assigned=unassigned")
        )
        reopened = client.post(
            f"{one}/messages", json={"kind": "inbound", "body": "One more question"}, headers=auth()
        )
        result["reopened"] = reopened.json().get("status")
        result["by_contact"] = len(ids(f"{base}/conversations?contact_id={ada}"))

        # Roles and tenants.
        result["reader_read"] = client.get(one, headers=auth("reader")).status_code
        result["reader_mark_read"] = client.post(f"{one}/read", headers=auth("reader")).status_code
        result["reader_reply"] = client.post(
            f"{one}/messages", json={"kind": "note", "body": "x"}, headers=auth("reader")
        ).status_code
        result["reader_create"] = client.post(
            f"{base}/conversations", json=thread, headers=auth("reader")
        ).status_code
        result["reader_patch"] = client.patch(
            one, json={"status": "closed"}, headers=auth("reader", version=1)
        ).status_code
        result["other_owner_get"] = client.get(one, headers=auth("other_owner")).status_code
        b_one = f"/v1/workspaces/{b.id}/conversations/{conv['id']}"
        result["other_tenant_path"] = client.get(b_one, headers=auth("other_owner")).status_code
        result["other_tenant_reply"] = client.post(
            f"{b_one}/messages", json={"kind": "note", "body": "x"}, headers=auth("other_owner")
        ).status_code
        result["other_tenant_list"] = len(
            ids(f"/v1/workspaces/{b.id}/conversations", "other_owner")
        )
        result["outsider"] = client.get(
            f"{base}/conversations", headers=auth("outsider")
        ).status_code
        result["bad_status"] = client.get(
            f"{base}/conversations?status=spam", headers=auth()
        ).status_code

        # Deleting the contact keeps the thread, without its contact.
        result["contact_delete"] = client.delete(
            f"{base}/contacts/{ada}", headers=auth()
        ).status_code
        after = client.get(one, headers=auth()).json()
        result["after_contact_delete"] = [after["contact_id"], len(after["messages"])]

    print("RESULT " + json.dumps(result, default=str))


if __name__ == "__main__":
    main()

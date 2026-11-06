"""Drives in-app notifications (decision N-1) and prints one `RESULT <json>`
line. Run in a fresh interpreter by `tests/integration/test_notifications.py`.
Refuses to run unless ENVIRONMENT=test.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi.testclient import TestClient
from saas_os.core.identity import issue_session
from saas_os.infra.db import tenant_session_scope
from sqlalchemy import text

from crm_app.app import create_app
from crm_app.roles import Role
from tests.integration.opportunity_route_probe import _member
from tests.integration.workspace_route_probe import _new_workspace


def _rows(workspace: uuid.UUID) -> list[list[str | None]]:
    with tenant_session_scope(workspace) as session:
        return [
            [kind, str(user), None if actor is None else str(actor)]
            for kind, user, actor in session.execute(
                text(
                    "SELECT kind, user_id, actor_user_id FROM crm_app.member_notification"
                    " WHERE tenant_id = :t ORDER BY created_at, id"
                ),
                {"t": workspace},
            ).all()
        ]


def main() -> None:  # noqa: PLR0915 - one scenario script, read top to bottom
    if os.environ.get("ENVIRONMENT") != "test":
        raise SystemExit("notification_probe runs only with ENVIRONMENT=test")
    a = _new_workspace("notify-a")
    b = _new_workspace("notify-b")
    member_id, member = _member(a, Role.MEMBER)
    reader_id, reader = _member(a, Role.READ_ONLY)
    tokens = {
        "owner": issue_session(a.owner_id)[1],
        "member": member,
        "reader": reader,
        "other_owner": issue_session(b.owner_id)[1],
    }

    def auth(caller: str, version: int | None = None, key: str | None = None) -> dict[str, str]:
        headers = {"Authorization": f"Bearer {tokens[caller]}"}
        if version is not None:
            headers["If-Match"] = f'"{version}"'
        if key is not None:
            headers["Idempotency-Key"] = key
        return headers

    base = f"/v1/workspaces/{a.id}"
    mine = f"{base}/me/notifications"
    result: dict[str, Any] = {
        "owner": str(a.owner_id),
        "member": str(member_id),
        "reader": str(reader_id),
    }
    with TestClient(create_app(), follow_redirects=False) as client:

        def listed(caller: str, **params: Any) -> dict[str, Any]:
            answer = client.get(mine, params=params, headers=auth(caller))
            assert answer.status_code == 200, answer.text
            return answer.json()

        result["empty"] = listed("member")

        # --- Tasks: assigned by someone else, idempotent replays, self-assignment ----------
        task = {"title": "Call Ada back", "assignee_user_id": str(member_id)}
        first = client.post(f"{base}/tasks", json=task, headers=auth("owner", key="task-1"))
        replay = client.post(f"{base}/tasks", json=task, headers=auth("owner", key="task-1"))
        result["task_replayed"] = replay.headers.get("idempotent-replayed")
        made = first.json()
        own = client.post(
            f"{base}/tasks",
            json={"title": "Mine", "assignee_user_id": str(a.owner_id)},
            headers=auth("owner"),
        ).json()
        # Renaming without reassigning notifies nobody; reassigning does.
        renamed = client.patch(
            f"{base}/tasks/{made['id']}",
            json={"title": "Call Ada back today"},
            headers=auth("owner", made["version"]),
        ).json()
        client.patch(
            f"{base}/tasks/{own['id']}",
            json={"assignee_user_id": str(member_id)},
            headers=auth("member", own["version"]),
        )
        result["after_tasks"] = _rows(a.id)

        # --- Conversations and appointments -----------------------------------------------
        contact = client.post(
            f"{base}/contacts",
            json={"first_name": "Ada", "email": "ada@example.test"},
            headers=auth("owner"),
        ).json()
        conversation = client.post(
            f"{base}/conversations",
            json={
                "contact_id": contact["id"],
                "channel": "email",
                "subject": "Your quote",
                "kind": "inbound",
                "body": "Hi",
            },
            headers=auth("owner"),
        ).json()
        client.patch(
            f"{base}/conversations/{conversation['id']}",
            json={"assignee_user_id": str(member_id)},
            headers=auth("owner", conversation["version"]),
        )
        start = datetime.now(UTC).replace(microsecond=0) + timedelta(days=3)
        appointment = client.post(
            f"{base}/appointments",
            json={
                "title": "Intro",
                "starts_at": start.isoformat(),
                "ends_at": (start + timedelta(minutes=30)).isoformat(),
                "host_user_id": str(member_id),
            },
            headers=auth("owner"),
        ).json()
        # The member moves it to the owner: the owner hears of it.
        client.patch(
            f"{base}/appointments/{appointment['id']}",
            json={"host_user_id": str(a.owner_id)},
            headers=auth("member", appointment["version"]),
        )
        result["after_all"] = _rows(a.id)

        # --- Reading: own only, labels, paging --------------------------------------------
        page = listed("member")
        result["member_page"] = page
        result["owner_page"] = listed("owner")
        result["reader_page"] = listed("reader")
        result["labels_follow_renames"] = renamed["title"]
        first_page = listed("member", limit=1)
        second_page = listed("member", limit=1, cursor=first_page["next_cursor"])
        result["paging"] = [
            [i["id"] for i in first_page["items"]],
            [i["id"] for i in second_page["items"]],
            first_page["next_cursor"] is not None,
        ]
        result["bad_cursor"] = [
            client.get(mine, params={"cursor": "nonsense"}, headers=auth("member")).status_code,
            client.get(
                mine,
                params={"cursor": first_page["next_cursor"], "unread": "true"},
                headers=auth("member"),
            ).status_code,
            client.get(mine, params={"limit": 51}, headers=auth("member")).status_code,
            client.get(
                mine, params={"user_id": str(a.owner_id)}, headers=auth("member")
            ).status_code,
        ]

        # --- Marking read: own only ---------------------------------------------------------
        owner_item = result["owner_page"]["items"][0]["id"]
        member_items = [i["id"] for i in page["items"]]
        result["mark_others"] = [
            client.post(f"{mine}/{owner_item}/read", headers=auth("member")).status_code,
            client.post(f"{mine}/{uuid.uuid4()}/read", headers=auth("member")).status_code,
            client.post(f"{mine}/{member_items[0]}/read", headers=auth("other_owner")).status_code,
        ]
        result["mark_one"] = [
            client.post(f"{mine}/{member_items[0]}/read", headers=auth("member")).status_code,
            client.post(f"{mine}/{member_items[0]}/read", headers=auth("member")).status_code,
            listed("member")["unread"],
            len(listed("member", unread="true")["items"]),
            listed("owner")["unread"],
        ]
        marked = client.post(f"{mine}/read-all", headers=auth("member"))
        result["mark_all"] = [
            marked.status_code,
            marked.json(),
            listed("member")["unread"],
            listed("owner")["unread"],
            client.post(f"{mine}/read-all", headers=auth("member")).json(),
        ]

        # --- A deleted record shows as unavailable ------------------------------------------
        client.delete(f"{base}/tasks/{made['id']}", headers=auth("owner"))
        result["deleted_label"] = [
            i["subject_label"] for i in listed("member")["items"] if i["subject_id"] == made["id"]
        ]

        # --- Another workspace ---------------------------------------------------------------
        result["foreign"] = [
            client.get(mine, headers=auth("other_owner")).status_code,
            client.post(f"{mine}/read-all", headers=auth("other_owner")).status_code,
            client.get(
                f"/v1/workspaces/{b.id}/me/notifications", headers=auth("other_owner")
            ).json()["items"],
        ]

        # --- Retention: old rows go when a new one is written for the same member -------------
        with tenant_session_scope(a.id) as session:
            session.execute(
                text(
                    "INSERT INTO crm_app.member_notification"
                    " (tenant_id, id, user_id, kind, subject_type, subject_id, actor_user_id,"
                    "  created_at)"
                    " VALUES (:t, :id, :u, 'task_assigned', 'task', :s, NULL, :at)"
                ),
                {
                    "t": a.id,
                    "id": uuid.uuid4(),
                    "u": member_id,
                    "s": uuid.uuid4(),
                    "at": datetime.now(UTC) - timedelta(days=91),
                },
            )
        before = len(_rows(a.id))
        client.post(
            f"{base}/tasks",
            json={"title": "Another", "assignee_user_id": str(member_id)},
            headers=auth("owner"),
        )
        with tenant_session_scope(a.id) as session:
            result["retention"] = [
                before,
                len(_rows(a.id)),
                session.execute(
                    text(
                        "SELECT count(*) FROM crm_app.member_notification"
                        " WHERE tenant_id = :t AND created_at < now() - interval '90 days'"
                    ),
                    {"t": a.id},
                ).scalar_one(),
            ]
    result["rows_b"] = len(_rows(b.id))
    print("RESULT " + json.dumps(result, default=str))


if __name__ == "__main__":
    main()

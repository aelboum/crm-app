"""Drives the automation notify action of decision P8-N and prints one
`RESULT <json>` line.

Run in a fresh interpreter by `tests/integration/test_automation_notify.py`.
Runs are advanced by calling the job's function directly, as the worker
would. Seeds throwaway workspaces. Refuses to run unless ENVIRONMENT=test.
"""

from __future__ import annotations

import json
import os
import uuid
from typing import Any

from fastapi.testclient import TestClient
from saas_os.core.authority import UserCaller
from saas_os.core.identity import issue_session, suspend_membership
from saas_os.infra.db import tenant_session_scope
from sqlalchemy import text

from crm_app import automations
from crm_app.app import create_app
from crm_app.roles import Role
from tests.integration.opportunity_route_probe import _member
from tests.integration.workspace_route_probe import _new_workspace


def _q(workspace: uuid.UUID, sql: str, **values: object) -> list[dict[str, Any]]:
    with tenant_session_scope(workspace) as session:
        return [dict(r._mapping) for r in session.execute(text(sql), {"t": workspace, **values})]


def _notices(workspace: uuid.UUID, contact: str) -> list[dict[str, Any]]:
    return _q(
        workspace,
        "SELECT user_id, kind, subject_type, note, actor_user_id FROM crm_app.member_notification"
        " WHERE tenant_id = :t AND subject_id = :c ORDER BY note",
        c=contact,
    )


def _run(workspace: uuid.UUID, contact: str) -> uuid.UUID:
    rows = _q(
        workspace,
        "SELECT id FROM crm_app.automation_run WHERE tenant_id = :t AND contact_id = :c",
        c=contact,
    )
    return rows[0]["id"]


def _steps(workspace: uuid.UUID, run: uuid.UUID) -> list[list[Any]]:
    rows = _q(
        workspace,
        "SELECT position, action, outcome, detail FROM crm_app.automation_step"
        " WHERE tenant_id = :t AND run_id = :r ORDER BY position",
        r=run,
    )
    return [[r["position"], r["action"], r["outcome"], r["detail"]] for r in rows]


def main() -> None:  # noqa: PLR0915 - one scenario script, read top to bottom
    if os.environ.get("ENVIRONMENT") != "test":
        raise SystemExit("automation_notify_probe runs only with ENVIRONMENT=test")
    a = _new_workspace("notify-a")
    b = _new_workspace("notify-b")
    member_id, member = _member(a, Role.MEMBER)
    leaver_id, _ = _member(a, Role.MEMBER)
    outsider_id, _ = _member(b, Role.MEMBER)
    tokens = {"owner": issue_session(a.owner_id)[1], "member": member}

    def auth(caller: str = "owner", version: int | None = None) -> dict[str, str]:
        headers = {"Authorization": f"Bearer {tokens[caller]}"}
        if version is not None:
            headers["If-Match"] = f'"{version}"'
        return headers

    base = f"/v1/workspaces/{a.id}"
    result: dict[str, Any] = {}
    with TestClient(create_app(), follow_redirects=False) as client:

        def create(name: str, yes: list[dict[str, Any]]) -> Any:
            return client.post(
                f"{base}/automations",
                json={
                    "name": name,
                    "definition": {"trigger": {"type": "contact_created"}, "yes": yes},
                },
                headers=auth(),
            )

        def activate(made: Any) -> Any:
            body = made.json()
            return client.post(
                f"{base}/automations/{body['id']}/activate",
                headers=auth(version=body["version"]),
            )

        def pause(made: Any) -> None:
            current = client.get(f"{base}/automations/{made.json()['id']}", headers=auth()).json()
            client.post(
                f"{base}/automations/{current['id']}/pause",
                headers=auth(version=current["version"]),
            )

        def contact(name: str) -> dict[str, Any]:
            email = f"{name.lower()}.{uuid.uuid4().hex[:8]}@example.org"
            body = {
                "first_name": name,
                "last_name": "Lee",
                "email": email,
                "owner_user_id": str(a.owner_id),
            }
            made = client.post(f"{base}/contacts", json=body, headers=auth())
            assert made.status_code == 201, made.text
            return made.json()

        # --- Refused definitions ------------------------------------------------------
        outsider = [{"type": "notify_member", "message": "Hi", "recipient": str(outsider_id)}]
        result["refused"] = [
            create("Empty", [{"type": "notify_member", "message": " "}]).status_code,
            activate(create("Outsider", outsider)).json()["detail"]["code"],
        ]

        # --- The owner (the contact's owner) and a named member ----------------------
        notify = create(
            "Tell the team",
            [
                {"type": "notify_member", "message": "New lead, call today"},
                {"type": "notify_member", "message": "FYI", "recipient": str(member_id)},
            ],
        )
        result["stored"] = notify.json()["definition"]["yes"]
        result["activated"] = activate(notify).status_code
        ann = contact("Ann")
        run = _run(a.id, ann["id"])
        result["status"] = automations.advance(a.id, run)
        result["notices"] = [
            [str(n["user_id"]), n["kind"], n["subject_type"], n["note"], n["actor_user_id"]]
            for n in _notices(a.id, ann["id"])
        ]
        result["owner_id"], result["member_id"] = str(a.owner_id), str(member_id)
        # A retried job finds the steps done: nobody is notified twice.
        automations.advance(a.id, run)
        result["after_retry"] = len(_notices(a.id, ann["id"]))
        listed = client.get(f"{base}/me/notifications", headers=auth("member")).json()["items"]
        keys = ("kind", "subject_type", "subject_label", "note", "actor_user_id")
        result["listed"] = [
            {k: item[k] for k in keys} for item in listed if item["subject_id"] == ann["id"]
        ]

        # --- No owner: skipped with a code, nothing written --------------------------
        bob = contact("Bob")
        _q(
            a.id,
            "UPDATE crm_app.contact SET owner_user_id = NULL WHERE tenant_id = :t AND id = :c"
            " RETURNING id",
            c=bob["id"],
        )
        bob_run = _run(a.id, bob["id"])
        automations.advance(a.id, bob_run)
        result["no_owner"] = [
            _steps(a.id, bob_run),
            [n["note"] for n in _notices(a.id, bob["id"])],
        ]
        pause(notify)

        # --- A named member who left: skipped, nothing written -----------------------
        leaving = create(
            "Tell the leaver",
            [{"type": "notify_member", "message": "Bye", "recipient": str(leaver_id)}],
        )
        activate(leaving)
        cy = contact("Cy")
        cy_run = _run(a.id, cy["id"])
        membership = next(
            m
            for m in client.get(f"{base}/members?limit=50", headers=auth()).json()["items"]
            if m["user_id"] == str(leaver_id)
        )
        suspend_membership(
            a.id, uuid.UUID(membership["membership_id"]), caller=UserCaller(a.owner_id)
        )
        automations.advance(a.id, cy_run)
        result["member_gone"] = [_steps(a.id, cy_run), len(_notices(a.id, cy["id"]))]
    print("RESULT " + json.dumps(result, default=str))


if __name__ == "__main__":
    main()

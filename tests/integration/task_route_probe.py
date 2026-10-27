"""Drives the task routes against the integration database and prints one
`RESULT <json>` line.

Run in a fresh interpreter by `tests/integration/test_task_routes.py`.
Seeds throwaway workspaces with made-up records. Refuses to run unless
ENVIRONMENT=test.
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

_ARCHIVE = (
    "UPDATE crm_app.contact SET archived_at = now() WHERE tenant_id = :tenant AND id = :contact"
)


def _archive(workspace: uuid.UUID, contact: str) -> None:
    with tenant_session_scope(workspace) as session:
        session.execute(text(_ARCHIVE), {"tenant": workspace, "contact": contact})


def _iso(moment: datetime) -> str:
    return moment.isoformat()


def main() -> None:  # noqa: PLR0915 - one scenario script, read top to bottom
    if os.environ.get("ENVIRONMENT") != "test":
        raise SystemExit("task_route_probe runs only with ENVIRONMENT=test")
    a = _new_workspace("tasks-a")
    b = _new_workspace("tasks-b")
    member_id, member = _member(a, Role.MEMBER)
    _, admin = _member(a, Role.ADMIN)
    _, reader = _member(a, Role.READ_ONLY)
    tokens = {
        "owner": issue_session(a.owner_id)[1],
        "admin": admin,
        "member": member,
        "reader": reader,
        "other_owner": issue_session(b.owner_id)[1],
    }

    def auth(caller: str, version: int | None = None) -> dict[str, str]:
        headers = {"Authorization": f"Bearer {tokens[caller]}"}
        if version is not None:
            headers["If-Match"] = f'"{version}"'
        return headers

    base = f"/v1/workspaces/{a.id}/tasks"
    now = datetime.now(UTC)
    result: dict[str, Any] = {"workspace": str(a.id)}
    with TestClient(create_app(), follow_redirects=False) as client:
        contact = client.post(
            f"/v1/workspaces/{a.id}/contacts",
            json={"first_name": "Sam", "last_name": "Jansen", "email": "sam@example.test"},
            headers=auth("owner"),
        ).json()
        old = client.post(
            f"/v1/workspaces/{a.id}/contacts",
            json={"first_name": "Old", "email": "old@example.test"},
            headers=auth("owner"),
        ).json()
        _archive(a.id, old["id"])
        company = client.post(
            f"/v1/workspaces/{a.id}/companies", json={"name": "Acme"}, headers=auth("owner")
        ).json()
        deal = client.post(
            f"/v1/workspaces/{a.id}/opportunities",
            json={"title": "Website redesign"},
            headers=auth("owner"),
        ).json()
        foreign_contact = client.post(
            f"/v1/workspaces/{b.id}/contacts",
            json={"first_name": "Bo", "email": "bo@example.test"},
            headers=auth("other_owner"),
        ).json()
        foreign_deal = client.post(
            f"/v1/workspaces/{b.id}/opportunities",
            json={"title": "Theirs"},
            headers=auth("other_owner"),
        ).json()

        # --- Who may do what ----------------------------------------------------------
        result["read"] = {
            caller: client.get(base, headers=auth(caller)).status_code
            for caller in ("owner", "admin", "member", "reader", "other_owner")
        }
        result["create"] = {
            caller: client.post(
                base, json={"title": f"By {caller}"}, headers=auth(caller)
            ).status_code
            for caller in ("owner", "admin", "member", "reader", "other_owner")
        }

        # --- Create --------------------------------------------------------------------
        full = client.post(
            base,
            json={
                "title": "  Call Sam about the proposal ",
                "priority": "high",
                "due_at": _iso(now + timedelta(days=2)),
                "assignee_user_id": str(member_id),
                "contact_id": contact["id"],
                "company_id": company["id"],
                "opportunity_id": deal["id"],
            },
            headers=auth("member"),
        )
        task = full.json()
        result["created"] = [full.status_code, full.headers.get("etag"), task]
        result["references"] = {
            label: client.post(base, json={"title": "R", **body}, headers=auth("owner")).json()[
                "detail"
            ]
            for label, body in (
                ("foreign_contact", {"contact_id": foreign_contact["id"]}),
                ("archived_contact", {"contact_id": old["id"]}),
                ("foreign_deal", {"opportunity_id": foreign_deal["id"]}),
                ("unknown_company", {"company_id": str(uuid.uuid4())}),
                ("foreign_assignee", {"assignee_user_id": str(b.owner_id)}),
            )
        }
        result["invalid"] = {
            label: client.post(base, json=body, headers=auth("owner")).status_code
            for label, body in (
                ("missing_title", {}),
                ("blank_title", {"title": "  "}),
                ("long_title", {"title": "x" * 201}),
                ("naive_due", {"title": "T", "due_at": "2026-12-01T10:00:00"}),
                ("bad_priority", {"title": "T", "priority": "urgent"}),
                ("done_on_create", {"title": "T", "done": True}),
            )
        }
        key = {"Idempotency-Key": "task-create-0001"}
        first = client.post(base, json={"title": "Once"}, headers={**auth("owner"), **key})
        again = client.post(base, json={"title": "Once"}, headers={**auth("owner"), **key})
        result["idempotent"] = [
            first.status_code,
            again.headers.get("idempotent-replayed"),
            first.json()["id"] == again.json()["id"],
        ]

        # --- Update, complete, reopen -------------------------------------------------
        item = f"{base}/{task['id']}"
        result["no_version"] = client.patch(
            item, json={"title": "X"}, headers=auth("member")
        ).status_code
        stale = client.patch(item, json={"title": "X"}, headers=auth("member", 9))
        result["stale"] = [stale.status_code, stale.json()["detail"]]
        result["reader_update"] = client.patch(
            item, json={"done": True}, headers=auth("reader", 1)
        ).status_code
        done = client.patch(item, json={"done": True}, headers=auth("member", 1)).json()
        again_done = client.patch(item, json={"done": True}, headers=auth("member", 2)).json()
        reopened = client.patch(
            item, json={"done": False, "priority": "low"}, headers=auth("admin", 2)
        ).json()
        result["lifecycle"] = [
            [
                done["done"],
                done["completed_at"] is not None,
                done["completed_by_user_id"] == str(member_id),
                done["version"],
            ],
            again_done["version"],
            [reopened["done"], reopened["completed_at"], reopened["priority"], reopened["version"]],
        ]
        result["update_invalid"] = {
            label: client.patch(item, json=body, headers=auth("owner", 3)).status_code
            for label, body in (
                ("null_title", {"title": None}),
                ("null_done", {"done": None}),
                ("string_done", {"done": "yes"}),
                ("null_priority", {"priority": None}),
            )
        }
        cleared = client.patch(
            item,
            json={"due_at": None, "contact_id": None, "assignee_user_id": None},
            headers=auth("owner", 3),
        ).json()
        result["cleared"] = [
            cleared["due_at"],
            cleared["contact"],
            cleared["assignee_user_id"],
            cleared["version"],
        ]

        # --- Lists, filters, counts ------------------------------------------------------
        for title, due, assignee in (
            ("Overdue call", now - timedelta(days=1), str(member_id)),
            ("Today email", now + timedelta(hours=1), None),
            ("Next week demo", now + timedelta(days=7), str(member_id)),
        ):
            body: dict[str, Any] = {"title": title, "due_at": _iso(due)}
            if assignee:
                body["assignee_user_id"] = assignee
            client.post(base, json=body, headers=auth("owner"))
        finished = client.post(base, json={"title": "Done already"}, headers=auth("owner")).json()
        client.patch(f"{base}/{finished['id']}", json={"done": True}, headers=auth("owner", 1))

        def titles(**params: Any) -> list[str]:
            response = client.get(base, params={"limit": 200, **params}, headers=auth("owner"))
            return [t["title"] for t in response.json()["items"]]

        result["filters"] = {
            "overdue": titles(overdue="true"),
            "window": titles(due_from=_iso(now), due_to=_iso(now + timedelta(days=3))),
            "done": titles(status="done"),
            "assignee": sorted(titles(assignee=str(member_id))),
            "contact_none": titles(contact_id=contact["id"]),
            "deal": titles(opportunity_id=deal["id"]),
            "due_order": titles()[:4],
        }
        result["counts"] = client.get(f"{base}/counts", headers=auth("member")).json()
        result["counts_assignee"] = client.get(
            f"{base}/counts", params={"assignee": str(member_id)}, headers=auth("owner")
        ).json()
        seen: list[str] = []
        cursor = None
        while True:
            params: dict[str, Any] = {"limit": 2, "status": "all"}
            if cursor:
                params["cursor"] = cursor
            page = client.get(base, params=params, headers=auth("owner")).json()
            seen += [t["id"] for t in page["items"]]
            cursor = page["next_cursor"]
            if not cursor:
                break
        total = client.get(base, params={"status": "all"}, headers=auth("owner")).json()["total"]
        result["paging"] = [len(seen), len(set(seen)), total]
        result["bad_cursor"] = client.get(
            base, params={"cursor": "x"}, headers=auth("owner")
        ).status_code
        result["naive_window"] = client.get(
            base, params={"due_from": "2026-10-27T00:00:00"}, headers=auth("owner")
        ).status_code

        # --- Another workspace -----------------------------------------------------------
        theirs = client.post(
            f"/v1/workspaces/{b.id}/tasks", json={"title": "Secret"}, headers=auth("other_owner")
        ).json()
        mine_path = f"{base}/{theirs['id']}"
        result["foreign"] = {
            "get": client.get(mine_path, headers=auth("owner")).json(),
            "patch": client.patch(
                mine_path, json={"done": True}, headers=auth("owner", 1)
            ).status_code,
            "delete": client.delete(mine_path, headers=auth("owner")).status_code,
            "listed": "Secret"
            in client.get(base, params={"status": "all"}, headers=auth("owner")).text,
        }

        # --- Delete (Members may, Q6) --------------------------------------------------
        result["delete"] = {
            "reader": client.delete(item, headers=auth("reader")).status_code,
            "member": client.delete(item, headers=auth("member")).status_code,
            "again": client.delete(item, headers=auth("member")).status_code,
        }
        result["task_id"] = task["id"]

    print("RESULT " + json.dumps(result, default=str))


if __name__ == "__main__":
    main()

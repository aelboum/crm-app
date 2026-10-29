"""Changes contacts and companies through the routes, reads their history
as different callers and prints one `RESULT <json>` line.

Run in a fresh interpreter by `tests/integration/test_history.py` (SaaS-OS
caches configuration per process). Workspaces and members are created as in
`record_route_probe`. All values are made up. Refuses to run unless
ENVIRONMENT=test.
"""

from __future__ import annotations

import json
import os
import secrets
import uuid
from typing import Any

from fastapi.testclient import TestClient
from saas_os.core.authority import UserCaller
from saas_os.core.identity import add_tenant_membership, issue_session
from saas_os.core.rbac import assign_role

from crm_app.app import create_app
from crm_app.roles import Role
from tests.integration.workspace_route_probe import PROVISIONING, _new_user, _new_workspace

# Values that must never appear in a history response (D5).
LEAK_CITY = "Leakcity-4b1d"
LEAK_EMAIL = "leak.history.9c2e@example.test"
# A note's text, which the workspace feed must not carry (P4-D 4).
FEED_NOTE = "Feednote-7a3e private remark"


def _email() -> str:
    return f"person.{secrets.token_hex(6)}@example.test"


def main() -> None:  # noqa: PLR0915 - one scenario script, read top to bottom
    if os.environ.get("ENVIRONMENT") != "test":
        raise SystemExit("history_probe runs only with ENVIRONMENT=test")
    a = _new_workspace("history-a")
    b = _new_workspace("history-b")
    users: dict[str, uuid.UUID] = {"owner": a.owner_id, "other_owner": b.owner_id}
    for role in (Role.MEMBER, Role.READ_ONLY):
        user = _new_user()
        membership = add_tenant_membership(a.id, user, caller=PROVISIONING)
        assign_role(a.id, membership.id, a.role_ids[role], caller=UserCaller(a.owner_id))
        users[role.value] = user
    users["outsider"] = _new_user()
    tokens = {name: issue_session(user)[1] for name, user in users.items()}

    def auth(caller: str | None) -> dict[str, str]:
        return {"Authorization": f"Bearer {tokens[caller]}"} if caller else {}

    base = f"/v1/workspaces/{a.id}"
    other = f"/v1/workspaces/{b.id}"
    result: dict[str, Any] = {
        "owner": str(a.owner_id),
        "member": str(users[Role.MEMBER.value]),
    }

    with TestClient(create_app(), follow_redirects=False) as client:

        def post(path: str, body: object, caller: str = "owner") -> Any:
            return client.post(path, json=body, headers=auth(caller))

        def patch(path: str, body: object, version: int, caller: str = "owner") -> Any:
            return client.patch(
                path, json=body, headers={**auth(caller), "If-Match": f'"{version}"'}
            )

        def history(path: str, caller: str | None = "owner", **params: object) -> Any:
            return client.get(f"{path}/activity", params=params, headers=auth(caller))

        # --- Every contact change writes its entries -------------------------------
        first = post(f"{base}/companies", {"name": "First BV"}).json()
        second = post(f"{base}/companies", {"name": "Second BV"}).json()
        contact = post(
            f"{base}/contacts",
            {"first_name": "Hist", "email": _email(), "company_id": first["id"]},
        ).json()
        item = f"{base}/contacts/{contact['id']}"
        version = 1
        steps: list[dict[str, object]] = [
            {"city": LEAK_CITY, "email": LEAK_EMAIL},  # updated: city, email
            {"lifecycle_stage": "customer"},  # stage_changed
            {"owner_user_id": result["member"]},  # owner_changed
            {"company_id": second["id"]},  # company_unlinked + company_linked
            {"company_id": None, "job_title": "Buyer"},  # updated + company_unlinked
            {"job_title": "Buyer"},  # no change: no entry
        ]
        statuses = []
        for body in steps:
            response = patch(item, body, version)
            statuses.append(response.status_code)
            version = response.json()["version"]
        statuses.append(post(f"{item}/archive", None).status_code)
        statuses.append(post(f"{item}/restore", None).status_code)
        result["contact_steps"] = statuses
        page = history(item, "Read-only", limit=100)
        result["contact_history_status"] = page.status_code
        result["contact_history"] = page.json()["items"]
        result["contact_history_text"] = page.text
        result["companies"] = {"first": first["id"], "second": second["id"]}

        # A refused change writes no entry: a duplicate email rolls back.
        taken = post(f"{base}/contacts", {"first_name": "Taken", "email": _email()}).json()
        refused = patch(item, {"email": taken["email"], "city": "Elsewhere"}, version)
        result["refused"] = [refused.status_code, len(history(item, limit=100).json()["items"])]

        # --- Company changes, and a deleted company unlinking its contacts --------
        doomed = post(f"{base}/companies", {"name": "Doomed BV"}).json()
        company_item = f"{base}/companies/{doomed['id']}"
        patch(company_item, {"name": "Doomed Ltd", "industry": "Retail"}, 1)
        post(f"{company_item}/archive", None)
        post(f"{company_item}/restore", None)
        result["company_history"] = history(company_item, limit=100).json()["items"]
        linked = post(
            f"{base}/contacts",
            {"first_name": "Linked", "email": _email(), "company_id": doomed["id"]},
        ).json()
        result["company_deleted"] = client.delete(company_item, headers=auth("owner")).status_code
        linked_history = history(f"{base}/contacts/{linked['id']}", limit=100).json()["items"]
        result["unlinked_by_delete"] = linked_history
        result["deleted_company_history"] = history(company_item).status_code
        result["doomed"] = doomed["id"]

        # --- Paging --------------------------------------------------------------------
        pages: list[list[str]] = []
        cursor: str | None = None
        while True:
            response = (
                history(item, limit=2, cursor=cursor) if cursor else history(item, limit=2)
            ).json()
            pages.append([entry["id"] for entry in response["items"]])
            cursor = response["next_cursor"]
            if not cursor:
                break
        result["pages"] = pages
        first_page = history(item, limit=2).json()
        result["cursor_other_record"] = history(
            f"{base}/contacts/{linked['id']}", cursor=first_page["next_cursor"]
        ).status_code
        result["cursor_garbage"] = history(item, cursor="not-a-cursor").status_code
        result["limit_too_high"] = history(item, limit=101).status_code
        result["unknown_param"] = history(item, sort="kind").status_code

        # --- The workspace's feed (P4-D 4) ----------------------------------------------
        note = post(f"{item}/notes", {"body": FEED_NOTE})
        post(f"{other}/contacts", {"first_name": "Elsewhere", "email": _email()}, "other_owner")

        def feed(caller: str | None = "owner", **params: object) -> Any:
            return client.get(f"{base}/activity", params=params, headers=auth(caller))

        response = feed(Role.READ_ONLY.value, limit=20)
        result["feed_status"] = [note.status_code, response.status_code]
        result["feed"] = response.json()["items"]
        result["feed_text"] = response.text
        result["feed_default"] = len(feed().json()["items"])
        result["contact"] = contact["id"]
        result["feed_records"] = {
            "contacts": [contact["id"], taken["id"], linked["id"]],
            "companies": [first["id"], second["id"], doomed["id"]],
        }
        result["feed_access"] = {
            "member": feed(Role.MEMBER.value).status_code,
            "outsider": feed("outsider").status_code,
            "other_owner": feed("other_owner").status_code,
            "anonymous": feed(None).status_code,
            "limit_zero": feed(limit=0).status_code,
            "limit_too_high": feed(limit=21).status_code,
            "unknown_param": feed(cursor="x").status_code,
        }
        result["other_feed"] = [
            e["record_name"]
            for e in client.get(f"{other}/activity", headers=auth("other_owner")).json()["items"]
        ]

        # --- Who may read it ---------------------------------------------------------
        foreign = f"{other}/contacts/{contact['id']}"
        result["access"] = {
            "member": history(item, Role.MEMBER.value).status_code,
            "read_only": history(item, Role.READ_ONLY.value).status_code,
            "outsider": history(item, "outsider").status_code,
            "other_owner": history(item, "other_owner").status_code,
            "anonymous": history(item, None).status_code,
            "foreign_path": history(foreign, "other_owner").status_code,
            "unknown_record": history(f"{base}/contacts/{uuid.uuid4()}").status_code,
            "company_path_for_contact": history(f"{base}/companies/{contact['id']}").status_code,
        }

    print("RESULT " + json.dumps(result, default=str))


if __name__ == "__main__":
    main()

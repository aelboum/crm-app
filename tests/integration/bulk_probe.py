"""Drives bulk actions on contacts (decision P3-BK) and prints one
`RESULT <json>` line.

Run in a fresh interpreter by `tests/integration/test_bulk_actions.py`.
Seeds throwaway workspaces. Refuses to run unless ENVIRONMENT=test.
"""

from __future__ import annotations

import json
import os
import uuid
from typing import Any

from fastapi.testclient import TestClient
from saas_os.core.identity import issue_session
from saas_os.infra.db import tenant_session_scope
from sqlalchemy import text

from crm_app.app import create_app
from crm_app.roles import Role
from tests.integration.opportunity_route_probe import _member
from tests.integration.workspace_route_probe import _new_workspace


def _q(workspace: uuid.UUID, sql: str, **values: object) -> list[dict[str, Any]]:
    with tenant_session_scope(workspace) as session:
        return [dict(r._mapping) for r in session.execute(text(sql), {"t": workspace, **values})]


def main() -> None:
    if os.environ.get("ENVIRONMENT") != "test":
        raise SystemExit("bulk_probe runs only with ENVIRONMENT=test")
    a = _new_workspace("bulk-a")
    b = _new_workspace("bulk-b")
    member_id, member = _member(a, Role.MEMBER)
    _, reader = _member(a, Role.READ_ONLY)
    tokens = {
        "owner": issue_session(a.owner_id)[1],
        "member": member,
        "reader": reader,
        "other": issue_session(b.owner_id)[1],
    }

    def auth(caller: str = "owner") -> dict[str, str]:
        return {"Authorization": f"Bearer {tokens[caller]}"}

    base = f"/v1/workspaces/{a.id}"
    result: dict[str, Any] = {}
    with TestClient(create_app(), follow_redirects=False) as client:

        def contact(name: str, where: str = base, caller: str = "owner") -> str:
            made = client.post(
                f"{where}/contacts",
                json={"first_name": name, "email": f"{name}.{uuid.uuid4().hex[:6]}@example.org"},
                headers=auth(caller),
            )
            assert made.status_code == 201, made.text
            return str(made.json()["id"])

        def bulk(body: dict[str, Any], caller: str = "member") -> Any:
            return client.post(f"{base}/contacts/bulk", json=body, headers=auth(caller))

        ids = [contact(name) for name in ("ann", "bob", "cy")]
        foreign = contact("dee", f"/v1/workspaces/{b.id}", "other")
        tag = client.post(f"{base}/tags", json={"name": "Hot"}, headers=auth()).json()["id"]
        missing = str(uuid.uuid4())

        def owners() -> list[str]:
            rows = _q(
                a.id,
                "SELECT owner_user_id FROM crm_app.contact WHERE tenant_id = :t"
                " AND id = ANY(CAST(:ids AS uuid[]))",
                ids=ids,
            )
            return [str(r["owner_user_id"]) for r in rows]

        # --- Assign: done, then unchanged; unknown and foreign ids skipped ------------
        first = bulk(
            {
                "contact_ids": [*ids, missing, foreign],
                "action": "assign_owner",
                "owner_user_id": str(member_id),
            }
        )
        assert first.status_code == 200, first.text
        result["assigned"] = first.json()
        result["missing"], result["foreign"] = missing, foreign
        result["owners"] = owners() == [str(member_id)] * 3
        result["again"] = bulk(
            {"contact_ids": ids, "action": "assign_owner", "owner_user_id": str(member_id)}
        ).json()
        result["foreign_untouched"] = _q(
            b.id,
            "SELECT owner_user_id FROM crm_app.contact WHERE tenant_id = :t AND id = :c",
            c=foreign,
        )[0]["owner_user_id"]

        # --- Tags, stage, archive and restore ---------------------------------------------
        result["tagged"] = [
            bulk({"contact_ids": ids, "action": "add_tag", "tag_id": tag}).json()["done"],
            bulk({"contact_ids": ids, "action": "add_tag", "tag_id": tag}).json()["unchanged"],
            bulk({"contact_ids": ids, "action": "remove_tag", "tag_id": tag}).json()["done"],
        ]
        result["staged"] = bulk(
            {"contact_ids": ids, "action": "set_stage", "stage": "customer"}
        ).json()["done"]
        archived = bulk({"contact_ids": ids[:2], "action": "archive"}).json()["done"]
        archived_now = len(
            _q(
                a.id,
                "SELECT id FROM crm_app.contact WHERE tenant_id = :t AND archived_at IS NOT NULL",
            )
        )
        restored = bulk({"contact_ids": ids[:2], "action": "restore"}).json()["done"]
        result["archived"] = [archived, archived_now, restored]

        # --- Each contact recorded as its own change -----------------------------------------
        result["history"] = _q(
            a.id,
            "SELECT count(*) AS n FROM crm_app.activity WHERE tenant_id = :t AND contact_id = :c",
            c=ids[0],
        )[0]["n"]
        result["audit"] = _q(
            a.id,
            "SELECT count(*) AS n FROM core.audit_log WHERE tenant_id = :t"
            " AND resource_id = :c AND action = 'crm_app.contact.updated'",
            c=ids[0],
        )[0]["n"]

        # --- Refusals -------------------------------------------------------------------------
        def detail(body: dict[str, Any]) -> Any:
            return bulk(body).json()["detail"]

        result["refused"] = {
            "outsider_owner": detail(
                {"contact_ids": ids, "action": "assign_owner", "owner_user_id": str(b.owner_id)}
            ),
            "bad_stage": detail({"contact_ids": ids, "action": "set_stage", "stage": "vip"}),
            "no_tag": detail({"contact_ids": ids, "action": "add_tag"}),
            "too_many": bulk(
                {"contact_ids": [str(uuid.uuid4()) for _ in range(101)], "action": "archive"}
            ).status_code,
            "empty": bulk({"contact_ids": [], "action": "archive"}).status_code,
            "reader": bulk({"contact_ids": ids, "action": "archive"}, "reader").status_code,
            "unknown_action": bulk({"contact_ids": ids, "action": "delete"}).status_code,
        }
    print("RESULT " + json.dumps(result, default=str))


if __name__ == "__main__":
    main()

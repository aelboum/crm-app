"""Drives round-robin assignment (decision P8-R) and prints one `RESULT
<json>` line. Run by `tests/integration/test_round_robin.py`. Seeds a
throwaway workspace. Refuses to run unless ENVIRONMENT=test.
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


def main() -> None:
    if os.environ.get("ENVIRONMENT") != "test":
        raise SystemExit("round_robin_probe runs only with ENVIRONMENT=test")
    a = _new_workspace("rr-a")
    first, _ = _member(a, Role.MEMBER)
    second, _ = _member(a, Role.MEMBER)
    headers = {"Authorization": f"Bearer {issue_session(a.owner_id)[1]}"}
    base = f"/v1/workspaces/{a.id}"
    result: dict[str, Any] = {}
    with TestClient(create_app(), follow_redirects=False) as client:

        def automation(name: str, users: list[str]) -> Any:
            step = {"type": "assign_round_robin", "user_ids": users}
            body = {
                "name": name,
                "definition": {"trigger": {"type": "contact_created"}, "yes": [step]},
            }
            return client.post(f"{base}/automations", json=body, headers=headers)

        made = automation("Spread leads", [str(first), str(second)]).json()
        result["one_member"] = automation("Too few", [str(first)]).status_code
        client.post(
            f"{base}/automations/{made['id']}/activate",
            headers={**headers, "If-Match": f'"{made["version"]}"'},
        )

        def contact(name: str) -> str:
            body = {"first_name": name, "email": f"{name}.{uuid.uuid4().hex[:6]}@example.org"}
            cid = client.post(f"{base}/contacts", json=body, headers=headers).json()["id"]
            sql = "SELECT id FROM crm_app.automation_run WHERE tenant_id = :t AND contact_id = :c"
            run = _q(a.id, sql, c=cid)[0]["id"]
            automations.advance(a.id, run)
            automations.advance(a.id, run)  # a retried job changes nothing
            sql = "SELECT owner_user_id FROM crm_app.contact WHERE tenant_id = :t AND id = :c"
            return str(_q(a.id, sql, c=cid)[0]["owner_user_id"])

        result["owners"] = [contact(n) for n in ("ann", "bob", "cy")]
        result["ids"] = [str(first), str(second)]
        members = client.get(f"{base}/members?limit=50", headers=headers).json()["items"]
        membership = next(m for m in members if m["user_id"] == str(first))
        suspend_membership(
            a.id, uuid.UUID(membership["membership_id"]), caller=UserCaller(a.owner_id)
        )
        result["after_leaving"] = [contact(n) for n in ("dee", "eve")]
    print("RESULT " + json.dumps(result, default=str))


if __name__ == "__main__":
    main()

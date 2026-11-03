"""Drives member display names (decision M-P1) and prints one `RESULT <json>`
line. Run in a fresh interpreter by `tests/integration/test_member_profiles.py`.
Refuses to run unless ENVIRONMENT=test.
"""

from __future__ import annotations

import json
import os
from typing import Any

from fastapi.testclient import TestClient
from saas_os.core.identity import issue_session
from saas_os.infra.db import tenant_session_scope
from sqlalchemy import text

from crm_app.app import create_app
from crm_app.roles import Role
from tests.integration.opportunity_route_probe import _member
from tests.integration.workspace_route_probe import _new_workspace


def main() -> None:
    if os.environ.get("ENVIRONMENT") != "test":
        raise SystemExit("member_profile_probe runs only with ENVIRONMENT=test")
    a = _new_workspace("profiles-a")
    b = _new_workspace("profiles-b")
    reader_id, reader = _member(a, Role.READ_ONLY)
    owner = issue_session(a.owner_id)[1]
    other_owner = issue_session(b.owner_id)[1]

    def auth(token: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {token}"}

    profile = f"/v1/workspaces/{a.id}/me/profile"
    result: dict[str, Any] = {}
    with TestClient(create_app(), follow_redirects=False) as client:
        result["empty"] = client.get(profile, headers=auth(owner)).json()["display_name"]
        set_owner = client.put(
            profile, json={"display_name": "  Anna   de Vries "}, headers=auth(owner)
        )
        result["set_owner"] = [set_owner.status_code, set_owner.json()]
        # A read-only member may set their own name too.
        set_reader = client.put(profile, json={"display_name": "Bram"}, headers=auth(reader))
        result["set_reader"] = [set_reader.status_code, set_reader.json()["display_name"]]
        listed = client.get(f"/v1/workspaces/{a.id}/members", headers=auth(owner)).json()
        result["listed"] = sorted(
            [str(m["user_id"]) == str(a.owner_id), m["display_name"]] for m in listed["items"]
        )
        result["refused"] = {
            label: client.put(profile, json=body, headers=auth(owner)).status_code
            for label, body in (
                ("too_long", {"display_name": "x" * 81}),
                ("control", {"display_name": "Anna\u200bde"}),
                ("newline", {"display_name": "Anna\nde"}),
                ("extra_field", {"display_name": "Anna", "user_id": str(reader_id)}),
                ("not_text", {"display_name": 5}),
            )
        }
        # Another workspace's owner: not a member of A, and A's names stay in A.
        result["foreign"] = [
            client.get(profile, headers=auth(other_owner)).status_code,
            client.put(profile, json={"display_name": "X"}, headers=auth(other_owner)).status_code,
            client.get(f"/v1/workspaces/{b.id}/me/profile", headers=auth(other_owner)).json()[
                "display_name"
            ],
        ]
        cleared = client.put(profile, json={"display_name": "  "}, headers=auth(reader))
        result["cleared"] = [cleared.status_code, cleared.json()["display_name"]]
        result["unchanged_owner"] = client.get(profile, headers=auth(owner)).json()["display_name"]
    with tenant_session_scope(a.id) as session:
        audits = session.execute(
            text(
                "SELECT action, metadata::text FROM core.audit_log"
                " WHERE tenant_id = :t AND resource_type = 'crm_app.member_profile'"
                " ORDER BY created_at"
            ),
            {"t": a.id},
        ).all()
        result["audits"] = [[action, "Anna" in meta or "Bram" in meta] for action, meta in audits]
        result["rows"] = session.execute(
            text("SELECT count(*) FROM crm_app.member_profile WHERE tenant_id = :t"), {"t": a.id}
        ).scalar_one()
    with tenant_session_scope(b.id) as session:
        result["rows_b"] = session.execute(
            text("SELECT count(*) FROM crm_app.member_profile WHERE tenant_id = :t"), {"t": b.id}
        ).scalar_one()
    result["ids"] = [str(a.owner_id), str(reader_id)]
    print("RESULT " + json.dumps(result, default=str))


if __name__ == "__main__":
    main()

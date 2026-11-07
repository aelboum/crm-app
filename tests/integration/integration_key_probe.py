"""Drives integrations and their API keys (decision P12-K) and prints one
`RESULT <json>` line.

Run in a fresh interpreter by `tests/integration/test_integrations.py`.
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


def _audit(workspace: uuid.UUID, resource_id: str) -> list[list[Any]]:
    with tenant_session_scope(workspace) as session:
        rows = session.execute(
            text(
                "SELECT action, actor_type, actor_user_id IS NULL AS no_user,"
                " actor_service_account_id FROM core.audit_log"
                " WHERE tenant_id = :t AND resource_id = :r ORDER BY created_at"
            ),
            {"t": workspace, "r": resource_id},
        )
        return [[r.action, r.actor_type, r.no_user, str(r.actor_service_account_id)] for r in rows]


def main() -> None:  # noqa: PLR0915 - one scenario script, read top to bottom
    if os.environ.get("ENVIRONMENT") != "test":
        raise SystemExit("integration_key_probe runs only with ENVIRONMENT=test")
    a = _new_workspace("keys-a")
    b = _new_workspace("keys-b")
    _, admin = _member(a, Role.ADMIN)
    _, member = _member(a, Role.MEMBER)
    tokens = {"owner": issue_session(a.owner_id)[1], "admin": admin, "member": member}

    def auth(caller: str = "owner") -> dict[str, str]:
        return {"Authorization": f"Bearer {tokens[caller]}"}

    def key(secret: str, version: int | None = None) -> dict[str, str]:
        headers = {"X-API-Key": secret}
        if version is not None:
            headers["If-Match"] = f'"{version}"'
        return headers

    base = f"/v1/workspaces/{a.id}"
    result: dict[str, Any] = {}
    with TestClient(create_app(), follow_redirects=False) as client:

        def integration(name: str, role: str, caller: str = "owner") -> Any:
            return client.post(
                f"{base}/integrations", json={"name": name, "role": role}, headers=auth(caller)
            )

        def issue(integration_id: str, name: str = "Main", caller: str = "owner") -> Any:
            return client.post(
                f"{base}/integrations/{integration_id}/keys",
                json={"name": name, "expires_in_days": 90},
                headers=auth(caller),
            )

        # --- Who may manage, and what may be asked for ------------------------------
        zap = integration("Zapier", "Member")
        assert zap.status_code == 201, zap.text
        result["created"] = [zap.status_code, zap.json()["role"], zap.json()["keys"]]
        result["by_admin"] = integration("Sheets", "Read-only", "admin").status_code
        result["by_member"] = integration("Nope", "Member", "member").status_code
        result["refused_roles"] = [
            integration("Too much", role).status_code for role in ("Admin", "Owner")
        ]
        result["duplicate"] = integration("Zapier", "Member").json()["detail"]["code"]

        # --- A key: shown once, never listed -----------------------------------------
        issued = issue(zap.json()["id"])
        assert issued.status_code == 201, issued.text
        secret = issued.json()["secret"]
        result["issued"] = [issued.status_code, issued.headers.get("cache-control"), len(secret)]
        listed = client.get(f"{base}/integrations", headers=auth()).text
        result["secret_listed"] = secret in listed

        # --- What the key may do ----------------------------------------------------
        made = client.post(
            f"{base}/contacts",
            json={"first_name": "Via", "email": f"via.{uuid.uuid4().hex[:6]}@example.org"},
            headers=key(secret),
        )
        assert made.status_code == 201, made.text
        contact = made.json()
        changed = client.patch(
            f"{base}/contacts/{contact['id']}",
            json={"job_title": "Buyer"},
            headers=key(secret, contact["version"]),
        )
        task = client.post(
            f"{base}/tasks",
            json={"title": "Call Via", "contact_id": contact["id"]},
            headers=key(secret),
        )
        result["allowed"] = [
            made.status_code,
            client.get(f"{base}/contacts", headers=key(secret)).status_code,
            changed.status_code,
            client.get(f"{base}/opportunities", headers=key(secret)).status_code,
            task.status_code,
            client.get(f"{base}/companies", headers=key(secret)).status_code,
        ]
        result["audit"] = _audit(a.id, contact["id"])
        result["integration_id"] = zap.json()["id"]

        # --- What the key may never do ------------------------------------------------
        current = client.get(f"{base}/contacts/{contact['id']}", headers=key(secret)).json()
        result["refused"] = {
            "delete": client.delete(
                f"{base}/contacts/{contact['id']}", headers=key(secret, current["version"])
            ).status_code,
            "integrations": client.get(f"{base}/integrations", headers=key(secret)).status_code,
            "members": client.get(f"{base}/members?limit=5", headers=key(secret)).status_code,
            "automations": client.get(f"{base}/automations", headers=key(secret)).status_code,
            "other_workspace": client.get(
                f"/v1/workspaces/{b.id}/contacts", headers=key(secret)
            ).status_code,
            "with_a_session": client.get(
                f"{base}/contacts", headers={**key(secret), **auth()}
            ).status_code,
            "bad_key": client.get(f"{base}/contacts", headers=key(secret + "x")).status_code,
        }

        # --- A Read-only integration reads, never writes -------------------------------
        reader = integration("Reader", "Read-only")
        reader_secret = issue(reader.json()["id"]).json()["secret"]
        result["read_only"] = [
            client.get(f"{base}/contacts", headers=key(reader_secret)).status_code,
            client.post(
                f"{base}/contacts",
                json={"first_name": "No", "phone": "+31 6 1111 2222"},
                headers=key(reader_secret),
            ).status_code,
        ]

        # --- Limits, revocation and disabling --------------------------------------------
        second = issue(zap.json()["id"], "Spare")
        result["third_key"] = issue(zap.json()["id"], "Extra").status_code
        revoked = client.post(
            f"{base}/integrations/{zap.json()['id']}/keys/{issued.json()['key']['id']}/revoke",
            headers=auth(),
        )
        result["revoked"] = [
            revoked.status_code,
            client.get(f"{base}/contacts", headers=key(secret)).status_code,
            client.get(f"{base}/contacts", headers=key(second.json()["secret"])).status_code,
        ]
        disabled = client.post(f"{base}/integrations/{zap.json()['id']}/disable", headers=auth())
        result["disabled"] = [
            disabled.status_code,
            disabled.json()["status"],
            all(k["revoked_at"] for k in disabled.json()["keys"]),
            client.get(f"{base}/contacts", headers=key(second.json()["secret"])).status_code,
            issue(zap.json()["id"], "After").status_code,
        ]
        result["other_workspace_integration"] = client.post(
            f"/v1/workspaces/{b.id}/integrations/{zap.json()['id']}/disable",
            headers={"Authorization": f"Bearer {issue_session(b.owner_id)[1]}"},
        ).status_code
    print("RESULT " + json.dumps(result, default=str))


if __name__ == "__main__":
    main()

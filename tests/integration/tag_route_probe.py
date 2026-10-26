"""Drives the tag vocabulary routes against the integration database and
prints one `RESULT <json>` line.

Run in a fresh interpreter by `tests/integration/test_tag_routes.py`.
Seeds made-up tags and records into throwaway workspaces. Refuses to run
unless ENVIRONMENT=test.
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
from tests.integration.contact_export_probe import _member
from tests.integration.workspace_route_probe import _new_workspace


def _sql(workspace: uuid.UUID, statement: str, **params: object) -> list[Any]:
    with tenant_session_scope(workspace) as session:
        result = session.execute(text(statement), {"tenant": workspace, **params})
        return list(result.all()) if statement.lstrip().startswith("SELECT") else []


def main() -> None:  # noqa: PLR0915 - one scenario script, read top to bottom
    if os.environ.get("ENVIRONMENT") != "test":
        raise SystemExit("tag_route_probe runs only with ENVIRONMENT=test")
    a = _new_workspace("tags-a")
    b = _new_workspace("tags-b")
    tokens = {
        "owner": issue_session(a.owner_id)[1],
        "admin": _member(a, Role.ADMIN),
        "member": _member(a, Role.MEMBER),
        "reader": _member(a, Role.READ_ONLY),
        "other_owner": issue_session(b.owner_id)[1],
    }

    def auth(caller: str, **extra: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {tokens[caller]}", **extra}

    base = f"/v1/workspaces/{a.id}/tags"
    result: dict[str, Any] = {"workspace": str(a.id)}
    with TestClient(create_app(), follow_redirects=False) as client:
        # --- Who may read and change ---------------------------------------------------
        result["read"] = {
            caller: client.get(base, headers=auth(caller)).status_code
            for caller in ("owner", "admin", "member", "reader", "other_owner")
        }
        result["anonymous"] = client.get(base).status_code
        result["create_refused"] = {
            caller: client.post(base, json={"name": "Nope"}, headers=auth(caller)).status_code
            for caller in ("member", "reader", "other_owner")
        }
        vip = client.post(base, json={"name": "  VIP "}, headers=auth("owner"))
        hot = client.post(base, json={"name": "Hot lead"}, headers=auth("admin"))
        result["created"] = [
            [vip.status_code, vip.json(), vip.headers.get("etag")],
            [hot.status_code, hot.json()],
        ]
        vip_id, hot_id = vip.json()["id"], hot.json()["id"]

        # --- Names --------------------------------------------------------------------
        duplicate = client.post(base, json={"name": "vip"}, headers=auth("admin"))
        result["duplicate"] = [duplicate.status_code, duplicate.json()]
        result["invalid"] = {
            label: client.post(base, json=body, headers=auth("owner")).status_code
            for label, body in (
                ("empty", {"name": ""}),
                ("blank", {"name": "   "}),
                ("long", {"name": "x" * 51}),
                ("control", {"name": "a\nb"}),
                ("extra", {"name": "Fine", "colour": "red"}),
                ("missing", {}),
            )
        }
        listed = client.get(base, headers=auth("reader")).json()
        result["listed"] = [[t["name"] for t in listed["items"]], listed["max_tags"]]

        # --- Renaming -----------------------------------------------------------------
        item = f"{base}/{vip_id}"
        result["rename_no_version"] = client.patch(
            item, json={"name": "VIPs"}, headers=auth("owner")
        ).status_code
        stale = client.patch(
            item, json={"name": "VIPs"}, headers=auth("owner", **{"If-Match": "7"})
        )
        result["rename_stale"] = [stale.status_code, stale.json()]
        result["rename_member"] = client.patch(
            item, json={"name": "VIPs"}, headers=auth("member", **{"If-Match": "1"})
        ).status_code
        same = client.patch(item, json={"name": "VIP"}, headers=auth("owner", **{"If-Match": "1"}))
        result["rename_same"] = [same.status_code, same.json()["version"]]
        cased = client.patch(item, json={"name": "vip"}, headers=auth("owner", **{"If-Match": "1"}))
        result["rename_case"] = [cased.status_code, cased.json(), cased.headers.get("etag")]
        clash = client.patch(
            item, json={"name": "HOT LEAD"}, headers=auth("owner", **{"If-Match": "2"})
        )
        result["rename_clash"] = [clash.status_code, clash.json()]

        # --- Another workspace's tag ---------------------------------------------------
        foreign = client.post(
            f"/v1/workspaces/{b.id}/tags", json={"name": "Secret"}, headers=auth("other_owner")
        ).json()
        result["foreign"] = {
            "rename": client.patch(
                f"{base}/{foreign['id']}",
                json={"name": "Mine"},
                headers=auth("owner", **{"If-Match": "1"}),
            ).json(),
            "delete": client.delete(f"{base}/{foreign['id']}", headers=auth("owner")).json(),
            "listed": "Secret" in client.get(base, headers=auth("owner")).text,
        }

        # --- Deleting removes the tag from records, which keep their version -----------
        contact = client.post(
            f"/v1/workspaces/{a.id}/contacts",
            json={"first_name": "Sam", "email": "sam@example.test"},
            headers=auth("owner"),
        ).json()
        company = client.post(
            f"/v1/workspaces/{a.id}/companies", json={"name": "Acme"}, headers=auth("owner")
        ).json()
        _sql(
            a.id,
            "INSERT INTO crm_app.contact_tag (tenant_id, contact_id, tag_id)"
            " VALUES (:tenant, :record, :tag)",
            record=contact["id"],
            tag=hot_id,
        )
        _sql(
            a.id,
            "INSERT INTO crm_app.company_tag (tenant_id, company_id, tag_id)"
            " VALUES (:tenant, :record, :tag)",
            record=company["id"],
            tag=hot_id,
        )
        result["delete_member"] = client.delete(
            f"{base}/{hot_id}", headers=auth("member")
        ).status_code
        result["deleted"] = client.delete(f"{base}/{hot_id}", headers=auth("admin")).status_code
        result["deleted_again"] = client.delete(
            f"{base}/{hot_id}", headers=auth("admin")
        ).status_code
        result["left_assigned"] = [
            _sql(a.id, "SELECT count(*) FROM crm_app.contact_tag")[0][0],
            _sql(a.id, "SELECT count(*) FROM crm_app.company_tag")[0][0],
        ]
        result["record_versions"] = [
            client.get(
                f"/v1/workspaces/{a.id}/contacts/{contact['id']}", headers=auth("owner")
            ).json()["version"],
            client.get(
                f"/v1/workspaces/{a.id}/companies/{company['id']}", headers=auth("owner")
            ).json()["version"],
        ]
        result["ids"] = {"vip": vip_id, "hot": hot_id}

    # --- At most 500 tags per workspace ----------------------------------------------
    c = _new_workspace("tags-limit")
    _sql(
        c.id,
        "INSERT INTO crm_app.tag (id, tenant_id, name)"
        " SELECT gen_random_uuid(), :tenant, 'Bulk ' || g FROM generate_series(1, 499) AS g",
    )
    with TestClient(create_app(), follow_redirects=False) as client:
        headers = {"Authorization": f"Bearer {issue_session(c.owner_id)[1]}"}
        limit = f"/v1/workspaces/{c.id}/tags"
        last = client.post(limit, json={"name": "Last"}, headers=headers)
        over = client.post(limit, json={"name": "Over"}, headers=headers)
        result["limit"] = [last.status_code, over.status_code, over.json()]
    print("RESULT " + json.dumps(result))


if __name__ == "__main__":
    main()

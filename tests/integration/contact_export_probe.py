"""Exports contacts against the integration database and prints one
`RESULT <json>` line.

Run in a fresh interpreter by `tests/integration/test_contact_export.py`,
in one of two modes:

- `main`: roles, workspace isolation, every filter and order compared with
  the contact list, the CSV contract, the 50,000-row bound and the
  per-user limit;
- `limiter_down`: the export with the rate limiter unreachable.

Seeds made-up records into throwaway workspaces. Refuses to run unless
ENVIRONMENT=test.
"""

from __future__ import annotations

import csv
import io
import json
import os
import sys
import uuid
from typing import Any

from fastapi.testclient import TestClient
from saas_os.core.authority import UserCaller
from saas_os.core.identity import add_tenant_membership, issue_session
from saas_os.core.rbac import assign_role
from saas_os.infra.db import tenant_session_scope
from sqlalchemy import text

from crm_app.app import create_app
from crm_app.roles import Role
from tests.integration.workspace_route_probe import PROVISIONING, _new_user, _new_workspace

BOM = "﻿"
BIG = 50_000


def _member(workspace: Any, role: Role) -> str:
    user = _new_user()
    membership = add_tenant_membership(workspace.id, user, caller=PROVISIONING)
    assign_role(
        workspace.id, membership.id, workspace.role_ids[role], caller=UserCaller(workspace.owner_id)
    )
    return issue_session(user)[1]


def _bulk(workspace: uuid.UUID, count: int, first_name: str) -> None:
    """`count` contacts in one statement, inside the workspace's own scope."""
    with tenant_session_scope(workspace) as session:
        session.execute(
            text(
                "INSERT INTO crm_app.contact (id, tenant_id, first_name, email, created_at,"
                " updated_at) SELECT gen_random_uuid(), :tenant, :first,"
                " :first || '.' || g || '@example.test', now(), now()"
                " FROM generate_series(1, :count) AS g"
            ),
            {"tenant": workspace, "first": first_name.lower(), "count": count},
        )


def _rows(response: Any) -> list[list[str]]:
    body = response.content.decode("utf-8")
    return list(csv.reader(io.StringIO(body.removeprefix(BOM), newline="")))


def main() -> None:  # noqa: PLR0915 - one scenario script, read top to bottom
    if os.environ.get("ENVIRONMENT") != "test":
        raise SystemExit("contact_export_probe runs only with ENVIRONMENT=test")
    mode = sys.argv[1]
    a = _new_workspace("export-a")
    b = _new_workspace("export-b")
    tokens = {
        "owner": issue_session(a.owner_id)[1],
        "admin": _member(a, Role.ADMIN),
        "limited_admin": _member(a, Role.ADMIN),
        # Each caller's exports count towards their own limit of 10: the
        # comparisons below get a caller of their own.
        "comparing_admin": _member(a, Role.ADMIN),
        "member": _member(a, Role.MEMBER),
        "reader": _member(a, Role.READ_ONLY),
        "other_owner": issue_session(b.owner_id)[1],
    }

    def auth(caller: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {tokens[caller]}"}

    base = f"/v1/workspaces/{a.id}"
    export = f"{base}/contacts/export.csv"
    result: dict[str, Any] = {"workspace": str(a.id), "other_workspace": str(b.id)}
    with TestClient(create_app(), follow_redirects=False) as client:
        if mode == "limiter_down":
            response = client.get(export, headers=auth("owner"))
            result["down"] = [response.status_code, response.headers.get("Retry-After")]
            print("RESULT " + json.dumps(result))
            return

        def create(path: str, body: dict[str, object], caller: str = "owner") -> dict[str, Any]:
            response = client.post(path, json=body, headers=auth(caller))
            assert response.status_code == 201, response.text
            return response.json()

        acme = create(f"{base}/companies", {"name": "Acme, Ltd"})
        zeta = create(f"{base}/companies", {"name": "Zeta"})
        foreign = create(
            f"/v1/workspaces/{b.id}/companies", {"name": "Foreign Secret BV"}, "other_owner"
        )
        create(
            f"/v1/workspaces/{b.id}/contacts",
            {"first_name": "Foreign", "email": "foreign@example.test"},
            "other_owner",
        )
        me = client.get("/auth/me", headers=auth("owner")).json()["user_id"]
        people = [
            {
                "first_name": "=cmd",
                "last_name": 'Jansen, "Sam"',
                "email": "sam@example.test",
                "phone": "+31 6 1234 5678",
                "city": "Zoë North",
                "company_id": acme["id"],
                "owner_user_id": me,
                "lifecycle_stage": "customer",
            },
            {"first_name": "Émile", "last_name": "张伟", "email": "emile@example.test"},
            {
                "first_name": "Ria",
                "last_name": "Bakker",
                "email": "ria@example.test",
                "job_title": "-Head of sales",
                "company_id": zeta["id"],
                "lifecycle_stage": "prospect",
            },
            {"first_name": "@home", "last_name": "Vries", "email": "home@example.test"},
            {"first_name": "Anna", "last_name": None, "email": "anna@example.test"},
        ]
        contacts = [create(f"{base}/contacts", body) for body in people]
        archived = create(f"{base}/contacts", {"first_name": "Old", "email": "old@example.test"})
        archiving = client.post(f"{base}/contacts/{archived['id']}/archive", headers=auth("owner"))
        assert archiving.status_code == 200, archiving.text

        # --- Roles and isolation ---------------------------------------------------
        result["roles"] = {
            caller: client.get(export, headers=auth(caller)).status_code
            for caller in ("owner", "admin", "member", "reader", "other_owner")
        }
        result["anonymous"] = client.get(export).status_code
        foreign_filter = client.get(
            export, params={"company_id": foreign["id"]}, headers=auth("owner")
        )
        result["foreign_filter"] = [foreign_filter.status_code, _rows(foreign_filter)]
        result["foreign_text"] = "Foreign" in client.get(
            export, params={"archived": "all"}, headers=auth("owner")
        ).content.decode("utf-8")

        # --- The file itself ----------------------------------------------------------
        plain = client.get(export, params={"q": "Jan"}, headers=auth("owner"))
        result["headers"] = {
            "type": plain.headers.get("content-type"),
            "disposition": plain.headers.get("content-disposition"),
            "cache": plain.headers.get("cache-control"),
        }
        result["bom_crlf"] = [plain.content.startswith(b"\xef\xbb\xbf"), b"\r\n" in plain.content]
        everyone = client.get(export, params={"archived": "all"}, headers=auth("owner"))
        result["rows"] = _rows(everyone)
        result["ids"] = {
            "sam": contacts[0]["id"],
            "ria": contacts[2]["id"],
            "archived": archived["id"],
            "acme": acme["id"],
            "zeta": zeta["id"],
        }

        # --- Selection and order match the list -------------------------------------
        cases: dict[str, dict[str, object]] = {
            "default": {},
            "search": {"q": "ri"},
            "owner": {"owner": me},
            "stage": {"lifecycle_stage": ["prospect", "customer"]},
            "company": {"company_id": [acme["id"]]},
            "archived": {"archived": "true"},
            "all": {"archived": "all"},
            "updated_desc": {"sort": "updated_at", "direction": "desc"},
            "name_desc": {"sort": "name", "direction": "desc"},
            "created_asc": {"sort": "created_at", "direction": "asc"},
        }
        compared = {}
        for label, params in cases.items():
            listed = client.get(
                f"{base}/contacts", params={**params, "limit": 200}, headers=auth("owner")
            ).json()
            exported = client.get(export, params=params, headers=auth("comparing_admin"))
            compared[label] = {
                "list": [item["id"] for item in listed["items"]],
                "export": [row[0] for row in _rows(exported)[1:]],
                "status": exported.status_code,
            }
        result["compared"] = compared
        result["refused_params"] = {
            name: client.get(export, params={name: value}, headers=auth("admin")).status_code
            for name, value in (("cursor", "x"), ("limit", "10"), ("colour", "red"))
        }

        # --- The per-user limit (10 per window) ---------------------------------------
        statuses = [
            client.get(export, headers=auth("limited_admin")).status_code for _ in range(10)
        ]
        eleventh = client.get(export, headers=auth("limited_admin"))
        result["limit"] = {
            "statuses": statuses,
            "eleventh": [eleventh.status_code, eleventh.headers.get("Retry-After")],
        }

    # --- The 50,000-row bound, in its own workspace ------------------------------------
    c = _new_workspace("export-big")
    big_owner = issue_session(c.owner_id)[1]
    big = f"/v1/workspaces/{c.id}/contacts/export.csv"
    _bulk(c.id, BIG, "Bulk")
    with TestClient(create_app(), follow_redirects=False) as client:
        headers = {"Authorization": f"Bearer {big_owner}"}
        exactly = client.get(big, headers=headers)
        _bulk(c.id, 1, "Extra")
        over = client.get(big, headers=headers)
    result["big"] = {
        "workspace": str(c.id),
        "exactly": [exactly.status_code, len(_rows(exactly)) - 1],
        "over": [over.status_code, over.headers.get("content-type"), over.json()],
    }
    print("RESULT " + json.dumps(result))


if __name__ == "__main__":
    main()

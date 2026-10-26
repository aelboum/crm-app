"""Exports companies against the integration database and prints one
`RESULT <json>` line.

Run in a fresh interpreter by `tests/integration/test_company_export.py`,
in one of two modes:

- `main`: roles, workspace isolation, every filter and order compared with
  the company list, the CSV contract, the 50,000-row bound, the per-user
  limit and its independence from the contacts export's limit;
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
from saas_os.core.identity import issue_session
from saas_os.infra.db import tenant_session_scope
from sqlalchemy import text

from crm_app.app import create_app
from crm_app.roles import Role
from tests.integration.contact_export_probe import _member
from tests.integration.workspace_route_probe import _new_workspace

BOM = "﻿"
BIG = 50_000
COMPARERS = 2  # each makes at most 10 exports, its own limit


def _bulk(workspace: uuid.UUID, count: int, name: str) -> None:
    """`count` companies in one statement, inside the workspace's own scope.
    No domain, so the active-domain unique index is never involved."""
    with tenant_session_scope(workspace) as session:
        session.execute(
            text(
                "INSERT INTO crm_app.company (id, tenant_id, name, created_at, updated_at)"
                " SELECT gen_random_uuid(), :tenant, :name || ' ' || g, now(), now()"
                " FROM generate_series(1, :count) AS g"
            ),
            {"tenant": workspace, "name": name, "count": count},
        )


def _rows(response: Any) -> list[list[str]]:
    body = response.content.decode("utf-8")
    return list(csv.reader(io.StringIO(body.removeprefix(BOM), newline="")))


def main() -> None:  # noqa: PLR0915 - one scenario script, read top to bottom
    if os.environ.get("ENVIRONMENT") != "test":
        raise SystemExit("company_export_probe runs only with ENVIRONMENT=test")
    mode = sys.argv[1]
    a = _new_workspace("company-export-a")
    b = _new_workspace("company-export-b")
    tokens = {
        "owner": issue_session(a.owner_id)[1],
        "admin": _member(a, Role.ADMIN),
        "limited_admin": _member(a, Role.ADMIN),
        "contact_spender": _member(a, Role.ADMIN),
        "member": _member(a, Role.MEMBER),
        "reader": _member(a, Role.READ_ONLY),
        "other_owner": issue_session(b.owner_id)[1],
    }
    # Each caller's exports count towards their own limit of 10: the
    # comparisons below share it out over callers of their own.
    for n in range(COMPARERS):
        tokens[f"comparing_admin_{n}"] = _member(a, Role.ADMIN)

    def auth(caller: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {tokens[caller]}"}

    base = f"/v1/workspaces/{a.id}"
    export = f"{base}/companies/export.csv"
    contacts_export = f"{base}/contacts/export.csv"
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

        me = client.get("/auth/me", headers=auth("owner")).json()["user_id"]
        stranger = client.get("/auth/me", headers=auth("other_owner")).json()["user_id"]
        create(
            f"/v1/workspaces/{b.id}/companies",
            {"name": "Foreign Secret BV", "domain": "foreign.example", "owner_user_id": stranger},
            "other_owner",
        )
        acme = create(
            f"{base}/companies",
            {
                "name": '=Acme, "Holdings"',
                "website": "https://acme.example/?a=1,b=2",
                "phone": "+31 20 123 4567",
                "industry": "@Logistics",
                "city": "Zoë North",
                "country_code": "nl",
                "owner_user_id": me,
            },
        )
        emile = create(
            f"{base}/companies", {"name": "Émile Bakkerij", "industry": "-Food", "city": "张家口"}
        )
        zeta = create(
            f"{base}/companies",
            {"name": "zeta Systems", "domain": "zeta.example", "owner_user_id": me},
        )
        create(f"{base}/companies", {"name": "Beta"})
        archived = create(f"{base}/companies", {"name": "Old Co"})
        archiving = client.post(f"{base}/companies/{archived['id']}/archive", headers=auth("owner"))
        assert archiving.status_code == 200, archiving.text
        # A later change, so the updated order differs from the created one.
        changed = client.patch(
            f"{base}/companies/{emile['id']}",
            json={"city": "Utrecht"},
            headers={**auth("owner"), "If-Match": str(emile["version"])},
        )
        assert changed.status_code == 200, changed.text

        # --- Roles and isolation ---------------------------------------------------
        result["roles"] = {
            caller: client.get(export, headers=auth(caller)).status_code
            for caller in ("owner", "admin", "member", "reader", "other_owner")
        }
        result["anonymous"] = client.get(export).status_code
        foreign_owner = client.get(export, params={"owner": stranger}, headers=auth("owner"))
        result["foreign_owner"] = [foreign_owner.status_code, _rows(foreign_owner)]
        everything = client.get(export, params={"archived": "all"}, headers=auth("owner"))
        result["foreign_text"] = any(
            word in everything.content.decode("utf-8") for word in ("Foreign", "foreign.example")
        )

        # --- The file itself ----------------------------------------------------------
        plain = client.get(export, params={"q": "ze"}, headers=auth("owner"))
        result["headers"] = {
            "type": plain.headers.get("content-type"),
            "disposition": plain.headers.get("content-disposition"),
            "cache": plain.headers.get("cache-control"),
        }
        result["bom_crlf"] = [plain.content.startswith(b"\xef\xbb\xbf"), b"\r\n" in plain.content]
        result["rows"] = _rows(everything)
        empty = client.get(export, params={"q": "nothing-matches"}, headers=auth("owner"))
        result["empty"] = [empty.status_code, _rows(empty)]
        result["ids"] = {
            "acme": acme["id"],
            "emile": emile["id"],
            "zeta": zeta["id"],
            "archived": archived["id"],
            "me": me,
        }

        # --- Selection and order match the list -------------------------------------
        cases: dict[str, dict[str, object]] = {
            "default": {},
            "search_name": {"q": "ZE"},
            "search_domain": {"q": "acme"},
            "owner_me": {"owner": "me"},
            "owner_id": {"owner": [me]},
            "archived": {"archived": "true"},
            "all": {"archived": "all"},
            "name_asc": {"sort": "name", "direction": "asc"},
            "name_desc": {"sort": "name", "direction": "desc"},
            "created_asc": {"sort": "created_at", "direction": "asc"},
            "created_desc": {"sort": "created_at", "direction": "desc"},
            "updated_asc": {"sort": "updated_at", "direction": "asc"},
            "updated_desc": {"sort": "updated_at", "direction": "desc"},
            "combined": {"q": "z", "owner": "me", "archived": "all", "sort": "updated_at"},
        }
        assert len(cases) <= COMPARERS * 10
        compared = {}
        for n, (label, params) in enumerate(cases.items()):
            listed = client.get(
                f"{base}/companies", params={**params, "limit": 200}, headers=auth("owner")
            ).json()
            # `me` is the caller: those cases export as the owner who listed.
            caller = "owner" if params.get("owner") == "me" else f"comparing_admin_{n // 10}"
            exported = client.get(export, params=params, headers=auth(caller))
            compared[label] = {
                "list": [item["id"] for item in listed["items"]],
                "export": [row[0] for row in _rows(exported)[1:]],
                "status": exported.status_code,
            }
        result["compared"] = compared
        result["refused_params"] = {
            name: client.get(export, params={name: value}, headers=auth("admin")).status_code
            for name, value in (
                ("cursor", "x"),
                ("limit", "10"),
                ("colour", "red"),
                ("company_id", acme["id"]),
                ("lifecycle_stage", "lead"),
                ("archived", "maybe"),
                ("sort", "industry"),
            )
        }
        bad_owner = client.get(export, params={"owner": "nobody"}, headers=auth("admin"))
        result["bad_owner"] = [bad_owner.status_code, bad_owner.json()]

        # --- The per-user limit (10 per window), separate per kind -------------------
        statuses = [
            client.get(export, headers=auth("limited_admin")).status_code for _ in range(10)
        ]
        eleventh = client.get(export, headers=auth("limited_admin"))
        contacts_after = client.get(contacts_export, headers=auth("limited_admin"))
        spent = [
            client.get(contacts_export, headers=auth("contact_spender")).status_code
            for _ in range(10)
        ]
        contacts_eleventh = client.get(contacts_export, headers=auth("contact_spender"))
        companies_after = client.get(export, headers=auth("contact_spender"))
        result["limit"] = {
            "statuses": statuses,
            "eleventh": [eleventh.status_code, eleventh.headers.get("Retry-After")],
            "contacts_after_companies": contacts_after.status_code,
            "contacts_spent": spent,
            "contacts_eleventh": contacts_eleventh.status_code,
            "companies_after_contacts": companies_after.status_code,
        }

    # --- The 50,000-row bound, in its own workspace ------------------------------------
    c = _new_workspace("company-export-big")
    big_owner = issue_session(c.owner_id)[1]
    big = f"/v1/workspaces/{c.id}/companies/export.csv"
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

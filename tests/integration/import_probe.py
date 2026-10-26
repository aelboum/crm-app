"""Drives the CSV import routes against the integration database and prints
one `RESULT <json>` line.

Run in a fresh interpreter by `tests/integration/test_imports.py`. Seeds
made-up records into throwaway workspaces. Refuses to run unless
ENVIRONMENT=test.
"""

from __future__ import annotations

import csv
import io
import json
import os
from typing import Any

from fastapi.testclient import TestClient
from saas_os.core.identity import issue_session

from crm_app.app import create_app
from crm_app.roles import Role
from tests.integration.contact_export_probe import _member
from tests.integration.workspace_route_probe import _new_workspace

CONTACTS = (
    "First name,Last name,E-mail,Phone,Stage,Notes\r\n"
    "Sam,Jansen,SAM@example.test,,customer,ignored\r\n"  # 1 valid
    "Ann,,not-an-email,,,\r\n"  # 2 invalid email
    "Bo,,,,,\r\n"  # 3 neither email nor phone
    "Existing,,taken@example.test,,,\r\n"  # 4 duplicate of a record
    "Sam again,,sam@example.test,,,\r\n"  # 5 duplicate of row 1
    "=cmd,,formula@example.test,+31 6 1234 5678,prospect,\r\n"  # 6 valid, kept as text
    "\r\n"  # blank, skipped
    "Zoë,,zoe@example.test,,,\r\n"  # 7 valid
)
COMPANIES = (
    "Company;Website;Country\r\n"
    "Acme;https://www.acme.example;nl\r\n"
    "Taken;https://taken.example;\r\n"
    ";https://nameless.example;\r\n"
)


def _csv_rows(response: Any) -> list[list[str]]:
    return list(csv.reader(io.StringIO(response.content.decode("utf-8"), newline="")))


def main() -> None:
    if os.environ.get("ENVIRONMENT") != "test":
        raise SystemExit("import_probe runs only with ENVIRONMENT=test")
    a = _new_workspace("imports-a")
    b = _new_workspace("imports-b")
    tokens = {
        "owner": issue_session(a.owner_id)[1],
        "admin": _member(a, Role.ADMIN),
        "limited_admin": _member(a, Role.ADMIN),
        "member": _member(a, Role.MEMBER),
        "reader": _member(a, Role.READ_ONLY),
        "other_owner": issue_session(b.owner_id)[1],
    }

    def auth(caller: str, content_type: str = "text/csv") -> dict[str, str]:
        return {"Authorization": f"Bearer {tokens[caller]}", "Content-Type": content_type}

    base = f"/v1/workspaces/{a.id}"
    imports = f"{base}/imports"
    result: dict[str, Any] = {"workspace": str(a.id)}
    with TestClient(create_app(), follow_redirects=False) as client:
        client.post(
            f"{base}/contacts",
            json={"first_name": "Taken", "email": "taken@example.test"},
            headers=auth("owner", "application/json"),
        )
        client.post(
            f"{base}/companies",
            json={"name": "Taken", "domain": "taken.example"},
            headers=auth("owner", "application/json"),
        )
        contacts_before = client.get(f"{base}/contacts", headers=auth("owner")).json()["total"]

        def preview(caller: str, body: bytes | str, **params: Any) -> Any:
            params.setdefault("entity", "contact")
            content = body.encode() if isinstance(body, str) else body
            return client.post(imports, params=params, content=content, headers=auth(caller))

        # --- Who may import ---------------------------------------------------------------
        result["roles"] = {
            caller: preview(caller, "first_name,email\r\nX,x@example.test\r\n").status_code
            for caller in ("admin", "member", "reader", "other_owner")
        }
        result["anonymous"] = client.post(imports, params={"entity": "contact"}).status_code

        # --- The upload itself --------------------------------------------------------------
        result["refused"] = {
            "json_body": client.post(
                imports,
                params={"entity": "contact"},
                content=b"{}",
                headers=auth("owner", "application/json"),
            ).status_code,
            "too_large": preview("owner", b"a" * (5 * 1024 * 1024 + 1)).json(),
            "unknown_param": preview("owner", "first_name\r\nX\r\n", colour="red").status_code,
            "bad_entity": preview("owner", "first_name\r\nX\r\n", entity="deal").status_code,
            "bad_mapping": preview("owner", CONTACTS, column=["notes:5"]).json(),
            "no_rows": preview("owner", "first_name,email\r\n").json(),
            "unmapped": preview("owner", "Notes\r\nx\r\n").json(),
        }

        # --- A contact file -------------------------------------------------------------
        contacts = preview("owner", CONTACTS)
        result["contacts"] = [contacts.status_code, contacts.json()]
        cp1252 = preview("owner", "first_name,email\r\nZoë,z1252@example.test\r\n".encode("cp1252"))
        result["cp1252"] = cp1252.json()["sample"]
        remapped = preview(
            "owner", "a,b,c\r\nX,Y,y@example.test\r\n", column=["first_name:1", "email:2"]
        )
        result["remapped"] = [remapped.json()["summary"]["mapping"], remapped.json()["sample"]]
        companies = preview("owner", COMPANIES, entity="company")
        result["companies"] = companies.json()
        import_id = contacts.json()["summary"]["id"]

        # --- Reading it back --------------------------------------------------------------
        result["get"] = client.get(f"{imports}/{import_id}", headers=auth("admin")).json()
        result["list"] = [
            item["id"] for item in client.get(imports, headers=auth("admin")).json()["items"]
        ]
        result["member_get"] = client.get(
            f"{imports}/{import_id}", headers=auth("member")
        ).status_code
        result["foreign_get"] = client.get(
            f"/v1/workspaces/{b.id}/imports/{import_id}", headers=auth("other_owner")
        ).status_code
        errors = client.get(f"{imports}/{import_id}/errors.csv", headers=auth("owner"))
        result["errors_csv"] = {
            "rows": _csv_rows(errors),
            "type": errors.headers.get("content-type"),
            "cache": errors.headers.get("cache-control"),
            "disposition": errors.headers.get("content-disposition"),
        }
        result["contacts_after"] = client.get(f"{base}/contacts", headers=auth("owner")).json()[
            "total"
        ]
        result["contacts_before"] = contacts_before
        result["import_id"] = import_id

        # --- Ten previews per user per window ----------------------------------------------
        statuses = [
            preview("limited_admin", "first_name,email\r\nX,x@example.test\r\n").status_code
            for _ in range(10)
        ]
        eleventh = preview("limited_admin", "first_name,email\r\nX,x@example.test\r\n")
        result["limit"] = [statuses, eleventh.status_code, eleventh.headers.get("Retry-After")]
    print("RESULT " + json.dumps(result))


if __name__ == "__main__":
    main()

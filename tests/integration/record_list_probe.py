"""Pages through the contact and company lists against the integration
database and prints one `RESULT <json>` line.

Run in a fresh interpreter by `tests/integration/test_record_lists.py`.
Seeds made-up records through the API into a throwaway workspace (names
chosen to exercise case, accents, NULL last names, ties and LIKE wildcards),
then records what the lists return; the test compares that with the order
PostgreSQL itself produces. Refuses to run unless ENVIRONMENT=test.
"""

from __future__ import annotations

import base64
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

# (first name, last name, stage): duplicates and NULL last names on purpose.
PEOPLE = [
    ("anna", "jansen", "lead"),
    ("Anna", "Jansen", "lead"),
    ("Émile", "Zola", "prospect"),
    ("Bert", None, "customer"),
    ("Carla", None, "lead"),
    ("dirk", "de Vries", "inactive"),
    ("Eva", "de vries", "customer"),
    ("Femke", "Bakker", "lead"),
    ("Gijs", "Bakker", "lead"),
    ("%off", "Wildcard", "lead"),
    ("under_score", "Wildcard", "lead"),
    ("Anna", "Jansen", "prospect"),
]
COMPANIES = ["acme", "Acme", "Bakkerij", "Zeta", "Äpfel", "Beta"]


def main() -> None:  # noqa: PLR0915 - one scenario script, read top to bottom
    if os.environ.get("ENVIRONMENT") != "test":
        raise SystemExit("record_list_probe runs only with ENVIRONMENT=test")
    a = _new_workspace("lists-a")
    b = _new_workspace("lists-b")
    reader = _new_user()
    membership = add_tenant_membership(a.id, reader, caller=PROVISIONING)
    assign_role(a.id, membership.id, a.role_ids[Role.READ_ONLY], caller=UserCaller(a.owner_id))
    tokens = {
        "owner": issue_session(a.owner_id)[1],
        "reader": issue_session(reader)[1],
        "other_owner": issue_session(b.owner_id)[1],
    }

    def auth(caller: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {tokens[caller]}"}

    base = f"/v1/workspaces/{a.id}"
    result: dict[str, Any] = {"workspace": str(a.id)}
    with TestClient(create_app(), follow_redirects=False) as client:

        def create(path: str, body: dict[str, object], caller: str = "owner") -> dict[str, Any]:
            response = client.post(path, json=body, headers=auth(caller))
            assert response.status_code == 201, response.text
            return response.json()

        companies = [create(f"{base}/companies", {"name": name}) for name in COMPANIES]
        acme = companies[0]["id"]
        contacts = []
        for index, (first, last, stage) in enumerate(PEOPLE):
            body: dict[str, object] = {
                "first_name": first,
                "last_name": last,
                "email": f"p{index}.{secrets.token_hex(4)}@example.test",
                "lifecycle_stage": stage,
            }
            if index % 3 == 0:
                body["company_id"] = acme
            if index % 4 == 0:
                body["owner_user_id"] = str(a.owner_id)
            contacts.append(create(f"{base}/contacts", body))
        archived = contacts[-1]["id"]
        client.post(f"{base}/contacts/{archived}/archive", headers=auth("owner"))
        create(
            f"/v1/workspaces/{b.id}/contacts",
            {"first_name": "Other", "phone": "+31 6 1"},
            "other_owner",
        )

        def pages(path: str, caller: str = "owner", **params: object) -> dict[str, Any]:
            ids: list[str] = []
            cursor = None
            first_page = None
            for _ in range(100):
                query = {**params, "limit": 3, **({"cursor": cursor} if cursor else {})}
                response = client.get(path, params=query, headers=auth(caller))
                if response.status_code != 200:
                    return {"status": response.status_code, "body": response.text}
                page = response.json()
                first_page = first_page or page
                ids += [item["id"] for item in page["items"]]
                cursor = page["next_cursor"]
                if cursor is None:
                    break
            return {"ids": ids, "total": first_page["total"] if first_page else None}

        result["contact_orders"] = {
            f"{sort}:{direction}": pages(f"{base}/contacts", sort=sort, direction=direction)
            for sort in ("name", "created_at", "updated_at")
            for direction in ("asc", "desc")
        }
        result["company_orders"] = {
            f"{sort}:{direction}": pages(f"{base}/companies", sort=sort, direction=direction)
            for sort in ("name", "created_at")
            for direction in ("asc", "desc")
        }
        result["reader"] = pages(f"{base}/contacts", caller="reader")
        result["filters"] = {
            "stage": pages(f"{base}/contacts", lifecycle_stage=["customer", "inactive"]),
            "owner_me": pages(f"{base}/contacts", owner="me"),
            "company": pages(f"{base}/contacts", company_id=acme),
            "archived_true": pages(f"{base}/contacts", archived="true"),
            "archived_all": pages(f"{base}/contacts", archived="all"),
            "q_anna": pages(f"{base}/contacts", q="ANN"),
            "q_last": pages(f"{base}/contacts", q="de v"),
            "q_email": pages(f"{base}/contacts", q="P1."),
            "q_percent": pages(f"{base}/contacts", q="%"),
            "q_underscore": pages(f"{base}/contacts", q="under_"),
            "q_underscore_wild": pages(f"{base}/contacts", q="u_der"),
            "q_injection": pages(f"{base}/contacts", q="'; DROP TABLE crm_app.contact; --"),
            "company_q": pages(f"{base}/companies", q="acm"),
        }
        result["ids"] = {
            "archived": archived,
            "acme": acme,
            "percent": contacts[9]["id"],
            "underscore": contacts[10]["id"],
        }

        # Paging consistency: a row inserted before the cursor mid-way is not
        # returned, and no original row repeats or goes missing.
        first = client.get(f"{base}/contacts", params={"limit": 4}, headers=auth("owner")).json()
        create(f"{base}/contacts", {"first_name": "Aaron", "last_name": "Aa", "phone": "+31 6 2"})
        rest = pages(f"{base}/contacts", cursor=first["next_cursor"])
        result["consistency"] = {
            "first": [item["id"] for item in first["items"]],
            "rest": rest,
        }

        cursor = first["next_cursor"]
        decoded = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4))
        forged = decoded.replace(b'"v":1', b'"v":9')
        tampered = base64.urlsafe_b64encode(forged).decode("ascii").rstrip("=")
        result["cursors"] = {
            "other_filters": client.get(
                f"{base}/contacts",
                params={"cursor": cursor, "q": "a"},
                headers=auth("owner"),
            ).status_code,
            "other_order": client.get(
                f"{base}/contacts",
                params={"cursor": cursor, "sort": "created_at"},
                headers=auth("owner"),
            ).status_code,
            "tampered": client.get(
                f"{base}/contacts", params={"cursor": tampered}, headers=auth("owner")
            ).status_code,
            "garbage": client.get(
                f"{base}/contacts", params={"cursor": "%%%"}, headers=auth("owner")
            ).status_code,
            "too_long": client.get(
                f"{base}/contacts", params={"cursor": "A" * 1025}, headers=auth("owner")
            ).status_code,
        }

        def status(path: str, caller: str = "owner", **params: object) -> int:
            return client.get(path, params=params, headers=auth(caller)).status_code

        result["validation"] = {
            "unknown_param": status(f"{base}/contacts", tenant_id=str(b.id)),
            "bad_sort": status(f"{base}/contacts", sort="email"),
            "bad_stage": status(f"{base}/contacts", lifecycle_stage="patient"),
            "limit_zero": status(f"{base}/contacts", limit=0),
            "limit_high": status(f"{base}/contacts", limit=201),
            "q_long": status(f"{base}/contacts", q="x" * 101),
            "bad_owner": status(f"{base}/contacts", owner="someone"),
            "company_stage": status(f"{base}/companies", lifecycle_stage="lead"),
        }
        result["isolation"] = {
            "other_owner_on_a": status(f"{base}/contacts", caller="other_owner"),
            "other_list": [
                item["first_name"]
                for item in client.get(
                    f"/v1/workspaces/{b.id}/contacts", headers=auth("other_owner")
                ).json()["items"]
            ],
            "unknown_workspace": status(f"/v1/workspaces/{uuid.uuid4()}/contacts"),
        }

    print("RESULT " + json.dumps(result, default=str))


if __name__ == "__main__":
    main()

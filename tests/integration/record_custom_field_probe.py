"""Sets custom field values on contacts and companies against the
integration database and prints one `RESULT <json>` line.

Run in a fresh interpreter by `tests/integration/test_record_custom_fields.py`.
Seeds made-up fields and records into throwaway workspaces. Refuses to run
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


def _bulk(workspace: uuid.UUID, count: int) -> None:
    with tenant_session_scope(workspace) as session:
        session.execute(
            text(
                "INSERT INTO crm_app.custom_field_definition"
                " (id, tenant_id, entity, key, label, field_type)"
                " SELECT gen_random_uuid(), :tenant, 'contact', 'f' || g, 'Field ' || g, 'text'"
                " FROM generate_series(1, :count) AS g"
            ),
            {"tenant": workspace, "count": count},
        )


def main() -> None:  # noqa: PLR0915 - one scenario script, read top to bottom
    if os.environ.get("ENVIRONMENT") != "test":
        raise SystemExit("record_custom_field_probe runs only with ENVIRONMENT=test")
    a = _new_workspace("values-a")
    b = _new_workspace("values-b")
    tokens = {
        "owner": issue_session(a.owner_id)[1],
        "member": _member(a, Role.MEMBER),
        "reader": _member(a, Role.READ_ONLY),
        "other_owner": issue_session(b.owner_id)[1],
    }

    def auth(caller: str, version: int | None = None) -> dict[str, str]:
        headers = {"Authorization": f"Bearer {tokens[caller]}"}
        if version is not None:
            headers["If-Match"] = str(version)
        return headers

    base = f"/v1/workspaces/{a.id}"
    result: dict[str, Any] = {"workspace": str(a.id)}
    with TestClient(create_app(), follow_redirects=False) as client:

        def field(workspace: uuid.UUID, caller: str, **body: object) -> dict[str, Any]:
            response = client.post(
                f"/v1/workspaces/{workspace}/custom-fields", json=body, headers=auth(caller)
            )
            assert response.status_code == 201, response.text
            return response.json()

        field(a.id, "owner", entity="contact", key="carrier", label="Carrier", field_type="text")
        field(a.id, "owner", entity="contact", key="seats", label="Seats", field_type="number")
        field(a.id, "owner", entity="contact", key="renewal", label="Renewal", field_type="date")
        field(a.id, "owner", entity="contact", key="vip", label="VIP", field_type="boolean")
        tier = field(
            a.id,
            "owner",
            entity="contact",
            key="tier",
            label="Tier",
            field_type="select",
            options=["Gold", "Silver"],
        )
        field(a.id, "owner", entity="company", key="plan", label="Plan", field_type="text")
        field(b.id, "other_owner", entity="contact", key="secret", label="S", field_type="text")

        contacts = f"{base}/contacts"
        created = client.post(
            contacts,
            json={
                "first_name": "Sam",
                "email": "sam@example.test",
                "custom_fields": {
                    "carrier": " Delta ",
                    "seats": 4.0,
                    "renewal": "2027-01-31",
                    "vip": False,
                    "tier": "Gold",
                },
            },
            headers=auth("member"),
        )
        result["created"] = [created.status_code, created.json()]
        sam = created.json()["id"]
        item = f"{contacts}/{sam}"

        def refused(body: dict[str, object], version: int = 1) -> Any:
            response = client.patch(item, json=body, headers=auth("owner", version))
            return [response.status_code, response.json()]

        result["refused"] = {
            "unknown": refused({"custom_fields": {"colour": "red"}}),
            "other_entity": refused({"custom_fields": {"plan": "Pro"}}),
            "other_workspace": refused({"custom_fields": {"secret": "x"}}),
            "bad_number": refused({"custom_fields": {"seats": "four"}}),
            "bad_option": refused({"custom_fields": {"tier": "Bronze"}}),
            "bad_date": refused({"custom_fields": {"renewal": "2027-02-30"}}),
            "bad_boolean": refused({"custom_fields": {"vip": "yes"}}),
            "nested": refused({"custom_fields": {"carrier": {"a": 1}}}),
            "null_object": refused({"custom_fields": None}),
        }
        result["reader"] = client.patch(
            item, json={"custom_fields": {"seats": 9}}, headers=auth("reader", 1)
        ).status_code
        merged = client.patch(
            item, json={"custom_fields": {"seats": 5, "carrier": None}}, headers=auth("member", 1)
        )
        result["merged"] = [
            merged.status_code,
            merged.json()["custom_fields"],
            merged.json()["version"],
        ]
        same = client.patch(item, json={"custom_fields": {"seats": 5}}, headers=auth("owner", 2))
        result["same_version"] = same.json()["version"]

        # --- An archived field is hidden and refused; restoring shows it again ----------
        fields = f"{base}/custom-fields/{tier['id']}"
        client.post(f"{fields}/archive", headers=auth("owner"))
        result["archived"] = {
            "detail": client.get(item, headers=auth("reader")).json()["custom_fields"],
            "write": refused({"custom_fields": {"tier": "Silver"}}, 2),
            "list": [
                entry["custom_fields"]
                for entry in client.get(contacts, headers=auth("reader")).json()["items"]
            ],
        }
        client.post(f"{fields}/restore", headers=auth("owner"))
        result["restored"] = client.get(item, headers=auth("reader")).json()["custom_fields"]

        company = client.post(
            f"{base}/companies",
            json={"name": "Acme", "custom_fields": {"plan": "Pro"}},
            headers=auth("owner"),
        )
        result["company"] = [company.status_code, company.json()["custom_fields"]]
        result["plain"] = client.post(
            contacts, json={"first_name": "Ann", "email": "ann@example.test"}, headers=auth("owner")
        ).json()["custom_fields"]
        result["ids"] = {"sam": sam}

    # --- A record's values are at most 32 KB --------------------------------------------
    c = _new_workspace("values-limit")
    _bulk(c.id, 50)
    with TestClient(create_app(), follow_redirects=False) as client:
        headers = {"Authorization": f"Bearer {issue_session(c.owner_id)[1]}"}
        big = {f"f{n}": "张" * 500 for n in range(1, 51)}
        over = client.post(
            f"/v1/workspaces/{c.id}/contacts",
            json={"first_name": "Big", "email": "big@example.test", "custom_fields": big},
            headers=headers,
        )
        result["too_large"] = [over.status_code, over.json()]
    print("RESULT " + json.dumps(result))


if __name__ == "__main__":
    main()

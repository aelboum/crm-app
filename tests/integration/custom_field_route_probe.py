"""Drives the custom field definition routes against the integration
database and prints one `RESULT <json>` line.

Run in a fresh interpreter by `tests/integration/test_custom_field_routes.py`.
Seeds made-up definitions into throwaway workspaces. Refuses to run unless
ENVIRONMENT=test.
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
                " SELECT gen_random_uuid(), :tenant, 'contact', 'bulk_' || g, 'Bulk ' || g, 'text'"
                " FROM generate_series(1, :count) AS g"
            ),
            {"tenant": workspace, "count": count},
        )


def main() -> None:  # noqa: PLR0915 - one scenario script, read top to bottom
    if os.environ.get("ENVIRONMENT") != "test":
        raise SystemExit("custom_field_route_probe runs only with ENVIRONMENT=test")
    a = _new_workspace("fields-a")
    b = _new_workspace("fields-b")
    tokens = {
        "owner": issue_session(a.owner_id)[1],
        "admin": _member(a, Role.ADMIN),
        "member": _member(a, Role.MEMBER),
        "reader": _member(a, Role.READ_ONLY),
        "other_owner": issue_session(b.owner_id)[1],
    }

    def auth(caller: str, version: int | None = None) -> dict[str, str]:
        headers = {"Authorization": f"Bearer {tokens[caller]}"}
        if version is not None:
            headers["If-Match"] = str(version)
        return headers

    base = f"/v1/workspaces/{a.id}/custom-fields"
    result: dict[str, Any] = {"workspace": str(a.id)}
    carrier_body = {
        "entity": "contact",
        "key": "carrier",
        "label": " Insurance carrier ",
        "field_type": "text",
    }
    with TestClient(create_app(), follow_redirects=False) as client:
        # --- Who may read and change ---------------------------------------------------
        result["read"] = {
            caller: client.get(base, headers=auth(caller)).status_code
            for caller in ("owner", "admin", "member", "reader", "other_owner")
        }
        result["anonymous"] = client.get(base).status_code
        result["create_refused"] = {
            caller: client.post(base, json=carrier_body, headers=auth(caller)).status_code
            for caller in ("member", "reader", "other_owner")
        }

        # --- Creating -------------------------------------------------------------------
        carrier = client.post(base, json=carrier_body, headers=auth("owner"))
        tier = client.post(
            base,
            json={
                "entity": "contact",
                "key": "tier",
                "label": "Tier",
                "field_type": "select",
                "options": [" Gold", "Silver"],
                "position": 1,
            },
            headers=auth("admin"),
        )
        seats = client.post(
            base,
            json={"entity": "company", "key": "seats", "label": "Seats", "field_type": "number"},
            headers=auth("owner"),
        )
        same_key_company = client.post(
            base, json={**carrier_body, "entity": "company"}, headers=auth("owner")
        )
        result["created"] = [
            [carrier.status_code, carrier.json(), carrier.headers.get("etag")],
            [tier.status_code, tier.json()],
            [seats.status_code, seats.json()["field_type"]],
            same_key_company.status_code,
        ]
        duplicate = client.post(base, json=carrier_body, headers=auth("owner"))
        result["duplicate"] = [duplicate.status_code, duplicate.json()]
        result["invalid"] = {
            label: [response.status_code, response.json()]
            for label, response in (
                (
                    "bad_key",
                    client.post(
                        base, json={**carrier_body, "key": "Bad Key"}, headers=auth("owner")
                    ),
                ),
                (
                    "bad_type",
                    client.post(
                        base,
                        json={**carrier_body, "key": "x1", "field_type": "money"},
                        headers=auth("owner"),
                    ),
                ),
                (
                    "bad_entity",
                    client.post(
                        base,
                        json={**carrier_body, "key": "x2", "entity": "deal"},
                        headers=auth("owner"),
                    ),
                ),
                (
                    "select_without_options",
                    client.post(
                        base,
                        json={**carrier_body, "key": "x3", "field_type": "select"},
                        headers=auth("owner"),
                    ),
                ),
                (
                    "text_with_options",
                    client.post(
                        base,
                        json={**carrier_body, "key": "x4", "options": ["a"]},
                        headers=auth("owner"),
                    ),
                ),
                (
                    "repeated_options",
                    client.post(
                        base,
                        json={
                            **carrier_body,
                            "key": "x5",
                            "field_type": "select",
                            "options": ["A", "a"],
                        },
                        headers=auth("owner"),
                    ),
                ),
                (
                    "blank_label",
                    client.post(
                        base,
                        json={**carrier_body, "key": "x6", "label": "  "},
                        headers=auth("owner"),
                    ),
                ),
                (
                    "extra",
                    client.post(
                        base,
                        json={**carrier_body, "key": "x7", "required": True},
                        headers=auth("owner"),
                    ),
                ),
            )
        }
        listed = client.get(base, headers=auth("reader")).json()
        result["listed"] = [
            [(item["entity"], item["key"]) for item in listed["items"]],
            listed["max_active"],
        ]
        result["contact_only"] = [
            item["key"]
            for item in client.get(
                base, params={"entity": "contact"}, headers=auth("reader")
            ).json()["items"]
        ]
        result["bad_filter"] = [
            client.get(base, params={"entity": "deal"}, headers=auth("reader")).status_code,
            client.get(base, params={"colour": "red"}, headers=auth("reader")).status_code,
        ]

        # --- Changing -------------------------------------------------------------------
        item = f"{base}/{carrier.json()['id']}"
        result["update"] = {
            "no_version": client.patch(
                item, json={"label": "Carrier"}, headers=auth("owner")
            ).status_code,
            "stale": client.patch(item, json={"label": "Carrier"}, headers=auth("owner", 9)).json(),
            "member": client.patch(
                item, json={"label": "Carrier"}, headers=auth("member", 1)
            ).status_code,
            "key": client.patch(item, json={"key": "other"}, headers=auth("owner", 1)).status_code,
            "type": client.patch(
                item, json={"field_type": "number"}, headers=auth("owner", 1)
            ).status_code,
            "null_label": client.patch(
                item, json={"label": None}, headers=auth("owner", 1)
            ).status_code,
            "options_on_text": client.patch(
                item, json={"options": ["a"]}, headers=auth("owner", 1)
            ).json(),
        }
        changed = client.patch(
            item, json={"label": "Carrier", "position": 5}, headers=auth("owner", 1)
        )
        same = client.patch(item, json={"label": "Carrier"}, headers=auth("owner", 2))
        options = client.patch(
            f"{base}/{tier.json()['id']}",
            json={"options": ["Gold", "Silver", "Bronze"]},
            headers=auth("owner", 1),
        )
        result["changed"] = [
            changed.status_code,
            changed.json(),
            same.json()["version"],
            options.json(),
        ]

        # --- Archiving and restoring ---------------------------------------------------
        archived = client.post(f"{item}/archive", headers=auth("admin"))
        again = client.post(f"{item}/archive", headers=auth("admin"))
        restored = client.post(f"{item}/restore", headers=auth("owner"))
        result["archive"] = [
            [archived.status_code, archived.json()["archived"], archived.json()["version"]],
            again.json()["version"],
            [restored.json()["archived"], restored.json()["version"]],
            client.post(f"{item}/archive", headers=auth("member")).status_code,
        ]

        # --- Another workspace's field ---------------------------------------------------
        foreign = client.post(
            f"/v1/workspaces/{b.id}/custom-fields", json=carrier_body, headers=auth("other_owner")
        ).json()
        result["foreign"] = [
            client.patch(
                f"{base}/{foreign['id']}", json={"label": "Mine"}, headers=auth("owner", 1)
            ).json(),
            client.post(f"{base}/{foreign['id']}/archive", headers=auth("owner")).json(),
        ]
        result["ids"] = {"carrier": carrier.json()["id"], "tier": tier.json()["id"]}

    # --- At most 50 active fields per entity ----------------------------------------
    c = _new_workspace("fields-limit")
    _bulk(c.id, 49)
    with TestClient(create_app(), follow_redirects=False) as client:
        headers = {"Authorization": f"Bearer {issue_session(c.owner_id)[1]}"}
        limit = f"/v1/workspaces/{c.id}/custom-fields"
        fiftieth = client.post(limit, json={**carrier_body, "key": "last"}, headers=headers)
        over = client.post(limit, json={**carrier_body, "key": "over"}, headers=headers)
        company = client.post(
            limit, json={**carrier_body, "key": "over", "entity": "company"}, headers=headers
        )
        client.post(f"{limit}/{fiftieth.json()['id']}/archive", headers=headers)
        room = client.post(limit, json={**carrier_body, "key": "room"}, headers=headers)
        restore = client.post(f"{limit}/{fiftieth.json()['id']}/restore", headers=headers)
        result["limit"] = [
            fiftieth.status_code,
            [over.status_code, over.json()],
            company.status_code,
            room.status_code,
            [restore.status_code, restore.json()],
        ]
    print("RESULT " + json.dumps(result))


if __name__ == "__main__":
    main()

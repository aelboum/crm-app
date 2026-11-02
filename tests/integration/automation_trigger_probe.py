"""Drives the automation triggers and actions of decision P8-B and prints
one `RESULT <json>` line.

Run in a fresh interpreter by `tests/integration/test_automation_triggers.py`.
Runs are advanced by calling the job's function directly, as the worker
would. Seeds throwaway workspaces. Refuses to run unless ENVIRONMENT=test.
"""

from __future__ import annotations

import json
import os
import secrets
import uuid
from typing import Any

from fastapi.testclient import TestClient
from saas_os.core.identity import issue_session
from saas_os.infra.db import tenant_session_scope
from sqlalchemy import text

from crm_app import automations
from crm_app.app import create_app
from crm_app.records import Scope
from tests.integration.workspace_route_probe import _new_workspace


def _q(workspace: uuid.UUID, sql: str, **values: object) -> list[dict[str, Any]]:
    with tenant_session_scope(workspace) as session:
        return [dict(r._mapping) for r in session.execute(text(sql), {"t": workspace, **values})]


def _runs(workspace: uuid.UUID, contact: str) -> list[dict[str, Any]]:
    return _q(
        workspace,
        "SELECT r.id, r.status, a.name FROM crm_app.automation_run r"
        " JOIN crm_app.automation a ON a.tenant_id = r.tenant_id AND a.id = r.automation_id"
        " WHERE r.tenant_id = :t AND r.contact_id = :c ORDER BY r.created_at",
        c=contact,
    )


def _finish(workspace: uuid.UUID, contact: str) -> list[str]:
    """Advance every running run of the contact until none is left."""
    names: list[str] = []
    for _ in range(10):
        running = [run for run in _runs(workspace, contact) if run["status"] == "running"]
        if not running:
            break
        for run in running:
            automations.advance(workspace, run["id"])
            names.append(str(run["name"]))
    return names


def main() -> None:  # noqa: PLR0915 - one scenario script, read top to bottom
    if os.environ.get("ENVIRONMENT") != "test":
        raise SystemExit("automation_trigger_probe runs only with ENVIRONMENT=test")
    a = _new_workspace("triggers-a")
    b = _new_workspace("triggers-b")
    tokens = {"owner": issue_session(a.owner_id)[1], "other_owner": issue_session(b.owner_id)[1]}

    def auth(caller: str = "owner", version: int | None = None) -> dict[str, str]:
        headers = {"Authorization": f"Bearer {tokens[caller]}"}
        if version is not None:
            headers["If-Match"] = f'"{version}"'
        return headers

    base = f"/v1/workspaces/{a.id}"
    result: dict[str, Any] = {}
    with TestClient(create_app(), follow_redirects=False) as client:

        def tag(name: str, where: str = base, caller: str = "owner") -> str:
            return str(
                client.post(f"{where}/tags", json={"name": name}, headers=auth(caller)).json()["id"]
            )

        hot, vip = tag("Hot"), tag("VIP")
        b_hot = tag("Hot", f"/v1/workspaces/{b.id}", "other_owner")
        stages = [
            s["id"]
            for s in client.get(f"{base}/pipelines", headers=auth()).json()["items"][0]["stages"]
        ]

        def create(
            name: str, definition: dict[str, Any], where: str = base, caller: str = "owner"
        ) -> Any:
            return client.post(
                f"{where}/automations",
                json={"name": name, "definition": definition},
                headers=auth(caller),
            )

        def activate(made: Any, where: str = base, caller: str = "owner") -> Any:
            body = made.json()
            return client.post(
                f"{where}/automations/{body['id']}/activate",
                headers=auth(caller, body["version"]),
            )

        # --- Definitions -----------------------------------------------------------------
        result["refused"] = {
            "tag_without_tag": create("x", {"trigger": {"type": "tag_added"}}).json()["detail"][
                "code"
            ],
            "stage_without_stage": create("x", {"trigger": {"type": "deal_stage_changed"}}).json()[
                "detail"
            ]["code"],
            "sources_on_tag": create(
                "x", {"trigger": {"type": "tag_added", "tag_id": hot, "sources": ["form"]}}
            ).json()["detail"]["code"],
            "bad_stage_action": create(
                "x",
                {
                    "trigger": {"type": "tag_added", "tag_id": hot},
                    "yes": [{"type": "set_lifecycle_stage", "stage": "royalty"}],
                },
            ).json()["detail"]["code"],
        }
        missing_form = create(
            "Missing form",
            {
                "trigger": {"type": "form_submitted", "form_id": str(uuid.uuid4())},
                "yes": [{"type": "add_tag", "tag_id": vip}],
            },
        )
        result["missing_subject"] = activate(missing_form).json()["detail"]

        hot_auto = create(
            "Hot to customer",
            {
                "trigger": {"type": "tag_added", "tag_id": hot},
                "yes": [
                    {"type": "set_lifecycle_stage", "stage": "customer"},
                    {"type": "remove_tag", "tag_id": hot},
                ],
            },
        )
        result["trigger_stored"] = hot_auto.json()["definition"]["trigger"]
        deal_auto = create(
            "Won stage tags VIP",
            {
                "trigger": {"type": "deal_stage_changed", "stage_id": stages[2]},
                "yes": [{"type": "add_tag", "tag_id": vip}],
            },
        )
        vip_auto = create(
            "VIP becomes customer",
            {
                "trigger": {"type": "tag_added", "tag_id": vip},
                "yes": [{"type": "set_lifecycle_stage", "stage": "customer"}],
            },
        )
        any_form = create(
            "Any form",
            {"trigger": {"type": "form_submitted"}, "yes": [{"type": "add_tag", "tag_id": vip}]},
        )
        result["activated"] = [
            activate(made).status_code for made in (hot_auto, deal_auto, vip_auto, any_form)
        ]
        b_auto = create(
            "B hot",
            {
                "trigger": {"type": "tag_added", "tag_id": b_hot},
                "yes": [{"type": "set_lifecycle_stage", "stage": "customer"}],
            },
            f"/v1/workspaces/{b.id}",
            "other_owner",
        )
        activate(b_auto, f"/v1/workspaces/{b.id}", "other_owner")

        def contact(where: str = base, caller: str = "owner") -> dict[str, Any]:
            made = client.post(
                f"{where}/contacts",
                json={"first_name": "C", "email": f"c.{secrets.token_hex(4)}@example.org"},
                headers=auth(caller),
            )
            assert made.status_code == 201, made.text
            return made.json()

        def set_tags(
            person: dict[str, Any], tags: list[str], where: str = base, caller: str = "owner"
        ) -> dict[str, Any]:
            current = client.get(f"{where}/contacts/{person['id']}", headers=auth(caller)).json()
            response = client.put(
                f"{where}/contacts/{person['id']}/tags",
                json={"tag_ids": tags},
                headers=auth(caller, current["version"]),
            )
            assert response.status_code == 200, response.text
            return response.json()

        def state(person: dict[str, Any], workspace: uuid.UUID = a.id) -> list[Any]:
            row = _q(
                workspace,
                "SELECT lifecycle_stage FROM crm_app.contact WHERE tenant_id = :t AND id = :c",
                c=person["id"],
            )[0]
            tags = _q(
                workspace,
                "SELECT tag_id FROM crm_app.contact_tag WHERE tenant_id = :t AND contact_id = :c",
                c=person["id"],
            )
            return [row["lifecycle_stage"], sorted(str(t["tag_id"]) for t in tags)]

        # --- A tag added by a member: stage set, tag taken off ------------------------------
        x = contact()
        set_tags(x, [hot])
        result["tag_started"] = [run["name"] for run in _runs(a.id, x["id"])]
        _finish(a.id, x["id"])
        result["tag_done"] = state(x) == ["customer", []]
        set_tags(x, [hot])
        result["tag_again"] = len(_runs(a.id, x["id"]))

        # --- A deal moved into the stage, and the chain it starts ---------------------------
        y = contact()
        deal = client.post(
            f"{base}/opportunities",
            json={"title": "Fit-out", "contact_id": y["id"], "stage_id": stages[0]},
            headers=auth(),
        ).json()
        result["deal_created_runs"] = len(_runs(a.id, y["id"]))
        moved = client.patch(
            f"{base}/opportunities/{deal['id']}",
            json={"stage_id": stages[1]},
            headers=auth("owner", deal["version"]),
        ).json()
        result["other_stage_runs"] = len(_runs(a.id, y["id"]))
        client.patch(
            f"{base}/opportunities/{deal['id']}",
            json={"stage_id": stages[2]},
            headers=auth("owner", moved["version"]),
        )
        result["stage_started"] = [run["name"] for run in _runs(a.id, y["id"])]
        result["chain"] = _finish(a.id, y["id"])
        result["chain_done"] = state(y) == ["customer", [vip]]
        nobody = client.post(
            f"{base}/opportunities",
            json={"title": "No contact", "stage_id": stages[0]},
            headers=auth(),
        ).json()
        result["no_contact_move"] = client.patch(
            f"{base}/opportunities/{nobody['id']}",
            json={"stage_id": stages[2]},
            headers=auth("owner", nobody["version"]),
        ).status_code

        # --- Form and booking events, as their hooks raise them ------------------------------
        z = contact()
        scope = Scope(workspace=a.id, actor=a.owner_id)
        with tenant_session_scope(a.id) as session:
            result["events"] = [
                automations.on_event(
                    session, scope, "form_submitted", uuid.UUID(z["id"]), uuid.uuid4()
                ),
                automations.on_event(
                    session, scope, "form_submitted", uuid.UUID(z["id"]), uuid.uuid4()
                ),
                automations.on_event(
                    session, scope, "appointment_booked", uuid.UUID(z["id"]), uuid.uuid4()
                ),
            ]

        # --- Other workspaces ---------------------------------------------------------------
        w = contact(f"/v1/workspaces/{b.id}", "other_owner")
        set_tags(w, [b_hot], f"/v1/workspaces/{b.id}", "other_owner")
        result["isolation"] = [
            len(_runs(b.id, w["id"])),
            _q(
                a.id,
                "SELECT count(*) AS n FROM crm_app.automation_run WHERE tenant_id = :t"
                " AND contact_id = :c",
                c=w["id"],
            )[0]["n"],
        ]
    print("RESULT " + json.dumps(result, default=str))


if __name__ == "__main__":
    main()

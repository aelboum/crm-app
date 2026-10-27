"""Drives the pipeline routes against the integration database and prints
one `RESULT <json>` line.

Run in a fresh interpreter by `tests/integration/test_pipeline_routes.py`.
Seeds throwaway workspaces. Refuses to run unless ENVIRONMENT=test.
"""

from __future__ import annotations

import json
import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from fastapi.testclient import TestClient
from saas_os.core.identity import issue_session
from saas_os.infra.db import tenant_session_scope
from sqlalchemy import text

from crm_app import pipelines
from crm_app.app import create_app
from crm_app.records import Scope
from crm_app.roles import Role
from tests.integration.contact_export_probe import _member
from tests.integration.workspace_route_probe import _new_workspace

_COUNTS = {
    "pipeline": "SELECT count(*) FROM crm_app.pipeline WHERE tenant_id = :tenant",
    "pipeline_stage": "SELECT count(*) FROM crm_app.pipeline_stage WHERE tenant_id = :tenant",
}


def _count(workspace: uuid.UUID, table: str) -> int:
    with tenant_session_scope(workspace) as session:
        return int(session.execute(text(_COUNTS[table]), {"tenant": workspace}).scalar_one())


def _stages(body: dict[str, Any]) -> list[list[Any]]:
    return [[s["name"], s["probability"], s["position"]] for s in body["stages"]]


def main() -> None:  # noqa: PLR0915 - one scenario script, read top to bottom
    if os.environ.get("ENVIRONMENT") != "test":
        raise SystemExit("pipeline_route_probe runs only with ENVIRONMENT=test")
    a = _new_workspace("pipelines-a")
    b = _new_workspace("pipelines-b")
    c = _new_workspace("pipelines-c")
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
            headers["If-Match"] = f'"{version}"'
        return headers

    base = f"/v1/workspaces/{a.id}/pipelines"
    result: dict[str, Any] = {"workspace": str(a.id)}

    # --- Concurrent first reads create the default pipeline once ----------------------
    scope_c = Scope(workspace=c.id, actor=c.owner_id)
    with ThreadPoolExecutor(max_workers=6) as pool:
        ids = list(pool.map(lambda _: pipelines.list_pipelines(scope_c)[0]["id"], range(6)))
    result["concurrent"] = [
        len(set(ids)),
        _count(c.id, "pipeline"),
        _count(c.id, "pipeline_stage"),
    ]

    with TestClient(create_app(), follow_redirects=False) as client:
        # --- Who may read ---------------------------------------------------------------
        result["read"] = {
            caller: client.get(base, headers=auth(caller)).status_code
            for caller in ("owner", "admin", "member", "reader", "other_owner")
        }
        result["anonymous"] = client.get(base).status_code
        first = client.get(base, headers=auth("reader")).json()
        again = client.get(base, headers=auth("owner")).json()
        pipeline = first["items"][0]
        result["default"] = {
            "count": len(first["items"]),
            "same_on_reread": again["items"][0]["id"] == pipeline["id"],
            "name": pipeline["name"],
            "version": pipeline["version"],
            "stages": _stages(pipeline),
            "max_stages": first["max_stages"],
            "keys": sorted(pipeline),
            "stage_keys": sorted(pipeline["stages"][0]),
        }
        item = f"{base}/{pipeline['id']}"
        stages = f"{item}/stages"
        stage_ids = [s["id"] for s in pipeline["stages"]]

        # --- Who may change -------------------------------------------------------------
        result["refused"] = {
            caller: [
                client.patch(item, json={"name": "X"}, headers=auth(caller, 1)).status_code,
                client.post(
                    stages, json={"name": "X", "probability": 5}, headers=auth(caller, 1)
                ).status_code,
                client.patch(
                    f"{stages}/{stage_ids[0]}", json={"probability": 5}, headers=auth(caller, 1)
                ).status_code,
                client.delete(f"{stages}/{stage_ids[0]}", headers=auth(caller, 1)).status_code,
                client.put(
                    f"{item}/stage-order", json={"stage_ids": stage_ids}, headers=auth(caller, 1)
                ).status_code,
            ]
            for caller in ("member", "reader", "other_owner")
        }

        # --- Renaming the pipeline ------------------------------------------------------
        result["rename_no_version"] = client.patch(
            item, json={"name": "New business"}, headers=auth("owner")
        ).status_code
        stale = client.patch(item, json={"name": "New business"}, headers=auth("owner", 9))
        result["rename_stale"] = [stale.status_code, stale.json()]
        renamed = client.patch(item, json={"name": "  New business "}, headers=auth("admin", 1))
        result["renamed"] = [
            renamed.status_code,
            renamed.json()["name"],
            renamed.json()["version"],
            renamed.headers.get("etag"),
        ]
        same = client.patch(item, json={"name": "New business"}, headers=auth("owner", 2))
        result["rename_same"] = [same.status_code, same.json()["version"]]

        # --- Adding stages --------------------------------------------------------------
        added = client.post(
            stages, json={"name": " Closing ", "probability": 90}, headers=auth("owner", 2)
        )
        result["added"] = [added.status_code, _stages(added.json()), added.json()["version"]]
        duplicate = client.post(
            stages, json={"name": "MEETING", "probability": 10}, headers=auth("owner", 3)
        )
        result["duplicate"] = [duplicate.status_code, duplicate.json()]
        result["invalid"] = {
            label: client.post(stages, json=body, headers=auth("owner", 3)).status_code
            for label, body in (
                ("empty", {"name": "", "probability": 1}),
                ("long", {"name": "x" * 41, "probability": 1}),
                ("control", {"name": "a\tb", "probability": 1}),
                ("over", {"name": "Fine", "probability": 101}),
                ("under", {"name": "Fine", "probability": -1}),
                ("text", {"name": "Fine", "probability": "50"}),
                ("bool", {"name": "Fine", "probability": True}),
                ("fraction", {"name": "Fine", "probability": 50.5}),
                ("extra", {"name": "Fine", "probability": 5, "colour": "red"}),
                ("missing", {"name": "Fine"}),
            )
        }

        # --- Changing a stage -----------------------------------------------------------
        meeting = stage_ids[1]
        changed = client.patch(
            f"{stages}/{meeting}",
            json={"name": "Demo", "probability": 45},
            headers=auth("admin", 3),
        )
        result["changed"] = [
            changed.status_code,
            _stages(changed.json()),
            changed.json()["version"],
        ]
        unchanged = client.patch(
            f"{stages}/{meeting}", json={"probability": 45}, headers=auth("admin", 4)
        )
        result["unchanged"] = [unchanged.status_code, unchanged.json()["version"]]
        result["empty_patch"] = client.patch(
            f"{stages}/{meeting}", json={}, headers=auth("admin", 4)
        ).status_code
        clash = client.patch(
            f"{stages}/{meeting}", json={"name": "proposal"}, headers=auth("admin", 4)
        )
        result["rename_clash"] = [clash.status_code, clash.json()]
        unknown = client.patch(
            f"{stages}/{uuid.uuid4()}", json={"probability": 1}, headers=auth("admin", 4)
        )
        result["unknown_stage"] = [unknown.status_code, unknown.json()]

        # --- Another workspace's pipeline and stages ------------------------------------
        foreign = client.get(
            f"/v1/workspaces/{b.id}/pipelines", headers=auth("other_owner")
        ).json()["items"][0]
        foreign_stage = foreign["stages"][0]["id"]
        result["foreign"] = {
            "rename": client.patch(
                f"{base}/{foreign['id']}", json={"name": "Mine"}, headers=auth("owner", 1)
            ).json(),
            "stage_by_own_pipeline": client.patch(
                f"{stages}/{foreign_stage}", json={"probability": 1}, headers=auth("owner", 4)
            ).json(),
            "delete": client.delete(
                f"{base}/{foreign['id']}/stages/{foreign_stage}", headers=auth("owner", 1)
            ).json(),
            "listed": foreign["id"] in client.get(base, headers=auth("owner")).text,
            "untouched": client.get(
                f"/v1/workspaces/{b.id}/pipelines", headers=auth("other_owner")
            ).json()["items"][0]["version"],
        }

        # --- Reordering -----------------------------------------------------------------
        current = client.get(base, headers=auth("owner")).json()["items"][0]
        order = [s["id"] for s in current["stages"]]
        reordered = client.put(
            f"{item}/stage-order", json={"stage_ids": order[::-1]}, headers=auth("owner", 4)
        )
        result["reordered"] = [
            reordered.status_code,
            _stages(reordered.json()),
            reordered.json()["version"],
        ]
        bad_orders = {
            "missing": order[1:],
            "repeated": [order[0], *order[:-1]],
            "foreign": [foreign_stage, *order[1:]],
        }
        result["bad_order"] = {}
        for label, ids_given in bad_orders.items():
            response = client.put(
                f"{item}/stage-order", json={"stage_ids": ids_given}, headers=auth("owner", 5)
            )
            result["bad_order"][label] = [response.status_code, response.json()["detail"]]

        # --- Removing and the limits ----------------------------------------------------
        removed = client.delete(f"{stages}/{order[2]}", headers=auth("owner", 5))
        result["removed"] = [
            removed.status_code,
            _stages(removed.json()),
            removed.json()["version"],
        ]
        version = removed.json()["version"]
        statuses = []
        for number in range(len(removed.json()["stages"]), 16):
            response = client.post(
                stages,
                json={"name": f"Step {number}", "probability": 50},
                headers=auth("owner", version),
            )
            statuses.append(response.status_code)
            if response.status_code == 201:
                version = response.json()["version"]
            else:
                result["over_limit"] = response.json()
        result["limit"] = [statuses.count(201), statuses[-1]]
        full = client.get(base, headers=auth("owner")).json()["items"][0]
        for stage in full["stages"][:-1]:
            version = client.delete(
                f"{stages}/{stage['id']}", headers=auth("owner", version)
            ).json()["version"]
        last = client.delete(f"{stages}/{full['stages'][-1]['id']}", headers=auth("owner", version))
        result["last_stage"] = [last.status_code, last.json()]
        result["counts"] = [_count(a.id, "pipeline"), _count(a.id, "pipeline_stage")]
        result["pipeline_id"] = pipeline["id"]
        result["ids"] = {"meeting": meeting, "closing": added.json()["stages"][-1]["id"]}

    print("RESULT " + json.dumps(result))


if __name__ == "__main__":
    main()

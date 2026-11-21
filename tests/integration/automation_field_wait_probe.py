"""Drives the automation step that waits for a contact field's value
(decision P8-J) and prints one `RESULT <json>` line.

Run in a fresh interpreter by `tests/integration/test_automation_field_wait.py`.
The probe sets the engine clock and advances runs by calling the job's
function, as the worker would. Seeds a throwaway workspace. Refuses to run
unless ENVIRONMENT=test.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi.testclient import TestClient
from saas_os.core.identity import issue_session
from saas_os.infra.db import tenant_session_scope
from sqlalchemy import text

from crm_app import automations
from crm_app.app import create_app
from tests.integration.workspace_route_probe import _new_workspace

START = datetime.now(UTC).replace(microsecond=0)


def _q(workspace: uuid.UUID, sql: str, **values: object) -> list[dict[str, Any]]:
    with tenant_session_scope(workspace) as session:
        return [dict(r._mapping) for r in session.execute(text(sql), {"t": workspace, **values})]


def _since(moment: datetime | None) -> float | None:
    return None if moment is None else (moment - START).total_seconds()


def main() -> None:  # noqa: PLR0915 - one scenario script, read top to bottom
    if os.environ.get("ENVIRONMENT") != "test":
        raise SystemExit("automation_field_wait_probe runs only with ENVIRONMENT=test")
    a = _new_workspace("field-wait")
    headers = {"Authorization": f"Bearer {issue_session(a.owner_id)[1]}"}
    base = f"/v1/workspaces/{a.id}"
    result: dict[str, Any] = {}
    clock = {"now": START}
    automations._now = lambda: clock["now"]  # the probe sets the engine clock

    def later(**delta: float) -> None:
        clock["now"] = START + timedelta(**delta)

    with TestClient(create_app(), follow_redirects=False) as client:
        seats = client.post(
            f"{base}/custom-fields",
            json={"entity": "contact", "key": "seats", "label": "Seats", "field_type": "number"},
            headers=headers,
        )
        assert seats.status_code == 201, seats.text
        tag = client.post(f"{base}/tags", json={"name": "Known"}, headers=headers).json()["id"]

        def create(steps: list[dict[str, Any]]) -> Any:
            return client.post(
                f"{base}/automations",
                json={
                    "name": f"Seats {uuid.uuid4().hex[:4]}",
                    "definition": {"trigger": {"type": "contact_created"}, "yes": steps},
                },
                headers=headers,
            )

        def activate(made: Any) -> Any:
            body = made.json()
            return client.post(
                f"{base}/automations/{body['id']}/activate",
                headers={**headers, "If-Match": f'"{body["version"]}"'},
            )

        # --- Refused when saved (shape) and when activated (the field) ----------
        wait = {"type": "wait_for_field", "field_key": "seats"}
        result["refused_save"] = [
            create([wait]).status_code,
            create([{**wait, "max_days": 0}]).status_code,
            create([{**wait, "max_days": 366}]).status_code,
        ]
        unknown = create([{**wait, "field_key": "unknown", "max_days": 2}])
        assert unknown.status_code == 201, unknown.text
        refused = activate(unknown)
        result["refused_activate"] = [refused.status_code, refused.json()["detail"]["rule"]]

        made = create([{**wait, "max_days": 2}, {"type": "add_tag", "tag_id": tag}])
        result["stored"] = made.json()["definition"]["yes"][0]
        result["activated"] = activate(made).status_code

        def contact(name: str, value: int | None = None) -> tuple[dict[str, Any], uuid.UUID]:
            given: dict[str, Any] = {
                "first_name": name,
                "email": f"{name.lower()}.{uuid.uuid4().hex[:6]}@example.org",
            }
            if value is not None:
                given["custom_fields"] = {"seats": value}
            body = client.post(f"{base}/contacts", json=given, headers=headers)
            assert body.status_code == 201, body.text
            sql = (
                "SELECT id FROM crm_app.automation_run"
                " WHERE tenant_id = :t AND contact_id = :c AND automation_id = :a"
            )
            found = _q(a.id, sql, c=body.json()["id"], a=made.json()["id"])
            return body.json(), found[0]["id"]

        def state(run: uuid.UUID) -> dict[str, Any]:
            row = _q(
                a.id,
                "SELECT status, next_step, resume_at, field_wait_until FROM crm_app.automation_run"
                " WHERE tenant_id = :t AND id = :r",
                r=run,
            )[0]
            done = _q(
                a.id,
                "SELECT position, outcome, detail FROM crm_app.automation_step"
                " WHERE tenant_id = :t AND run_id = :r ORDER BY position",
                r=run,
            )
            return {
                "status": row["status"],
                "next_step": row["next_step"],
                "resume_in": _since(row["resume_at"]),
                "wait_ends_in": _since(row["field_wait_until"]),
                "steps": [[s["position"], s["outcome"], s["detail"]] for s in done],
            }

        # Ann has the value already: the step is done at once.
        _, ann = contact("Ann", 5)
        result["ann"] = [automations.advance(a.id, ann), state(ann)]

        # Bob has none: the run stays on the step and looks again in 10
        # minutes; a job retried before then changes nothing.
        bob_contact, bob = contact("Bob")
        result["bob_waiting"] = [automations.advance(a.id, bob), state(bob)]
        later(minutes=5)
        result["bob_early"] = [automations.advance(a.id, bob), state(bob)]
        later(minutes=10)
        result["bob_still"] = [automations.advance(a.id, bob), state(bob)]
        # Bob's seats are filled in: the next look finds the value.
        updated = client.patch(
            f"{base}/contacts/{bob_contact['id']}",
            json={"custom_fields": {"seats": 3}},
            headers={**headers, "If-Match": f'"{bob_contact["version"]}"'},
        )
        assert updated.is_success, updated.text
        later(minutes=20)
        result["bob_found"] = [automations.advance(a.id, bob), state(bob)]

        # Cy never gets one: after the two days the step is skipped and the
        # run goes on.
        later(minutes=0)
        _, cy = contact("Cy")
        automations.advance(a.id, cy)
        later(days=1, hours=23, minutes=55)
        result["cy_last_look"] = [automations.advance(a.id, cy), state(cy)]
        later(days=2, minutes=1)
        result["cy_timed_out"] = [automations.advance(a.id, cy), state(cy)]

        # Dee is waiting when the field is archived: the step is skipped.
        later(minutes=0)
        _, dee = contact("Dee")
        automations.advance(a.id, dee)
        archived = client.post(
            f"{base}/custom-fields/{seats.json()['id']}/archive", headers=headers
        )
        assert archived.is_success, archived.text
        later(minutes=11)
        result["dee_gone"] = [automations.advance(a.id, dee), state(dee)]

        tagged = _q(
            a.id,
            "SELECT c.first_name FROM crm_app.contact_tag ct JOIN crm_app.contact c"
            " ON c.tenant_id = ct.tenant_id AND c.id = ct.contact_id"
            " WHERE ct.tenant_id = :t AND ct.tag_id = :g ORDER BY c.first_name",
            g=tag,
        )
        result["tagged"] = [r["first_name"] for r in tagged]
        history = client.get(f"{base}/automations/{made.json()['id']}/runs", headers=headers)
        result["history"] = history.status_code
        runs = history.json() if history.is_success else []
        items = runs["items"] if isinstance(runs, dict) else runs
        result["history_actions"] = sorted(
            {step["action"] for run in items for step in run["steps"]}
        )
    print("RESULT " + json.dumps(result, default=str))


if __name__ == "__main__":
    main()

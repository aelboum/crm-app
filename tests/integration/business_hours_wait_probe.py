"""Drives the automation step that waits for business hours (decision P8-W)
and prints one `RESULT <json>` line. Run by
`tests/integration/test_business_hours_wait.py`. Seeds a throwaway
workspace and sets the engine's clock. Refuses to run unless
ENVIRONMENT=test.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi.testclient import TestClient
from saas_os.core.identity import issue_session
from saas_os.infra.db import tenant_session_scope
from sqlalchemy import text

from crm_app import automations
from crm_app.app import create_app
from tests.integration.workspace_route_probe import _new_workspace

# Monday 2026-11-09; the hours below are 09:00-17:00 UTC every day.
EARLY = datetime(2026, 11, 9, 3, 0, tzinfo=UTC)
OPENING = datetime(2026, 11, 9, 9, 0, tzinfo=UTC)
MIDDAY = datetime(2026, 11, 9, 12, 0, tzinfo=UTC)


def _q(workspace: uuid.UUID, sql: str, **values: object) -> list[dict[str, Any]]:
    with tenant_session_scope(workspace) as session:
        return [dict(r._mapping) for r in session.execute(text(sql), {"t": workspace, **values})]


def main() -> None:
    if os.environ.get("ENVIRONMENT") != "test":
        raise SystemExit("business_hours_wait_probe runs only with ENVIRONMENT=test")
    a = _new_workspace("bh-wait")
    headers = {"Authorization": f"Bearer {issue_session(a.owner_id)[1]}"}
    base = f"/v1/workspaces/{a.id}"
    result: dict[str, Any] = {}
    clock = {"now": EARLY}
    automations._now = lambda: clock["now"]  # the probe sets the engine clock
    with TestClient(create_app(), follow_redirects=False) as client:
        tag = client.post(f"{base}/tags", json={"name": "Open"}, headers=headers).json()["id"]
        steps = [{"type": "wait_for_business_hours"}, {"type": "add_tag", "tag_id": tag}]
        body = {
            "name": "Work hours",
            "definition": {"trigger": {"type": "contact_created"}, "yes": steps},
        }
        made = client.post(f"{base}/automations", json=body, headers=headers).json()
        bad = {**body, "definition": {**body["definition"], "yes": [{**steps[0], "x": 1}]}}
        result["extra_key"] = client.post(
            f"{base}/automations", json=bad, headers=headers
        ).status_code
        client.post(
            f"{base}/automations/{made['id']}/activate",
            headers={**headers, "If-Match": f'"{made["version"]}"'},
        )

        def contact(name: str) -> uuid.UUID:
            given = {"first_name": name, "email": f"{name}.{uuid.uuid4().hex[:6]}@example.org"}
            cid = client.post(f"{base}/contacts", json=given, headers=headers).json()["id"]
            sql = "SELECT id FROM crm_app.automation_run WHERE tenant_id = :t AND contact_id = :c"
            return _q(a.id, sql, c=cid)[0]["id"]

        def state(run: uuid.UUID) -> dict[str, Any]:
            row = _q(
                a.id,
                "SELECT status, resume_at FROM crm_app.automation_run"
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
                "resume_at": row["resume_at"].isoformat() if row["resume_at"] else None,
                "steps": [[s["position"], s["outcome"], s["detail"]] for s in done],
            }

        # No business hours yet: the step is skipped and the run goes on.
        run = contact("nohours")
        automations.advance(a.id, run)
        result["no_hours"] = state(run)

        settings = client.get(f"{base}/settings", headers=headers).json()
        client.patch(
            f"{base}/settings",
            json={
                "time_zone": "UTC",
                "business_hours": [{"opens": "09:00", "closes": "17:00"}] * 7,
            },
            headers={**headers, "If-Match": f'"{settings["version"]}"'},
        )

        # Before opening: waits until 09:00; a retried job before then changes nothing.
        run = contact("early")
        automations.advance(a.id, run)
        automations.advance(a.id, run)
        result["early"] = state(run)
        clock["now"] = OPENING
        automations.advance(a.id, run)
        result["at_opening"] = state(run)

        # While open: goes straight on.
        clock["now"] = MIDDAY
        run = contact("midday")
        automations.advance(a.id, run)
        result["midday"] = state(run)
    print("RESULT " + json.dumps(result, default=str))


if __name__ == "__main__":
    main()

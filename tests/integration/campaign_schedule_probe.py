"""Drives scheduled campaigns (decision P7-SC) and prints one `RESULT <json>`.

Run in a fresh interpreter by `tests/integration/test_campaign_schedule.py`.
Nothing is sent: the scheduling workspace is a rehearsal workspace (decision
P7-R), so a started campaign's emails are closed unsent, and another
workspace has neither sending nor rehearsal. Seeds throwaway workspaces.
Refuses to run unless ENVIRONMENT=test.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi.testclient import TestClient
from saas_os.core.identity import issue_session
from saas_os.infra.db import session_scope, tenant_session_scope
from sqlalchemy import text

from crm_app import campaigns, suppression
from crm_app.app import create_app
from crm_app.records import Scope
from crm_app.roles import Role
from tests.integration.opportunity_route_probe import _member
from tests.integration.workspace_route_probe import _new_workspace


def _queue_row(campaign_id: str) -> Any:
    with session_scope() as session:
        return session.execute(
            text("SELECT due_at FROM crm_app.campaign_queue WHERE campaign_id = :c"),
            {"c": campaign_id},
        ).one_or_none()


def main() -> None:  # noqa: PLR0915 - one scenario script, read top to bottom
    if os.environ.get("ENVIRONMENT") != "test":
        raise SystemExit("campaign_schedule_probe runs only with ENVIRONMENT=test")
    for name in ("EMAIL_SENDING_ENABLED", "EMAIL_CAMPAIGN_SENDING_ENABLED", "EMAIL_PARENT_DOMAIN"):
        os.environ.pop(name, None)
    a = _new_workspace("schedule-a")
    b = _new_workspace("schedule-b")
    os.environ["CAMPAIGN_REHEARSAL_WORKSPACES"] = str(a.id)
    os.environ["PUBLIC_APP_ORIGIN"] = "https://app.example.test"
    _, member = _member(a, Role.MEMBER)
    tokens = {
        "owner": issue_session(a.owner_id)[1],
        "member": member,
        "other_owner": issue_session(b.owner_id)[1],
    }

    def auth(caller: str = "owner", version: int | None = None) -> dict[str, str]:
        headers = {"Authorization": f"Bearer {tokens[caller]}"}
        if version is not None:
            headers["If-Match"] = f'"{version}"'
        return headers

    base = f"/v1/workspaces/{a.id}"
    result: dict[str, Any] = {}
    with TestClient(create_app(), follow_redirects=False) as client:
        person = client.post(
            f"{base}/contacts",
            json={"first_name": "Ada", "email": "ada@example.test", "lifecycle_stage": "lead"},
            headers=auth(),
        ).json()["id"]
        suppression.record_consent(
            Scope(workspace=a.id, actor=a.owner_id), uuid.UUID(person), "Yes, email me news."
        )
        draft = {
            "name": "Winter news",
            "subject": "News for {{first_name}}",
            "body": "Hello {{first_name}}.",
            "segment": {"stages": ["lead"]},
        }

        def approved(name: str) -> str:
            made = client.post(
                f"{base}/campaigns", json={**draft, "name": name}, headers=auth()
            ).json()
            one = f"{base}/campaigns/{made['id']}"
            for step, version in (("validate", 1), ("submit", 2), ("approve", 3)):
                client.post(f"{one}/{step}", headers=auth(version=version))
            return str(made["id"])

        now = datetime.now(UTC)
        at = (now + timedelta(hours=1)).replace(microsecond=0)
        winter = approved("Winter news")
        one = f"{base}/campaigns/{winter}"
        draft_id = client.post(f"{base}/campaigns", json=draft, headers=auth()).json()["id"]

        def schedule(target: str, when: datetime, caller: str = "owner", version: int = 4) -> Any:
            return client.post(
                f"{target}/schedule",
                json={"at": when.isoformat()},
                headers=auth(caller, version),
            )

        result["refused"] = [
            schedule(one, at, "member").status_code,
            client.post(f"{one}/schedule", json={"at": at.isoformat()}, headers=auth()).status_code,
            schedule(one, now - timedelta(minutes=1)).json()["detail"]["rule"],
            schedule(one, now + timedelta(days=91)).json()["detail"]["code"],
            schedule(one, at.replace(tzinfo=None)).status_code,
            schedule(f"{base}/campaigns/{draft_id}", at, version=1).json()["detail"]["code"],
            schedule(f"/v1/workspaces/{b.id}/campaigns/{winter}", at, "other_owner").status_code,
            client.post(f"{one}/unschedule", headers=auth(version=4)).status_code,
        ]
        scheduled = schedule(one, at).json()
        result["scheduled"] = [
            scheduled["status"],
            scheduled["scheduled_at"] is not None,
            scheduled["version"],
        ]
        result["row_due"] = _queue_row(winter) is not None and _queue_row(winter)[0] is not None
        # Not yet due: the run leaves it approved and the row in place.
        early = campaigns.run_queued(batch=10, now=now)
        result["early"] = [
            early["campaigns"],
            client.get(one, headers=auth()).json()["status"],
            _queue_row(winter) is not None,
        ]
        # Due: queued as the member who scheduled it, processed as a rehearsal.
        due = campaigns.run_queued(batch=10, now=at + timedelta(seconds=1))
        started = client.get(one, headers=auth()).json()
        result["due"] = [
            due["campaigns"],
            started["status"],
            started["scheduled_at"],
            _queue_row(winter) is None,
        ]

        # Editing a scheduled campaign clears the time; the run drops its row.
        spring = approved("Spring news")
        s_one = f"{base}/campaigns/{spring}"
        schedule(s_one, at)
        edited = client.patch(
            s_one, json={"subject": "Spring for {{first_name}}"}, headers=auth(version=5)
        ).json()
        dropped = campaigns.run_queued(batch=10, now=at + timedelta(seconds=1))
        result["edited"] = [
            edited["status"],
            edited["scheduled_at"],
            dropped["campaigns"],
            client.get(s_one, headers=auth()).json()["status"],
            _queue_row(spring) is None,
        ]

        # Unscheduling keeps the approval and removes the row; queuing at once
        # after a schedule replaces it.
        autumn = approved("Autumn news")
        a_one = f"{base}/campaigns/{autumn}"
        schedule(a_one, at)
        cleared = client.post(f"{a_one}/unschedule", headers=auth(version=5)).json()
        result["unscheduled"] = [
            cleared["status"],
            cleared["scheduled_at"],
            _queue_row(autumn) is None,
        ]
        schedule(a_one, at, version=6)
        queued = client.post(f"{a_one}/queue", headers=auth(version=7)).json()
        result["queued_now"] = [
            queued["status"],
            queued["scheduled_at"],
            _queue_row(autumn) is not None and _queue_row(autumn)[0] is None,
        ]
        campaigns.run_queued(batch=10)

        # Workspace b has neither sending nor rehearsal: refused.
        b_draft = client.post(
            f"/v1/workspaces/{b.id}/campaigns", json=draft, headers=auth("other_owner")
        ).json()
        result["unavailable"] = schedule(
            f"/v1/workspaces/{b.id}/campaigns/{b_draft['id']}", at, "other_owner", 1
        ).json()["detail"]["code"]

        with tenant_session_scope(a.id) as session:
            result["audit"] = sorted(
                row[0]
                for row in session.execute(
                    text(
                        "SELECT action || ':' || coalesce(metadata->>'scheduled', '-')"
                        " FROM core.audit_log WHERE tenant_id = :t AND resource_id = :c"
                        " AND action IN ('crm_app.campaign.scheduled',"
                        " 'crm_app.campaign.queued')"
                    ),
                    {"t": a.id, "c": winter},
                )
            )
    print("RESULT " + json.dumps(result, default=str))


if __name__ == "__main__":
    main()

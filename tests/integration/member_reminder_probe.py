"""Drives hosts' in-app appointment reminders (decision N-2) and prints one
`RESULT <json>` line.

Run in a fresh interpreter by `tests/integration/test_member_reminders.py`.
Seeds throwaway workspaces with made-up appointments; the run is given its
clock, so no test waits. Refuses to run unless ENVIRONMENT=test.
"""

from __future__ import annotations

import json
import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi.testclient import TestClient
from saas_os.core.identity import issue_session
from saas_os.infra.db import select, session_scope, tenant_session_scope
from sqlalchemy import text

from crm_app import member_reminders
from crm_app.app import create_app
from crm_app.models import MemberReminderWorkspace
from crm_app.roles import Role
from tests.integration.opportunity_route_probe import _member
from tests.integration.workspace_route_probe import _new_workspace


def _registered(*workspaces: uuid.UUID) -> list[str]:
    with session_scope() as session:
        rows = session.execute(
            select(MemberReminderWorkspace.workspace_id).where(
                MemberReminderWorkspace.workspace_id.in_(workspaces)
            )
        ).scalars()
        return sorted(str(row) for row in rows)


def _count(workspace: uuid.UUID) -> int:
    """This workspace's upcoming-appointment notifications: the run is
    global, and other tests' workspaces may have appointments due too."""
    with tenant_session_scope(workspace) as session:
        return int(
            session.execute(
                text(
                    "SELECT count(*) FROM crm_app.member_notification"
                    " WHERE tenant_id = :t AND kind = 'appointment_upcoming'"
                ),
                {"t": workspace},
            ).scalar_one()
        )


def _run(workspace: uuid.UUID, when: datetime) -> int:
    """Run the reminders at `when`; how many `workspace` got."""
    before = _count(workspace)
    member_reminders.run_due(when)
    return _count(workspace) - before


def main() -> None:  # noqa: PLR0915 - one scenario script, read top to bottom
    if os.environ.get("ENVIRONMENT") != "test":
        raise SystemExit("member_reminder_probe runs only with ENVIRONMENT=test")
    a = _new_workspace("host-remind-a")
    b = _new_workspace("host-remind-b")
    host, host_token = _member(a, Role.MEMBER)
    tokens = {
        "owner": issue_session(a.owner_id)[1],
        "host": host_token,
        "other_owner": issue_session(b.owner_id)[1],
    }

    def auth(caller: str, version: int | None = None) -> dict[str, str]:
        headers = {"Authorization": f"Bearer {tokens[caller]}"}
        if version is not None:
            headers["If-Match"] = f'"{version}"'
        return headers

    now = datetime.now(UTC)
    result: dict[str, Any] = {}
    with TestClient(create_app(), follow_redirects=False) as client:

        def book(workspace: Any, caller: str, owner: uuid.UUID, minutes: float) -> dict[str, Any]:
            start = now + timedelta(minutes=minutes)
            made = client.post(
                f"/v1/workspaces/{workspace.id}/appointments",
                json={
                    "title": "Intro call",
                    "starts_at": start.isoformat(),
                    "ends_at": (start + timedelta(minutes=30)).isoformat(),
                    "host_user_id": str(owner),
                    "allow_conflict": True,
                },
                headers=auth(caller),
            )
            if made.status_code != 201:
                raise SystemExit(f"booking failed: {made.status_code} {made.text[:300]}")
            return made.json()

        def upcoming(workspace: Any, caller: str) -> list[dict[str, Any]]:
            listed = client.get(
                f"/v1/workspaces/{workspace.id}/me/notifications", headers=auth(caller)
            ).json()
            return [
                {"subject_id": item["subject_id"], "actor": item["actor_user_id"]}
                for item in listed["items"]
                if item["kind"] == "appointment_upcoming"
            ]

        def at(start: str, minutes_before: float) -> datetime:
            return datetime.fromisoformat(start) - timedelta(minutes=minutes_before)

        # The owner books the member as host two hours ahead; one ten
        # minutes ahead; one that is cancelled; one in another workspace.
        later = book(a, "owner", host, 120)
        soon = book(a, "owner", host, 10)
        dropped = book(a, "owner", host, 130)
        client.patch(
            f"/v1/workspaces/{a.id}/appointments/{dropped['id']}",
            json={"status": "cancelled"},
            headers=auth("owner", dropped["version"]),
        )
        other = book(b, "other_owner", b.owner_id, 180)
        result["registered"] = _registered(a.id, b.id) == sorted([str(a.id), str(b.id)])

        # Made ten minutes ahead: within the lead time, never reminded of.
        result["short_notice_run"] = _run(a.id, at(soon["starts_at"], 5))
        # Too early, then within 30 minutes, then again: one reminder.
        result["runs"] = [
            _run(a.id, at(later["starts_at"], 40)),
            _run(a.id, at(later["starts_at"], 20)),
            _run(a.id, at(later["starts_at"], 10)),
        ]
        result["host_sees"] = upcoming(a, "host")
        result["later_id"] = later["id"]
        result["owner_sees"] = upcoming(a, "owner")
        result["other_workspace"] = upcoming(b, "other_owner")
        result["soon_or_dropped"] = [
            row["subject_id"]
            for row in result["host_sees"]
            if row["subject_id"] in (soon["id"], dropped["id"])
        ]

        # Workspace b's appointment is reminded of in b only (the clock only moves forward).
        result["other_run"] = _run(b.id, at(other["starts_at"], 20))
        result["other_after"] = len(upcoming(b, "other_owner"))

        # Rescheduled three hours later: reminded of again for its new time.
        current = client.get(
            f"/v1/workspaces/{a.id}/appointments/{later['id']}", headers=auth("owner")
        ).json()
        moved_start = datetime.fromisoformat(later["starts_at"]) + timedelta(hours=3)
        moved = client.patch(
            f"/v1/workspaces/{a.id}/appointments/{later['id']}",
            json={
                "starts_at": moved_start.isoformat(),
                "ends_at": (moved_start + timedelta(minutes=30)).isoformat(),
                "allow_conflict": True,
            },
            headers=auth("owner", current["version"]),
        )
        result["moved_status"] = moved.status_code
        result["after_move"] = _run(a.id, moved_start - timedelta(minutes=15))
        result["host_count_after_move"] = len(upcoming(a, "host"))

        # Two runs at once for a new appointment: one reminder.
        raced = book(a, "owner", host, 240)
        race_at = at(raced["starts_at"], 20)
        before_race = _count(a.id)
        with ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(lambda _: member_reminders.run_due(race_at), (1, 2)))
        with tenant_session_scope(a.id) as session:
            result["race"] = [
                _count(a.id) - before_race,
                session.execute(
                    text(
                        "SELECT count(*) FROM crm_app.member_notification"
                        " WHERE tenant_id = :t AND kind = 'appointment_upcoming'"
                        " AND subject_id = :s"
                    ),
                    {"t": a.id, "s": uuid.UUID(raced["id"])},
                ).scalar_one(),
            ]

        # Once every known appointment has started, the registry row goes.
        member_reminders.run_due(now + timedelta(days=2))
        result["left_after"] = _registered(a.id, b.id)
        member_reminders.register(b.id, now + timedelta(days=3))
        result["forgotten"] = member_reminders.forget_workspace(b.id)

    print("RESULT " + json.dumps(result, default=str))


if __name__ == "__main__":
    main()

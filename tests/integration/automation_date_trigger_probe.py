"""Drives the automation trigger on a contact's date (decision P8-I) and
prints one `RESULT <json>` line.

Run in a fresh interpreter by `tests/integration/test_automation_date_trigger.py`.
The maintenance run's `start_date_reached` is called directly with chosen
times, tomorrow in the workspace's zone, and runs are advanced by calling
the job's function, as the worker would. Seeds throwaway workspaces.
Refuses to run unless ENVIRONMENT=test.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient
from saas_os.core.identity import issue_session
from saas_os.infra.db import session_scope, tenant_session_scope
from sqlalchemy import text

from crm_app import automations
from crm_app.app import create_app
from tests.integration.workspace_route_probe import _new_workspace

ZONE = ZoneInfo("Europe/Amsterdam")


def _q(workspace: uuid.UUID, sql: str, **values: object) -> list[dict[str, Any]]:
    with tenant_session_scope(workspace) as session:
        return [dict(r._mapping) for r in session.execute(text(sql), {"t": workspace, **values})]


def _runs(workspace: uuid.UUID) -> dict[str, list[str]]:
    """Each automation's contacts with a run, by the contact's first name."""
    rows = _q(
        workspace,
        "SELECT a.name, c.first_name FROM crm_app.automation_run r"
        " JOIN crm_app.automation a ON a.tenant_id = r.tenant_id AND a.id = r.automation_id"
        " JOIN crm_app.contact c ON c.tenant_id = r.tenant_id AND c.id = r.contact_id"
        " WHERE r.tenant_id = :t ORDER BY a.name, c.first_name",
    )
    out: dict[str, list[str]] = {}
    for row in rows:
        out.setdefault(row["name"], []).append(row["first_name"])
    return out


def _registered(workspace: uuid.UUID) -> int:
    with session_scope() as session:
        return session.execute(
            text("SELECT count(*) FROM crm_app.automation_date_workspace WHERE workspace_id = :w"),
            {"w": workspace},
        ).scalar_one()


def main() -> None:  # noqa: PLR0915 - one scenario script, read top to bottom
    if os.environ.get("ENVIRONMENT") != "test":
        raise SystemExit("automation_date_trigger_probe runs only with ENVIRONMENT=test")
    a = _new_workspace("date-trigger-a")
    b = _new_workspace("date-trigger-b")
    tokens = {"a": issue_session(a.owner_id)[1], "b": issue_session(b.owner_id)[1]}

    def auth(who: str = "a", version: int | None = None) -> dict[str, str]:
        headers = {"Authorization": f"Bearer {tokens[who]}"}
        if version is not None:
            headers["If-Match"] = f'"{version}"'
        return headers

    # "Today" for the scans is tomorrow in the workspace's zone, so every
    # time chosen is later than the activations.
    today = (datetime.now(ZONE) + timedelta(days=1)).date()

    def at(hour: int, minute: int = 30) -> datetime:
        return datetime.combine(today, time(hour, minute), tzinfo=ZONE)

    result: dict[str, Any] = {}
    with TestClient(create_app(), follow_redirects=False) as client:

        def base(who: str) -> str:
            return f"/v1/workspaces/{(a if who == 'a' else b).id}"

        def field(who: str, **body: object) -> None:
            made = client.post(f"{base(who)}/custom-fields", json=body, headers=auth(who))
            assert made.status_code == 201, made.text

        def contact(who: str, name: str, renewal: str | None) -> dict[str, Any]:
            body: dict[str, Any] = {
                "first_name": name,
                "email": f"{name.lower()}.{uuid.uuid4().hex[:8]}@example.org",
            }
            if renewal is not None:
                body["custom_fields"] = {"renewal": renewal}
            made = client.post(f"{base(who)}/contacts", json=body, headers=auth(who))
            assert made.status_code == 201, made.text
            return made.json()

        for who in ("a", "b"):
            field(who, entity="contact", key="renewal", label="Renewal", field_type="date")
        field("a", entity="contact", key="note", label="Note", field_type="text")
        tag = client.post(f"{base('a')}/tags", json={"name": "due"}, headers=auth()).json()["id"]

        def day(offset: int) -> str:
            return (today + timedelta(days=offset)).isoformat()

        # Contacts first: creating them starts nothing, since no automation
        # has the `contact_created` trigger.
        contact("a", "Ann", day(7))  # renewal in a week: "7 days before" today
        contact("a", "Bob", day(8))  # a day later: not yet
        contact("a", "Cy", None)  # no date
        dee = contact("a", "Dee", day(7))  # archived
        archived = client.post(f"{base('a')}/contacts/{dee['id']}/archive", headers=auth())
        assert archived.is_success, archived.text
        contact("a", "Fay", day(0))  # renewal today
        contact("b", "Eve", day(7))  # another workspace, no automation

        def create(name: str, trigger: dict[str, Any]) -> Any:
            return client.post(
                f"{base('a')}/automations",
                json={
                    "name": name,
                    "definition": {
                        "trigger": {"type": "date_reached", **trigger},
                        "yes": [{"type": "add_tag", "tag_id": tag}],
                    },
                },
                headers=auth(),
            )

        def activate(made: Any) -> Any:
            body = made.json()
            return client.post(
                f"{base('a')}/automations/{body['id']}/activate",
                headers=auth(version=body["version"]),
            )

        # --- Refused when saved (shape) and when activated (the field) -----------------
        result["refused_save"] = [
            create("No hour", {"field_key": "renewal"}).status_code,
            create("Far", {"field_key": "renewal", "hour": 9, "offset_days": 400}).status_code,
        ]
        refused = []
        for key in ("unknown", "note"):
            made = create("Refused", {"field_key": key, "hour": 9})
            assert made.status_code == 201, made.text
            answer = activate(made)
            refused.append([answer.status_code, answer.json()["detail"]["rule"]])
        result["refused_activate"] = refused
        result["registered_before"] = _registered(a.id)

        week = create("Week before", {"field_key": "renewal", "offset_days": -7, "hour": 9})
        on_day = create("On the day", {"field_key": "renewal", "hour": 11})
        result["stored"] = week.json()["definition"]["trigger"]
        result["activated"] = [activate(week).status_code, activate(on_day).status_code]
        result["registered"] = _registered(a.id)

        # 10:30: the week-before automation's hour has come, the other's not.
        result["first"] = automations.start_date_reached(at(10))
        result["after_first"] = _runs(a.id)
        # Before the look is due again: nothing.
        result["too_soon"] = automations.start_date_reached(at(10, 32))
        # 11:30: the on-the-day automation starts Fay; Ann is not started twice.
        result["second"] = automations.start_date_reached(at(11))
        result["after_second"] = _runs(a.id)
        result["other_workspace"] = _runs(b.id)

        # The runs are due at once and do their steps.
        statuses = {}
        for row in _q(a.id, "SELECT id FROM crm_app.automation_run WHERE tenant_id = :t"):
            statuses[str(row["id"])] = automations.advance(a.id, row["id"])
        result["statuses"] = sorted(set(statuses.values()))
        tagged = _q(
            a.id,
            "SELECT c.first_name FROM crm_app.contact_tag ct JOIN crm_app.contact c"
            " ON c.tenant_id = ct.tenant_id AND c.id = ct.contact_id"
            " WHERE ct.tenant_id = :t AND ct.tag_id = :g ORDER BY c.first_name",
            g=tag,
        )
        result["tagged"] = [r["first_name"] for r in tagged]

        # With both paused, the next look finds nothing active and removes
        # the workspace's row.
        for made in (week, on_day):
            current = client.get(f"{base('a')}/automations/{made.json()['id']}", headers=auth())
            paused = client.post(
                f"{base('a')}/automations/{made.json()['id']}/pause",
                headers=auth(version=current.json()["version"]),
            )
            assert paused.is_success, paused.text
        result["paused"] = automations.start_date_reached(at(13))
        result["registered_after"] = _registered(a.id)
    print("RESULT " + json.dumps(result, default=str))


if __name__ == "__main__":
    main()

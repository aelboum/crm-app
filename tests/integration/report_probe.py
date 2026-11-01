"""Seeds a known dataset and reads the reports (decision P10-A); prints one
`RESULT <json>` line.

Run in a fresh interpreter by `tests/integration/test_reports.py`. Records
are created through the routes and then moved to fixed times with SQL, so
every expected figure is known. The workspace keeps the default time zone,
Europe/Amsterdam, so the period 2026-10-01..2026-10-31 starts at
2026-09-30T22:00Z. Refuses to run unless ENVIRONMENT=test.
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
from tests.integration.opportunity_route_probe import _member
from tests.integration.workspace_route_probe import _new_user, _new_workspace

PERIOD = {"start": "2026-10-01", "end": "2026-10-31"}
_MOVE_CONTACT = "UPDATE crm_app.contact SET created_at = :at WHERE tenant_id = :tenant AND id = :id"


def _sql(workspace: uuid.UUID, statement: str, **values: object) -> None:
    with tenant_session_scope(workspace) as session:
        session.execute(text(statement), {"tenant": workspace, **values})


def main() -> None:
    if os.environ.get("ENVIRONMENT") != "test":
        raise SystemExit("report_probe runs only with ENVIRONMENT=test")
    a = _new_workspace("reports-a")
    b = _new_workspace("reports-b")
    admin_id, admin = _member(a, Role.ADMIN)
    _, reader = _member(a, Role.READ_ONLY)
    tokens = {
        "owner": issue_session(a.owner_id)[1],
        "admin": admin,
        "reader": reader,
        "other_owner": issue_session(b.owner_id)[1],
        "outsider": issue_session(_new_user())[1],
    }
    owner = a.owner_id

    def auth(caller: str | None = "owner") -> dict[str, str]:
        return {"Authorization": f"Bearer {tokens[caller]}"} if caller else {}

    base = f"/v1/workspaces/{a.id}"
    result: dict[str, Any] = {"owner": str(owner), "admin": str(admin_id)}
    with TestClient(create_app(), follow_redirects=False) as client:

        def post(path: str, body: dict[str, Any], caller: str = "owner", where: str = base) -> str:
            response = client.post(f"{where}/{path}", json=body, headers=auth(caller))
            assert response.status_code == 201, (path, response.status_code, response.text)
            return str(response.json()["id"])

        # --- Contacts: two in the period (one just after its start in
        # Amsterdam), one just before it, one long before. -----------------------------
        contacts = [
            ("2026-10-05T10:00Z", "manual"),
            ("2026-09-30T22:30Z", "referral"),
            ("2026-09-30T21:30Z", "manual"),
            ("2026-07-01T10:00Z", "manual"),
        ]
        for n, (when, source) in enumerate(contacts):
            made = post(
                "contacts", {"first_name": f"C{n}", "email": f"c{n}@example.test", "source": source}
            )
            _sql(
                a.id,
                _MOVE_CONTACT,
                at=when,
                id=made,
            )
        # Another workspace's contact in the period.
        elsewhere = post(
            "contacts",
            {"first_name": "Elsewhere", "email": "x@example.test"},
            "other_owner",
            f"/v1/workspaces/{b.id}",
        )
        _sql(
            b.id,
            _MOVE_CONTACT,
            at="2026-10-05T10:00Z",
            id=elsewhere,
        )

        # --- Deals --------------------------------------------------------------------------
        client.get(f"{base}/pipelines", headers=auth())
        deals = [
            # created, outcome, closed, amount, currency, owner
            ("2026-10-02T09:00Z", "won", "2026-10-10T09:00Z", "1000.50", "EUR", owner),
            ("2026-09-10T09:00Z", "lost", "2026-10-12T09:00Z", "200", "EUR", owner),
            ("2026-10-03T09:00Z", "open", None, "75", "EUR", owner),
            ("2026-09-01T09:00Z", "won", "2026-09-15T09:00Z", "50", "USD", owner),
            ("2026-10-06T09:00Z", "won", "2026-10-20T09:00Z", "300", "USD", admin_id),
        ]
        for n, (created, outcome, closed, amount, currency, deal_owner) in enumerate(deals):
            made = post("opportunities", {"title": f"D{n}", "amount": amount})
            _sql(
                a.id,
                "UPDATE crm_app.opportunity SET created_at = :created, outcome = :outcome,"
                " closed_at = :closed, currency = :currency, owner_user_id = :owner,"
                " lost_reason = CASE WHEN :outcome = 'lost' THEN 'Price' END"
                " WHERE tenant_id = :tenant AND id = :id",
                created=created,
                outcome=outcome,
                closed=closed,
                currency=currency,
                owner=deal_owner,
                id=made,
            )

        # --- Tasks --------------------------------------------------------------------------
        tasks = [
            # created, due, completed, completed by
            ("2026-10-02T09:00Z", "2026-10-04T09:00Z", "2026-10-03T09:00Z", owner),  # on time
            ("2026-10-02T09:00Z", "2026-10-05T09:00Z", "2026-10-09T09:00Z", admin_id),  # late
            ("2026-09-20T09:00Z", None, "2026-10-01T10:00Z", owner),  # no due time
            ("2026-10-10T09:00Z", "2026-10-01T09:00Z", None, None),  # open, overdue now
            ("2026-09-05T09:00Z", None, "2026-09-06T09:00Z", owner),  # the previous period
        ]
        for n, (created, due, completed, by) in enumerate(tasks):
            made = post("tasks", {"title": f"T{n}"})
            _sql(
                a.id,
                "UPDATE crm_app.task SET created_at = :created, due_at = :due,"
                " completed_at = :completed, completed_by_user_id = :by"
                " WHERE tenant_id = :tenant AND id = :id",
                created=created,
                due=due,
                completed=completed,
                by=by,
                id=made,
            )

        # --- Appointments -------------------------------------------------------------------
        appointments = [
            ("2026-10-03T09:00Z", "completed", owner),
            ("2026-10-04T09:00Z", "no_show", owner),
            ("2026-10-05T09:00Z", "cancelled", owner),
            ("2026-10-06T09:00Z", "confirmed", admin_id),
            ("2026-09-20T09:00Z", "completed", owner),
        ]
        for n, (starts, status, host) in enumerate(appointments):
            made = post(
                "appointments",
                {
                    "title": f"A{n}",
                    "starts_at": "2030-01-01T09:00:00Z",
                    "ends_at": "2030-01-01T09:30:00Z",
                    "host_user_id": str(owner),
                    "allow_conflict": True,
                },
            )
            _sql(
                a.id,
                "UPDATE crm_app.appointment SET starts_at = :starts,"
                " ends_at = CAST(:starts AS timestamptz) + interval '30 minutes', status = :status,"
                " host_user_id = :host,"
                " cancelled_at = CASE WHEN :status = 'cancelled' THEN now() END"
                " WHERE tenant_id = :tenant AND id = :id",
                starts=starts,
                status=status,
                host=host,
                id=made,
            )

        # --- The reports ----------------------------------------------------------------------
        def report(
            kind: str, caller: str | None = "owner", where: str = base, **params: str
        ) -> Any:
            return client.get(
                f"{where}/reports/{kind}", params=params or PERIOD, headers=auth(caller)
            )

        for kind in ("contacts", "deals", "tasks", "appointments"):
            result[kind] = report(kind).json()
        result["other_workspace_contacts"] = report(
            "contacts", "other_owner", f"/v1/workspaces/{b.id}"
        ).json()["created"]
        result["access"] = {
            caller or "anonymous": {
                kind: report(kind, caller).status_code
                for kind in ("contacts", "deals", "tasks", "appointments")
            }
            for caller in ("admin", "reader", "other_owner", "outsider", None)
        }
        result["refusals"] = {
            "end_before_start": report("deals", start="2026-10-31", end="2026-10-01").json(),
            "too_long": report("deals", start="2025-01-01", end="2026-01-02").json(),
            "year": report("deals", start="1800-01-01", end="1800-01-31").json(),
            "missing": report("deals", start="2026-10-01").status_code,
            "extra": report("deals", start="2026-10-01", end="2026-10-31", owner="x").status_code,
            "not_a_date": report("deals", start="yesterday", end="2026-10-31").status_code,
        }
        result["one_day"] = report("contacts", start="2026-10-01", end="2026-10-01").json()

    print("RESULT " + json.dumps(result, default=str))


if __name__ == "__main__":
    main()

"""Drives the campaign report (decision P10-C) and prints one
`RESULT <json>` line.

Run in a fresh interpreter by `tests/integration/test_report_campaigns.py`.
Campaigns are queued and processed as rehearsals (decision P7-R), so no
email is sent; queue times are then moved with SQL to place each campaign
in the period, the one before, or neither. Seeds throwaway workspaces.
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
from saas_os.infra.db import tenant_session_scope
from sqlalchemy import text

from crm_app import campaigns, suppression
from crm_app.app import create_app
from crm_app.records import Scope
from tests.integration.workspace_route_probe import _new_user, _new_workspace


def _sql(workspace: uuid.UUID, statement: str, **values: object) -> None:
    with tenant_session_scope(workspace) as session:
        session.execute(text(statement), {"t": workspace, **values})


def main() -> None:  # noqa: PLR0915 - one scenario script, read top to bottom
    if os.environ.get("ENVIRONMENT") != "test":
        raise SystemExit("report_campaign_probe runs only with ENVIRONMENT=test")
    for name in ("EMAIL_SENDING_ENABLED", "EMAIL_CAMPAIGN_SENDING_ENABLED", "EMAIL_PARENT_DOMAIN"):
        os.environ.pop(name, None)
    a = _new_workspace("report-campaign-a")
    b = _new_workspace("report-campaign-b")
    os.environ["CAMPAIGN_REHEARSAL_WORKSPACES"] = f"{a.id},{b.id}"
    os.environ["PUBLIC_APP_ORIGIN"] = "https://app.example.test"
    tokens = {
        "owner": issue_session(a.owner_id)[1],
        "other_owner": issue_session(b.owner_id)[1],
        "outsider": issue_session(_new_user())[1],
    }

    def auth(caller: str = "owner", version: int | None = None) -> dict[str, str]:
        headers = {"Authorization": f"Bearer {tokens[caller]}"}
        if version is not None:
            headers["If-Match"] = f'"{version}"'
        return headers

    result: dict[str, Any] = {}
    a_base, b_base = f"/v1/workspaces/{a.id}", f"/v1/workspaces/{b.id}"
    with TestClient(create_app(), follow_redirects=False) as client:

        def contact(base: str, caller: str, first: str) -> str:
            email = f"{first.lower()}.{uuid.uuid4().hex[:8]}@example.org"
            made = client.post(
                f"{base}/contacts",
                json={"first_name": first, "email": email, "lifecycle_stage": "lead"},
                headers=auth(caller),
            )
            assert made.status_code == 201, made.text
            workspace = a if base == a_base else b
            scope = Scope(workspace=workspace.id, actor=workspace.owner_id)
            suppression.record_consent(scope, uuid.UUID(made.json()["id"]), "Yes, email me.")
            return made.json()["id"]

        def rehearse(base: str, caller: str, name: str) -> str:
            made = client.post(
                f"{base}/campaigns",
                json={
                    "name": name,
                    "subject": "News for {{first_name}}",
                    "body": "Hello {{ first_name }}, a rehearsal.",
                    "segment": {"stages": ["lead"]},
                },
                headers=auth(caller),
            )
            assert made.status_code == 201, made.text
            one = f"{base}/campaigns/{made.json()['id']}"
            for step, version in (("validate", 1), ("submit", 2), ("approve", 3), ("queue", 4)):
                answer = client.post(f"{one}/{step}", headers=auth(caller, version))
                assert answer.is_success, (step, answer.text)
            campaigns.run_queued(batch=10)
            return made.json()["id"]

        ada = contact(a_base, "owner", "Ada")
        contact(a_base, "owner", "Ben")
        contact(b_base, "other_owner", "Cy")

        # Three campaigns of two recipients each in a; one in b.
        latest = rehearse(a_base, "owner", "Latest")
        earlier = rehearse(a_base, "owner", "Earlier")
        before = rehearse(a_base, "owner", "Before")
        outside = rehearse(a_base, "owner", "Outside")
        rehearse(b_base, "other_owner", "Other workspace")
        # A draft is never queued, so never counted.
        client.post(
            f"{a_base}/campaigns",
            json={
                "name": "Draft",
                "subject": "S",
                "body": "B",
                "segment": {"stages": ["lead"]},
            },
            headers=auth(),
        )

        # The period is the last 10 days up to today; before is 10 days earlier.
        now = datetime.now(UTC)
        for campaign, at in (
            (latest, now - timedelta(hours=1)),
            (earlier, now - timedelta(days=3)),
            (before, now - timedelta(days=15)),
            (outside, now - timedelta(days=40)),
        ):
            _sql(
                a.id,
                "UPDATE crm_app.campaign SET queued_at = :at WHERE tenant_id = :t AND id = :c",
                at=at,
                c=campaign,
            )
        _sql(
            a.id,
            "UPDATE crm_app.campaign_recipient SET status = 'unsubscribed'"
            " WHERE tenant_id = :t AND campaign_id = :c AND contact_id = :p",
            c=latest,
            p=ada,
        )

        today = now.date()
        period = {"start": str(today - timedelta(days=9)), "end": str(today)}

        def report(caller: str = "owner", base: str = a_base, **query: str) -> Any:
            return client.get(
                f"{base}/reports/campaigns", params=query or period, headers=auth(caller)
            )

        result["ids"] = {"latest": latest, "earlier": earlier}
        result["report"] = report().json()
        result["other_workspace"] = report("other_owner", b_base).json()["campaigns"]
        result["cross"] = report("other_owner").status_code
        result["outsider"] = report("outsider").status_code
        result["bad_period"] = report(start=str(today), end=str(today - timedelta(days=1)))
        result["bad_period"] = result["bad_period"].status_code

        # --- The same report as CSV (decision P10-C.1) -----------------------------
        exported = client.get(
            f"{a_base}/reports/campaigns/export.csv", params=period, headers=auth()
        )
        result["csv"] = {
            "status": exported.status_code,
            "type": exported.headers.get("content-type"),
            "disposition": exported.headers.get("content-disposition"),
            "lines": exported.content.decode("utf-8-sig").splitlines(),
        }
        result["csv_outsider"] = client.get(
            f"{a_base}/reports/campaigns/export.csv", params=period, headers=auth("outsider")
        ).status_code
    print("RESULT " + json.dumps(result, default=str))


if __name__ == "__main__":
    main()

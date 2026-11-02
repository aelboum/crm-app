"""Drives unverified public matches and consent confirmation (decision P7-V)
and prints one `RESULT <json>` line.

Run in a fresh interpreter by `tests/integration/test_consent_confirmations.py`.
Nothing is sent: the confirmation email is only queued (sending is off), and
its link is read back from the queued text. Refuses to run unless
ENVIRONMENT=test.
"""

from __future__ import annotations

import json
import os
import re
import secrets
import uuid
from typing import Any

from fastapi.testclient import TestClient
from saas_os.core.identity import issue_session
from saas_os.infra.db import tenant_session_scope
from sqlalchemy import text

from crm_app.app import create_app
from tests.integration.workspace_route_probe import _new_workspace

FIELDS = [
    {"key": "first", "type": "text", "label": "First name", "required": True,
     "target": "first_name"},
    {"key": "email", "type": "email", "label": "Email", "required": True, "target": "email"},
]  # fmt: skip
WORDING = "Yes, send me news."
STAGE = {"type": "set_lifecycle_stage", "stage": "customer"}


def _q(workspace: uuid.UUID, sql: str, **values: object) -> list[dict[str, Any]]:
    with tenant_session_scope(workspace) as session:
        return [dict(r._mapping) for r in session.execute(text(sql), {"t": workspace, **values})]


def main() -> None:
    if os.environ.get("ENVIRONMENT") != "test":
        raise SystemExit("consent_confirmation_probe runs only with ENVIRONMENT=test")
    os.environ.pop("EMAIL_SENDING_ENABLED", None)
    os.environ["PUBLIC_APP_ORIGIN"] = "https://app.example.org"
    a = _new_workspace("consent-a")
    b = _new_workspace("consent-b")
    owner = {"Authorization": f"Bearer {issue_session(a.owner_id)[1]}"}
    base = f"/v1/workspaces/{a.id}"
    result: dict[str, Any] = {}
    with TestClient(create_app(), follow_redirects=False) as client:
        tag = client.post(f"{base}/tags", json={"name": "Web lead"}, headers=owner).json()["id"]
        form = client.post(
            f"{base}/forms",
            json={"name": "News", "fields": FIELDS, "tag_id": tag, "consent_text": WORDING},
            headers=owner,
        ).json()
        client.patch(
            f"{base}/forms/{form['id']}",
            json={"status": "published"},
            headers={**owner, "If-Match": '"1"'},
        )
        for definition in (
            {"trigger": {"type": "form_submitted"}, "yes": [STAGE]},
            {"trigger": {"type": "tag_added", "tag_id": tag}, "yes": [STAGE]},
        ):  # fmt: skip
            made = client.post(
                f"{base}/automations",
                json={"name": f"A {secrets.token_hex(2)}", "definition": definition},
                headers=owner,
            ).json()
            client.post(
                f"{base}/automations/{made['id']}/activate",
                headers={**owner, "If-Match": f'"{made["version"]}"'},
            )
        ada = client.post(
            f"{base}/contacts",
            json={"first_name": "Ada", "email": "ada@customer.example.org"},
            headers=owner,
        ).json()
        public = f"/v1/public/forms/{a.id}/{form['public_key']}"

        def submit(email: str, idem: str) -> int:
            return client.post(
                public,
                json={"answers": {"first": "Someone", "email": email}, "consent": True},
                headers={"Idempotency-Key": idem},
            ).status_code

        # --- A stranger types an existing contact's email ---------------------------------
        result["matched_submit"] = submit("ada@customer.example.org", "m-1")
        result["matched"] = {
            "tags": _q(
                a.id,
                "SELECT count(*) AS n FROM crm_app.contact_tag"
                " WHERE tenant_id = :t AND contact_id = :c",
                c=ada["id"],
            )[0]["n"],
            "consent": _q(
                a.id,
                "SELECT count(*) AS n FROM crm_app.consent_record"
                " WHERE tenant_id = :t AND contact_id = :c",
                c=ada["id"],
            )[0]["n"],
            "runs": _q(
                a.id,
                "SELECT count(*) AS n FROM crm_app.automation_run"
                " WHERE tenant_id = :t AND contact_id = :c",
                c=ada["id"],
            )[0]["n"],
            "stage": _q(
                a.id,
                "SELECT lifecycle_stage FROM crm_app.contact WHERE tenant_id = :t AND id = :c",
                c=ada["id"],
            )[0]["lifecycle_stage"],
            "submission": _q(
                a.id,
                "SELECT outcome, consent FROM crm_app.form_submission"
                " WHERE tenant_id = :t AND contact_id = :c",
                c=ada["id"],
            ),
        }
        pending = _q(
            a.id,
            "SELECT c.token_hash, c.confirmed_at, m.purpose, m.status, m.to_email, m.text_body"
            " FROM crm_app.consent_confirmation c JOIN crm_app.email_message m"
            " ON m.tenant_id = c.tenant_id AND m.id = c.email_message_id"
            " WHERE c.tenant_id = :t AND c.contact_id = :c",
            c=ada["id"],
        )
        link = re.search(
            r"https://app\.example\.org/app/c/[0-9a-f-]+#([A-Za-z0-9_-]+)", pending[0]["text_body"]
        )
        token = link.group(1) if link else ""
        result["pending"] = [
            len(pending),
            pending[0]["purpose"],
            pending[0]["status"],
            pending[0]["to_email"],
            pending[0]["confirmed_at"],
            len(pending[0]["token_hash"]),
            token not in json.dumps([pending[0]["token_hash"]]),
            bool(token),
        ]
        audits = (
            _q(
                a.id,
                "SELECT action FROM core.audit_log_entries WHERE tenant_id = :t"
                " AND action LIKE 'crm_app.consent_confirmation.%' ORDER BY created_at",
            )
            if False
            else []
        )
        del audits

        # --- Confirming: once, idempotent, bound to its workspace ---------------------------
        confirm = f"/v1/public/consent/{a.id}/confirm"
        result["confirm"] = [
            client.post(f"/v1/public/consent/{b.id}/confirm", json={"token": token}).status_code,
            client.post(confirm, json={"token": "x" * 43}).status_code,
            client.post(confirm, json={"token": token}).status_code,
            client.post(confirm, json={"token": token}).status_code,
            _q(
                a.id,
                "SELECT status, method, wording FROM crm_app.consent_record"
                " WHERE tenant_id = :t AND contact_id = :c",
                c=ada["id"],
            ),
        ]

        # --- An expired link confirms nothing ----------------------------------------------
        submit("ada@customer.example.org", "m-2")
        # A second submission at once queues no second email (one pending
        # confirmation per contact and form a day).
        submit("ada@customer.example.org", "m-3")
        result["pending_after_repeat"] = _q(
            a.id,
            "SELECT count(*) AS n FROM crm_app.consent_confirmation"
            " WHERE tenant_id = :t AND contact_id = :c AND confirmed_at IS NULL",
            c=ada["id"],
        )[0]["n"]
        latest = _q(
            a.id,
            "SELECT c.id AS id, m.text_body FROM crm_app.consent_confirmation c"
            " JOIN crm_app.email_message m ON m.tenant_id = c.tenant_id"
            " AND m.id = c.email_message_id"
            " WHERE c.tenant_id = :t AND c.confirmed_at IS NULL",
        )[0]
        expired_token = re.search(r"#([A-Za-z0-9_-]+)", latest["text_body"]).group(1)  # type: ignore[union-attr]
        with tenant_session_scope(a.id) as session:
            session.execute(
                text(
                    "UPDATE crm_app.consent_confirmation SET expires_at = created_at"
                    " - interval '1 day', created_at = created_at - interval '8 days'"
                    " WHERE tenant_id = :t AND id = :i"
                ),
                {"t": a.id, "i": latest["id"]},
            )
        result["expired"] = [
            client.post(confirm, json={"token": expired_token}).status_code,
            _q(
                a.id,
                "SELECT count(*) AS n FROM crm_app.consent_record"
                " WHERE tenant_id = :t AND contact_id = :c",
                c=ada["id"],
            )[0]["n"],
        ]

        # --- A new person: unchanged behaviour ----------------------------------------------
        result["new_submit"] = submit("new.person@customer.example.org", "n-1")
        new = _q(
            a.id,
            "SELECT id FROM crm_app.contact WHERE tenant_id = :t AND email = :e",
            e="new.person@customer.example.org",
        )[0]["id"]
        result["new"] = {
            "tags": _q(
                a.id,
                "SELECT count(*) AS n FROM crm_app.contact_tag"
                " WHERE tenant_id = :t AND contact_id = :c",
                c=new,
            )[0]["n"],
            "consent": _q(
                a.id,
                "SELECT method FROM crm_app.consent_record"
                " WHERE tenant_id = :t AND contact_id = :c",
                c=new,
            ),
            "runs": _q(
                a.id,
                "SELECT count(*) AS n FROM crm_app.automation_run"
                " WHERE tenant_id = :t AND contact_id = :c",
                c=new,
            )[0]["n"],
            "confirmations": _q(
                a.id,
                "SELECT count(*) AS n FROM crm_app.consent_confirmation"
                " WHERE tenant_id = :t AND contact_id = :c",
                c=new,
            )[0]["n"],
        }
    print("RESULT " + json.dumps(result, default=str))


if __name__ == "__main__":
    main()

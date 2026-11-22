"""Drives the automation step that sends one marketing email (decision P8-E)
and prints one `RESULT <json>` line.

Run in a fresh interpreter by `tests/integration/test_automation_email.py`.
The probe sets the engine clock, makes campaign sending available in this
process only, and hands emails to a recording provider: nothing leaves the
machine. Seeds throwaway workspaces. Refuses to run unless ENVIRONMENT=test.
"""

from __future__ import annotations

import json
import os
import re
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi.testclient import TestClient
from saas_os.core.identity import issue_session
from saas_os.infra.db import tenant_session_scope
from sqlalchemy import text

from crm_app import automations, campaigns, emails, suppression
from crm_app.app import create_app
from crm_app.records import RecordError, Scope
from crm_app.roles import Role
from tests.integration.campaign_probe import Recorder
from tests.integration.opportunity_route_probe import _member
from tests.integration.workspace_route_probe import _new_workspace

START = datetime.now(UTC).replace(microsecond=0)
ORIGIN = "https://app.example.test"
_SWITCHES = ("EMAIL_SENDING_ENABLED", "EMAIL_CAMPAIGN_SENDING_ENABLED", "EMAIL_PARENT_DOMAIN")


def _q(workspace: uuid.UUID, sql: str, **values: object) -> list[dict[str, Any]]:
    with tenant_session_scope(workspace) as session:
        return [dict(r._mapping) for r in session.execute(text(sql), {"t": workspace, **values})]


def _sending(on: bool) -> None:
    campaigns.SENDING_AVAILABLE = on
    for name in _SWITCHES:
        os.environ.pop(name, None)
    if on:
        os.environ["EMAIL_SENDING_ENABLED"] = "true"
        os.environ["EMAIL_CAMPAIGN_SENDING_ENABLED"] = "true"
        os.environ["EMAIL_PARENT_DOMAIN"] = "example.test"


def main() -> None:  # noqa: PLR0915 - one scenario script, read top to bottom
    if os.environ.get("ENVIRONMENT") != "test":
        raise SystemExit("automation_email_probe runs only with ENVIRONMENT=test")
    _sending(False)
    os.environ.pop("CAMPAIGN_REHEARSAL_WORKSPACES", None)
    os.environ["PUBLIC_APP_ORIGIN"] = ORIGIN
    a = _new_workspace("automation-email-a")
    b = _new_workspace("automation-email-b")
    member, _ = _member(a, Role.MEMBER)
    result: dict[str, Any] = {}
    clock = {"now": START}
    automations._now = lambda: clock["now"]  # the probe sets the engine clock

    def later(**delta: float) -> None:
        clock["now"] = START + timedelta(**delta)

    with TestClient(create_app(), follow_redirects=False) as client:

        def setup(workspace: Any) -> dict[str, Any]:
            headers = {"Authorization": f"Bearer {issue_session(workspace.owner_id)[1]}"}
            base = f"/v1/workspaces/{workspace.id}"
            template = client.post(
                f"{base}/email-templates",
                json={
                    "name": "Welcome",
                    "subject": "Welcome {{first_name}}",
                    "body": "Hello {{first_name}},\nthanks for joining.",
                },
                headers=headers,
            )
            assert template.status_code == 201, template.text
            return {"headers": headers, "base": base, "template": template.json()}

        def create(ctx: dict[str, Any], steps: list[dict[str, Any]]) -> Any:
            return client.post(
                f"{ctx['base']}/automations",
                json={
                    "name": f"Welcome {uuid.uuid4().hex[:4]}",
                    "definition": {"trigger": {"type": "contact_created"}, "yes": steps},
                },
                headers=ctx["headers"],
            )

        def activate(ctx: dict[str, Any], made: Any) -> Any:
            body = made.json()
            return client.post(
                f"{ctx['base']}/automations/{body['id']}/activate",
                headers={**ctx["headers"], "If-Match": f'"{body["version"]}"'},
            )

        ctx = setup(a)
        send = {"type": "send_email", "template_id": ctx["template"]["id"]}

        # --- Refused when saved (shape) and when activated -------------------------
        result["refused_save"] = [
            create(ctx, [{**send, "daily_limit": 0}]).status_code,
            create(ctx, [{**send, "daily_limit": 1001}]).status_code,
            create(ctx, [{"type": "send_email", "template_id": "nope"}]).status_code,
        ]
        unknown = create(ctx, [{**send, "template_id": str(uuid.uuid4())}])
        assert unknown.status_code == 201, unknown.text
        refused = activate(ctx, unknown)
        result["refused_activate"] = [refused.status_code, refused.json()["detail"]["rule"]]
        # Content sent with a draft is never kept: the template decides.
        made = create(ctx, [{**send, "daily_limit": 2, "subject": "Mine", "body": "Mine"}])
        result["stored"] = made.json()["definition"]["yes"][0]
        # A member without the right to approve campaigns cannot activate it,
        # even through the service (the route already needs Owner or Admin).
        try:
            automations.activate(
                Scope(workspace=a.id, actor=member),
                uuid.UUID(made.json()["id"]),
                expected_version=made.json()["version"],
            )
            result["member_activate"] = "activated"
        except RecordError as exc:
            result["member_activate"] = [exc.status, exc.code]
        activated = activate(ctx, made)
        result["activated"] = activated.status_code
        automation_id = made.json()["id"]
        version = _q(
            a.id,
            "SELECT definition FROM crm_app.automation_version"
            " WHERE tenant_id = :t AND automation_id = :a",
            a=automation_id,
        )[0]["definition"]
        result["frozen"] = version["yes"][0]
        # Editing the template afterwards changes nothing that is sent.
        edited = client.patch(
            f"{ctx['base']}/email-templates/{ctx['template']['id']}",
            json={"subject": "Changed {{first_name}}"},
            headers={**ctx["headers"], "If-Match": f'"{ctx["template"]["version"]}"'},
        )
        assert edited.status_code == 200, edited.text
        owner_scope = Scope(workspace=a.id, actor=a.owner_id)

        def contact(
            name: str, *, consent: bool = True, email: bool = True
        ) -> tuple[uuid.UUID, uuid.UUID]:
            given: dict[str, Any] = {"first_name": name}
            if email:
                given["email"] = f"{name.lower()}.{uuid.uuid4().hex[:6]}@example.test"
            else:
                given["phone"] = "+31 20 123 4567"
            body = client.post(f"{ctx['base']}/contacts", json=given, headers=ctx["headers"])
            assert body.status_code == 201, body.text
            contact_id = uuid.UUID(body.json()["id"])
            if consent and email:
                suppression.record_consent(owner_scope, contact_id, "Yes, email me news.")
            sql = (
                "SELECT id FROM crm_app.automation_run"
                " WHERE tenant_id = :t AND contact_id = :c AND automation_id = :a"
            )
            return contact_id, _q(a.id, sql, c=contact_id, a=automation_id)[0]["id"]

        def steps(run: uuid.UUID) -> list[list[Any]]:
            return [
                [s["outcome"], s["detail"]]
                for s in _q(
                    a.id,
                    "SELECT outcome, detail FROM crm_app.automation_step"
                    " WHERE tenant_id = :t AND run_id = :r ORDER BY position",
                    r=run,
                )
            ]

        def sent_count() -> int:
            return len(
                _q(
                    a.id,
                    "SELECT id FROM crm_app.automation_email"
                    " WHERE tenant_id = :t AND automation_id = :a",
                    a=automation_id,
                )
            )

        # --- Sending unavailable: the step is skipped, nothing is queued ----------
        _, ann = contact("Ann")
        result["ann"] = [automations.advance(a.id, ann), steps(ann), sent_count()]

        # --- Sending available ------------------------------------------------------
        _sending(True)
        recorder = Recorder()
        bob_id, bob = contact("Bob")
        queued: list[uuid.UUID] = []
        result["bob"] = [automations.advance(a.id, bob, queued), steps(bob), len(queued)]
        message = _q(
            a.id,
            "SELECT purpose, subject, text_body, status, list_unsubscribe_url"
            " FROM crm_app.email_message WHERE tenant_id = :t AND id = :e",
            e=queued[0],
        )[0]
        token = re.search(r"/app/u/[0-9a-f-]+#([0-9a-f]{32})", message["text_body"])
        result["bob_email"] = [
            message["purpose"],
            message["subject"],
            message["text_body"].startswith("Hello Bob,\nthanks for joining."),
            message["status"],
            bool(token and message["list_unsubscribe_url"].endswith(f"/{a.id}/{token.group(1)}")),
        ]
        result["bob_sent"] = emails.send(a.id, queued[0], provider=recorder)
        result["bob_headers"] = [
            len(recorder.sent[-1].list_unsubscribe),
            recorder.sent[-1].list_unsubscribe_post,
        ]
        # A retried job finds the step done and queues nothing more.
        result["bob_again"] = [automations.advance(a.id, bob), sent_count()]

        _, cal = contact("Cal", consent=False)
        result["cal"] = [automations.advance(a.id, cal), steps(cal)]
        _, dan = contact("Dan", email=False)
        result["dan"] = [automations.advance(a.id, dan), steps(dan)]
        _, eve = contact("Eve")
        result["eve"] = [automations.advance(a.id, eve), steps(eve)]
        # The limit of 2 in 24 hours is used up.
        _, fay = contact("Fay")
        result["fay"] = [automations.advance(a.id, fay), steps(fay), sent_count()]
        later(hours=25)
        _, gus = contact("Gus")
        result["gus"] = [automations.advance(a.id, gus), steps(gus), sent_count()]

        # --- Unsubscribing from Bob's email ------------------------------------------
        path = f"/v1/public/unsubscribe/{a.id}/{token.group(1) if token else 'x'}"
        result["unsubscribe"] = [
            client.post(path).status_code,
            client.post(path).status_code,
            client.post(
                f"/v1/public/unsubscribe/{b.id}/{token.group(1) if token else 'x'}"
            ).status_code,
        ]
        result["unsubscribed"] = [
            _q(
                a.id,
                "SELECT status FROM crm_app.automation_email"
                " WHERE tenant_id = :t AND contact_id = :c",
                c=bob_id,
            )[0]["status"],
            len(
                _q(
                    a.id,
                    "SELECT id FROM crm_app.suppression WHERE tenant_id = :t"
                    " AND reason = 'unsubscribed'",
                )
            ),
        ]
        # The link keeps working once the automation is deleted.
        eve_body = _q(
            a.id,
            "SELECT m.text_body FROM crm_app.automation_email e"
            " JOIN crm_app.email_message m ON m.tenant_id = e.tenant_id"
            " AND m.id = e.email_message_id"
            " WHERE e.tenant_id = :t AND e.run_id = :r",
            r=eve,
        )[0]["text_body"]
        eve_token = re.search(r"#([0-9a-f]{32})", eve_body)
        deleted = client.delete(
            f"{ctx['base']}/automations/{automation_id}", headers=ctx["headers"]
        )
        result["after_delete"] = [
            deleted.status_code,
            client.post(
                f"/v1/public/unsubscribe/{a.id}/{eve_token.group(1) if eve_token else 'x'}"
            ).status_code,
            len(
                _q(
                    a.id,
                    "SELECT id FROM crm_app.automation_email"
                    " WHERE tenant_id = :t AND automation_id IS NULL AND status = 'unsubscribed'",
                )
            ),
        ]

        # --- Rehearsal: workspace b named, sending unavailable -----------------------
        _sending(False)
        os.environ["CAMPAIGN_REHEARSAL_WORKSPACES"] = str(b.id)
        later(hours=26)
        ctx_b = setup(b)
        made_b = create(ctx_b, [{"type": "send_email", "template_id": ctx_b["template"]["id"]}])
        assert activate(ctx_b, made_b).status_code == 200
        person = client.post(
            f"{ctx_b['base']}/contacts",
            json={"first_name": "Ida", "email": "ida@example.test"},
            headers=ctx_b["headers"],
        ).json()["id"]
        suppression.record_consent(
            Scope(workspace=b.id, actor=b.owner_id), uuid.UUID(person), "Yes, email me news."
        )
        run_b = _q(
            b.id,
            "SELECT id FROM crm_app.automation_run WHERE tenant_id = :t AND contact_id = :c",
            c=person,
        )[0]["id"]
        queued_b: list[uuid.UUID] = []
        status_b = automations.advance(b.id, run_b, queued_b)
        rehearsed = _q(
            b.id,
            "SELECT m.status, m.last_error FROM crm_app.automation_email e"
            " JOIN crm_app.email_message m ON m.tenant_id = e.tenant_id"
            " AND m.id = e.email_message_id WHERE e.tenant_id = :t",
        )
        result["rehearsal"] = [
            status_b,
            [
                [s["outcome"], s["detail"]]
                for s in _q(
                    b.id,
                    "SELECT outcome, detail FROM crm_app.automation_step"
                    " WHERE tenant_id = :t AND run_id = :r",
                    r=run_b,
                )
            ],
            len(queued_b),
            [[r["status"], r["last_error"]] for r in rehearsed],
        ]
        # Workspace a cannot see workspace b's rows.
        result["isolated"] = len(
            _q(a.id, "SELECT id FROM crm_app.automation_email WHERE tenant_id = :b", b=b.id)
        )
        os.environ.pop("CAMPAIGN_REHEARSAL_WORKSPACES", None)

    print("RESULT " + json.dumps(result, default=str))


if __name__ == "__main__":
    main()

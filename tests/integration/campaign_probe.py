"""Drives campaigns (decision P7-C) and prints one `RESULT <json>` line.

Run in a fresh interpreter by `tests/integration/test_campaigns.py`.
Nothing is sent: queuing is refused while campaign sending is unavailable,
and the one path that queues campaign emails is exercised with sending made
available in this process only, its emails handed to a recording provider.
Seeds throwaway workspaces. Refuses to run unless ENVIRONMENT=test.
"""

from __future__ import annotations

import json
import os
import re
import uuid
from typing import Any

from fastapi.testclient import TestClient
from saas_os.core.email import EmailMessage, EmailSendResult
from saas_os.core.identity import issue_session
from saas_os.infra.db import session_scope, tenant_session_scope
from sqlalchemy import text

from crm_app import campaigns, emails, suppression
from crm_app.app import create_app
from crm_app.records import Scope
from crm_app.roles import Role
from tests.integration.opportunity_route_probe import _member
from tests.integration.workspace_route_probe import _new_user, _new_workspace


class Recorder:
    def __init__(self) -> None:
        self.sent: list[EmailMessage] = []

    def send(self, message: EmailMessage) -> EmailSendResult:
        self.sent.append(message)
        return EmailSendResult(accepted=True, provider_message_id=f"re_{uuid.uuid4().hex}")


def _scalar(workspace: uuid.UUID, sql: str, **values: object) -> Any:
    with tenant_session_scope(workspace) as session:
        return session.execute(text(sql), {"t": workspace, **values}).scalar_one()


def main() -> None:  # noqa: PLR0915 - one scenario script, read top to bottom
    if os.environ.get("ENVIRONMENT") != "test":
        raise SystemExit("campaign_probe runs only with ENVIRONMENT=test")
    for name in ("EMAIL_SENDING_ENABLED", "EMAIL_CAMPAIGN_SENDING_ENABLED", "EMAIL_PARENT_DOMAIN"):
        os.environ.pop(name, None)
    a = _new_workspace("campaign-a")
    b = _new_workspace("campaign-b")
    _, member = _member(a, Role.MEMBER)
    _, reader = _member(a, Role.READ_ONLY)
    tokens = {
        "owner": issue_session(a.owner_id)[1],
        "member": member,
        "reader": reader,
        "other_owner": issue_session(b.owner_id)[1],
        "outsider": issue_session(_new_user())[1],
    }

    def auth(caller: str = "owner", version: int | None = None) -> dict[str, str]:
        headers = {"Authorization": f"Bearer {tokens[caller]}"}
        if version is not None:
            headers["If-Match"] = f'"{version}"'
        return headers

    owner_scope = Scope(workspace=a.id, actor=a.owner_id)
    base = f"/v1/workspaces/{a.id}"
    result: dict[str, Any] = {}
    with TestClient(create_app(), follow_redirects=False) as client:

        def contact(first: str, email: str | None, stage: str = "lead") -> str:
            body: dict[str, Any] = {"first_name": first, "lifecycle_stage": stage}
            if email:
                body["email"] = email
            else:
                body["phone"] = "+31 20 123 4567"
            return str(client.post(f"{base}/contacts", json=body, headers=auth()).json()["id"])

        ada = contact("Ada", "ada@example.test")
        contact("Grace", "grace@example.test")  # no consent: excluded
        mal = contact("Mal", "mal@example.test")
        contact("Phoneonly", None)
        contact("Cust", "cust@example.test", stage="customer")
        for person in (ada, mal):
            suppression.record_consent(owner_scope, uuid.UUID(person), "Yes, email me news.")
        suppression.add(owner_scope, ["mal@example.test"], reason="manual", note=None)

        draft = {
            "name": "Autumn news",
            "subject": "News for {{first_name}}",
            "body": "Hello {{ first_name }},\nour autumn update.",
            "segment": {"stages": ["lead"]},
        }
        made = client.post(f"{base}/campaigns", json=draft, headers=auth("member"))
        camp = made.json()
        one = f"{base}/campaigns/{camp['id']}"
        result["created"] = [made.status_code, camp.get("status"), camp.get("approved")]
        result["refused"] = [
            client.post(
                f"{base}/campaigns", json={**draft, "body": "Hi {{secret}}"}, headers=auth()
            ).status_code,
            client.post(
                f"{base}/campaigns", json={**draft, "segment": {}}, headers=auth()
            ).status_code,
            client.post(
                f"{base}/campaigns",
                json={**draft, "segment": {"stages": ["lead"], "all_contacts": True}},
                headers=auth(),
            ).status_code,
            client.post(f"{base}/campaigns", json=draft, headers=auth("reader")).status_code,
            client.post(f"{base}/campaigns", json=draft, headers=auth("other_owner")).status_code,
            client.post(f"{base}/campaigns", json=draft, headers=auth("outsider")).status_code,
        ]
        result["no_version"] = client.post(f"{one}/validate", headers=auth("member")).status_code

        validated = client.post(f"{one}/validate", headers=auth("member", 1)).json()
        result["validated"] = [validated["status"], validated["estimate"]]
        result["early_approve"] = client.post(f"{one}/approve", headers=auth(version=2)).json()
        submitted = client.post(f"{one}/submit", headers=auth("member", 2)).json()
        result["submitted"] = submitted["status"]
        result["member_approve"] = client.post(
            f"{one}/approve", headers=auth("member", 3)
        ).status_code
        result["stale_approve"] = client.post(f"{one}/approve", headers=auth(version=2)).status_code
        approved = client.post(f"{one}/approve", headers=auth(version=3)).json()
        result["approved"] = [approved["status"], approved["approved"]]

        # Changing an approved campaign withdraws its approval.
        edited = client.patch(
            one, json={"subject": "Big news for {{first_name}}"}, headers=auth("member", 4)
        ).json()
        result["edited"] = [edited["status"], edited["approved"], edited["estimate"]]
        result["approve_after_edit"] = client.post(
            f"{one}/approve", headers=auth(version=5)
        ).json()["detail"]
        client.post(f"{one}/validate", headers=auth("member", 5))
        client.post(f"{one}/submit", headers=auth("member", 6))
        rejected = client.post(
            f"{one}/reject", json={"note": "Shorten it"}, headers=auth(version=7)
        ).json()
        result["rejected"] = [rejected["status"], rejected["decision_note"]]
        client.post(f"{one}/validate", headers=auth("member", 8))
        client.post(f"{one}/submit", headers=auth("member", 9))
        final = client.post(f"{one}/approve", headers=auth(version=10)).json()
        result["reapproved"] = [final["status"], final["approved"]]

        # Queuing is refused while campaign sending is unavailable.
        queue = f"{one}/queue"
        result["queue_unavailable"] = [
            client.post(queue, headers=auth(version=11)).json()["detail"],
            client.post(queue, headers=auth("member", 11)).status_code,
        ]
        listed = client.get(f"{base}/campaigns", headers=auth("reader")).json()
        result["listed"] = [len(listed["items"]), listed["sending_available"]]
        result["isolation"] = [
            len(
                client.get(f"/v1/workspaces/{b.id}/campaigns", headers=auth("other_owner")).json()[
                    "items"
                ]
            ),
            client.get(one, headers=auth("other_owner")).status_code,
            client.get(
                f"/v1/workspaces/{b.id}/campaigns/{camp['id']}", headers=auth("other_owner")
            ).status_code,
        ]

        # With sending made available in this process only: an approval that
        # no longer matches is refused; a matching one queues, and processing
        # adds each eligible contact once.
        campaigns.SENDING_AVAILABLE = True
        os.environ["EMAIL_SENDING_ENABLED"] = "true"
        os.environ["EMAIL_CAMPAIGN_SENDING_ENABLED"] = "true"
        os.environ["EMAIL_PARENT_DOMAIN"] = "example.test"
        with tenant_session_scope(a.id) as session:
            session.execute(
                text(
                    "UPDATE crm_app.campaign SET approved_hash = :h"
                    " WHERE tenant_id = :t AND id = :c"
                ),
                {"h": "0" * 64, "t": a.id, "c": camp["id"]},
            )
        result["outdated"] = client.post(queue, headers=auth(version=11)).json()["detail"]
        with tenant_session_scope(a.id) as session:
            session.execute(
                text(
                    "UPDATE crm_app.campaign SET approved_hash = content_hash"
                    " WHERE tenant_id = :t AND id = :c"
                ),
                {"t": a.id, "c": camp["id"]},
            )
        queued = client.post(queue, headers=auth(version=11)).json()
        result["queued"] = queued["status"]
        processed = campaigns.process(
            owner_scope,
            uuid.UUID(camp["id"]),
            workspace_name="Acme",
            unsubscribe_base="https://app.example.test/app/u",
            one_click_base="https://app.example.test/v1/public/unsubscribe",
        )
        again = campaigns.process(
            owner_scope,
            uuid.UUID(camp["id"]),
            workspace_name="Acme",
            unsubscribe_base="https://app.example.test/app/u",
            one_click_base="https://app.example.test/v1/public/unsubscribe",
        )
        result["processed"] = [
            processed["status"],
            len(processed["queued_emails"]),
            len(again["queued_emails"]),
        ]
        result["recipients"] = _scalar(
            a.id, "SELECT count(*) FROM crm_app.campaign_recipient WHERE tenant_id = :t"
        )
        email_id = uuid.UUID(processed["queued_emails"][0])
        body = _scalar(
            a.id,
            "SELECT text_body FROM crm_app.email_message WHERE tenant_id = :t AND id = :e",
            e=email_id,
        )
        result["rendered"] = [body.startswith("Hello Ada,"), "Unsubscribe: https://" in body]
        token = re.search(r"/app/u/[0-9a-f-]+#([0-9a-f]{32})", body)
        recorder = Recorder()
        result["sent"] = emails.send(a.id, email_id, provider=recorder)
        result["sender"] = recorder.sent[-1].sender if recorder.sent else None
        # One-click unsubscribe headers (decision E-H1): the public route,
        # with the same token as the body's link.
        header = recorder.sent[-1].list_unsubscribe if recorder.sent else ()
        result["headers"] = [
            len(header),
            bool(recorder.sent and recorder.sent[-1].list_unsubscribe_post),
            bool(header and token and header[0].endswith(f"/{a.id}/{token.group(1)}")),
            bool(
                header and header[0].startswith("https://app.example.test/v1/public/unsubscribe/")
            ),
        ]
        result["message_id_stored"] = _scalar(
            a.id,
            "SELECT message_id = :m FROM crm_app.email_message WHERE tenant_id = :t AND id = :e",
            e=email_id,
            m=recorder.sent[-1].message_id if recorder.sent else "",
        )

        # Unsubscribing: suppressed and consent withdrawn; repeats, unknown
        # tokens and another workspace's path change nothing visible.
        path = f"/v1/public/unsubscribe/{a.id}/{token.group(1) if token else 'x'}"
        result["unsubscribe"] = [
            client.post(path).status_code,
            client.post(path).status_code,
            client.post(f"/v1/public/unsubscribe/{a.id}/{'0' * 32}").status_code,
            client.post(
                f"/v1/public/unsubscribe/{b.id}/{token.group(1) if token else 'x'}"
            ).status_code,
            client.post(f"/v1/public/unsubscribe/{a.id}/not-a-token").status_code,
        ]
        result["after_unsubscribe"] = [
            _scalar(
                a.id,
                "SELECT count(*) FROM crm_app.suppression WHERE tenant_id = :t"
                " AND email = 'ada@example.test' AND reason = 'unsubscribed'",
            ),
            _scalar(
                a.id,
                "SELECT count(*) FROM crm_app.consent_record WHERE tenant_id = :t"
                " AND status = 'withdrawn' AND method = 'unsubscribe_link'",
            ),
            _scalar(
                a.id,
                "SELECT status FROM crm_app.campaign_recipient WHERE tenant_id = :t LIMIT 1",
            ),
        ]
        # The link is the actor (K3.5): system entries, once, no member named.
        with tenant_session_scope(a.id) as session:
            result["unsubscribe_audit"] = [
                list(row)
                for row in session.execute(
                    text(
                        "SELECT action, actor_type, actor_user_id IS NULL,"
                        " metadata->'system_actor'->>'kind', metadata->'system_actor'->>'name',"
                        " metadata->>'initiated_by'"
                        " FROM core.audit_log WHERE tenant_id = :t"
                        " AND metadata->'system_actor'->>'name' = 'crm_app.unsubscribe_link'"
                        " ORDER BY action"
                    ),
                    {"t": a.id},
                )
            ]
        # A campaign email queued before the unsubscribe is not sent after it.
        late = campaigns.SENDING_AVAILABLE
        with tenant_session_scope(a.id) as session:
            again_id = emails.queue(
                session,
                owner_scope,
                purpose="campaign",
                to_email="ada@example.test",
                subject="Late",
                text_body="Late news",
                contact_id=uuid.UUID(ada),
                list_unsubscribe_url=f"https://app.example.test/v1/public/unsubscribe/{a.id}/late",
            )
        result["late_send"] = [late, emails.send(a.id, again_id, provider=recorder)]

        # The sending queue (decision P7-S), in workspace b: queuing records
        # the campaign; the maintenance run adds recipients in batches as
        # the sending component, then removes the row.
        origin = os.environ.get("PUBLIC_APP_ORIGIN")
        os.environ["PUBLIC_APP_ORIGIN"] = "https://app.example.test"
        # Workspace a's campaign was processed above: its row goes now.
        result["queue_drained"] = campaigns.run_queued()["finished"]
        b_scope = Scope(workspace=b.id, actor=b.owner_id)
        b_base = f"/v1/workspaces/{b.id}"
        for first in ("Bea", "Cal", "Dot"):
            made_id = client.post(
                f"{b_base}/contacts",
                json={
                    "first_name": first,
                    "lifecycle_stage": "lead",
                    "email": f"{first.lower()}@example.test",
                },
                headers=auth("other_owner"),
            ).json()["id"]
            suppression.record_consent(b_scope, uuid.UUID(made_id), "Yes, email me news.")
        winter = client.post(
            f"{b_base}/campaigns",
            json={**draft, "name": "Winter news"},
            headers=auth("other_owner"),
        ).json()
        w_one = f"{b_base}/campaigns/{winter['id']}"
        for step, version in (("validate", 1), ("submit", 2), ("approve", 3)):
            client.post(f"{w_one}/{step}", headers=auth("other_owner", version))
        w_queued = client.post(f"{w_one}/queue", headers=auth("other_owner", 4)).json()

        def queue_rows() -> int:
            with session_scope() as session:
                return session.execute(
                    text("SELECT count(*) FROM crm_app.campaign_queue WHERE campaign_id = :c"),
                    {"c": winter["id"]},
                ).scalar_one()

        def w_status() -> str:
            return _scalar(
                b.id,
                "SELECT status FROM crm_app.campaign WHERE tenant_id = :t AND id = :c",
                c=winter["id"],
            )

        result["queue_recorded"] = [w_queued["status"], queue_rows()]
        os.environ["PUBLIC_APP_ORIGIN"] = "http://app.example.test"
        no_https = campaigns.run_queued(batch=2)
        os.environ["PUBLIC_APP_ORIGIN"] = "https://app.example.test"
        try:
            first_run = campaigns.run_queued(batch=2)
            mid = [w_status(), queue_rows()]
            second_run = campaigns.run_queued(batch=2)
            done = [w_status(), queue_rows()]
            # A row whose campaign does not exist is removed, nothing sent.
            campaigns._register(b.id, uuid.uuid4(), b.owner_id)
            third_run = campaigns.run_queued(batch=2)
        finally:
            if origin is None:
                os.environ.pop("PUBLIC_APP_ORIGIN", None)
            else:
                os.environ["PUBLIC_APP_ORIGIN"] = origin

        def counts(run: dict[str, Any]) -> list[int]:
            return [run["campaigns"], run["finished"], run["waiting"], len(run["emails"])]

        result["queue_runs"] = {
            "no_https": counts(no_https),
            "first": [*counts(first_run), *mid],
            "second": [*counts(second_run), *done],
            "stale": counts(third_run),
        }
        result["queue_recipients"] = _scalar(
            b.id,
            "SELECT count(*) FROM crm_app.campaign_recipient"
            " WHERE tenant_id = :t AND campaign_id = :c",
            c=winter["id"],
        )
        result["queue_emails_in_b"] = all(
            workspace == b.id for workspace, _ in [*first_run["emails"], *second_run["emails"]]
        )
        with tenant_session_scope(b.id) as session:
            result["queue_audit"] = [
                list(row)
                for row in session.execute(
                    text(
                        "SELECT action, actor_type, metadata->'system_actor'->>'name',"
                        " metadata->>'on_behalf_of_user_id' = :o"
                        " FROM core.audit_log WHERE tenant_id = :t AND resource_id = :c"
                        " AND action IN ('crm_app.campaign.queued', 'crm_app.campaign.completed')"
                        " ORDER BY action"
                    ),
                    {"t": b.id, "c": winter["id"], "o": str(b.owner_id)},
                )
            ]

        # Production: no campaign can be queued even with the switches on.
        os.environ["ENVIRONMENT"] = "production"
        try:
            result["production"] = campaigns.sending_available()
        finally:
            os.environ["ENVIRONMENT"] = "test"
        campaigns.SENDING_AVAILABLE = False
        for name in (
            "EMAIL_SENDING_ENABLED",
            "EMAIL_CAMPAIGN_SENDING_ENABLED",
            "EMAIL_PARENT_DOMAIN",
        ):
            os.environ.pop(name, None)

        second = client.post(f"{base}/campaigns", json=draft, headers=auth()).json()
        result["cancel"] = [
            client.post(
                f"{base}/campaigns/{second['id']}/cancel", headers=auth("member", 1)
            ).json()["status"],
            client.post(
                f"{base}/campaigns/{second['id']}/cancel", headers=auth("member", 2)
            ).status_code,
            client.patch(
                f"{base}/campaigns/{second['id']}", json={"name": "x"}, headers=auth("member", 2)
            ).status_code,
        ]
        result["audit_text"] = _scalar(
            a.id,
            "SELECT count(*) FROM core.audit_log WHERE tenant_id = :t"
            " AND action LIKE 'crm_app.campaign.%' AND metadata::text LIKE '%autumn%'",
        )
        result["audit_steps"] = _scalar(
            a.id,
            "SELECT count(*) FROM core.audit_log WHERE tenant_id = :t"
            " AND action = 'crm_app.campaign.approved'",
        )
    print("RESULT " + json.dumps(result, default=str))


if __name__ == "__main__":
    main()

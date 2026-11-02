"""Drives customer-owned sending domains (decision P6-D) and prints one
`RESULT <json>` line.

Run in a fresh interpreter by `tests/integration/test_sending_domains.py`.
The provider is a test double in this process (never Resend); webhook
bodies are signed here with a made-up secret; email goes to a recording
provider. Seeds throwaway workspaces. Refuses to run unless ENVIRONMENT=test.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
import uuid
from typing import Any

from fastapi.testclient import TestClient
from saas_os.core.email import EmailMessage, EmailSendResult
from saas_os.core.identity import issue_session
from saas_os.infra.db import session_scope, tenant_session_scope
from saas_os.infra.secrets import get_secrets_provider
from sqlalchemy import text

from crm_app import emails, sending_domains
from crm_app.app import create_app
from crm_app.domains import sending_domains as rules
from crm_app.records import Scope
from crm_app.roles import Role
from tests.integration.opportunity_route_probe import _member
from tests.integration.workspace_route_probe import _new_user, _new_workspace

# A made-up webhook key for tests only.
KEY = b"0011223344556677889900aabbccddee"  # pragma: allowlist secret
SECRET = "whsec_" + base64.b64encode(KEY).decode()  # pragma: allowlist secret
WEBHOOK = "/v1/public/email/resend/events"


class FakeProvider:
    def __init__(self) -> None:
        self.created: list[str] = []
        self.verified: list[str] = []

    def create(self, name: str) -> rules.ProviderDomain:
        self.created.append(name)
        return rules.provider_domain(
            {
                "id": f"dom_{secrets.token_hex(6)}",
                "name": name,
                "status": "not_started",
                "records": [
                    {
                        "record": "SPF",
                        "name": "send",
                        "type": "TXT",
                        "value": "v=spf1 include:provider.example.org ~all",
                        "ttl": "Auto",
                        "status": "not_started",
                    },
                    {
                        "record": "DKIM",
                        "name": "resend._domainkey",
                        "type": "TXT",
                        "value": "p=MIGfMA0GCSq",
                        "ttl": "Auto",
                        "status": "not_started",
                    },
                ],
            }
        )

    def verify(self, provider_id: str) -> None:
        self.verified.append(provider_id)


class Recorder:
    def __init__(self) -> None:
        self.sent: list[EmailMessage] = []

    def send(self, message: EmailMessage) -> EmailSendResult:
        self.sent.append(message)
        return EmailSendResult(accepted=True, provider_message_id=f"re_{uuid.uuid4().hex}")


def _signed(payload: dict[str, Any]) -> tuple[bytes, dict[str, str]]:
    body = json.dumps(payload).encode()
    event_id = f"msg_{secrets.token_hex(6)}"
    stamp = str(int(time.time()))
    digest = hmac.new(KEY, f"{event_id}.{stamp}.".encode() + body, hashlib.sha256).digest()
    return body, {
        "svix-id": event_id,
        "svix-timestamp": stamp,
        "svix-signature": "v1," + base64.b64encode(digest).decode(),
        "content-type": "application/json",
    }


def main() -> None:  # noqa: PLR0915 - one scenario script, read top to bottom
    if os.environ.get("ENVIRONMENT") != "test":
        raise SystemExit("sending_domain_probe runs only with ENVIRONMENT=test")
    os.environ["EMAIL_PARENT_DOMAIN"] = "platform.org"
    os.environ["RESEND_WEBHOOK_SECRET"] = SECRET
    get_secrets_provider.cache_clear()
    a = _new_workspace("send-a")
    b = _new_workspace("send-b")
    _, member = _member(a, Role.MEMBER)
    tokens = {
        "owner": issue_session(a.owner_id)[1],
        "member": member,
        "other_owner": issue_session(b.owner_id)[1],
        "outsider": issue_session(_new_user())[1],
    }

    def auth(caller: str = "owner", version: int | None = None) -> dict[str, str]:
        headers = {"Authorization": f"Bearer {tokens[caller]}"}
        if version is not None:
            headers["If-Match"] = f'"{version}"'
        return headers

    scope_a = Scope(workspace=a.id, actor=a.owner_id)
    provider = FakeProvider()
    recorder = Recorder()
    domain = f"acme-{secrets.token_hex(3)}.nl"
    result: dict[str, Any] = {}
    with TestClient(create_app(), follow_redirects=False) as client:
        base = f"/v1/workspaces/{a.id}/sending-domains"

        def add(name: str, caller: str = "owner", workspace: uuid.UUID = a.id) -> Any:
            return client.post(
                f"/v1/workspaces/{workspace}/sending-domains",
                json={"domain": name},
                headers=auth(caller),
            )

        # Without a provider a domain is kept, unregistered, and says why.
        plain = add(f"plain-{secrets.token_hex(3)}.nl")
        listed = client.get(base, headers=auth()).json()
        result["no_provider"] = [
            plain.status_code,
            plain.json()["status"],
            plain.json()["last_error"],
            listed["provider_configured"],
        ]
        result["refused"] = [
            add("not a domain").status_code,
            add("mail.platform.org").status_code,
            add("www.example.com").status_code,
            add(f"x-{secrets.token_hex(3)}.nl", "member").status_code,
            add(f"x-{secrets.token_hex(3)}.nl", "outsider").status_code,
        ]

        # With a provider: the provider's own records are kept exactly.
        registered = sending_domains.register(scope_a, domain, provider=provider)
        domain_id = uuid.UUID(str(registered["id"]))
        result["registered"] = [
            registered["status"],
            [r["record"] for r in registered["records"]],
            registered["records"][0]["value"],
            provider.created == [domain],
        ]
        result["taken"] = [add(domain).status_code, add(domain, "other_owner", b.id).status_code]

        def identity(
            body: dict[str, Any], caller: str = "owner", workspace: uuid.UUID = a.id
        ) -> Any:
            return client.post(
                f"/v1/workspaces/{workspace}/sending-domains/{domain_id}/identities",
                json=body,
                headers=auth(caller),
            )

        jan = identity(
            {"local_part": "Jan", "for_conversation": True, "default_conversation": True}
        ).json()
        result["identity"] = [jan["address"], jan["usable"]]
        result["identity_refused"] = [
            identity({"local_part": "a+b", "for_conversation": True}).status_code,
            identity({"local_part": "none"}).status_code,
            identity({"local_part": "Jan", "for_campaign": True}).status_code,
            identity(
                {"local_part": "eve", "for_conversation": True}, "other_owner", b.id
            ).status_code,
        ]

        def queue_reply() -> uuid.UUID:
            with tenant_session_scope(a.id) as session:
                return emails.queue(
                    session,
                    scope_a,
                    purpose="conversation_reply",
                    to_email="ada@customer.org",
                    subject="Re: quote",
                    text_body="Here it is.",
                )

        def sender_of(email_id: uuid.UUID) -> Any:
            with tenant_session_scope(a.id) as session:
                return session.execute(
                    text(
                        "SELECT sender_address FROM crm_app.email_message"
                        " WHERE tenant_id = :t AND id = :e"
                    ),
                    {"t": a.id, "e": email_id},
                ).scalar_one()

        # Unverified: replies keep the platform's conversation sender.
        result["before_verify"] = sender_of(queue_reply())

        with tenant_session_scope(a.id) as session:
            pid = session.execute(
                text(
                    "SELECT provider_id FROM crm_app.sending_domain"
                    " WHERE tenant_id = :t AND id = :d"
                ),
                {"t": a.id, "d": domain_id},
            ).scalar_one()

        def event(payload: dict[str, Any]) -> int:
            body, headers = _signed(payload)
            return client.post(WEBHOOK, content=body, headers=headers).status_code

        def domain_event(
            status: str, provider_id: str, minute: int, name: str | None = None
        ) -> int:
            return event(
                {
                    "type": "domain.updated",
                    "created_at": f"2026-11-01T10:{minute:02d}:00Z",
                    "data": {"id": provider_id, "name": name or domain, "status": status},
                }
            )

        def status_now() -> str:
            found = next(d for d in sending_domains.list_domains(scope_a) if d["domain"] == domain)
            return str(found["status"])

        result["verify_request"] = sending_domains.verify(
            scope_a, domain_id, expected_version=1, provider=provider
        )["status"]
        result["events"] = [
            domain_event("verified", pid, 1),
            domain_event("verified", "dom_unknown", 2),
            event({"type": "domain.updated", "data": {"id": 5}}),
        ]
        now = next(d for d in sending_domains.list_domains(scope_a) if d["domain"] == domain)
        result["after_verify"] = [now["status"], now["identities"][0]["usable"]]

        # Verified: replies go out from the workspace's own address.
        os.environ["EMAIL_SENDING_ENABLED"] = "true"
        os.environ["EMAIL_CONVERSATION_SENDING_ENABLED"] = "true"
        own = queue_reply()
        result["own_sender"] = [
            sender_of(own),
            emails.send(a.id, own, provider=recorder),
            recorder.sent[-1].sender if recorder.sent else None,
        ]

        # The provider reports the domain failing: an email queued with the
        # identity waits and is never sent from another address.
        waiting = queue_reply()
        domain_event("failed", pid, 10)
        sent_before = len(recorder.sent)
        result["after_failure"] = [
            sender_of(waiting),
            emails.send(a.id, waiting, provider=recorder),
            len(recorder.sent) - sent_before,
        ]
        os.environ.pop("EMAIL_SENDING_ENABLED")
        os.environ.pop("EMAIL_CONVERSATION_SENDING_ENABLED")

        # 13-H3: an older event delivered late, or one naming another
        # domain, changes nothing.
        result["late_events"] = [
            domain_event("verified", pid, 5),
            status_now(),
            domain_event("verified", pid, 20, name="other-example.nl"),
            status_now(),
        ]

        # 13-H3: a name never verified is released after its claim time.
        squat = f"squat-{secrets.token_hex(3)}.nl"
        held = add(squat).json()
        result["claim_held"] = [
            held["claim_expires_at"] is not None,
            add(squat, "other_owner", b.id).status_code,
        ]
        with tenant_session_scope(a.id) as session:
            session.execute(
                text(
                    "UPDATE crm_app.sending_domain SET created_at = now() - interval '8 days'"
                    " WHERE tenant_id = :t AND id = :d"
                ),
                {"t": a.id, "d": held["id"]},
            )
        with session_scope() as session:
            session.execute(
                text(
                    "UPDATE crm_app.sending_domain_index"
                    " SET claimed_at = now() - interval '8 days' WHERE domain = :n"
                ),
                {"n": squat},
            )
        released = sending_domains.release_unverified()
        expired = next(d for d in sending_domains.list_domains(scope_a) if d["domain"] == squat)
        result["claim_released"] = [
            released >= 1,
            expired["status"],
            expired["last_error"],
            expired["claim_expires_at"],
            client.post(
                f"{base}/{held['id']}/verify", headers=auth(version=expired["version"])
            ).status_code,
            add(squat, "other_owner", b.id).status_code,
        ]
        # A verified domain is never released, however old its claim.
        with session_scope() as session:
            session.execute(
                text(
                    "UPDATE crm_app.sending_domain_index"
                    " SET claimed_at = now() - interval '30 days' WHERE domain = :n"
                ),
                {"n": domain},
            )
        sending_domains.release_unverified()
        result["verified_kept"] = add(domain, "other_owner", b.id).status_code

        # Other workspaces see nothing; removing frees the domain.
        result["isolation"] = [
            str(domain_id)
            in [
                item["id"]
                for item in client.get(
                    f"/v1/workspaces/{b.id}/sending-domains", headers=auth("other_owner")
                ).json()["items"]
            ],
            client.delete(
                f"/v1/workspaces/{b.id}/sending-domains/{domain_id}",
                headers=auth("other_owner"),
            ).status_code,
            client.delete(f"{base}/{domain_id}", headers=auth("member")).status_code,
        ]
        result["removed"] = [
            client.delete(f"{base}/{domain_id}", headers=auth()).status_code,
            add(domain, "other_owner", b.id).status_code,
        ]
    print("RESULT " + json.dumps(result, default=str))


if __name__ == "__main__":
    main()

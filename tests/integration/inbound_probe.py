"""Drives inbound email (decision P6-I) and prints one `RESULT <json>` line.

Run in a fresh interpreter by `tests/integration/test_inbound_email.py`.
Received emails come from a test double of the receiving API in this
process, never from Resend; webhook bodies are signed here with a made-up
secret; outbound replies go to a recording provider. Seeds throwaway
workspaces. Refuses to run unless ENVIRONMENT=test.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import threading
import time
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi.testclient import TestClient
from saas_os.core.email import EmailMessage, EmailSendResult
from saas_os.core.identity import issue_session
from saas_os.infra.db import session_scope, tenant_session_scope
from saas_os.infra.secrets import get_secrets_provider
from sqlalchemy import text

from crm_app import emails, inbound
from crm_app.app import create_app
from crm_app.domains import inbound as rules
from crm_app.models import ConversationRouteIndex
from crm_app.roles import Role
from tests.integration.opportunity_route_probe import _member
from tests.integration.workspace_route_probe import _new_user, _new_workspace

# A made-up webhook key for tests only.
KEY = b"fedcba9876543210fedcba9876543210"  # pragma: allowlist secret
SECRET = "whsec_" + base64.b64encode(KEY).decode()  # pragma: allowlist secret
WEBHOOK = "/v1/public/email/resend/inbound"
PARENT = "example.test"
RUN = secrets.token_hex(4)


class Receiving:
    """A test double of the receiving API: answers from a dict."""

    def __init__(self) -> None:
        self.answers: dict[str, Any] = {}
        self.calls: list[str] = []
        self.lock = threading.Lock()

    def fetch(self, provider_email_id: str) -> object:
        with self.lock:
            self.calls.append(provider_email_id)
        answer = self.answers[provider_email_id]
        if isinstance(answer, inbound.FetchError):
            raise answer
        return answer


class Recorder:
    def __init__(self) -> None:
        self.sent: list[EmailMessage] = []

    def send(self, message: EmailMessage) -> EmailSendResult:
        self.sent.append(message)
        return EmailSendResult(accepted=True, provider_message_id=f"re_{uuid.uuid4().hex}")


def _signed(
    event_id: str, payload: dict[str, Any], *, age: int = 0
) -> tuple[bytes, dict[str, str]]:
    body = json.dumps(payload).encode()
    stamp = str(int(time.time()) - age)
    digest = hmac.new(KEY, f"{event_id}.{stamp}.".encode() + body, hashlib.sha256).digest()
    return body, {
        "svix-id": event_id,
        "svix-timestamp": stamp,
        "svix-signature": "v1," + base64.b64encode(digest).decode(),
        "content-type": "application/json",
    }


def _received(email_id: str) -> dict[str, Any]:
    return {
        "type": "email.received",
        "created_at": datetime.now(UTC).isoformat(),
        "data": {"email_id": email_id, "to": ["someone@inbound.example.test"]},
    }


def _inbound_row(provider_email_id: str) -> dict[str, Any] | None:
    with session_scope() as session:
        row = session.execute(
            text(
                "SELECT status, attempts, reason, last_error, workspace_id, sender_domain,"
                " next_attempt_at IS NOT NULL AS waiting"
                " FROM crm_app.inbound_email WHERE provider_email_id = :e"
            ),
            {"e": provider_email_id},
        ).first()
    return (
        None
        if row is None
        else {k: str(v) if isinstance(v, uuid.UUID) else v for k, v in row._mapping.items()}
    )


def _count_inbound() -> int:
    with session_scope() as session:
        return int(session.execute(text("SELECT count(*) FROM crm_app.inbound_email")).scalar_one())


def _messages(workspace: uuid.UUID, conversation: str) -> list[dict[str, Any]]:
    with tenant_session_scope(workspace) as session:
        return [
            dict(r._mapping)
            for r in session.execute(
                text(
                    "SELECT kind, body, author_user_id IS NULL AS from_contact, attachments"
                    " FROM crm_app.conversation_message"
                    " WHERE tenant_id = :t AND conversation_id = :c ORDER BY created_at, id"
                ),
                {"t": workspace, "c": conversation},
            )
        ]


def _token(workspace: uuid.UUID, conversation: str) -> str | None:
    with tenant_session_scope(workspace) as session:
        return session.execute(
            text(
                "SELECT token FROM crm_app.conversation_route"
                " WHERE tenant_id = :t AND conversation_id = :c"
            ),
            {"t": workspace, "c": conversation},
        ).scalar_one_or_none()


def _answer(sender: str, to: list[str], **extra: Any) -> dict[str, Any]:
    return {
        "object": "email",
        "from": sender,
        "to": to,
        "subject": extra.pop("subject", "Re: Your quote"),
        "text": extra.pop("text", "Thanks, got it."),
        "html": extra.pop("html", None),
        "authentication": {"spf": "pass", "dkim": "pass", "dmarc": extra.pop("dmarc", "pass")},
        "attachments": extra.pop("attachments", []),
        **extra,
    }


def main() -> None:  # noqa: PLR0915 - one scenario script, read top to bottom
    if os.environ.get("ENVIRONMENT") != "test":
        raise SystemExit("inbound_probe runs only with ENVIRONMENT=test")
    for name in ("EMAIL_INBOUND_ENABLED", "EMAIL_PARENT_DOMAIN", "RESEND_INBOUND_WEBHOOK_SECRET"):
        os.environ.pop(name, None)
    get_secrets_provider.cache_clear()
    a = _new_workspace("inbound-a")
    b = _new_workspace("inbound-b")
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

    receiving = Receiving()
    result: dict[str, Any] = {}
    with TestClient(create_app(), follow_redirects=False) as client:

        def thread(workspace: uuid.UUID, caller: str, email: str) -> str:
            base = f"/v1/workspaces/{workspace}"
            contact = client.post(
                f"{base}/contacts",
                json={"first_name": "Ada", "last_name": "Lovelace", "email": email},
                headers=auth(caller),
            ).json()["id"]
            made = client.post(
                f"{base}/conversations",
                json={
                    "contact_id": contact,
                    "channel": "email",
                    "subject": "Your quote",
                    "kind": "outbound",
                    "body": "Here is your quote.",
                },
                headers=auth(caller),
            )
            return str(made.json()["id"])

        conv = thread(a.id, "owner", "ada@example.test")
        conv_b = thread(b.id, "other_owner", "bob@example.test")
        token = _token(a.id, conv)
        token_b = _token(b.id, conv_b)
        result["route"] = [token is not None and len(token) == 32, token != token_b]
        with session_scope() as session:
            indexed = session.get(ConversationRouteIndex, rules.token_hash(token or ""))
            result["index"] = [str(indexed.workspace_id) == str(a.id)] if indexed else [False]

        # --- The reply carries its routing address only while inbound is on -------------
        os.environ["EMAIL_SENDING_ENABLED"] = "true"
        os.environ["EMAIL_CONVERSATION_SENDING_ENABLED"] = "true"
        os.environ["EMAIL_PARENT_DOMAIN"] = PARENT
        recorder = Recorder()
        with tenant_session_scope(a.id) as session:
            email_ids = [
                r[0]
                for r in session.execute(
                    text(
                        "SELECT email_message_id FROM crm_app.conversation_message"
                        " WHERE tenant_id = :t AND conversation_id = :c"
                        " AND email_message_id IS NOT NULL"
                    ),
                    {"t": a.id, "c": conv},
                )
            ]
        emails.send(a.id, email_ids[0], provider=recorder)
        result["reply_to_inbound_off"] = recorder.sent[-1].reply_to
        os.environ["EMAIL_INBOUND_ENABLED"] = "true"
        second = client.post(
            f"/v1/workspaces/{a.id}/conversations/{conv}/messages",
            json={"kind": "outbound", "body": "And the invoice."},
            headers=auth(),
        )
        with tenant_session_scope(a.id) as session:
            latest = session.execute(
                text(
                    "SELECT email_message_id FROM crm_app.conversation_message"
                    " WHERE tenant_id = :t AND conversation_id = :c"
                    " AND email_message_id IS NOT NULL ORDER BY created_at DESC LIMIT 1"
                ),
                {"t": a.id, "c": conv},
            ).scalar_one()
        emails.send(a.id, latest, provider=recorder)
        result["reply_to_inbound_on"] = [second.status_code, recorder.sent[-1].reply_to]
        result["expected_reply_to"] = f"reply+{token}@inbound.{PARENT}"
        os.environ.pop("EMAIL_SENDING_ENABLED")
        os.environ.pop("EMAIL_CONVERSATION_SENDING_ENABLED")

        # --- The webhook ---------------------------------------------------------------
        def post(event_id: str, payload: dict[str, Any], **kw: Any) -> int:
            body, headers = _signed(event_id, payload, **kw)
            return client.post(WEBHOOK, content=body, headers=headers).status_code

        result["no_secret"] = post(f"evt_{RUN}_0", _received(f"re_{RUN}_none"))
        os.environ["RESEND_INBOUND_WEBHOOK_SECRET"] = SECRET
        get_secrets_provider.cache_clear()
        os.environ["EMAIL_INBOUND_ENABLED"] = "false"
        result["switched_off"] = post(f"evt_{RUN}_0", _received(f"re_{RUN}_none"))
        os.environ["EMAIL_INBOUND_ENABLED"] = "true"
        start = _count_inbound()
        body, headers = _signed(f"evt_{RUN}_forged", _received(f"re_{RUN}_forged"))
        result["signatures"] = [
            client.post(
                WEBHOOK, content=body.replace(b"forged", b"other_"), headers=headers
            ).status_code,
            client.post(
                WEBHOOK, content=body, headers={**headers, "svix-signature": "v1,AAAA"}
            ).status_code,
            post(f"evt_{RUN}_old", _received(f"re_{RUN}_old"), age=600),
            _count_inbound() - start,
        ]
        before = _count_inbound()
        result["recorded"] = [
            post(f"evt_{RUN}_1", _received(f"re_{RUN}_1")),
            post(f"evt_{RUN}_1", _received(f"re_{RUN}_1")),
            post(f"evt_{RUN}_1b", _received(f"re_{RUN}_1")),
            _count_inbound() - before,
        ]
        result["other_type"] = [
            post(
                f"evt_{RUN}_delivered",
                {"type": "email.delivered", "data": {"email_id": f"re_{RUN}_x"}},
            ),
            _count_inbound() - before,
        ]
        result["malformed_event"] = post(
            f"evt_{RUN}_bad", {"type": "email.received", "created_at": "now", "data": {}}
        )
        result["after_webhook"] = _inbound_row(f"re_{RUN}_1")

        # --- Processing ----------------------------------------------------------------
        route = f"reply+{token}@inbound.{PARENT}"
        stranger = f"reply+{rules.new_token()}@inbound.{PARENT}"
        forged = rules.new_token()
        with session_scope() as session:
            # An index row that points at A's thread with a token A never issued.
            session.add(
                ConversationRouteIndex(
                    token_hash=rules.token_hash(forged),
                    workspace_id=a.id,
                    conversation_id=uuid.UUID(conv),
                )
            )
        attachment = {
            "id": "att",
            "filename": "../../etc/passwd.exe",
            "content_type": "Application/X-MSDownload",
            "size": 4096,
        }
        receiving.answers.update(
            {
                f"re_{RUN}_1": _answer("Ada Lovelace <ADA@example.test>", [route]),
                f"re_{RUN}_2": _answer(
                    "mallory@evil.test", [route], text="Please pay to this account."
                ),
                f"re_{RUN}_3": _answer("ada@example.test", [stranger]),
                f"re_{RUN}_4": _answer("ada@example.test", ["info@example.test"]),
                f"re_{RUN}_5": inbound.FetchError("rate_limited", retry_after=120),
                f"re_{RUN}_6": inbound.FetchError("not_found", transient=False),
                f"re_{RUN}_7": {"object": "email", "to": [route], "text": "no sender"},
                f"re_{RUN}_8": _answer(
                    "ada@example.test",
                    [route],
                    text=None,
                    html="<p>Hello <b>there</b></p><script>alert(1)</script><style>p{}</style>",
                    dmarc="fail",
                ),
                f"re_{RUN}_9": _answer("bob@example.test", [f"reply+{token_b}@inbound.{PARENT}"]),
                f"re_{RUN}_10": _answer("ada@example.test", [f"reply+{forged}@inbound.{PARENT}"]),
                f"re_{RUN}_11": _answer(
                    "ada@example.test", [route, f"reply+{token_b}@inbound.{PARENT}"]
                ),
                f"re_{RUN}_12": _answer(
                    "ada@example.test", [route], text="See attached.", attachments=[attachment]
                ),
            }
        )
        client.patch(
            f"/v1/workspaces/{a.id}/conversations/{conv}",
            json={"status": "closed"},
            headers=auth(
                version=client.get(
                    f"/v1/workspaces/{a.id}/conversations/{conv}", headers=auth()
                ).json()["version"]
            ),
        )
        for n in range(2, 13):
            post(f"evt_{RUN}_{n}", _received(f"re_{RUN}_{n}"))
        counts = inbound.process_due(receiving)
        result["counts"] = counts
        result["rows"] = {f"re_{n}": _inbound_row(f"re_{RUN}_{n}") for n in range(1, 13)}
        conversation = client.get(
            f"/v1/workspaces/{a.id}/conversations/{conv}", headers=auth()
        ).json()
        result["reopened"] = conversation["status"]
        result["messages"] = _messages(a.id, conv)
        result["b_messages"] = [m["body"] for m in _messages(b.id, conv_b)]
        result["api_attachments"] = [m.get("attachments") for m in conversation["messages"]]

        # A worker that died after delivering, before recording it: the row is
        # taken again once stale, and the email is not added twice.
        with session_scope() as session:
            session.execute(
                text(
                    "UPDATE crm_app.inbound_email SET status = 'processing', workspace_id = NULL,"
                    " updated_at = now() - interval '1 hour' WHERE provider_email_id = :e"
                ),
                {"e": f"re_{RUN}_1"},
            )
        inbound.process_due(receiving)
        result["redelivered_count"] = sum(
            1 for m in _messages(a.id, conv) if m["body"] == "Thanks, got it."
        )

        # Two workers at once take each email once.
        for n in (13, 14, 15, 16):
            receiving.answers[f"re_{RUN}_{n}"] = _answer(
                "ada@example.test", [route], text=f"Parallel {n}"
            )
            post(f"evt_{RUN}_{n}", _received(f"re_{RUN}_{n}"))
        workers = [
            threading.Thread(target=inbound.process_due, args=(receiving,)) for _ in range(2)
        ]
        for w in workers:
            w.start()
        for w in workers:
            w.join()
        result["parallel"] = sorted(
            m["body"] for m in _messages(a.id, conv) if m["body"].startswith("Parallel")
        )
        result["parallel_fetches"] = sorted(
            c
            for c in receiving.calls
            if c in {f"re_{RUN}_13", f"re_{RUN}_14", f"re_{RUN}_15", f"re_{RUN}_16"}
        )

        # --- Review ------------------------------------------------------------------
        reviews = f"/v1/workspaces/{a.id}/conversation-reviews"
        listed = client.get(reviews, headers=auth("member"))
        items = {i["reason"]: i for i in listed.json()["items"]}
        result["reviews"] = sorted(items)
        result["review_text"] = items.get("dmarc_failed", {}).get("body")
        result["review_access"] = [
            client.get(reviews, headers=auth("reader")).status_code,
            client.get(reviews, headers=auth("other_owner")).status_code,
            client.get(reviews, headers=auth("outsider")).status_code,
            len(
                client.get(
                    f"/v1/workspaces/{b.id}/conversation-reviews", headers=auth("other_owner")
                ).json()["items"]
            ),
        ]
        mismatch = items["sender_mismatch"]
        accept = f"{reviews}/{mismatch['id']}/accept"
        result["accept"] = [
            client.post(accept, headers=auth()).status_code,
            client.post(accept, headers=auth(version=9)).status_code,
            client.post(accept, headers=auth("reader", version=1)).status_code,
            client.post(
                f"/v1/workspaces/{b.id}/conversation-reviews/{mismatch['id']}/accept",
                headers=auth("other_owner", version=1),
            ).status_code,
            client.post(accept, headers=auth(version=1)).status_code,
            client.post(accept, headers=auth(version=2)).status_code,
        ]
        dmarc = items["dmarc_failed"]
        result["discard"] = client.post(
            f"{reviews}/{dmarc['id']}/discard", headers=auth(version=1)
        ).json()["status"]
        bodies = [m["body"] for m in _messages(a.id, conv)]
        result["after_review"] = [
            bodies.count("Please pay to this account."),
            any("Hello there" in body for body in bodies),
        ]
        result["pending_after"] = len(client.get(reviews, headers=auth()).json()["items"])

        # --- Production: nothing is received or processed ----------------------------
        os.environ["ENVIRONMENT"] = "production"
        try:
            result["production"] = [
                client.post(
                    WEBHOOK, content=b"{}", headers={"content-type": "application/json"}
                ).status_code,
                inbound.process_due(receiving),
            ]
        finally:
            os.environ["ENVIRONMENT"] = "test"

        # The processor's own entries (K3.5): one per message it added and per
        # email it held, however often an email was processed; no member.
        with tenant_session_scope(a.id) as session:
            result["inbound_audit"] = {
                str(row[0]): [row[1], row[2]]
                for row in session.execute(
                    text(
                        "SELECT action, count(*), bool_and(actor_user_id IS NULL)"
                        " FROM core.audit_log WHERE tenant_id = :t"
                        " AND metadata->'system_actor'->>'name' = 'crm_app.inbound_process'"
                        " GROUP BY action"
                    ),
                    {"t": a.id},
                )
            }
            result["inbound_rows"] = {
                "crm_app.conversation.inbound_received": session.execute(
                    text(
                        "SELECT count(*) FROM crm_app.conversation_message m"
                        " WHERE m.tenant_id = :t AND m.inbound_email_id IS NOT NULL"
                        # An accepted review adds its message as the member's act.
                        " AND NOT EXISTS (SELECT 1 FROM crm_app.inbound_quarantine q"
                        "  WHERE q.tenant_id = m.tenant_id AND q.status = 'accepted'"
                        "  AND q.inbound_email_id = m.inbound_email_id)"
                    ),
                    {"t": a.id},
                ).scalar_one(),
                "crm_app.conversation.inbound_quarantined": session.execute(
                    text("SELECT count(*) FROM crm_app.inbound_quarantine WHERE tenant_id = :t"),
                    {"t": a.id},
                ).scalar_one(),
            }
    print("RESULT " + json.dumps(result, default=str))


if __name__ == "__main__":
    main()

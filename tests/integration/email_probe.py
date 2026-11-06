"""Drives transactional email (decision P6-E) against the integration
database and prints one `RESULT <json>` line.

Run in a fresh interpreter by `tests/integration/test_emails.py`. Emails go
to a recording provider in this process, never to a real one; the webhook
is called with bodies signed here with a made-up secret. Seeds throwaway
workspaces. Refuses to run unless ENVIRONMENT=test.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from typing import Any

from fastapi.testclient import TestClient
from saas_os.core.email import EmailMessage, EmailProviderError, EmailSendResult
from saas_os.infra.db import session_scope, tenant_session_scope
from saas_os.infra.secrets import get_secrets_provider
from sqlalchemy import text

from crm_app import emails, suppression
from crm_app.app import create_app
from crm_app.models import EmailIndex
from crm_app.records import Scope
from tests.integration.workspace_route_probe import _new_workspace

# A made-up webhook key for tests only.
KEY = b"0123456789abcdef0123456789abcdef"  # pragma: allowlist secret
SECRET = "whsec_" + base64.b64encode(KEY).decode()  # pragma: allowlist secret
WEBHOOK = "/v1/public/email/resend/events"


class Recorder:
    """A provider that records what it is given and answers as told."""

    def __init__(self) -> None:
        self.sent: list[EmailMessage] = []
        self.mode = "ok"
        self.lock = threading.Lock()

    def send(self, message: EmailMessage) -> EmailSendResult:
        if self.mode == "slow":
            time.sleep(0.5)
        if self.mode == "transient":
            raise EmailProviderError("send", "rate_limit_exceeded", reply_code=429)
        if self.mode == "retry_after":
            raise EmailProviderError(
                "send", "rate_limit_exceeded", reply_code=429, retry_after_seconds=600
            )
        if self.mode == "permanent":
            raise EmailProviderError("send", "validation_error", permanent=True, reply_code=422)
        with self.lock:
            self.sent.append(message)
            return EmailSendResult(accepted=True, provider_message_id=f"re_{uuid.uuid4().hex}")


def _row(workspace: uuid.UUID, email_id: uuid.UUID) -> dict[str, Any]:
    with tenant_session_scope(workspace) as session:
        row = session.execute(
            text(
                "SELECT status, attempts, last_error, provider, provider_message_id"
                " FROM crm_app.email_message WHERE tenant_id = :t AND id = :id"
            ),
            {"t": workspace, "id": email_id},
        ).one()
        return dict(row._mapping)


def _count(workspace: uuid.UUID, sql: str, **values: object) -> int:
    with tenant_session_scope(workspace) as session:
        return int(session.execute(text(sql), {"t": workspace, **values}).scalar_one())


def _index(email_id: uuid.UUID) -> dict[str, Any] | None:
    with session_scope() as session:
        row = session.get(EmailIndex, email_id)
        if row is None:
            return None
        return {
            "provider_message_id": row.provider_message_id,
            "retry_at": row.retry_at is not None,
        }


def _wait_seconds(workspace: uuid.UUID, email_id: uuid.UUID) -> int | None:
    with tenant_session_scope(workspace) as session:
        at = session.execute(
            text(
                "SELECT next_attempt_at FROM crm_app.email_message"
                " WHERE tenant_id = :t AND id = :id"
            ),
            {"t": workspace, "id": email_id},
        ).scalar_one()
    return None if at is None else round((at - datetime.now(UTC)).total_seconds())


def _due_now(workspace: uuid.UUID, email_id: uuid.UUID) -> None:
    with tenant_session_scope(workspace) as session:
        session.execute(
            text(
                "UPDATE crm_app.email_message SET next_attempt_at = now() - interval '1 second'"
                " WHERE tenant_id = :t AND id = :id"
            ),
            {"t": workspace, "id": email_id},
        )


def main() -> None:  # noqa: PLR0915 - one scenario script, read top to bottom
    if os.environ.get("ENVIRONMENT") != "test":
        raise SystemExit("email_probe runs only with ENVIRONMENT=test")
    a = _new_workspace("email-a")
    b = _new_workspace("email-b")
    scope = Scope(workspace=a.id, actor=a.owner_id)
    provider = Recorder()
    result: dict[str, Any] = {"workspace": str(a.id)}

    def queue(to: str = "ada@example.test", subject: str = "Your booking") -> uuid.UUID:
        with tenant_session_scope(a.id) as session:
            return emails.queue(
                session, scope, purpose="test", to_email=to, subject=subject, text_body="Hello."
            )

    def send(email_id: uuid.UUID) -> str:
        try:
            return emails.send(a.id, email_id, provider=provider)
        except emails.EmailSendDeferredError as exc:
            return f"deferred:{exc}"

    # --- Off by default: nothing is handed to a provider ---------------------------------
    os.environ.pop("EMAIL_SENDING_ENABLED", None)
    first = queue()
    result["disabled"] = [send(first), _row(a.id, first)["status"], len(provider.sent)]
    result["queued_index"] = _index(first)

    # --- Sent once, with a stable Message-ID; a replayed job sends nothing more ---------
    os.environ["EMAIL_SENDING_ENABLED"] = "true"
    result["sent"] = send(first)
    row = _row(a.id, first)
    result["sent_row"] = {k: row[k] for k in ("status", "attempts", "provider")}
    result["message"] = {
        "message_id": provider.sent[0].message_id,
        "expected": f"<{first}@mail.example.test>",
        "to": list(provider.sent[0].to),
    }
    result["sent_index"] = _index(first)
    result["replay"] = [send(first), len(provider.sent)]

    # --- Two jobs for one email at once: one send ------------------------------------------
    racing = queue()
    provider.mode = "slow"
    with ThreadPoolExecutor(max_workers=2) as pool:
        answers = sorted(pool.map(send, (racing, racing)))
    provider.mode = "ok"
    result["race"] = [answers, sum(1 for m in provider.sent if str(racing) in (m.message_id or ""))]

    # --- A transient failure is retried; a permanent one fails ------------------------------
    flaky = queue()
    provider.mode = "transient"
    result["transient"] = [send(flaky), _row(a.id, flaky), _index(flaky)]
    provider.mode = "ok"
    # Not before its backoff: the next job only waits, then it is due.
    result["backoff"] = [send(flaky), _wait_seconds(a.id, flaky), len(provider.sent)]
    _due_now(a.id, flaky)
    result["after_transient"] = [send(flaky), _row(a.id, flaky)["attempts"]]
    refused = queue()
    provider.mode = "permanent"
    result["permanent"] = [send(refused), _row(a.id, refused)["last_error"], _index(refused)]
    provider.mode = "ok"

    # --- A suppressed address is never sent to; tries are bounded ----------------------------
    suppression.add(scope, ["grace@example.test"], reason="manual", note=None)
    blocked = queue("Grace@Example.test")
    before = len(provider.sent)
    result["suppressed"] = [send(blocked), len(provider.sent) - before]
    tired = queue()
    with tenant_session_scope(a.id) as session:
        session.execute(
            text("UPDATE crm_app.email_message SET attempts = 5 WHERE tenant_id = :t AND id = :id"),
            {"t": a.id, "id": tired},
        )
    result["exhausted"] = [send(tired), _row(a.id, tired)["last_error"]]

    # --- Retry-After: never sooner than the provider asks (decision P6-S) ----------------
    patient = queue()
    provider.mode = "retry_after"
    result["retry_after"] = [send(patient), _wait_seconds(a.id, patient)]
    provider.mode = "ok"

    # --- Rate limits per stream and workspace (decision P6-S) ----------------------------
    c = _new_workspace("email-c")
    scope_b = Scope(workspace=c.id, actor=c.owner_id)

    def queue_b(purpose: str = "test") -> uuid.UUID:
        with tenant_session_scope(c.id) as session:
            return emails.queue(
                session,
                scope_b,
                purpose=purpose,
                to_email="bob@example.test",
                subject="Hi",
                text_body="Hello.",
            )

    os.environ["EMAIL_TRANSACTIONAL_WORKSPACE_PER_MINUTE"] = "2"
    limited = [queue_b() for _ in range(3)]
    outcomes = [emails.send(c.id, e, provider=provider) for e in limited]
    result["rate_limited"] = [outcomes, _row(c.id, limited[2])["status"]]
    result["rate_wait"] = (_wait_seconds(c.id, limited[2]) or 0) > 0
    os.environ.pop("EMAIL_TRANSACTIONAL_WORKSPACE_PER_MINUTE")

    # --- Streams: a conversation reply needs its own switch and sender -------------------
    reply = queue_b("conversation_reply")
    stream_off = emails.send(c.id, reply, provider=provider)
    os.environ["EMAIL_CONVERSATION_SENDING_ENABLED"] = "true"
    no_parent = emails.send(c.id, reply, provider=provider)
    os.environ["EMAIL_PARENT_DOMAIN"] = "example.test"
    before = len(provider.sent)
    sent_reply = emails.send(c.id, reply, provider=provider)
    result["streams"] = {
        "outcomes": [stream_off, no_parent, sent_reply],
        "from": provider.sent[before].sender if len(provider.sent) > before else None,
        "message_id_domain": (provider.sent[before].message_id or "").rsplit("@", 1)[-1]
        if len(provider.sent) > before
        else None,
    }
    transactional = queue_b()
    emails.send(c.id, transactional, provider=provider)
    result["transactional_from"] = provider.sent[-1].sender
    for name in ("EMAIL_CONVERSATION_SENDING_ENABLED", "EMAIL_PARENT_DOMAIN"):
        os.environ.pop(name)

    # --- Production: the send path refuses even if a switch is on ------------------------
    guarded = queue()
    os.environ["ENVIRONMENT"] = "production"
    try:
        before = len(provider.sent)
        result["production"] = [send(guarded), len(provider.sent) - before]
    finally:
        os.environ["ENVIRONMENT"] = "test"

    # --- Another workspace sees none of it ---------------------------------------------------
    result["other_workspace_rows"] = _count(b.id, "SELECT count(*) FROM crm_app.email_message")
    result["own_rows"] = _count(a.id, "SELECT count(*) FROM crm_app.email_message")

    # --- A queued email whose transaction rolled back leaves an orphan the sweeper drops ------
    ghost = uuid.uuid4()
    with session_scope() as session:
        session.add(
            EmailIndex(email_message_id=ghost, workspace_id=a.id, retry_at=datetime.now(UTC))
        )
    result["orphan"] = [emails.orphan(a.id, ghost), _index(ghost), emails.orphan(a.id, first)]

    # --- The webhook ---------------------------------------------------------------------------
    provider_id = _row(a.id, first)["provider_message_id"]

    def signed(
        event_id: str, payload: dict[str, Any], *, age: int = 0
    ) -> tuple[bytes, dict[str, str]]:
        body = json.dumps(payload).encode()
        stamp = str(int(time.time()) - age)
        digest = hmac.new(KEY, f"{event_id}.{stamp}.".encode() + body, hashlib.sha256).digest()
        headers = {
            "svix-id": event_id,
            "svix-timestamp": stamp,
            "svix-signature": "v1," + base64.b64encode(digest).decode(),
            "content-type": "application/json",
        }
        return body, headers

    def event(kind: str, email_id: str = provider_id) -> dict[str, Any]:
        return {
            "type": kind,
            "created_at": datetime.now(UTC).isoformat(),
            "data": {"email_id": email_id},
        }

    events_sql = "SELECT count(*) FROM crm_app.email_event WHERE tenant_id = :t"
    with TestClient(create_app(), follow_redirects=False) as client:

        def post(event_id: str, payload: dict[str, Any], **kw: Any) -> int:
            body, headers = signed(event_id, payload, **kw)
            return client.post(WEBHOOK, content=body, headers=headers).status_code

        os.environ.pop("RESEND_WEBHOOK_SECRET", None)
        get_secrets_provider.cache_clear()
        result["no_secret"] = post("msg_none", event("email.delivered"))
        os.environ["RESEND_WEBHOOK_SECRET"] = SECRET
        get_secrets_provider.cache_clear()

        delivered = post("msg_delivered", event("email.delivered"))
        result["delivered"] = [delivered, _row(a.id, first)["status"], _count(a.id, events_sql)]
        result["duplicate"] = [
            post("msg_delivered", event("email.delivered")),
            _count(a.id, events_sql),
        ]
        result["late_delay"] = [
            post("msg_delayed", event("email.delivery_delayed")),
            _row(a.id, first)["status"],
        ]
        result["bounced"] = [
            post("msg_bounced", event("email.bounced")),
            _row(a.id, first)["status"],
        ]
        result["bounce_suppression"] = _count(
            a.id,
            "SELECT count(*) FROM crm_app.suppression WHERE tenant_id = :t AND email = :e"
            " AND origin = 'provider' AND reason = 'bounced'",
            e="ada@example.test",
        )
        body, headers = signed("msg_forged", event("email.complained"))
        result["forged"] = [
            client.post(
                WEBHOOK, content=body.replace(b"complained", b"delivered"), headers=headers
            ).status_code,
            client.post(
                WEBHOOK, content=body, headers={**headers, "svix-signature": "v1,AAAA"}
            ).status_code,
            post("msg_old", event("email.complained"), age=600),
            _count(a.id, events_sql),
        ]
        result["unknown_email"] = [
            post("msg_unknown", event("email.delivered", "re_unknown")),
            _count(a.id, events_sql),
        ]
        result["ignored_type"] = [
            post("msg_opened", event("email.opened")),
            _count(a.id, events_sql),
        ]
        racing_id = _row(a.id, racing)["provider_message_id"]
        result["provider_failed"] = [
            post("msg_failed", event("email.failed", racing_id)),
            _row(a.id, racing)["status"],
            post("msg_failed_late", event("email.delivered", racing_id)),
            _row(a.id, racing)["status"],
        ]
        # An email queued by nobody (K3.5): the worker and the webhook record
        # their own system entries, the provider suppression too; no member.
        with tenant_session_scope(a.id) as session:
            nobody = emails.queue(
                session,
                Scope(workspace=a.id, actor=None),  # type: ignore[arg-type]
                purpose="test",
                to_email="nobody@example.test",
                subject="Hello",
                text_body="Hello.",
            )
        nobody_sent = send(nobody)
        nobody_bounced = post(
            "msg_nobody_bounced",
            event("email.bounced", _row(a.id, nobody)["provider_message_id"]),
        )
        with tenant_session_scope(a.id) as session:
            entries = session.execute(
                text(
                    "SELECT action, actor_type, actor_user_id IS NULL,"
                    " metadata->'system_actor'->>'name', metadata::text"
                    " FROM core.audit_log WHERE tenant_id = :t"
                    " AND (resource_id = :e OR (action = 'crm_app.suppression.added'"
                    " AND metadata->'system_actor'->>'name' = 'crm_app.email_events'))"
                    " ORDER BY created_at"
                ),
                {"t": a.id, "e": str(nobody)},
            ).all()
        result["nobody"] = {
            "outcomes": [nobody_sent, nobody_bounced],
            "entries": [list(row[:4]) for row in entries],
            "address_in_audit": any("nobody@example.test" in row[4] for row in entries),
        }
        result["too_large"] = client.post(
            WEBHOOK, content=b"x" * (70 * 1024), headers={"content-type": "application/json"}
        ).status_code
        result["other_workspace_events"] = _count(b.id, "SELECT count(*) FROM crm_app.email_event")
    result["first"] = str(first)

    print("RESULT " + json.dumps(result, default=str))


if __name__ == "__main__":
    main()

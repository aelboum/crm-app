"""The email provider's webhooks (decisions P6-E, P6-I).

    POST /v1/public/email/resend/events     delivery events
    POST /v1/public/email/resend/inbound    received emails

Public (SaaS-OS `public_route`): Resend calls it with no session. It answers
404 until `RESEND_WEBHOOK_SECRET` is set through the secrets provider, is
limited per client address before anything is read, takes at most 64 KiB,
and refuses a body whose Svix signature is missing, wrong or older than
five minutes (401 `invalid_signature`) before parsing it. A verified event
is recorded once per provider event id; an event type this product does
not track, or an email it does not know, is acknowledged (204) and stored
nowhere, so the provider stops retrying. Nothing from the body is echoed.

The inbound webhook has its own secret (`RESEND_INBOUND_WEBHOOK_SECRET`)
and answers 404 unless that is set and `EMAIL_INBOUND_ENABLED` is on (never
in production). It applies the same limits and signature check, then
records each `email.received` event once, before any processing, and
enqueues the inbound job; a malformed received event is refused (400
`malformed_event`) so it stays visible in the provider's delivery log.
The body names an email, never a workspace: routing happens later, from
server-side data only.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.concurrency import run_in_threadpool
from saas_os.api.auth.config import get_auth_http_config, resolve_client_address
from saas_os.api.errors import route_not_found
from saas_os.api.route_policy import public_route
from saas_os.infra.secrets import get_secrets_provider

from crm_app import emails, inbound
from crm_app.api.forms import _limited
from crm_app.api.inputs import parse_json, raw_body
from crm_app.domains import emails as rules
from crm_app.domains import inbound as inbound_rules
from crm_app.settings import inbound_enabled

public_router = APIRouter(prefix="/v1/public/email", tags=["email webhooks"])

_public = Depends(
    public_route(
        "the email provider's signed delivery events; the signature, not a session,"
        " authenticates the caller"
    )
)


def _secret(name: str = "RESEND_WEBHOOK_SECRET") -> str | None:
    value = get_secrets_provider().get(name)
    return value.strip() if value and value.strip() else None


async def _verified(request: Request, secret: str) -> tuple[str, bytes]:
    """The event id and body of a signed request, or 401 before parsing."""
    address = resolve_client_address(
        request, trust_proxy_headers=get_auth_http_config().trust_proxy_headers
    )
    await _limited(f"email-webhook:{address}")
    body = await raw_body(request, rules.WEBHOOK_BODY_MAX)
    event_id = request.headers.get("svix-id", "")
    valid = rules.signature_valid(
        secret,
        event_id,
        request.headers.get("svix-timestamp", ""),
        request.headers.get("svix-signature", ""),
        body,
        datetime.now(UTC),
    )
    if not valid:
        raise HTTPException(401, detail={"code": "invalid_signature"})
    return event_id, body


@public_router.post(
    "/resend/events",
    status_code=204,
    dependencies=[_public],
    name="resend_email_events",
    openapi_extra={
        "requestBody": {"required": True, "content": {"application/json": {"schema": {}}}}
    },
)
async def resend_events(request: Request) -> Response:
    secret = _secret()
    if secret is None:
        raise route_not_found()
    event_id, body = await _verified(request, secret)
    payload: Any = parse_json(body)
    event = rules.provider_event(event_id, payload)
    if event is not None:
        await run_in_threadpool(emails.apply_event, event)
    return Response(status_code=204)


@public_router.post(
    "/resend/inbound",
    status_code=204,
    dependencies=[_public],
    name="resend_inbound_email",
    openapi_extra={
        "requestBody": {"required": True, "content": {"application/json": {"schema": {}}}}
    },
)
async def resend_inbound(request: Request) -> Response:
    secret = _secret("RESEND_INBOUND_WEBHOOK_SECRET")
    if secret is None or not inbound_enabled() or inbound.production():
        raise route_not_found()
    event_id, body = await _verified(request, secret)
    payload: Any = parse_json(body)
    try:
        event = inbound_rules.received_event(payload)
    except inbound_rules.InboundRejected:
        raise HTTPException(400, detail={"code": "malformed_event"}) from None
    if event is not None and await run_in_threadpool(inbound.record, event_id, event) == "recorded":
        await inbound.enqueue()
    return Response(status_code=204)

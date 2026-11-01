"""The email provider's delivery webhook (decision P6-E).

    POST /v1/public/email/resend/events

Public (SaaS-OS `public_route`): Resend calls it with no session. It answers
404 until `RESEND_WEBHOOK_SECRET` is set through the secrets provider, is
limited per client address before anything is read, takes at most 64 KiB,
and refuses a body whose Svix signature is missing, wrong or older than
five minutes (401 `invalid_signature`) before parsing it. A verified event
is recorded once per provider event id; an event type this product does
not track, or an email it does not know, is acknowledged (204) and stored
nowhere, so the provider stops retrying. Nothing from the body is echoed.
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

from crm_app import emails
from crm_app.api.forms import _limited
from crm_app.api.inputs import parse_json, raw_body
from crm_app.domains import emails as rules

public_router = APIRouter(prefix="/v1/public/email", tags=["email webhooks"])

_public = Depends(
    public_route(
        "the email provider's signed delivery events; the signature, not a session,"
        " authenticates the caller"
    )
)


def _secret() -> str | None:
    value = get_secrets_provider().get("RESEND_WEBHOOK_SECRET")
    return value.strip() if value and value.strip() else None


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
    payload: Any = parse_json(body)
    event = rules.provider_event(event_id, payload)
    if event is not None:
        await run_in_threadpool(emails.apply_event, event)
    return Response(status_code=204)

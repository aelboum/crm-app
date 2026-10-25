"""Self-service signup routes (decisions S-1, S-1.1; `SIGNUP-PLAN.md` §4, Stage C).

    POST /v1/signups           Idempotency-Key header; body {"workspace_name"}
    GET  /v1/signups/current

Both answer 404 while `SIGNUP_ENABLED` is off (`crm_app.settings`), and
need a signed-in person (SaaS-OS's `authenticated` policy). The person is
the server-side session's user; the body has exactly one field, so a
request naming a user, a parent workspace, a role or any authority is
refused (422), and nothing submitted is echoed back.

`POST` order, which is also the counting rule (owner decision of
2026-10-25; `SIGNUP-PLAN.md` §4):

1. the per-person and per-address rate limits (SaaS-OS limiter, failing
   closed with 503); a request refused here is not counted;
2. the platform-wide rolling 24-hour cap, checked and counted atomically
   (`signups.record_attempt`); a request refused only because the cap is
   reached is not counted, and an unavailable counter refuses (503);
3. from here on the request counts, whatever happens next: the
   `Idempotency-Key` (read and validated only now), the verified email, the
   body (read, parsed and validated only now), the per-person workspace
   limit, then provisioning.

The answer: 201 with the new signup (complete, or 202 while still
provisioning); 200 with the existing one for a replay of the same key or
while another signup is unfinished; 409 for a key reused with a different
body or the workspace limit; 429 when the cap is reached.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Request, Response
from fastapi.concurrency import run_in_threadpool
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, ConfigDict, ValidationError
from saas_os.api.auth.config import get_auth_http_config, resolve_client_address
from saas_os.api.dependencies import get_current_session
from saas_os.api.errors import (
    conflict,
    forbidden,
    idempotency_key_invalid,
    invalid_request,
    rate_limited,
    route_not_found,
    service_unavailable,
)
from saas_os.core.idempotency import IdempotencyKeyInvalidError, validate_idempotency_key
from saas_os.core.identity import Session
from saas_os.infra.ratelimit import (
    RateLimitBackendError,
    RateLimitExceededError,
    enforce_rate_limit,
    get_ratelimit_config,
)

from crm_app import signups
from crm_app.domains.signup import InvalidWorkspaceNameError, normalize_workspace_name
from crm_app.settings import signup_enabled, signup_limit

router = APIRouter(prefix="/v1/signups", tags=["signups"])

_RETRY_AFTER_SECONDS = 5
_CAP_RETRY_AFTER_SECONDS = 3600
_IDEMPOTENCY_KEY = "Idempotency-Key"
# A body larger than this cannot hold a valid request; refused unread.
_MAX_BODY_BYTES = 4096


class SignupRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workspace_name: str


class SignupOut(BaseModel):
    id: uuid.UUID
    state: Literal["started", "provisioning", "complete", "failed", "expired"]
    workspace_id: uuid.UUID | None
    created_at: datetime
    error_code: str | None


def _out(view: signups.SignupView) -> SignupOut:
    return SignupOut.model_validate(
        {
            "id": view.id,
            "state": view.state,
            "workspace_id": view.workspace_id,
            "created_at": view.created_at,
            "error_code": view.error_code,
        }
    )


async def _limited(key: str) -> None:
    try:
        await enforce_rate_limit(key, config=get_ratelimit_config())
    except RateLimitExceededError as exc:
        raise rate_limited(exc.retry_after_seconds) from None
    except RateLimitBackendError:
        raise service_unavailable(_RETRY_AFTER_SECONDS) from None


async def _enabled() -> None:
    """The kill switch: while signup is off the routes do not exist."""
    if not signup_enabled():
        raise route_not_found()


async def _signup_caller(
    request: Request,
    _on: Annotated[None, Depends(_enabled)],
    session: Annotated[Session, Depends(get_current_session)],
) -> Session:
    """The signed-in person, after the per-person and per-address limits."""
    await _limited(f"signup:user:{session.user_id}")
    address = resolve_client_address(
        request, trust_proxy_headers=get_auth_http_config().trust_proxy_headers
    )
    await _limited(f"signup:client:{address}")
    return session


def _idempotency_key(request: Request) -> str:
    key = request.headers.get(_IDEMPOTENCY_KEY)
    if key is None:
        raise invalid_request("idempotency_key_required")
    try:
        validate_idempotency_key(key)
    except IdempotencyKeyInvalidError:
        raise idempotency_key_invalid() from None
    return key


async def _payload(request: Request) -> Any:
    raw = await request.body()
    if len(raw) > _MAX_BODY_BYTES:
        raise invalid_request("body_too_large")
    try:
        return json.loads(raw)
    except ValueError:
        raise RequestValidationError(
            [{"loc": ("body",), "msg": "The body is not JSON.", "type": "json_invalid"}]
        ) from None


def _validated(payload: Any) -> str:
    try:
        body = SignupRequest.model_validate(payload)
    except ValidationError as exc:
        raise RequestValidationError(exc.errors(include_input=False)) from None
    try:
        return normalize_workspace_name(body.workspace_name)
    except InvalidWorkspaceNameError:
        raise invalid_request("invalid_workspace_name") from None


@router.post(
    "",
    response_model=SignupOut,
    status_code=201,
    responses={200: {"model": SignupOut}, 202: {"model": SignupOut}},
    openapi_extra={
        "parameters": [
            {
                "name": _IDEMPOTENCY_KEY,
                "in": "header",
                "required": True,
                "schema": {"type": "string", "maxLength": 255},
            }
        ],
        "requestBody": {
            "required": True,
            "content": {"application/json": {"schema": SignupRequest.model_json_schema()}},
        },
    },
)
async def create_signup(
    request: Request,
    response: Response,
    session: Annotated[Session, Depends(_signup_caller)],
) -> SignupOut:
    """The header and the body are read here, after the attempt is counted,
    so a request that passed the rate limits counts even when they are
    malformed (owner decision S-1.2)."""
    try:
        await run_in_threadpool(signups.record_attempt, signup_limit("SIGNUP_MAX_ATTEMPTS_PER_24H"))
    except signups.SignupRefusedError:
        raise rate_limited(_CAP_RETRY_AFTER_SECONDS) from None
    except signups.CounterUnavailableError:
        raise service_unavailable(_RETRY_AFTER_SECONDS) from None
    # Counted from here on.
    idempotency_key = _idempotency_key(request)
    if session.verified_email is None:
        raise forbidden()
    name = _validated(await _payload(request))
    try:
        view, created = await run_in_threadpool(
            signups.start,
            session.user_id,
            idempotency_key,
            name,
            max_workspaces=signup_limit("SIGNUP_MAX_WORKSPACES_PER_USER"),
        )
    except signups.SignupRefusedError as exc:
        raise conflict(exc.code) from None
    if view.state in signups.OPEN_STATES:
        view = await run_in_threadpool(signups.run, view.id, session.user_id)
    if not created:
        response.status_code = 200
    elif view.state != "complete":
        response.status_code = 202
    return _out(view)


@router.get("/current", response_model=SignupOut)
def current_signup(session: Annotated[Session, Depends(_signup_caller)]) -> SignupOut:
    """The person's unfinished signup, else their latest one. Read-only."""
    if session.verified_email is None:
        raise forbidden()
    view = signups.current(session.user_id)
    if view is None:
        raise route_not_found()
    return _out(view)

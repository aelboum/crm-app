"""The public consent confirmation route (decision P7-V).

    POST /v1/public/consent/{workspace_id}/confirm   public

The emailed link opens a page that posts the token (kept in the link's
fragment, so it never reaches a server log). 204 when the consent is, or
already was, confirmed; 404 for an unknown or expired token, the same in
either case. Limited per client address. The token, not a session,
identifies the person; it is looked up only in the path's workspace.
"""

from __future__ import annotations

import re
import uuid

from fastapi import APIRouter, Depends, Request, Response
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, ConfigDict, Field
from saas_os.api.auth.config import get_auth_http_config, resolve_client_address
from saas_os.api.errors import route_not_found
from saas_os.api.route_policy import public_route

from crm_app import consent_confirmations
from crm_app.api.forms import _limited

public_router = APIRouter(prefix="/v1/public/consent", tags=["consent"])

_TOKEN = re.compile(r"[A-Za-z0-9_-]{20,100}")
_public = Depends(
    public_route(
        "a person confirms the consent given with their email address; the token from"
        " the emailed link, not a session, identifies them"
    )
)


class ConfirmIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    token: str = Field(max_length=200)


@public_router.post(
    "/{workspace_id}/confirm", status_code=204, dependencies=[_public], name="confirm_consent"
)
async def confirm_consent(workspace_id: uuid.UUID, body: ConfirmIn, request: Request) -> Response:
    address = resolve_client_address(
        request, trust_proxy_headers=get_auth_http_config().trust_proxy_headers
    )
    await _limited(f"consent-confirm:{address}")
    if not _TOKEN.fullmatch(body.token):
        raise route_not_found()
    confirmed = await run_in_threadpool(consent_confirmations.confirm, workspace_id, body.token)
    if not confirmed:
        raise route_not_found()
    return Response(status_code=204)

"""Where the browser goes after signing out (decision P2-F; finding from the
Phase 2 browser verification, 2026-10-24).

SaaS-OS's `POST /auth/logout` ends the application session only; the
identity provider's own session survives, so on a shared computer the next
"Sign in" would continue as the previous person without a password. The
frontend therefore sends the browser on to the provider's end-session
endpoint (OIDC RP-Initiated Logout 1.0) after the application sign-out,
which ends the provider session and returns to `<PUBLIC_APP_ORIGIN>/app`.

    GET /v1/sign-out-url   public: {"url": ...}

The endpoint is configuration (`OIDC_END_SESSION_ENDPOINT`, validated at
start-up), never discovered at request time. The URL carries only the
public client ID and the fixed return address, which must be registered as
a post-logout redirect URI at the provider (`deploy/local/configure-zitadel.py`
locally). Without the setting the frontend just reloads `/app`.
"""

from __future__ import annotations

import os
from urllib.parse import urlencode

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from saas_os.api.route_policy import public_route
from saas_os.infra.secrets import get_secrets_provider

router = APIRouter(prefix="/v1", tags=["session"])

_public = Depends(
    public_route("public sign-out address: the provider's endpoint and public client ID")
)


class SignOutTarget(BaseModel):
    # None when no end-session endpoint is configured: reload the app.
    url: str | None


@router.get("/sign-out-url", response_model=SignOutTarget, dependencies=[_public])
def sign_out_url() -> SignOutTarget:
    endpoint = os.environ.get("OIDC_END_SESSION_ENDPOINT")
    if not endpoint:
        return SignOutTarget(url=None)
    query = urlencode(
        {
            # Read like the rest of the OIDC settings (crm_app.settings);
            # a public identifier, already in every authorization request.
            "client_id": get_secrets_provider().get("OIDC_CLIENT_ID"),
            "post_logout_redirect_uri": os.environ["PUBLIC_APP_ORIGIN"].rstrip("/") + "/app",
        }
    )
    return SignOutTarget(url=f"{endpoint}?{query}")

"""Applies this project's sign-in security settings to the LOCAL ZITADEL
instance (decision D-IDL; README.md, "Local identity").

    uv run python deploy/local/configure-zitadel.py

Run after `saas-os-local-identity`, and again whenever the local ZITADEL
database is recreated. Idempotent. Development tooling only: the
application never calls ZITADEL (SaaS-OS ADR-0023), and production settings
are applied by the deployment, not by this script.

Settings (instance defaults, so every organisation inherits them):
- no self-registration: accounts come from invitations and provisioning;
- no external identity providers: none is configured or approved;
- unknown usernames are not revealed, so accounts cannot be enumerated;
- lockout after 5 wrong passwords or one-time codes (an administrator
  unlocks the user in the ZITADEL console);
- two-factor authentication stays optional.

And on this project's OIDC application (the one with `OIDC_CLIENT_ID`):
- `<PUBLIC_APP_ORIGIN>/app` is an allowed post-sign-out address, so signing
  out of the application also ends the ZITADEL session (OIDC RP-initiated
  logout, decision P2-F; `crm_app.api.sign_out`).

Uses the bootstrap machine user's token from `deploy/local/.bootstrap/`
(untracked). The token is read from the file and never printed.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.request
from pathlib import Path

TOKEN_FILE = Path(__file__).resolve().parent / ".bootstrap" / "bootstrap.pat"

LOGIN_CHANGES = {
    "allowRegister": False,
    "allowExternalIdp": False,
    "ignoreUnknownUsernames": True,
    "forceMfa": False,
}
LOCKOUT = {"maxPasswordAttempts": "5", "maxOtpAttempts": "5"}

# Read-only fields the login-policy update does not accept.
_NOT_UPDATABLE = {"details", "isDefault", "secondFactors", "multiFactors", "idps"}


def _call(base: str, token: str, method: str, path: str, body: object = None) -> dict:
    # `base` is checked in main() to be http://localhost or http://127.0.0.1.
    request = urllib.request.Request(  # noqa: S310
        base + path,
        method=method,
        data=None if body is None else json.dumps(body).encode(),
        headers={
            "Authorization": "Bearer " + token,
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
        return json.load(response)


def main() -> int:
    base = os.environ.get("OIDC_ISSUER_URL", "http://localhost:8000").rstrip("/")
    if not base.startswith(("http://localhost", "http://127.0.0.1")):
        print(f"refusing: {base} is not a local issuer", file=sys.stderr)
        return 2
    token = TOKEN_FILE.read_text(encoding="utf-8").strip()

    current = _call(base, token, "GET", "/admin/v1/policies/login")["policy"]
    wanted = {k: v for k, v in current.items() if k not in _NOT_UPDATABLE} | LOGIN_CHANGES
    if any(current.get(k, False) != v for k, v in LOGIN_CHANGES.items()):
        _call(base, token, "PUT", "/admin/v1/policies/login", wanted)

    lockout = _call(base, token, "GET", "/admin/v1/policies/lockout")["policy"]
    if any(lockout.get(k) != v for k, v in LOCKOUT.items()):
        _call(base, token, "PUT", "/admin/v1/policies/password/lockout", LOCKOUT)

    login = _call(base, token, "GET", "/admin/v1/policies/login")["policy"]
    lockout = _call(base, token, "GET", "/admin/v1/policies/lockout")["policy"]
    applied = {k: login.get(k, False) for k in LOGIN_CHANGES} | {k: lockout.get(k) for k in LOCKOUT}
    print("local ZITADEL sign-in settings:", json.dumps(applied, sort_keys=True))
    sign_out = _allow_post_logout_redirect(base, token)
    print("post-sign-out address allowed:", sign_out)
    return 0 if applied == LOGIN_CHANGES | LOCKOUT and sign_out else 1


# Fields `UpdateApplication` would reset if omitted (as SaaS-OS's local
# bootstrap re-sends them for the same reason).
_PRESERVED_OIDC = (
    "responseTypes",
    "grantTypes",
    "applicationType",
    "authMethodType",
    "clockSkew",
    "loginVersion",
    "idTokenUserinfoAssertion",
)


def _all(base: str, token: str, path: str, filters: list[dict], key: str) -> list[dict]:
    items: list[dict] = []
    while True:
        page = _call(
            base,
            token,
            "POST",
            path,
            {
                "pagination": {"offset": str(len(items)), "limit": 100, "asc": True},
                "filters": filters,
            },
        )
        batch = page.get(key, [])
        items.extend(batch)
        if len(batch) < 100:
            return items


def _allow_post_logout_redirect(base: str, token: str) -> bool:
    """Adds `<PUBLIC_APP_ORIGIN>/app` to the application's post-logout
    redirect URIs, keeping everything else; idempotent."""
    client_id = os.environ["OIDC_CLIENT_ID"]
    target = os.environ.get("PUBLIC_APP_ORIGIN", "http://localhost:8000").rstrip("/") + "/app"
    projects = _all(base, token, "/zitadel.project.v2.ProjectService/ListProjects", [], "projects")
    for project in projects:
        applications = _all(
            base,
            token,
            "/zitadel.application.v2.ApplicationService/ListApplications",
            [{"projectIdFilter": {"projectId": project["projectId"]}}],
            "applications",
        )
        for app in applications:
            oidc = app.get("oidcConfiguration") or {}
            if oidc.get("clientId") != client_id:
                continue
            current = oidc.get("postLogoutRedirectUris") or []
            if target not in current:
                kept = {key: oidc[key] for key in _PRESERVED_OIDC if key in oidc}
                _call(
                    base,
                    token,
                    "POST",
                    "/zitadel.application.v2.ApplicationService/UpdateApplication",
                    {
                        "applicationId": app["applicationId"],
                        "projectId": project["projectId"],
                        "oidcConfiguration": kept | {"postLogoutRedirectUris": [*current, target]},
                    },
                )
            return True
    print("refusing: no application with OIDC_CLIENT_ID found", file=sys.stderr)
    return False


if __name__ == "__main__":
    raise SystemExit(main())

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

Opt-in trial of LeadStack branding on Login V2 (README.md, "Trying LeadStack
branding on the login pages"); unset leaves branding untouched:
- `ZITADEL_LOCAL_BRANDING=leadstack` sets LeadStack's colours, logo
  (`branding/leadstack-logo.svg`), no watermark, no login-name suffix, and
  replaces every Login V2 text that names Zitadel;
- `ZITADEL_LOCAL_BRANDING=default` restores ZITADEL's own branding and texts.

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

LOGO_FILE = Path(__file__).resolve().parent / "branding" / "leadstack-logo.svg"

# The instance label policy ("branding"). LeadStack's values follow
# frontend/src/styles.css (--accent, --ink, --canvas, --risk-fg); the design
# is light only. ZITADEL's values are its defaults, read from a fresh instance.
BRANDING = {
    "leadstack": {
        "primaryColor": "#0e7c6b",
        "warnColor": "#a3302a",
        "backgroundColor": "#f4f5f7",
        "fontColor": "#161b26",
        "primaryColorDark": "#0e7c6b",
        "warnColorDark": "#a3302a",
        "backgroundColorDark": "#f4f5f7",
        "fontColorDark": "#161b26",
        "hideLoginNameSuffix": True,
        "disableWatermark": True,
        "themeMode": "THEME_MODE_LIGHT",
    },
    "default": {
        "primaryColor": "#5469d4",
        "warnColor": "#cd3d56",
        "backgroundColor": "#fafafa",
        "fontColor": "#000000",
        "primaryColorDark": "#2073c4",
        "warnColorDark": "#ff3b5b",
        "backgroundColorDark": "#111827",
        "fontColorDark": "#ffffff",
        "hideLoginNameSuffix": False,
        "disableWatermark": False,
        "themeMode": "THEME_MODE_AUTO",
    },
}

# Overrides of Login V2's English texts (apps/login/locales/en.json at
# v4.19.5); Login V2 merges them with its defaults. These are all the
# strings that name Zitadel, plus the first page's heading, worded as on
# LeadStack's own sign-in screen (frontend/src/i18n/en.ts).
LEADSTACK_TEXTS = {
    "common": {"title": "Sign in to LeadStack"},
    "loginname": {
        "title": "Sign in to LeadStack",
        "description": "Use your organisation account to open your workspaces.",
        "register": "Create an account",
    },
    "register": {"description": "Create your LeadStack account."},
    "idp": {"signInWithZitadel": "Sign in with LeadStack"},
    "device": {
        "request": {
            "disclaimer": (
                "By clicking Allow, you allow {appName} and LeadStack to use your "
                "information in accordance with their respective terms of service "
                "and privacy policies. You can revoke this access at any time."
            )
        }
    },
}

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
    branding = os.environ.get("ZITADEL_LOCAL_BRANDING", "").strip().lower()
    if branding not in ("", *BRANDING):
        print(
            "refusing: ZITADEL_LOCAL_BRANDING must be leadstack, default or unset",
            file=sys.stderr,
        )
        return 2

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
    brand = _apply_branding(base, token, branding) if branding else True
    if branding:
        print(f"login branding: {branding} applied:", brand)
    return 0 if applied == LOGIN_CHANGES | LOCKOUT and sign_out and brand else 1


def _apply_branding(base: str, token: str, name: str) -> bool:
    """Sets the instance branding and Login V2's English texts, then
    activates the branding (ZITADEL keeps edits as a preview until then);
    idempotent."""
    _call(base, token, "PUT", "/admin/v1/policies/label", BRANDING[name])
    if name == "leadstack":
        _upload(base, token, "/assets/v1/instance/policy/label/logo", LOGO_FILE)
    else:
        _call(base, token, "DELETE", "/assets/v1/instance/policy/label/logo")
    _call(base, token, "POST", "/admin/v1/policies/label/_activate", {})
    texts = LEADSTACK_TEXTS if name == "leadstack" else {}
    _call(
        base,
        token,
        "PUT",
        "/v2/settings/hosted_login_translation",
        {"instance": True, "locale": "en", "translations": texts},
    )
    policy = _call(base, token, "GET", "/admin/v1/policies/label")["policy"]
    stored = _call(
        base, token, "GET", "/v2/settings/hosted_login_translation?instance=true&locale=en"
    ).get("translations", {})
    return (
        all(policy.get(k, False) == v for k, v in BRANDING[name].items())
        and bool(policy.get("logoUrl")) == (name == "leadstack")
        and all(k in stored for k in texts)
    )


def _upload(base: str, token: str, path: str, file: Path) -> None:
    """POSTs `file` as the multipart field `file` (ZITADEL's asset API)."""
    boundary = "crm-app-local-upload"
    body = (
        (
            f'--{boundary}\r\nContent-Disposition: form-data; name="file"; '
            f'filename="{file.name}"\r\nContent-Type: image/svg+xml\r\n\r\n'
        ).encode()
        + file.read_bytes()
        + f"\r\n--{boundary}--\r\n".encode()
    )
    request = urllib.request.Request(  # noqa: S310
        base + path,
        method="POST",
        data=body,
        headers={
            "Authorization": "Bearer " + token,
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
    )
    with urllib.request.urlopen(request, timeout=30):  # noqa: S310
        pass


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

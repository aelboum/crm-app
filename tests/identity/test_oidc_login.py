"""OIDC login against the local ZITADEL, end to end (opt-in).

Runs only with `CRM_APP_IDENTITY_TEST=1` and the development settings
exported, with the `identity` Compose profile running and the OIDC
application bootstrapped (README.md, "Local identity"). It starts the real
application server behind the `edge` proxy and signs in as ZITADEL's
first-instance administrator through the real OIDC flow: the application's
`/auth/login` starts an authorization request (PKCE, state, nonce), ZITADEL
checks the administrator's password and issues the code, and the
application's `/auth/callback` exchanges it and issues the SaaS-OS session.

ZITADEL's Login V2 pages are a JavaScript application that a plain HTTP
client cannot drive, so the test does what those pages do on the server
side (decision P2-F, owner, 2026-10-24): it creates a ZITADEL session with
the user and password checks and finalises the authorization request
through ZITADEL's v2 API, authenticated with the local login client's
token (`deploy/local/.bootstrap/login-client.pat`, written by ZITADEL's
first-instance setup, git-ignored). The login pages themselves are checked
by a manual browser sign-in.

Nothing secret is printed or asserted on: the password and the token come
from the environment and the bootstrap file, and are checked to be absent
from the server's log.
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest

from tests.support import REPO_ROOT

pytestmark = pytest.mark.skipif(
    os.environ.get("CRM_APP_IDENTITY_TEST") != "1",
    reason="opt-in: set CRM_APP_IDENTITY_TEST=1 with local ZITADEL running",
)

# Never printed, and checked to be absent from the server's log.
_SECRET_NAMES = ("ZITADEL_FIRSTINSTANCE_ADMIN_PASSWORD", "POSTGRES_PASSWORD", "APP_DB_PASSWORD")


def _login_name() -> str:
    explicit = os.environ.get("ZITADEL_FIRSTINSTANCE_ADMIN_LOGIN_NAME")
    if explicit:
        return explicit
    # ZITADEL's login name is username@<org>.<external domain>.
    issuer_host = urlsplit(os.environ["OIDC_ISSUER_URL"]).hostname
    return f"{os.environ['ZITADEL_FIRSTINSTANCE_ADMIN_USERNAME']}@crm-app-local.{issuer_host}"


def _port_is_free(host: str, port: int) -> bool:
    with socket.socket() as probe:
        return probe.connect_ex((host, port)) != 0


def _app_port() -> int:
    """The port the `edge` proxy forwards the public origin to (decision
    D-IDL, `deploy/local/Caddyfile`: `CRM_APP_UPSTREAM`, default
    `http://host.docker.internal:8001`). The public origin's own port
    belongs to the proxy, which also serves ZITADEL's login on that origin."""
    upstream = os.environ.get("CRM_APP_UPSTREAM", "http://host.docker.internal:8001")
    return urlsplit(upstream).port or 80


@pytest.fixture
def app_server(tmp_path: Path) -> Iterator[tuple[str, Path]]:
    origin = os.environ["PUBLIC_APP_ORIGIN"]
    port = _app_port()
    assert _port_is_free("127.0.0.1", port), f"port {port} is already in use"
    log_path = tmp_path / "server.log"
    with log_path.open("w", encoding="utf-8") as log:
        server = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "crm_app.app:create_app",
                "--factory",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
            ],
            cwd=REPO_ROOT,
            env=dict(os.environ),
            stdout=log,
            stderr=subprocess.STDOUT,
        )
        try:
            deadline = time.monotonic() + 60
            while True:
                try:
                    if httpx.get(f"{origin}/readyz", timeout=2).status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                assert server.poll() is None, log_path.read_text(encoding="utf-8")[-2000:]
                assert time.monotonic() < deadline, "server never became ready"
                time.sleep(0.5)
            yield origin, log_path
        finally:
            server.terminate()
            try:
                server.wait(timeout=30)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait(timeout=30)


# The local login client's token (ZITADEL_FIRSTINSTANCE_LOGINCLIENTPATPATH in
# deploy/local/compose.yaml): what ZITADEL's own Login V2 uses for these calls.
_LOGIN_CLIENT_PAT = Path(
    os.environ.get(
        "CRM_APP_LOGIN_CLIENT_PAT_PATH",
        str(REPO_ROOT / "deploy" / "local" / ".bootstrap" / "login-client.pat"),
    )
)


def _sign_in(client: httpx.Client, origin: str) -> None:
    """The OIDC sign-in, completing ZITADEL's part through its v2 API as its
    Login V2 does: create a session with the user and password checks, then
    finalise the authorization request with it and follow the callback."""
    issuer = os.environ["OIDC_ISSUER_URL"].rstrip("/")
    token = _LOGIN_CLIENT_PAT.read_text(encoding="utf-8").strip()
    zitadel = {"Authorization": f"Bearer {token}"}

    # The application starts the flow; ZITADEL sends the browser to Login V2
    # with the authorization request's ID.
    started = client.get(f"{origin}/auth/login")
    login_page = urlsplit(str(started.url))
    assert login_page.path.startswith("/ui/v2/login"), "ZITADEL did not show its login"
    request_id = parse_qs(login_page.query)["requestId"][0].removeprefix("oidc_")

    session = client.post(
        f"{issuer}/v2/sessions",
        headers=zitadel,
        json={
            "checks": {
                "user": {"loginName": _login_name()},
                "password": {"password": os.environ["ZITADEL_FIRSTINSTANCE_ADMIN_PASSWORD"]},
            }
        },
    )
    assert session.status_code in (200, 201), f"session not created: {session.status_code}"
    created = session.json()

    finalised = client.post(
        f"{issuer}/v2/oidc/auth_requests/{request_id}",
        headers=zitadel,
        json={
            "session": {
                "sessionId": created["sessionId"],
                "sessionToken": created["sessionToken"],
            }
        },
    )
    assert finalised.status_code == 200, f"authorization not finalised: {finalised.status_code}"

    # Back to the application's callback, which exchanges the code.
    landed = client.get(finalised.json()["callbackUrl"])
    assert urlsplit(str(landed.url)).netloc == urlsplit(origin).netloc
    assert not urlsplit(str(landed.url)).path.startswith("/auth/callback")


def test_login_session_and_logout(app_server: tuple[str, Path]) -> None:
    origin, log_path = app_server
    with httpx.Client(follow_redirects=True, timeout=30) as client:
        assert client.get(f"{origin}/auth/me").status_code == 401

        _sign_in(client, origin)

        me = client.get(f"{origin}/auth/me")
        assert me.status_code == 200
        assert set(me.json()) == {"user_id"}

        # Cookie-authenticated mutations must carry the application's Origin
        # (SaaS-OS ADR-0044); without it the session must survive.
        refused = client.post(f"{origin}/auth/logout", headers={"Origin": "https://evil.example"})
        assert refused.status_code == 403
        assert client.get(f"{origin}/auth/me").status_code == 200

        # Where the frontend sends the browser next, to end ZITADEL's session
        # too (decision P2-F): the issuer's own end-session endpoint.
        sign_out_url = client.get(f"{origin}/v1/sign-out-url").json()["url"]
        if os.environ.get("OIDC_END_SESSION_ENDPOINT"):
            discovered = client.get(
                f"{os.environ['OIDC_ISSUER_URL'].rstrip('/')}/.well-known/openid-configuration"
            ).json()["end_session_endpoint"]
            assert sign_out_url.split("?")[0] == discovered

        logged_out = client.post(f"{origin}/auth/logout", headers={"Origin": origin})
        assert logged_out.status_code < 400
        assert client.get(f"{origin}/auth/me").status_code == 401

    log = log_path.read_text(encoding="utf-8")
    for name in _SECRET_NAMES:
        value = os.environ.get(name)
        if value:
            assert value not in log, f"{name} appeared in the server log"
    assert _LOGIN_CLIENT_PAT.read_text(encoding="utf-8").strip() not in log

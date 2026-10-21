"""OIDC login against the local ZITADEL, end to end (opt-in).

Runs only with `CRM_APP_IDENTITY_TEST=1` and the development settings
exported, with the `identity` Compose profile running and the OIDC
application bootstrapped (README.md, "Local identity"). It starts the real
application server, signs in as ZITADEL's first-instance administrator
through ZITADEL's own login pages, and checks the session SaaS-OS issues.

ZITADEL's login pages are third-party HTML, so this test is deliberately
opt-in: a ZITADEL upgrade may change them. Nothing secret is printed or
asserted on; the password comes from the environment.
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from collections.abc import Iterator
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlsplit

import httpx
import pytest

from tests.support import REPO_ROOT

pytestmark = pytest.mark.skipif(
    os.environ.get("CRM_APP_IDENTITY_TEST") != "1",
    reason="opt-in: set CRM_APP_IDENTITY_TEST=1 with local ZITADEL running",
)

# Never printed, and checked to be absent from the server's log.
_SECRET_NAMES = ("ZITADEL_FIRSTINSTANCE_ADMIN_PASSWORD", "POSTGRES_PASSWORD", "APP_DB_PASSWORD")


class _FirstForm(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.action: str | None = None
        self.fields: dict[str, str] = {}
        self.buttons: list[tuple[str | None, str]] = []
        self._inside = False
        self._done = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key: value or "" for key, value in attrs}
        if tag == "form" and not self._done:
            self.action, self._inside = values.get("action", ""), True
        elif self._inside and tag in ("input", "button"):
            if tag == "button" or values.get("type") == "submit":
                self.buttons.append((values.get("name"), values.get("value", "")))
            elif values.get("name"):
                self.fields[values["name"]] = values.get("value", "")

    def handle_endtag(self, tag: str) -> None:
        if tag == "form" and self._inside:
            self._inside, self._done = False, True


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


@pytest.fixture
def app_server(tmp_path: Path) -> Iterator[tuple[str, Path]]:
    origin = os.environ["PUBLIC_APP_ORIGIN"]
    port = urlsplit(origin).port or 80
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


def _sign_in(client: httpx.Client, origin: str) -> None:
    password = os.environ["ZITADEL_FIRSTINSTANCE_ADMIN_PASSWORD"]
    response = client.get(f"{origin}/auth/login")
    for _ in range(8):
        if urlsplit(str(response.url)).netloc == urlsplit(origin).netloc:
            return
        form = _FirstForm()
        form.feed(response.text)
        assert form.action is not None, f"no form at {urlsplit(str(response.url)).path}"
        data = dict(form.fields)
        if "loginName" in data:
            data["loginName"] = _login_name()
        if "password" in data:
            data["password"] = password
        if any(name == "skip" for name, _ in form.buttons):
            data["skip"] = "true"  # the optional second-factor setup prompt
        response = client.post(urljoin(str(response.url), form.action), data=data)
    pytest.fail("the login flow did not return to the application")


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

        logged_out = client.post(f"{origin}/auth/logout", headers={"Origin": origin})
        assert logged_out.status_code < 400
        assert client.get(f"{origin}/auth/me").status_code == 401

    log = log_path.read_text(encoding="utf-8")
    for name in _SECRET_NAMES:
        value = os.environ.get(name)
        if value:
            assert value not in log, f"{name} appeared in the server log"

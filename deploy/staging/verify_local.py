"""Check the running local staging stack against the brief's exit criteria.

    uv run python deploy/staging/verify_local.py

Needs the stack from `compose.yaml` running with the `stateful-local`
profile (see its header). Prints one line per check and exits 1 if any
fails. Covers what a local run can prove (decision D-STG):

- E1  /healthz and /readyz 200 over HTTPS through the edge.
- E2  the app refuses to start with a plain-text database or Redis URL.
- E3  both migration histories at head, applied over TLS by a
      non-superuser owner that cannot bypass Row-Level Security; the app
      holds no migration or admin credential.
- E6  every email switch refused at start-up in production.
- E7  the worker has no direct route out; its proxy allows CONNECT to a
      public IPv4 address on 443 only.
- E4  sign-in through the stack's ZITADEL on the app's own origin: the
      app starts the flow, ZITADEL authenticates, the app's callback issues
      a Secure, HttpOnly session; the app verified its issuer against the
      local CA only; sign-out ends the session and continues to ZITADEL's
      end-session endpoint. Not the brief's whole E4: no browser, no MFA.
- E5  through that signed-in session, the user's own workspace answers and
      another owner's workspace is refused, and the directory lists only
      the user's own.
- E10 the edge caps request bodies and replaces X-Forwarded-For.

E4 and E5 need `identity_local.py` to have run. ZITADEL's Login V2 pages
are a JavaScript application, so the sign-in does what those pages do on
the server side, as tests/identity/test_oidc_login.py does: a ZITADEL
session with the user and password checks, then the authorization request
finalised with it (the login client's token from `.local/bootstrap/`).
The two workspaces are provisioned with `crm_app.provision`, as an operator
would, and found again on later runs.

E8 (backup and restore) and E9 (alerting) need the backup timers and
monitoring in the stack; they are not checked here yet.

Every command run here is a fixed `docker` invocation built in this file;
every URL is the fixed local origin.
"""

from __future__ import annotations

import json
import os
import shutil
import ssl
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import httpx

HERE = Path(__file__).resolve().parent
LOCAL = HERE / ".local"
DOCKER = shutil.which("docker") or "docker"
COMPOSE = [
    DOCKER,
    "compose",
    "--env-file",
    str(LOCAL / "compose.env"),
    "-f",
    str(HERE / "compose.yaml"),
    "--profile",
    "stateful-local",
]
ORIGIN = "https://leadstack.localhost:8443"
PROJECT = "crm-app-staging"
SAAS_OS_HEAD = "e2b7c4d9a1f6"  # pragma: allowlist secret
results: list[tuple[str, bool, str]] = []

_HEADS = """
import os, psycopg
url = os.environ["MIGRATIONS_DATABASE_URL"].replace("postgresql+psycopg://", "postgresql://")
with psycopg.connect(url) as c:
    core = c.execute("SELECT version_num FROM alembic_version_saas_os").fetchone()[0]
    product = c.execute("SELECT version_num FROM alembic_version").fetchone()[0]
    role = c.execute(
        "SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user"
    ).fetchone()
    tls = c.execute("SELECT ssl FROM pg_stat_ssl WHERE pid = pg_backend_pid()").fetchone()[0]
print(core, product, role[0], role[1], tls)
"""

_CREDENTIALS = """
import os
print(sorted(k for k in os.environ if any(w in k for w in ("MIGRATIONS", "POSTGRES", "OWNER"))))
"""

_EGRESS = """
import json, socket
def direct(host, port):
    try:
        socket.create_connection((host, port), timeout=5).close()
        return "connected"
    except OSError as exc:
        return type(exc).__name__
def connect(target):
    s = socket.create_connection(("egress-proxy", 3128), timeout=10)
    s.sendall(f"CONNECT {target} HTTP/1.1\\r\\nHost: {target}\\r\\n\\r\\n".encode())
    line = s.recv(200).split(b"\\r\\n", 1)[0].decode()
    s.close()
    return line.split(" ")[1] if " " in line else line
print(json.dumps({
    "direct": direct("1.1.1.1", 443),
    "public 443": connect("1.1.1.1:443"),
    "public 80": connect("1.1.1.1:80"),
    "a host name": connect("example.com:443"),
    "10.0.0.1": connect("10.0.0.1:443"),
    "172.16.0.10": connect("172.16.0.10:443"),
}))
"""

_START = """
from sqlalchemy import text
from crm_app.app import create_app
from saas_os.infra.db import session_scope
create_app()
with session_scope() as session:
    session.execute(text("SELECT 1"))
print("STARTED")
"""

_ECHO = """
import http.server as h
class E(h.BaseHTTPRequestHandler):
    def do_GET(self):
        b = (self.headers.get("X-Forwarded-For") or "").encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)
h.HTTPServer(("0.0.0.0", 8000), E).serve_forever()
"""


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))
    print(f"{'PASS' if ok else 'FAIL'}  {name}{(' - ' + detail) if detail else ''}")


def run(args: list[str], stdin: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 - fixed docker commands built in this file
        args, input=stdin, capture_output=True, text=True, timeout=240, check=False
    )


def compose(*args: str, stdin: str | None = None) -> subprocess.CompletedProcess[str]:
    return run([*COMPOSE, *args], stdin)


def settings() -> dict[str, str]:
    lines = (LOCAL / "app.env").read_text(encoding="utf-8").splitlines()
    return dict(line.split("=", 1) for line in lines if "=" in line and not line.startswith("#"))


def edge_context() -> ssl.SSLContext:
    """Trust only the local CA, which issued the edge's certificate."""
    return ssl.create_default_context(cafile=str(LOCAL / "ca.crt"))


def fetch(
    path: str,
    context: ssl.SSLContext,
    *,
    body: bytes | None = None,
    headers: dict[str, str] | None = None,
) -> tuple[int, str]:
    method = "POST" if body is not None else "GET"
    url = ORIGIN + path
    req = urllib.request.Request(url, data=body, headers=headers or {}, method=method)  # noqa: S310
    try:
        with urllib.request.urlopen(req, context=context, timeout=15) as resp:  # noqa: S310 - fixed https origin
            return resp.status, resp.read().decode(errors="replace")
    except urllib.error.HTTPError as exc:
        return exc.code, ""
    except urllib.error.URLError:
        # The edge closed the connection mid-upload: refused (status 0).
        return 0, ""


def refuses(**overrides: str) -> tuple[bool, str]:
    """Start the app once with `overrides`; True when start-up refuses."""
    values = {**settings(), **overrides}
    with tempfile.NamedTemporaryFile("w", suffix=".env", delete=False, encoding="utf-8") as handle:
        handle.write("\n".join(f"{k}={v}" for k, v in values.items()) + "\n")
        path = handle.name
    try:
        started = run(
            [
                DOCKER,
                "run",
                "--rm",
                "--network",
                f"{PROJECT}_internal",
                "--env-file",
                path,
                "-v",
                f"{LOCAL / 'ca.crt'}:/certs/ca.crt:ro",
                "crm-app:staging",
                "python",
                "-c",
                _START,
            ]
        )
    finally:
        os.unlink(path)
    last = (started.stderr.strip().splitlines() or [""])[-1][:140]
    return "STARTED" not in started.stdout and started.returncode != 0, last


def forwarded_for(context: ssl.SSLContext) -> tuple[bool, str]:
    """What the app would see as X-Forwarded-For when a client sends one:
    the app is swapped for a one-off echo service under its name, then
    started again."""
    compose("stop", "app")
    echo = run(
        [
            DOCKER,
            "run",
            "-d",
            "--rm",
            "--name",
            f"{PROJECT}-xff-echo",
            "--network",
            f"{PROJECT}_edge",
            "--network-alias",
            "app",
            "crm-app:staging",
            "python",
            "-c",
            _ECHO,
        ]
    )
    seen = ""
    try:
        for _ in range(20):
            try:
                status, seen = fetch("/xff", context, headers={"X-Forwarded-For": "6.6.6.6"})
                if status == 200:
                    break
            except (urllib.error.URLError, ConnectionError):
                pass
            time.sleep(1)
    finally:
        run([DOCKER, "rm", "-f", f"{PROJECT}-xff-echo"])
        compose("start", "app")
    return echo.returncode == 0 and seen != "" and "6.6.6.6" not in seen, seen


def _compose_env() -> dict[str, str]:
    lines = (LOCAL / "compose.env").read_text(encoding="utf-8").splitlines()
    return dict(line.split("=", 1) for line in lines if "=" in line and not line.startswith("#"))


def sign_in(client: httpx.Client) -> tuple[bool, str, str]:
    """The OIDC sign-in as ZITADEL's administrator; returns (signed in, the
    user's OIDC subject, detail)."""
    token = (LOCAL / "bootstrap" / "login-client.pat").read_text(encoding="utf-8").strip()
    zitadel = {"Authorization": f"Bearer {token}"}
    started = client.get(f"{ORIGIN}/auth/login")
    page = urlsplit(str(started.url))
    if not page.path.startswith("/ui/v2/login"):
        return False, "", f"not sent to Login V2 ({started.status_code} {page.path})"
    request_id = parse_qs(page.query)["requestId"][0].removeprefix("oidc_")
    password = _compose_env()["ZITADEL_ADMIN_PASSWORD"]
    session = client.post(
        f"{ORIGIN}/v2/sessions",
        headers=zitadel,
        json={
            "checks": {
                "user": {"loginName": "admin@crm-app-staging.leadstack.localhost"},
                "password": {"password": password},
            }
        },
    )
    if session.status_code not in (200, 201):
        return False, "", f"session {session.status_code}"
    created = session.json()
    detail = client.get(f"{ORIGIN}/v2/sessions/{created['sessionId']}", headers=zitadel)
    subject = detail.json()["session"]["factors"]["user"]["id"]
    finalised = client.post(
        f"{ORIGIN}/v2/oidc/auth_requests/{request_id}",
        headers=zitadel,
        json={
            "session": {"sessionId": created["sessionId"], "sessionToken": created["sessionToken"]}
        },
    )
    if finalised.status_code != 200:
        return False, subject, f"finalise {finalised.status_code}"
    landed = client.get(finalised.json()["callbackUrl"])
    path = urlsplit(str(landed.url)).path
    return not path.startswith("/auth/callback") and landed.status_code < 400, subject, path


def session_cookie_flags(client: httpx.Client) -> str:
    """The flags on the app's session cookie (SaaS-OS's default name)."""
    for cookie in client.cookies.jar:
        if cookie.name.endswith("saas_os_session"):
            secure = "Secure" if cookie.secure else "not Secure"
            httponly = "HttpOnly" if cookie.has_nonstandard_attr("HttpOnly") else "not HttpOnly"
            return f"{cookie.name}: {secure}, {httponly}"
    return "no app cookie"


def provision(name: str, subject: str) -> str:
    """An operator's `crm_app.provision` in a one-off app container; the
    workspace's ID."""
    done = compose(
        "run",
        "--rm",
        "--no-deps",
        "-T",
        "app",
        "python",
        "-m",
        "crm_app.provision",
        "--name",
        name,
        "--owner-issuer",
        ORIGIN,
        "--owner-subject",
        subject,
        "--confirm-production",
    )
    for line in done.stdout.splitlines():
        if line.startswith("workspace id:"):
            return line.split(":", 1)[1].strip()
    return ""


def identity_checks() -> None:
    if "staging-placeholder" in settings().get("OIDC_CLIENT_ID", "staging-placeholder"):
        check("E4 sign-in (run identity_local.py first)", False)
        return
    with httpx.Client(
        verify=ssl.create_default_context(cafile=str(LOCAL / "ca.crt")),
        follow_redirects=True,
        timeout=30,
        trust_env=False,
    ) as client:
        check(
            "E4 signed out, /auth/me is refused", client.get(f"{ORIGIN}/auth/me").status_code == 401
        )
        ok, subject, detail = sign_in(client)
        check("E4 sign-in through ZITADEL on the app's origin", ok, detail)
        me = client.get(f"{ORIGIN}/auth/me")
        check("E4 signed in, /auth/me answers", me.status_code == 200, str(me.status_code))
        flags = session_cookie_flags(client)
        check(
            "E4 the session cookie is Secure and HttpOnly",
            "not" not in flags and ":" in flags,
            flags,
        )
        if not ok:
            return

        own = provision("Staging check: own", subject)
        other = provision("Staging check: other owner", "staging-check-nobody")
        check("E5 two workspaces provisioned", bool(own and other), f"{own} {other}")
        answered = client.get(f"{ORIGIN}/v1/workspaces/{own}")
        check(
            "E5 the user's own workspace answers",
            answered.status_code == 200,
            str(answered.status_code),
        )
        for path in (f"/v1/workspaces/{other}", f"/v1/workspaces/{other}/members"):
            refused = client.get(ORIGIN + path)
            check(
                f"E5 another owner's workspace is refused ({path.rsplit('/', 1)[-1][:8]})",
                refused.status_code in (403, 404),
                str(refused.status_code),
            )
        listed = client.get(f"{ORIGIN}/v1/workspaces").text
        check("E5 the directory lists only the user's own", own in listed and other not in listed)

        # Sign-out: the app's session ends, and the address the frontend
        # sends the browser to next is ZITADEL's own end-session endpoint.
        sign_out = client.get(f"{ORIGIN}/v1/sign-out-url").json().get("url") or ""
        check(
            "E4 sign-out continues to ZITADEL's end-session endpoint",
            sign_out.startswith(f"{ORIGIN}/oidc/v1/end_session"),
            sign_out.split("?", 1)[0],
        )
        ended = client.post(f"{ORIGIN}/auth/logout", headers={"Origin": ORIGIN})
        after = client.get(f"{ORIGIN}/auth/me").status_code
        check("E4 signed out, the session is gone", ended.status_code < 400 and after == 401)


def main() -> int:
    if not (LOCAL / "app.env").exists():
        print("run prepare_local.py and start the stack first", file=sys.stderr)
        return 2
    context = edge_context()

    for path in ("/healthz", "/readyz"):
        status, _ = fetch(path, context)
        check(f"E1 {path} over HTTPS", status == 200, str(status))

    values = settings()
    plain = values["DATABASE_URL"].split("?", 1)[0] + "?sslmode=disable"
    check("E2 refuses sslmode=disable", *refuses(DATABASE_URL=plain))
    no_tls = values["REDIS_URL"].replace("rediss://", "redis://", 1)
    check("E2 refuses redis:// (no TLS)", *refuses(REDIS_URL=no_tls))

    heads = compose("run", "--rm", "--no-deps", "-T", "migrate", "python", "-", stdin=_HEADS)
    parts = heads.stdout.split()
    versions = Path(__file__).resolve().parents[2] / "src/crm_app/migrations/versions"
    product_head = sorted(p.stem for p in versions.glob("0*.py"))[-1]
    check("E3 SaaS-OS migrations at head", parts[:1] == [SAAS_OS_HEAD], " ".join(parts[:2]))
    check("E3 product migrations at head", parts[1:2] == [product_head], product_head)
    check("E3 owner is no superuser, cannot bypass RLS", parts[2:4] == ["False", "False"])
    check("E3 the owner's connection uses TLS", parts[4:5] == ["True"])
    held = compose("exec", "-T", "app", "python", "-", stdin=_CREDENTIALS).stdout.strip()
    check("E3 the app holds no migration or admin credential", held == "[]", held)

    identity_checks()

    # With a sender set, so the only reason left to refuse is production.
    sender = {"EMAIL_DEFAULT_SENDER": "team@mail.example.test"}
    for flag in (
        "EMAIL_SENDING_ENABLED",
        "EMAIL_CONVERSATION_SENDING_ENABLED",
        "EMAIL_CAMPAIGN_SENDING_ENABLED",
        "EMAIL_INBOUND_ENABLED",
        "EMAIL_CUSTOMER_DOMAINS_ENABLED",
    ):
        refused, why = refuses(**sender, **{flag: "true"})
        check(f"E6 refuses {flag}=true in production", refused and "production" in why, why)

    probe = compose("exec", "-T", "worker", "python", "-", stdin=_EGRESS)
    try:
        egress = json.loads(probe.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        egress = {}
    direct = str(egress.get("direct"))
    check("E7 the worker has no direct route out", direct not in ("None", "connected"), direct)
    public = str(egress.get("public 443"))
    check("E7 the proxy allows CONNECT to a public IPv4 on 443", public == "200", public)
    for target in ("public 80", "a host name", "10.0.0.1", "172.16.0.10"):
        answer = str(egress.get(target))
        check(f"E7 the proxy refuses {target}", answer == "403", answer)

    big = b"x" * (7 * 1024 * 1024)
    status, _ = fetch("/v1/workspaces", context, body=big)
    check("E10 the edge refuses a 7 MB body", status in (0, 413), str(status or "aborted"))
    form = "/v1/public/forms/x/submissions"
    json_type = {"Content-Type": "application/json"}
    status, _ = fetch(form, context, body=b"x" * (100 * 1024), headers=json_type)
    check("E10 the edge refuses a 100 KB public body", status in (0, 413), str(status or "aborted"))
    status, _ = fetch(form, context, body=b"{}", headers=json_type)
    check("E10 a small public body reaches the app", status not in (413, 502), str(status))
    check("E10 the edge replaces a client's X-Forwarded-For", *forwarded_for(context))

    failed = [name for name, ok, _ in results if not ok]
    print(f"\n{len(results) - len(failed)} passed, {len(failed)} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

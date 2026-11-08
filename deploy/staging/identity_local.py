"""Create the OIDC application in the local staging stack's ZITADEL.

    uv run python deploy/staging/identity_local.py

Run once after the stack first starts (and again after `down -v`). Like
`saas-os-local-identity` and `deploy/local/configure-zitadel.py` for local
development, and for the same reason: the stack's ZITADEL starts empty.

1. `saas-os-local-identity` finds or creates the project and the public
   PKCE application, with the callback derived from the origin and the
   Login V2 address on the same origin (SaaS-OS ADR-0025).
2. `deploy/local/configure-zitadel.py` applies the sign-in settings (no
   self-registration, no username probing, lockout) and registers
   `<origin>/auth/login` as the post-sign-out address.
3. The client ID ZITADEL assigned replaces the placeholder in `app.env`,
   and `app` and `worker` are recreated to read it.

Both calls trust `.local/trust.crt` (the local CA, plus the public CAs on
a host) and use the bootstrap token ZITADEL wrote to `.local/bootstrap/`
(git-ignored); the token is never printed.

On the staging VPS (decision D-STG.5) it runs inside the app image, on the
edge network, with `--origin https://<host> --no-restart`; the host shell
then recreates `app` and `worker`. The bootstrap token is a staging
shortcut: production configures ZITADEL with a system-user key (SaaS-OS
ADR-0025 section 7).
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
LOCAL = HERE / ".local"
ORIGIN = "https://leadstack.localhost:8443"
DOCKER = shutil.which("docker") or "docker"
IDENTITY = shutil.which("saas-os-local-identity") or "saas-os-local-identity"


def _run(args: list[str], env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 - fixed commands built in this file
        args, env=env, capture_output=True, text=True, timeout=300, check=False
    )


def _options(argv: list[str]) -> tuple[str, bool] | None:
    """`--origin https://<host>` and `--no-restart` (a host, D-STG.5)."""
    rest = [a for a in argv if a != "--no-restart"]
    if not rest:
        return ORIGIN, "--no-restart" not in argv
    if len(rest) == 2 and rest[0] == "--origin" and rest[1].startswith("https://"):
        return rest[1].rstrip("/"), "--no-restart" not in argv
    return None


def main(argv: list[str]) -> int:
    options = _options(argv)
    pat = LOCAL / "bootstrap" / "bootstrap.pat"
    if options is None or not pat.exists():
        print(
            "usage: identity_local.py [--origin https://<host>] [--no-restart], "
            "after the stack has started (it writes the bootstrap token)",
            file=sys.stderr,
        )
        return 2
    origin, restart = options
    trust = LOCAL / "trust.crt"
    if not trust.exists():
        trust = LOCAL / "ca.crt"
    env = {
        **os.environ,
        "OIDC_CA_BUNDLE": str(trust),
        # configure-zitadel.py uses urllib's default context.
        "SSL_CERT_FILE": str(trust),
        "OIDC_ISSUER_URL": origin,
        "PUBLIC_APP_ORIGIN": origin,
        # configure-zitadel.py refuses any other issuer than a local one or
        # exactly this named staging host (D-STG.5).
        "ZITADEL_STAGING_ISSUER": origin,
        "ZITADEL_BOOTSTRAP_PAT_PATH": str(pat),
    }
    created = _run(
        [
            IDENTITY,
            "--zitadel-url",
            origin,
            "--pat-path",
            str(pat),
            "--public-app-origin",
            origin,
            "--project-name",
            "crm-app",
            "--application-name",
            "crm-app-backend",
            "--login-v2-base-uri",
            origin + "/ui/v2/login/",
        ],
        env,
    )
    found = re.search(r"OIDC_CLIENT_ID=(\d+)", created.stdout)
    if created.returncode != 0 or not found:
        print("saas-os-local-identity failed", file=sys.stderr)
        print(created.stderr[-1500:], file=sys.stderr)
        return 1
    client_id = found.group(1)

    configured = _run(
        [sys.executable, str(HERE.parent / "local" / "configure-zitadel.py")],
        {**env, "OIDC_CLIENT_ID": client_id},
    )
    if configured.returncode != 0:
        print("configure-zitadel.py failed", file=sys.stderr)
        print(configured.stderr[-1500:], file=sys.stderr)
        return 1

    app_env = LOCAL / "app.env"
    text = app_env.read_text(encoding="utf-8")
    text = re.sub(r"(?m)^OIDC_CLIENT_ID=.*$", f"OIDC_CLIENT_ID={client_id}", text)
    app_env.write_bytes(text.encode("utf-8"))
    if not restart:
        print(f"OIDC application ready (client {client_id}); recreate app and worker")
        return 0

    compose = [
        DOCKER,
        "compose",
        "--env-file",
        str(LOCAL / "compose.env"),
        "-f",
        str(HERE / "compose.yaml"),
        "--profile",
        "stateful-local",
    ]
    restarted = _run([*compose, "up", "-d", "--wait", "--force-recreate", "app", "worker"], env)
    if restarted.returncode != 0:
        print(restarted.stderr[-1500:], file=sys.stderr)
        return 1
    print(f"OIDC application ready (client {client_id}); app and worker restarted")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

"""Run the stack's scheduled commands and prove its heartbeat, locally.

    uv run python deploy/staging/schedule_local.py

Decision D-STG.3; brief H exit criterion E9 as far as a local run can take
it. With the stack from `compose.yaml` running (and `identity_local.py`
done):

1. Every command a timer in `systemd/` starts runs once in the product
   image against the stack, the way `leadstack-job@.service` runs it
   (`docker compose run --rm --no-deps -T app python -m <module>`), and
   exits 0.
2. `heartbeat.sh` (what `leadstack-heartbeat.service` runs) pings a
   stand-in monitor on 127.0.0.1 while the worker runs; with the worker
   stopped, it exits non-zero and sends nothing, which is what makes a
   monitoring service alert; with the worker started again, it pings again.

Not proven here: the monitoring service raising the alert itself (it is
not chosen yet; brief H section 8), and systemd running the timers (this
machine has none; the unit files are checked by
`tests/unit/test_staging_timers.py`).

Prints one line per check and exits 1 if any fails. Every command is a
fixed `docker` or `sh` invocation built here.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
LOCAL = HERE / ".local"
UNITS = HERE / "systemd"
DOCKER = shutil.which("docker") or "docker"
SH = shutil.which("sh") or shutil.which("bash") or "sh"
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
results: list[tuple[str, bool, str]] = []
pings: list[float] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))
    print(f"{'PASS' if ok else 'FAIL'}  {name}{(' - ' + detail) if detail else ''}")


def run(args: list[str], env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 - fixed docker and sh commands built here
        args, env=env, capture_output=True, text=True, timeout=600, check=False
    )


def scheduled_modules() -> list[str]:
    """The modules the timers start, read from the timer files themselves."""
    found = []
    for timer in sorted(UNITS.glob("*.timer")):
        unit = re.search(r"^Unit=leadstack-job@(.+)\.service$", timer.read_text(), re.M)
        if unit:
            found.append(unit.group(1))
    return found


class _Monitor(BaseHTTPRequestHandler):
    """The stand-in for the monitoring service's heartbeat address."""

    def do_GET(self) -> None:
        pings.append(time.time())
        self.send_response(200)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, format: str, *args: object) -> None:
        return


def heartbeat(url: str) -> subprocess.CompletedProcess[str]:
    env = {
        **os.environ,
        # Git Bash would turn the POSIX paths below into Windows ones.
        "MSYS_NO_PATHCONV": "1",
        "STACK_DIR": HERE.as_posix(),
        "ENV_FILE": (LOCAL / "compose.env").as_posix(),
        "COMPOSE_EXTRA": "--profile stateful-local",
        "HEARTBEAT_URL": url,
    }
    return run([SH, str(HERE / "heartbeat.sh")], env)


def _worker_healthy() -> bool:
    for _ in range(40):
        state = run(
            [DOCKER, "inspect", "-f", "{{.State.Health.Status}}", "crm-app-staging-worker-1"]
        )
        if state.stdout.strip() == "healthy":
            return True
        time.sleep(3)
    return False


def main() -> int:
    if not (LOCAL / "app.env").exists():
        print("run prepare_local.py and start the stack first", file=sys.stderr)
        return 2

    modules = scheduled_modules()
    check("S14 the timers start the scheduled commands", len(modules) >= 6, ", ".join(modules))
    for module in [*modules, "crm_app.health_check"]:
        done = run([*COMPOSE, "run", "--rm", "--no-deps", "-T", "app", "python", "-m", module])
        last = (done.stdout.strip() or done.stderr.strip()).splitlines()[-1:] or [""]
        check(f"S14 {module} runs in the production image", done.returncode == 0, last[0][:160])

    server = HTTPServer(("127.0.0.1", 0), _Monitor)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{server.server_port}/heartbeat"
    try:
        sent = heartbeat(url)
        check(
            "E9 the heartbeat pings while the worker runs",
            sent.returncode == 0 and len(pings) == 1,
            sent.stdout.strip()[-80:] or sent.stderr.strip()[-160:],
        )

        run([*COMPOSE, "stop", "worker"])
        # The worker's sentinel in Redis lives 16 seconds after its last refresh.
        time.sleep(20)
        missed = heartbeat(url)
        check(
            "E9 with the worker stopped, no ping is sent",
            missed.returncode != 0 and len(pings) == 1,
            missed.stderr.strip()[-80:],
        )
    finally:
        run([*COMPOSE, "start", "worker"])
    healthy = _worker_healthy()
    again = heartbeat(url)
    check(
        "E9 with the worker back, the heartbeat pings again",
        healthy and again.returncode == 0 and len(pings) == 2,
        again.stdout.strip()[-80:],
    )
    server.shutdown()

    failed = [name for name, ok, _ in results if not ok]
    print(f"\n{len(results) - len(failed)} passed, {len(failed)} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

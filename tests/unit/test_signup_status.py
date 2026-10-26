"""`GET /v1/signups/status` (Stage D): the public flag the start page reads
to decide whether to offer signup. It follows the kill switch that guards
the signup routes, needs no session, and says nothing beyond the flag.

Run in a fresh interpreter with placeholder settings, because SaaS-OS
resolves configuration at import time; nothing is contacted.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.support import PLACEHOLDER_SETTINGS, clean_environment, run_python

_PROBE = (
    "import json\n"
    "from fastapi.testclient import TestClient\n"
    "from saas_os.api.route_policy import assert_route_policies\n"
    "from crm_app.app import create_app\n"
    "app = create_app()\n"
    "policies = assert_route_policies(app, production=False)\n"
    "# No lifespan: start-up checks would contact the placeholder database.\n"
    "client = TestClient(app)\n"
    "status = client.get('/v1/signups/status')\n"
    "print('RESULT ' + json.dumps({\n"
    "    'policy': str(policies['GET /v1/signups/status'].kind),\n"
    "    'status': status.status_code,\n"
    "    'body': status.json(),\n"
    "    'cache': status.headers.get('cache-control'),\n"
    "    'write': client.post('/v1/signups/status').status_code,\n"
    "    'post': client.post('/v1/signups', json={}).status_code,\n"
    "    'current': client.get('/v1/signups/current').status_code,\n"
    "}))\n"
)


def _run(tmp_path: Path, **extra: str) -> dict[str, object]:
    env = {**PLACEHOLDER_SETTINGS, "TRUST_PROXY_HEADERS": "true", **extra}
    result = run_python(_PROBE, clean_environment(env), tmp_path)
    assert result.returncode == 0, result.stderr
    line = next(x for x in result.stdout.splitlines() if x.startswith("RESULT "))
    return json.loads(line.removeprefix("RESULT "))


@pytest.mark.parametrize("setting", [None, "false"])
def test_while_signup_is_off_the_flag_is_false_and_the_routes_do_not_exist(
    tmp_path: Path, setting: str | None
) -> None:
    result = _run(tmp_path, **({} if setting is None else {"SIGNUP_ENABLED": setting}))
    assert result["policy"] == "public"
    assert (result["status"], result["body"]) == (200, {"enabled": False})
    assert result["cache"] == "no-store"
    # The flag does not open the kill switch: the signup routes stay absent.
    assert (result["post"], result["current"]) == (404, 404)


def test_while_signup_is_on_the_flag_is_true_and_says_nothing_else(tmp_path: Path) -> None:
    result = _run(tmp_path, SIGNUP_ENABLED="true", SIGNUP_MAX_WORKSPACES_PER_USER="7")
    assert (result["status"], result["body"]) == (200, {"enabled": True})
    # No limits or configuration in the answer, and nothing to write to.
    assert result["write"] == 405
    # The routes now exist but still need a signed-in person.
    assert (result["post"], result["current"]) == (401, 401)

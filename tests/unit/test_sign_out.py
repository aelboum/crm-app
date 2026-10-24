"""`GET /v1/sign-out-url` (finding from the Phase 2 browser verification,
decision P2-F): after the application signs out, the browser ends the
identity provider's session too (OIDC RP-Initiated Logout).

Run in a fresh interpreter with placeholder settings, because SaaS-OS
resolves configuration at import time; nothing is contacted.
"""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from tests.support import PLACEHOLDER_SETTINGS, clean_environment, run_python

_PROBE = (
    "import json\n"
    "from fastapi.testclient import TestClient\n"
    "from saas_os.api.route_policy import assert_route_policies\n"
    "from crm_app.app import create_app\n"
    "app = create_app()\n"
    "policies = assert_route_policies(app, production=False)\n"
    "# No lifespan: start-up checks would contact the placeholder database.\n"
    "response = TestClient(app).get('/v1/sign-out-url')\n"
    "print('RESULT ' + json.dumps({\n"
    "    'policy': str(policies['GET /v1/sign-out-url'].kind),\n"
    "    'status': response.status_code,\n"
    "    'body': response.json(),\n"
    "    'cache': response.headers.get('cache-control'),\n"
    "}))\n"
)


def _run(tmp_path: Path, **extra: str) -> dict[str, object]:
    result = run_python(_PROBE, clean_environment({**PLACEHOLDER_SETTINGS, **extra}), tmp_path)
    assert result.returncode == 0, result.stderr
    line = next(x for x in result.stdout.splitlines() if x.startswith("RESULT "))
    return json.loads(line.removeprefix("RESULT "))


def test_without_an_end_session_endpoint_the_app_just_reloads(tmp_path: Path) -> None:
    result = _run(tmp_path)
    assert result["policy"] == "public"
    assert (result["status"], result["body"]) == (200, {"url": None})
    assert result["cache"] == "no-store"


def test_with_one_the_url_carries_only_the_client_id_and_the_return_address(
    tmp_path: Path,
) -> None:
    endpoint = "https://identity.invalid/oidc/v1/end_session"
    result = _run(tmp_path, OIDC_END_SESSION_ENDPOINT=endpoint)
    body = result["body"]
    assert isinstance(body, dict)
    url = urlsplit(str(body["url"]))
    assert f"{url.scheme}://{url.netloc}{url.path}" == endpoint
    assert parse_qs(url.query) == {
        "client_id": ["placeholder-client"],
        "post_logout_redirect_uri": ["https://app.invalid/app"],
    }

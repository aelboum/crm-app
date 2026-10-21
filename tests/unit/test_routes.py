"""Every product route declares the intended SaaS-OS route policy.

Checked with SaaS-OS's own startup check (`saas_os.api.route_policy.
assert_route_policies`) on the fully assembled application, built in a fresh
interpreter with placeholder settings, so no service is contacted. Whether
the policy then admits or refuses a given caller is tested against a real
database in `tests/integration/test_workspace_routes.py`.
"""

from __future__ import annotations

import json
from pathlib import Path

from crm_app.permissions import PERMISSIONS
from crm_app.roles import ROLE_TEMPLATES
from tests.support import PLACEHOLDER_SETTINGS, clean_environment, run_python

PRODUCT_PREFIX = "/v1/workspaces"

EXPECTED = {
    "GET /v1/workspaces/{tenant_id}": "crm_app.workspace:read",
    "GET /v1/workspaces/{tenant_id}/members": "membership:read",
}

_PROBE = (
    "import json\n"
    "from crm_app.app import create_app\n"
    "from saas_os.api.route_policy import assert_route_policies\n"
    "policies = assert_route_policies(create_app(), production=False)\n"
    "print('POLICIES ' + json.dumps({k: [str(p.kind), p.detail, p.accepts_api_key]"
    " for k, p in policies.items()}))\n"
)


def _product_policies(tmp_path: Path) -> dict[str, tuple[str, str, bool]]:
    result = run_python(_PROBE, clean_environment(PLACEHOLDER_SETTINGS), tmp_path)
    assert result.returncode == 0, result.stderr
    line = next(x for x in result.stdout.splitlines() if x.startswith("POLICIES "))
    policies = json.loads(line.removeprefix("POLICIES "))
    return {k: (v[0], v[1], v[2]) for k, v in policies.items() if PRODUCT_PREFIX in k}


def test_product_routes_require_exactly_the_intended_permission(tmp_path: Path) -> None:
    policies = _product_policies(tmp_path)
    assert {key: detail for key, (_, detail, _) in policies.items()} == EXPECTED
    assert {kind for kind, _, _ in policies.values()} == {"permission"}
    assert not any(accepts_api_key for _, _, accepts_api_key in policies.values())
    # Membership and role changes wait for the last-Owner safeguard.
    assert all(key.startswith("GET ") for key in policies)


def test_route_permissions_are_registered_and_granted_to_every_role() -> None:
    for detail in EXPECTED.values():
        resource, _, action = detail.rpartition(":")
        assert (resource, action) in PERMISSIONS
        assert all((resource, action) in template for template in ROLE_TEMPLATES.values())

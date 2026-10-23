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
from crm_app.roles import ROLE_TEMPLATES, Role
from tests.support import PLACEHOLDER_SETTINGS, clean_environment, run_python

PRODUCT_PREFIX = "/v1/workspaces"

MEMBER = "/v1/workspaces/{tenant_id}/members/{membership_id}"
EXPECTED = {
    "GET /v1/workspaces/{tenant_id}": "crm_app.workspace:read",
    "GET /v1/workspaces/{tenant_id}/members": "membership:read",
    "GET /v1/workspaces/{tenant_id}/access": "crm_app.workspace:read",
    f"POST {MEMBER}/roles": "membership_role:create",
    f"DELETE {MEMBER}/roles/{{role}}": "membership_role:delete",
    f"POST {MEMBER}/suspend": "membership:suspend",
    f"POST {MEMBER}/reactivate": "membership:reactivate",
    f"POST {MEMBER}/revoke": "membership:revoke",
}
# Membership and role changes (gate G-LOCK): Owner and Admin only.
CHANGING = {key for key in EXPECTED if not key.startswith("GET ")}

# Contact and company records (slice 3A, decision P3-A): reads for every role,
# create and update (including archive and restore) for Owner, Admin and
# Member, permanent delete for Owner and Admin (Q6).
RECORDS: dict[str, str] = {}
for _path, _resource in (("contacts", "crm_app.contact"), ("companies", "crm_app.company")):
    _collection = f"/v1/workspaces/{{tenant_id}}/{_path}"
    _item = f"{_collection}/{{record_id}}"
    RECORDS |= {
        f"GET {_collection}": f"{_resource}:read",
        f"POST {_collection}": f"{_resource}:create",
        f"GET {_item}": f"{_resource}:read",
        f"PATCH {_item}": f"{_resource}:update",
        f"POST {_item}/archive": f"{_resource}:update",
        f"POST {_item}/restore": f"{_resource}:update",
        f"DELETE {_item}": f"{_resource}:delete",
    }
EDITORS = {Role.OWNER, Role.ADMIN, Role.MEMBER}

_PROBE = (
    "import json\n"
    "from crm_app.app import create_app\n"
    "from saas_os.api.route_policy import assert_route_policies\n"
    "policies = assert_route_policies(create_app(), production=False)\n"
    "print('POLICIES ' + json.dumps({k: [str(p.kind), p.detail, p.accepts_api_key]"
    " for k, p in policies.items()}))\n"
)


# The frontend's static files (crm_app.api.spa): public, read-only, no data.
FRONTEND = {"GET,HEAD /", "GET,HEAD /app", "GET,HEAD /app/{requested:path}"}


def _policies(tmp_path: Path) -> dict[str, tuple[str, str, bool]]:
    result = run_python(_PROBE, clean_environment(PLACEHOLDER_SETTINGS), tmp_path)
    assert result.returncode == 0, result.stderr
    line = next(x for x in result.stdout.splitlines() if x.startswith("POLICIES "))
    policies = json.loads(line.removeprefix("POLICIES "))
    return {k: (v[0], v[1], v[2]) for k, v in policies.items()}


def _product_policies(tmp_path: Path) -> dict[str, tuple[str, str, bool]]:
    return {k: v for k, v in _policies(tmp_path).items() if PRODUCT_PREFIX in k}


def test_product_routes_require_exactly_the_intended_permission(tmp_path: Path) -> None:
    policies = _product_policies(tmp_path)
    assert {key: detail for key, (_, detail, _) in policies.items()} == EXPECTED | RECORDS
    assert {kind for kind, _, _ in policies.values()} == {"permission"}
    assert not any(accepts_api_key for _, _, accepts_api_key in policies.values())
    changing = {key for key in policies if not key.startswith("GET ")}
    assert changing == CHANGING | {key for key in RECORDS if not key.startswith("GET ")}


def test_route_permissions_are_registered() -> None:
    for detail in (EXPECTED | RECORDS).values():
        resource, _, action = detail.rpartition(":")
        assert (resource, action) in PERMISSIONS


def test_reading_routes_are_open_to_every_role_and_changes_to_owner_and_admin() -> None:
    for key, detail in EXPECTED.items():
        resource, _, action = detail.rpartition(":")
        holders = {
            role for role, template in ROLE_TEMPLATES.items() if (resource, action) in template
        }
        expected = set(Role) if key not in CHANGING else {Role.OWNER, Role.ADMIN}
        assert holders == expected, key


def test_frontend_routes_are_public_and_read_only(tmp_path: Path) -> None:
    policies = _policies(tmp_path)
    frontend = {key: kind for key, (kind, _, _) in policies.items() if key in FRONTEND}
    assert frontend == dict.fromkeys(FRONTEND, "public")
    assert not any(
        key.split(" ", 1)[1].startswith("/app") for key in policies if key not in FRONTEND
    )


def test_record_routes_follow_the_role_matrix() -> None:
    for key, detail in RECORDS.items():
        resource, _, action = detail.rpartition(":")
        holders = {
            role for role, template in ROLE_TEMPLATES.items() if (resource, action) in template
        }
        expected = {
            "read": set(Role),
            "create": EDITORS,
            "update": EDITORS,
            "delete": {Role.OWNER, Role.ADMIN},
        }[action]
        assert holders == expected, key

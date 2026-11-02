"""Drives `crm_app.role_upgrade` (decision P2-G7) and prints one
`RESULT <json>` line.

Run in a fresh interpreter by `tests/integration/test_role_upgrade.py`.
"Old" workspaces are provisioned with templates that lack the
conversation permissions and CSV import, as workspaces made before those
changes were; one also holds a custom grant outside its template. Refuses
to run unless ENVIRONMENT=test.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import secrets
import uuid
from typing import Any

from saas_os.core.authority import UserCaller
from saas_os.core.identity import add_tenant_membership
from saas_os.core.rbac import (
    assign_first_role_for_new_tenant,
    assign_role,
    can,
    create_role,
    grant_permission,
    register_permission,
)
from saas_os.core.tenancy import TenantStatus, create_tenant, transition_tenant_status

from crm_app import role_upgrade
from crm_app.roles import ROLE_TEMPLATES, Role
from tests.integration.workspace_route_probe import PROVISIONING, _new_user, _new_workspace

LATER = {
    ("crm_app.conversation", "read"),
    ("crm_app.conversation", "reply"),
    ("crm_app.crm_data", "import"),
}
CUSTOM = ("crm_app.crm_data", "export")


def _old_workspace(label: str, *, custom: bool = False) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    """A workspace as provisioned before `LATER` existed: its id, its
    Owner's and a Member's user ids."""
    tenant = create_tenant(f"upgrade-{label}-{secrets.token_hex(4)}", caller=PROVISIONING)
    transition_tenant_status(tenant.id, TenantStatus.ACTIVE, caller=PROVISIONING)
    roles: dict[Role, uuid.UUID] = {}
    for role, keys in ROLE_TEMPLATES.items():
        created = create_role(tenant.id, role.value, caller=PROVISIONING)
        granted = set(keys) - LATER
        if custom and role is Role.MEMBER:
            granted.add(CUSTOM)
        for resource, action in sorted(granted):
            permission = register_permission(resource, action)
            grant_permission(tenant.id, created.id, permission.id, caller=PROVISIONING)
        roles[role] = created.id
    owner = _new_user()
    membership = add_tenant_membership(tenant.id, owner, caller=PROVISIONING)
    assign_first_role_for_new_tenant(
        tenant.id, membership.id, roles[Role.OWNER], caller=PROVISIONING
    )
    member = _new_user()
    joined = add_tenant_membership(tenant.id, member, caller=PROVISIONING)
    assign_role(tenant.id, joined.id, roles[Role.MEMBER], caller=UserCaller(owner))
    return tenant.id, owner, member


def _can(user: uuid.UUID, tenant: uuid.UUID, key: tuple[str, str]) -> bool:
    return bool(can(actor_id=user, tenant_id=tenant, action=key[1], resource=key[0]))


def _summary(plan: role_upgrade.WorkspacePlan) -> dict[str, Any]:
    return {
        "skipped": plan.skipped,
        "roles": {
            r.role: {
                "missing": [":".join(k) for k in r.missing],
                "held_back": [":".join(k) for k in r.held_back],
                "granted": [":".join(k) for k in r.granted],
                "custom": r.custom,
            }
            for r in plan.roles
        },
    }


def _cli(*args: str) -> tuple[int, str]:
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
        code = role_upgrade.main(list(args))
    return code, out.getvalue()


def main() -> None:
    if os.environ.get("ENVIRONMENT") != "test":
        raise SystemExit("role_upgrade_probe runs only with ENVIRONMENT=test")
    old, owner, member = _old_workspace("old", custom=True)
    other, other_owner, other_member = _old_workspace("other")
    fresh = _new_workspace("fresh")
    bare = create_tenant(f"upgrade-bare-{secrets.token_hex(4)}", caller=PROVISIONING)
    transition_tenant_status(bare.id, TenantStatus.ACTIVE, caller=PROVISIONING)
    reply = ("crm_app.conversation", "reply")
    read = ("crm_app.conversation", "read")
    imports = ("crm_app.crm_data", "import")
    result: dict[str, Any] = {}

    result["before"] = [_can(member, old, reply), _can(owner, old, imports)]
    code, text = _cli("--workspace", str(old))
    result["dry_run"] = [code, text.splitlines()[0]]
    result["after_dry_run"] = [_can(member, old, reply), _can(owner, old, read)]

    # 13-R1: the dry run's fingerprint binds the apply to what was reviewed.
    printed = text.splitlines()[1].removeprefix("plan fingerprint: ")
    code, as_json = _cli("--workspace", str(other), "--json")
    report = json.loads(as_json)
    wrong_code, wrong = _cli("--workspace", str(other), "--apply", "--expect", "0" * 16)
    result["fingerprint"] = [
        len(printed),
        code,
        report["applied"],
        report["fingerprint"] != printed,
        sorted(report["workspaces"][0]["roles"][0]),
        wrong_code,
        "plan changed" in wrong,
        _can(other_member, other, reply),
    ]

    first = role_upgrade.upgrade([old], apply_changes=True, include_administrative=False)
    result["first"] = _summary(first[0])
    result["after_first"] = [
        _can(member, old, reply),
        _can(member, old, read),
        _can(owner, old, reply),
        _can(owner, old, imports),
        _can(member, old, CUSTOM),
        _can(member, old, imports),
    ]
    second = role_upgrade.upgrade([old], apply_changes=True, include_administrative=True)
    result["second"] = _summary(second[0])
    result["after_second"] = [_can(owner, old, imports), _can(member, old, imports)]
    again = role_upgrade.upgrade([old], apply_changes=True, include_administrative=True)
    result["again"] = _summary(again[0])

    result["other_untouched"] = [
        _can(other_member, other, reply),
        _can(other_owner, other, imports),
    ]
    result["fresh"] = _summary(role_upgrade.plan(fresh.id, include_administrative=True))
    result["bare"] = role_upgrade.plan(bare.id).skipped
    result["unknown"] = role_upgrade.plan(uuid.uuid4()).skipped

    code, text = _cli("--workspace", "not-a-uuid")
    result["bad_id"] = [code, text.strip()]
    os.environ["ENVIRONMENT"] = "production"
    try:
        code, text = _cli("--all", "--apply")
        unbound_code, unbound = _cli("--all", "--apply", "--confirm-production")
    finally:
        os.environ["ENVIRONMENT"] = "test"
    result["production"] = [code, text.strip()]
    result["production_needs_expect"] = [unbound_code, "--expect" in unbound]
    result["other_after_refusal"] = _can(other_member, other, reply)
    # The reviewed fingerprint applies, and only then.
    code, dry = _cli("--workspace", str(other))
    reviewed = dry.splitlines()[1].removeprefix("plan fingerprint: ")
    applied_code, _ = _cli("--workspace", str(other), "--apply", "--expect", reviewed)
    result["bound_apply"] = [applied_code, _can(other_member, other, reply)]
    print("RESULT " + json.dumps(result, default=str))


if __name__ == "__main__":
    main()

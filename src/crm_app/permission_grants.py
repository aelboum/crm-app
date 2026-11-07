"""Permission grant migrations for existing workspaces (SaaS-OS ADR 0060).

Design: `docs/project/PERMISSION-GRANT-MIGRATIONS-PLAN.md`, step A. Nothing
here runs by itself: a platform operator applies a list with SaaS-OS's

    saas-os-operator apply-permission-grants --namespace crm_app
        --module crm_app.permission_grants[:ADMINISTRATIVE_MIGRATIONS] ...

first without `--apply`. New workspaces get the full templates from
`crm_app.provisioning.seed_roles`; these lists bring workspaces created
earlier up to the same templates, once per workspace.

Rules (enforced by `tests/unit/test_permission_grants.py`):

- **Append-only.** An entry is never edited, reordered away or removed once
  shipped: SaaS-OS refuses the whole run when an applied migration's digest
  changes. A new permission gets a new entry with a new id.
- **Templates = baseline + migrations.** For every role, `ROLE_TEMPLATES`
  equals `BASELINE` (the templates before the first addition, commit
  `3bce9b6^`) plus every permission its migrations declare. A permission
  added to a template without a migration fails the test.
- **No authority-changing permission** (membership, invitation, role, ...):
  SaaS-OS refuses them; such a change goes through a workspace's owner.
- **Administrative permissions are held back** in `ADMINISTRATIVE_MIGRATIONS`,
  applied only in a separately approved run (Brief 7).
- **Authority-changing additions** cannot be migrations (SaaS-OS refuses
  them: such a change goes through a workspace's owner). They are listed in
  `OWNER_GRANTED_ADDITIONS` instead, each truly authority-changing and named
  with its decision; new workspaces get them from the templates at
  provisioning, workspaces created earlier only through their owner (no
  route yet; decision P12-K).

`python -m crm_app.permission_grants --report` prints, read-only, which
permissions each migration would add and to how many workspaces: the
review evidence SaaS-OS's own dry run (counts only) does not give.
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field

from saas_os.core.permission_grants import PermissionGrantMigration

from crm_app.roles import Role

NAMESPACE = "crm_app"
Key = tuple[str, str]


def _migration(
    migration_id: str, role: Role, permissions: tuple[Key, ...], reason: str
) -> PermissionGrantMigration:
    return PermissionGrantMigration(
        id=migration_id,
        namespace=NAMESPACE,
        role_name=role.value,
        permissions=permissions,
        reason=reason,
    )


# Ordered by the decision that added each permission (the commits touching
# `crm_app/roles.py` since Phase 2). Append new entries at the end.
PERMISSION_GRANT_MIGRATIONS: tuple[PermissionGrantMigration, ...] = (
    _migration(
        "crm_app.p7a.forms.owner",
        Role.OWNER,
        (("crm_app.form", "read"),),
        "P7-A: Forms and lead capture (Phase 7A)",
    ),
    _migration(
        "crm_app.p7a.forms.admin",
        Role.ADMIN,
        (("crm_app.form", "read"),),
        "P7-A: Forms and lead capture (Phase 7A)",
    ),
    _migration(
        "crm_app.p7a.forms.member",
        Role.MEMBER,
        (("crm_app.form", "read"),),
        "P7-A: Forms and lead capture (Phase 7A)",
    ),
    _migration(
        "crm_app.p7a.forms.read_only",
        Role.READ_ONLY,
        (("crm_app.form", "read"),),
        "P7-A: Forms and lead capture (Phase 7A)",
    ),
    _migration(
        "crm_app.p5a.appointments.owner",
        Role.OWNER,
        (
            ("crm_app.appointment", "read"),
            ("crm_app.appointment", "create"),
            ("crm_app.appointment", "update"),
            ("crm_app.appointment", "delete"),
        ),
        "P5-A: Appointments (Phase 5A)",
    ),
    _migration(
        "crm_app.p5a.appointments.admin",
        Role.ADMIN,
        (
            ("crm_app.appointment", "read"),
            ("crm_app.appointment", "create"),
            ("crm_app.appointment", "update"),
            ("crm_app.appointment", "delete"),
        ),
        "P5-A: Appointments (Phase 5A)",
    ),
    _migration(
        "crm_app.p5a.appointments.member",
        Role.MEMBER,
        (
            ("crm_app.appointment", "read"),
            ("crm_app.appointment", "create"),
            ("crm_app.appointment", "update"),
        ),
        "P5-A: Appointments (Phase 5A)",
    ),
    _migration(
        "crm_app.p5a.appointments.read_only",
        Role.READ_ONLY,
        (("crm_app.appointment", "read"),),
        "P5-A: Appointments (Phase 5A)",
    ),
    _migration(
        "crm_app.p5c.booking_pages.owner",
        Role.OWNER,
        (("crm_app.booking_page", "read"),),
        "P5-C: Public booking pages (Phase 5C)",
    ),
    _migration(
        "crm_app.p5c.booking_pages.admin",
        Role.ADMIN,
        (("crm_app.booking_page", "read"),),
        "P5-C: Public booking pages (Phase 5C)",
    ),
    _migration(
        "crm_app.p5c.booking_pages.member",
        Role.MEMBER,
        (("crm_app.booking_page", "read"),),
        "P5-C: Public booking pages (Phase 5C)",
    ),
    _migration(
        "crm_app.p5c.booking_pages.read_only",
        Role.READ_ONLY,
        (("crm_app.booking_page", "read"),),
        "P5-C: Public booking pages (Phase 5C)",
    ),
    _migration(
        "crm_app.p7b.suppression.owner",
        Role.OWNER,
        (("crm_app.suppression", "read"),),
        "P7-B: Suppression list and consent (Phase 7B)",
    ),
    _migration(
        "crm_app.p7b.suppression.admin",
        Role.ADMIN,
        (("crm_app.suppression", "read"),),
        "P7-B: Suppression list and consent (Phase 7B)",
    ),
    _migration(
        "crm_app.p7b.suppression.member",
        Role.MEMBER,
        (("crm_app.suppression", "read"),),
        "P7-B: Suppression list and consent (Phase 7B)",
    ),
    _migration(
        "crm_app.p8a.automations.owner",
        Role.OWNER,
        (("crm_app.automation", "read"),),
        "P8-A: Automations (Phase 8A)",
    ),
    _migration(
        "crm_app.p8a.automations.admin",
        Role.ADMIN,
        (("crm_app.automation", "read"),),
        "P8-A: Automations (Phase 8A)",
    ),
    _migration(
        "crm_app.p8a.automations.member",
        Role.MEMBER,
        (("crm_app.automation", "read"),),
        "P8-A: Automations (Phase 8A)",
    ),
    _migration(
        "crm_app.p8a.automations.read_only",
        Role.READ_ONLY,
        (("crm_app.automation", "read"),),
        "P8-A: Automations (Phase 8A)",
    ),
    _migration(
        "crm_app.p6c.conversations.owner",
        Role.OWNER,
        (
            ("crm_app.conversation", "read"),
            ("crm_app.conversation", "reply"),
        ),
        "P6-C: Conversations (Phase 6C)",
    ),
    _migration(
        "crm_app.p6c.conversations.admin",
        Role.ADMIN,
        (
            ("crm_app.conversation", "read"),
            ("crm_app.conversation", "reply"),
        ),
        "P6-C: Conversations (Phase 6C)",
    ),
    _migration(
        "crm_app.p6c.conversations.member",
        Role.MEMBER,
        (
            ("crm_app.conversation", "read"),
            ("crm_app.conversation", "reply"),
        ),
        "P6-C: Conversations (Phase 6C)",
    ),
    _migration(
        "crm_app.p6c.conversations.read_only",
        Role.READ_ONLY,
        (("crm_app.conversation", "read"),),
        "P6-C: Conversations (Phase 6C)",
    ),
    _migration(
        "crm_app.p7c.campaigns.owner",
        Role.OWNER,
        (
            ("crm_app.campaign", "read"),
            ("crm_app.campaign", "manage"),
        ),
        "P7-C: Campaigns (Phase 7C)",
    ),
    _migration(
        "crm_app.p7c.campaigns.admin",
        Role.ADMIN,
        (
            ("crm_app.campaign", "read"),
            ("crm_app.campaign", "manage"),
        ),
        "P7-C: Campaigns (Phase 7C)",
    ),
    _migration(
        "crm_app.p7c.campaigns.member",
        Role.MEMBER,
        (
            ("crm_app.campaign", "read"),
            ("crm_app.campaign", "manage"),
        ),
        "P7-C: Campaigns (Phase 7C)",
    ),
    _migration(
        "crm_app.p7c.campaigns.read_only",
        Role.READ_ONLY,
        (("crm_app.campaign", "read"),),
        "P7-C: Campaigns (Phase 7C)",
    ),
)

# Administrative or safeguarded permissions (`role_upgrade.GUARDED`): applied
# only in their own, separately approved run.
ADMINISTRATIVE_MIGRATIONS: tuple[PermissionGrantMigration, ...] = (
    _migration(
        "crm_app.p3f.import.administrative.owner",
        Role.OWNER,
        (("crm_app.crm_data", "import"),),
        "P3-F: CRM data import (Phase 3F)",
    ),
    _migration(
        "crm_app.p3f.import.administrative.admin",
        Role.ADMIN,
        (("crm_app.crm_data", "import"),),
        "P3-F: CRM data import (Phase 3F)",
    ),
    _migration(
        "crm_app.p7a.forms.administrative.owner",
        Role.OWNER,
        (("crm_app.form", "manage"),),
        "P7-A: Forms and lead capture (Phase 7A)",
    ),
    _migration(
        "crm_app.p7a.forms.administrative.admin",
        Role.ADMIN,
        (("crm_app.form", "manage"),),
        "P7-A: Forms and lead capture (Phase 7A)",
    ),
    _migration(
        "crm_app.p5c.booking_pages.administrative.owner",
        Role.OWNER,
        (("crm_app.booking_page", "manage"),),
        "P5-C: Public booking pages (Phase 5C)",
    ),
    _migration(
        "crm_app.p5c.booking_pages.administrative.admin",
        Role.ADMIN,
        (("crm_app.booking_page", "manage"),),
        "P5-C: Public booking pages (Phase 5C)",
    ),
    _migration(
        "crm_app.p7b.suppression.administrative.owner",
        Role.OWNER,
        (("crm_app.suppression", "manage"),),
        "P7-B: Suppression list and consent (Phase 7B)",
    ),
    _migration(
        "crm_app.p7b.suppression.administrative.admin",
        Role.ADMIN,
        (("crm_app.suppression", "manage"),),
        "P7-B: Suppression list and consent (Phase 7B)",
    ),
    _migration(
        "crm_app.p8a.automations.administrative.owner",
        Role.OWNER,
        (("crm_app.automation", "manage"),),
        "P8-A: Automations (Phase 8A)",
    ),
    _migration(
        "crm_app.p8a.automations.administrative.admin",
        Role.ADMIN,
        (("crm_app.automation", "manage"),),
        "P8-A: Automations (Phase 8A)",
    ),
    _migration(
        "crm_app.p7c.campaigns.administrative.owner",
        Role.OWNER,
        (("crm_app.campaign", "approve"),),
        "P7-C: Campaigns (Phase 7C)",
    ),
    _migration(
        "crm_app.p7c.campaigns.administrative.admin",
        Role.ADMIN,
        (("crm_app.campaign", "approve"),),
        "P7-C: Campaigns (Phase 7C)",
    ),
    _migration(
        "crm_app.p12k.integrations.administrative.owner",
        Role.OWNER,
        (("crm_app.integration", "manage"),),
        "P12-K: Integrations and API keys (Phase 12K)",
    ),
    _migration(
        "crm_app.p12k.integrations.administrative.admin",
        Role.ADMIN,
        (("crm_app.integration", "manage"),),
        "P12-K: Integrations and API keys (Phase 12K)",
    ),
)


@dataclass(frozen=True)
class OwnerGranted:
    """A permission added to a role template that SaaS-OS counts as
    authority-changing: never a migration, so workspaces created before the
    addition get it only through their owner."""

    role: Role
    permission: Key
    decision: str


_P12 = (
    ("service_account", "create", "P12-K"),
    ("service_account", "disable", "P12-K"),
    ("service_account_role", "create", "P12-K"),
    ("api_key", "create", "P12-K"),
    ("api_key", "revoke", "P12-K"),
    ("webhook_subscription", "create", "P12-H"),
    ("webhook_subscription", "delete", "P12-H"),
)

OWNER_GRANTED_ADDITIONS: tuple[OwnerGranted, ...] = tuple(
    OwnerGranted(role, (resource, action), decision)
    for role in (Role.OWNER, Role.ADMIN)
    for resource, action, decision in _P12
)


# --- Read-only report ---------------------------------------------------------------------


@dataclass
class MigrationReport:
    id: str
    role: str
    permissions: list[str]
    workspaces: int = 0
    role_missing: int = 0
    lacking: int = 0
    grants_needed: int = 0
    lacking_by_permission: dict[str, int] = field(default_factory=dict)


def _granted(tenant_id: uuid.UUID, role_id: uuid.UUID) -> set[Key]:
    from saas_os.core.rbac import Permission, RolePermission  # noqa: PLC0415
    from saas_os.infra.db import select, tenant_session_scope  # noqa: PLC0415

    with tenant_session_scope(tenant_id) as session:
        rows = session.execute(
            select(Permission.resource, Permission.action)
            .join(RolePermission, RolePermission.permission_id == Permission.id)
            .where(RolePermission.tenant_id == tenant_id, RolePermission.role_id == role_id)
        ).all()
    return {(resource, action) for resource, action in rows}


def report(
    migrations: Sequence[PermissionGrantMigration], tenant_ids: Sequence[uuid.UUID]
) -> list[MigrationReport]:
    """Per migration: how many of `tenant_ids` lack its role, and how many
    lack one of its permissions. Reads only; changes nothing. Unlike SaaS-OS,
    a migration already applied is counted again (this has no ledger)."""
    from crm_app.provisioning import roles_by_name  # noqa: PLC0415

    results = [
        MigrationReport(m.id, m.role_name, [f"{r}:{a}" for r, a in m.permissions])
        for m in migrations
    ]
    for tenant_id in tenant_ids:
        roles = roles_by_name(tenant_id)
        held: dict[str, set[Key]] = {}
        for migration, result in zip(migrations, results, strict=True):
            result.workspaces += 1
            role = roles.get(migration.role_name)
            if role is None:
                result.role_missing += 1
                continue
            if migration.role_name not in held:
                held[migration.role_name] = _granted(tenant_id, role.id)
            missing = [k for k in migration.permissions if k not in held[migration.role_name]]
            if missing:
                result.lacking += 1
                result.grants_needed += len(missing)
                for resource, action in missing:
                    name = f"{resource}:{action}"
                    result.lacking_by_permission[name] = (
                        result.lacking_by_permission.get(name, 0) + 1
                    )
    return results


def _tenants(args: argparse.Namespace) -> list[uuid.UUID]:
    if args.all:
        from saas_os.core.tenancy import list_open_tenant_ids  # noqa: PLC0415

        return list(list_open_tenant_ids())
    return [uuid.UUID(value) for value in args.workspace]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m crm_app.permission_grants",
        description="Report, read-only, what the permission grant migrations would add.",
    )
    parser.add_argument("--report", action="store_true", required=True)
    parser.add_argument(
        "--administrative", action="store_true", help="report ADMINISTRATIVE_MIGRATIONS"
    )
    scope = parser.add_mutually_exclusive_group(required=True)
    scope.add_argument("--workspace", action="append", default=[], metavar="ID")
    scope.add_argument("--all", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        tenant_ids = _tenants(args)
    except ValueError:
        parser.error("--workspace takes a workspace id")
    migrations = ADMINISTRATIVE_MIGRATIONS if args.administrative else PERMISSION_GRANT_MIGRATIONS
    results = report(migrations, tenant_ids)
    if args.json:
        print(json.dumps([vars(r) for r in results], indent=2))
        return 0
    print(f"workspaces: {len(tenant_ids)}")
    for r in results:
        print(
            f"{r.id} ({r.role}): {', '.join(r.permissions)}"
            f" | lacking {r.lacking}, role missing {r.role_missing}, grants {r.grants_needed}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Give existing workspaces the permissions their role templates gained later
(gate G7, decision P2-G7).

    python -m crm_app.role_upgrade (--workspace <id> ... | --all)
        [--apply [--expect FINGERPRINT]] [--include-administrative]
        [--confirm-production] [--json]

An operator command, never an HTTP route. Without `--apply` it only reports,
with a fingerprint of exactly what it would grant; `--apply --expect` grants
only if the plan still matches that reviewed fingerprint (required in
production), and `--json` prints the report for the change record
(decision 13-R1, runbook in `docs/project/ROLE-UPGRADE-RUNBOOK.md`).
For each workspace it compares the four product roles (Owner, Admin,
Member, Read-only, found by their exact names) with
`crm_app.roles.ROLE_TEMPLATES` and grants what is missing. It never
revokes a grant, never creates or renames a role, never touches a
membership, and never grants anything outside the role's own template, so
custom grants stay as they are and no role gains more than the approved
matrix gives it.

Safeguards:
- Administrative and safeguarded permissions (those the matrix marks
  sensitive) are held back unless `--include-administrative` is given; the
  report lists them.
- A workspace is skipped unless it is active and has all four product
  roles (otherwise it was not made by `crm_app.provision`).
- `ENVIRONMENT=production` needs `--confirm-production`.
- Each grant is SaaS-OS's own `grant_permission`, its own audited
  transaction (`role_permission.grant`); a duplicate is skipped, so a
  re-run, or a run interrupted half-way, is safe.

SaaS-OS v0.6.0 has no documented operation for this (upstream request
saas-os #88). The grants use `SystemCaller(PROVISIONING)`, the only caller
`grant_permission` accepts for a permission no member holds yet; that
caller's documented purpose is a workspace's initial authority structure,
so this use extends it, as recorded in decision P2-G7.

Prints identifiers and permission names only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field

from crm_app.roles import CATALOGUE, ROLE_TEMPLATES, Kind, Role

Key = tuple[str, str]

# Held back unless the operator includes them explicitly.
GUARDED: frozenset[Key] = frozenset(
    p.key for p in CATALOGUE if p.kind is Kind.ADMINISTRATIVE or p.sensitive
)


class UpgradeRefusedError(RuntimeError):
    """The command will not act; the message says why."""


@dataclass
class RolePlan:
    role: str
    missing: list[Key] = field(default_factory=list)
    held_back: list[Key] = field(default_factory=list)
    custom: int = 0
    granted: list[Key] = field(default_factory=list)


@dataclass
class WorkspacePlan:
    tenant_id: uuid.UUID
    skipped: str | None = None
    roles: list[RolePlan] = field(default_factory=list)


def split(
    missing: frozenset[Key] | set[Key], *, include_administrative: bool
) -> tuple[list[Key], list[Key]]:
    """What may be granted and what is held back, each sorted."""
    held: set[Key] = set() if include_administrative else {k for k in missing if k in GUARDED}
    return sorted(missing - held), sorted(held)


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


def plan(tenant_id: uuid.UUID, *, include_administrative: bool = False) -> WorkspacePlan:
    """What an upgrade of one workspace would grant; changes nothing."""
    from saas_os.core.tenancy import TenantNotFoundError, TenantStatus, get_tenant  # noqa: PLC0415

    from crm_app.provisioning import roles_by_name  # noqa: PLC0415

    result = WorkspacePlan(tenant_id)
    try:
        tenant = get_tenant(tenant_id)
    except TenantNotFoundError:
        result.skipped = "not found"
        return result
    if tenant.status != TenantStatus.ACTIVE.value:
        result.skipped = f"status is {tenant.status}"
        return result
    roles = roles_by_name(tenant_id)
    absent = [role.value for role in Role if role.value not in roles]
    if absent:
        result.skipped = "not a product workspace (missing roles: " + ", ".join(absent) + ")"
        return result
    for role in Role:
        template = ROLE_TEMPLATES[role]
        held = _granted(tenant_id, roles[role.value].id)
        grant, back = split(template - held, include_administrative=include_administrative)
        result.roles.append(
            RolePlan(role.value, missing=grant, held_back=back, custom=len(held - template))
        )
    return result


def apply(workspace: WorkspacePlan) -> None:
    """Grant each planned permission; a grant already there is skipped."""
    from saas_os.core.authority import SystemAuthority, SystemCaller  # noqa: PLC0415
    from saas_os.core.rbac import (  # noqa: PLC0415
        DuplicatePermissionGrantError,
        grant_permission,
        register_permission,
    )

    from crm_app.provisioning import roles_by_name  # noqa: PLC0415

    if workspace.skipped:
        return
    caller = SystemCaller(SystemAuthority.PROVISIONING)
    roles = roles_by_name(workspace.tenant_id)
    for role in workspace.roles:
        role_id = roles[role.role].id
        for resource, action in role.missing:
            permission = register_permission(resource, action)
            try:
                grant_permission(workspace.tenant_id, role_id, permission.id, caller=caller)
                role.granted.append((resource, action))
            except DuplicatePermissionGrantError:
                pass


def fingerprint(plans: Sequence[WorkspacePlan]) -> str:
    """A short digest of exactly what a run would grant: the dry run prints
    it, and `--apply --expect` refuses unless the plan still matches what
    was reviewed (decision 13-R1)."""
    canonical = sorted(
        (
            str(w.tenant_id),
            w.skipped or "",
            sorted((r.role, sorted(f"{a}:{b}" for a, b in r.missing)) for r in w.roles),
        )
        for w in plans
    )
    digest = hashlib.sha256(json.dumps(canonical, separators=(",", ":")).encode("utf-8"))
    return digest.hexdigest()[:16]


def upgrade(
    targets: Sequence[uuid.UUID],
    *,
    apply_changes: bool,
    include_administrative: bool,
    expect: str | None = None,
) -> list[WorkspacePlan]:
    plans = [plan(t, include_administrative=include_administrative) for t in targets]
    if apply_changes:
        if expect is not None and fingerprint(plans) != expect.strip().lower():
            raise UpgradeRefusedError(
                "The plan changed since the reviewed dry run (fingerprint "
                f"{fingerprint(plans)}, expected {expect}); run the dry run again."
            )
        for workspace in plans:
            apply(workspace)
    return plans


def _targets(args: argparse.Namespace) -> list[uuid.UUID]:
    if args.all:
        from saas_os.core.tenancy import list_open_tenant_ids  # noqa: PLC0415

        return list(list_open_tenant_ids())
    try:
        return [uuid.UUID(value) for value in args.workspace]
    except ValueError:
        raise UpgradeRefusedError("A workspace id is not a UUID.") from None


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m crm_app.role_upgrade",
        description="Grant existing workspaces' product roles what their templates gained.",
    )
    which = parser.add_mutually_exclusive_group(required=True)
    which.add_argument("--workspace", action="append", default=[], help="A workspace id.")
    which.add_argument("--all", action="store_true", help="Every workspace that is not closed.")
    parser.add_argument("--apply", action="store_true", help="Grant; without it, only report.")
    parser.add_argument(
        "--include-administrative",
        action="store_true",
        help="Also grant administrative and safeguarded permissions.",
    )
    parser.add_argument(
        "--confirm-production", action="store_true", help="Required when ENVIRONMENT=production."
    )
    parser.add_argument(
        "--expect",
        metavar="FINGERPRINT",
        help="With --apply: the fingerprint of the reviewed dry run; required in production.",
    )
    parser.add_argument(
        "--json", action="store_true", help="Print the report as JSON (for the change record)."
    )
    return parser


def report_json(plans: Sequence[WorkspacePlan], *, applied: bool) -> dict[str, object]:
    """The same report as data: identifiers and permission names only."""

    def names(keys: Sequence[Key]) -> list[str]:
        return [f"{resource}:{action}" for resource, action in keys]

    return {
        "applied": applied,
        "fingerprint": fingerprint(plans),
        "workspaces": [
            {
                "workspace": str(w.tenant_id),
                "skipped": w.skipped,
                "roles": [
                    {
                        "role": r.role,
                        "grant": names(r.granted if applied else r.missing),
                        "held_back": names(r.held_back),
                        "custom_grants_kept": r.custom,
                    }
                    for r in w.roles
                ],
            }
            for w in plans
        ],
    }


def report(plans: Sequence[WorkspacePlan], *, applied: bool) -> list[str]:
    lines = ["role upgrade: " + ("APPLIED" if applied else "DRY RUN, nothing was changed")]
    lines.append(f"plan fingerprint: {fingerprint(plans)}")
    for workspace in plans:
        if workspace.skipped:
            lines.append(f"workspace {workspace.tenant_id}: skipped ({workspace.skipped})")
            continue
        lines.append(f"workspace {workspace.tenant_id}:")
        for role in workspace.roles:
            done = role.granted if applied else role.missing
            verb = "granted" if applied else "would grant"
            names = ", ".join(f"{r}:{a}" for r, a in done) or "nothing"
            lines.append(f"  {role.role}: {verb} {names}")
            if role.held_back:
                held = ", ".join(f"{r}:{a}" for r, a in role.held_back)
                lines.append(f"  {role.role}: held back (needs --include-administrative) {held}")
            if role.custom:
                lines.append(f"  {role.role}: {role.custom} grant(s) outside the template kept")
    return lines


def main(argv: Sequence[str] | None = None) -> int:
    from crm_app.settings import Process, validate_settings  # noqa: PLC0415

    args = _parser().parse_args(argv)
    try:
        production = os.environ.get("ENVIRONMENT", "") == "production"
        if production and not args.confirm_production:
            raise UpgradeRefusedError(
                "ENVIRONMENT is production: pass --confirm-production to upgrade roles."
            )
        if production and args.apply and not args.expect:
            raise UpgradeRefusedError(
                "In production --apply needs --expect with the reviewed dry run's fingerprint."
            )
        validate_settings(Process.APP)
        plans = upgrade(
            _targets(args),
            apply_changes=args.apply,
            include_administrative=args.include_administrative,
            expect=args.expect,
        )
    except UpgradeRefusedError as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(report_json(plans, applied=args.apply), indent=2))
    else:
        print("\n".join(report(plans, applied=args.apply)))
    return 0


if __name__ == "__main__":
    sys.exit(main())

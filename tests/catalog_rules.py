"""Rules every tenant-owned product table must meet, as pure functions.

`tests/integration/test_tenant_table_guard.py` feeds them facts read from
the PostgreSQL catalogs; `tests/unit/test_catalog_rules.py` tests the rules
themselves. Each function returns a list of violations, empty when the
table complies, so a failure names every problem at once.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass

# The runtime role's privileges on every product table (migration 0001:
# "Each table added later grants SELECT, INSERT, UPDATE, DELETE on itself").
REQUIRED_PRIVILEGES = ("SELECT", "INSERT", "UPDATE", "DELETE")
FORBIDDEN_PRIVILEGES = ("TRUNCATE", "REFERENCES", "TRIGGER")
CHECKED_PRIVILEGES = REQUIRED_PRIVILEGES + FORBIDDEN_PRIVILEGES


@dataclass(frozen=True)
class Policy:
    """One row of `pg_policy`, in the shape `tenant_rls_statements` emits."""

    name: str
    command: str  # pg_policy.polcmd: "*" means ALL
    permissive: bool
    roles: tuple[str, ...]  # "public" for the PUBLIC pseudo-role
    using: str | None
    with_check: str | None


def privilege_violations(
    table: str, held: Mapping[str, bool], *, append_only: bool = False
) -> list[str]:
    """Exactly CRUD, or for an append-only table (decision P3-B D6) exactly
    SELECT, INSERT and DELETE: UPDATE is then forbidden, not optional."""
    required = tuple(p for p in REQUIRED_PRIVILEGES if not (append_only and p == "UPDATE"))
    forbidden = FORBIDDEN_PRIVILEGES + (("UPDATE",) if append_only else ())
    unchecked = [p for p in CHECKED_PRIVILEGES if p not in held]
    missing = [p for p in required if p in held and not held[p]]
    excess = [p for p in forbidden if held.get(p)]
    return (
        [f"{table}: privilege {p} was not checked" for p in unchecked]
        + [f"{table}: runtime role lacks {p}" for p in missing]
        + [f"{table}: runtime role holds forbidden {p}" for p in excess]
    )


def rls_violations(table: str, *, enabled: bool, forced: bool) -> list[str]:
    problems = []
    if not enabled:
        problems.append(f"{table}: row-level security is not enabled")
    if not forced:
        problems.append(f"{table}: row-level security is not forced")
    return problems


def policy_violations(table: str, policies: Sequence[Policy]) -> list[str]:
    """Exactly the policy `saas_os.infra.db.tenant_rls_statements` creates:
    one permissive policy for every command and role, scoped by the
    transaction's `app.tenant_id`, with no separate WITH CHECK."""
    if len(policies) != 1:
        return [f"{table}: expected exactly one policy, found {len(policies)}"]
    policy = policies[0]
    problems = []
    if policy.name != f"{table}_tenant_isolation":
        problems.append(f"{table}: unexpected policy name {policy.name!r}")
    if policy.command != "*":
        problems.append(f"{table}: policy applies to {policy.command!r}, not every command")
    if not policy.permissive:
        problems.append(f"{table}: policy is restrictive, not permissive")
    if policy.roles != ("public",):
        problems.append(f"{table}: policy applies to {policy.roles}, not PUBLIC")
    using = policy.using or ""
    if "tenant_id" not in using or "current_setting('app.tenant_id'" not in using:
        problems.append(f"{table}: policy is not scoped by app.tenant_id")
    if policy.with_check is not None:
        problems.append(f"{table}: policy has an unexpected WITH CHECK")
    return problems


def classification_violations(
    tables: Collection[str], tenant_tables: Collection[str], global_tables: Collection[str]
) -> list[str]:
    """Every product table is either tenant-owned (has `tenant_id`, so the
    RLS and purge rules apply) or explicitly declared global. A table that
    is neither would escape those rules silently."""
    tenant, declared = set(tenant_tables), set(global_tables)
    return [
        f"{t}: has no tenant_id and is not declared global"
        for t in sorted(set(tables) - tenant - declared)
    ] + [f"{t}: declared global but has a tenant_id" for t in sorted(tenant & declared)]


def purge_violations(tenant_tables: Collection[str], covered: Collection[str]) -> list[str]:
    return [f"{t}: not covered by tenant purge" for t in sorted(set(tenant_tables) - set(covered))]


# --- Global tables (decision S-1, option A; migration 0006) ----------------

_USER_SETTING = "current_setting('crm_app.signup_user_id'"
_MAINTENANCE_SETTING = "crm_app.signup_maintenance"
# pg_policy.polcmd for each restrictive owner policy, and which expressions
# it must have: (USING, WITH CHECK).
_OWNER_POLICIES = {
    "owner_read": ("r", True, False),
    "owner_insert": ("a", False, True),
    "owner_update": ("w", True, True),
    "owner_delete": ("d", True, False),
}


def _exclusion_violations(table: str, policy: Policy) -> list[str]:
    """SaaS-OS's `tenant_context_exclusion_statements` policy: permissive,
    every command and role, visible only with no `app.tenant_id`."""
    problems = []
    if policy.command != "*" or not policy.permissive or policy.roles != ("public",):
        problems.append(f"{table}: exclusion policy is not permissive for every command and role")
    using = policy.using or ""
    if "current_setting('app.tenant_id'" not in using or "IS NULL" not in using:
        problems.append(f"{table}: exclusion policy does not require an empty app.tenant_id")
    if policy.with_check is not None:
        problems.append(f"{table}: exclusion policy has an unexpected WITH CHECK")
    return problems


def _owner_violations(table: str, suffix: str, policy: Policy) -> list[str]:
    command, wants_using, wants_check = _OWNER_POLICIES[suffix]
    problems = []
    if policy.permissive:
        problems.append(f"{table}: {policy.name} is permissive, not restrictive")
    if policy.command != command:
        problems.append(f"{table}: {policy.name} applies to {policy.command!r}, not {command!r}")
    if policy.roles != ("public",):
        problems.append(f"{table}: {policy.name} applies to {policy.roles}, not PUBLIC")
    for label, expression, wanted in (
        ("USING", policy.using, wants_using),
        ("WITH CHECK", policy.with_check, wants_check),
    ):
        if wanted and (expression is None or _USER_SETTING not in expression):
            problems.append(f"{table}: {policy.name} {label} is not scoped by the person")
        if not wanted and expression is not None:
            problems.append(f"{table}: {policy.name} has an unexpected {label}")
    writes = (policy.using or "") + (policy.with_check or "")
    if suffix != "owner_read" and _MAINTENANCE_SETTING in writes:
        problems.append(f"{table}: {policy.name} lets the maintenance flag write")
    return problems


def global_policy_violations(
    table: str, policies: Sequence[Policy], *, person_scoped: bool
) -> list[str]:
    """Exactly SaaS-OS's tenant-context exclusion policy, plus, for a
    person-scoped table, the four restrictive owner policies of migration
    0006: every row limited to `crm_app.signup_user_id`; the maintenance
    flag may widen reading only, never writing."""
    expected = {f"{table}_no_tenant_context"}
    if person_scoped:
        expected |= {f"{table}_{suffix}" for suffix in _OWNER_POLICIES}
    by_name = {policy.name: policy for policy in policies}
    problems = [f"{table}: missing policy {name}" for name in sorted(expected - set(by_name))]
    problems += [f"{table}: unexpected policy {name}" for name in sorted(set(by_name) - expected)]
    if f"{table}_no_tenant_context" in by_name:
        problems += _exclusion_violations(table, by_name[f"{table}_no_tenant_context"])
    if person_scoped:
        for suffix in _OWNER_POLICIES:
            policy = by_name.get(f"{table}_{suffix}")
            if policy is not None:
                problems += _owner_violations(table, suffix, policy)
    return problems


def global_reference_violations(
    table: str, *, names_workspace: bool, references_tenants: bool, purge_covered: bool
) -> list[str]:
    """A global table that names a workspace must not hold a foreign key into
    `core.tenants` (it would block SaaS-OS's purge), and the purge
    participant must remove its rows."""
    if not names_workspace:
        return []
    problems = []
    if references_tenants:
        problems.append(f"{table}: references core.tenants, which would block tenant purge")
    if not purge_covered:
        problems.append(f"{table}: names a workspace but is not covered by tenant purge")
    return problems

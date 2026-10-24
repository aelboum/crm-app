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

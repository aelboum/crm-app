"""The workspace directory: which workspaces the signed-in person belongs
to (`PHASE2-PLAN.md` §6.4, decision P2-F 2).

No table: the directory reads the open workspaces from SaaS-OS
(`list_open_tenant_ids`) and keeps those where the person holds an ACTIVE
membership (`get_membership`) and that still admit their members
(`is_accessible_to_principals`). It holds nothing of its own, so it can
never go stale, and listing grants nothing: every workspace request is
still authorized on its own by `require_permission` (P2-B).

The cost is one membership read per open workspace, which suits the tens
to hundreds of workspaces of the MVP; the index table of §6.4 can replace
it if that grows. The route rate-limits each person.

Only the workspace's ID and name are returned, and only after the
membership check (fail closed). SaaS-OS resolves configuration at import
time; only code that runs after validation imports this module.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from saas_os.core.identity import get_membership
from saas_os.core.tenancy import (
    PlatformTenantNotConfiguredError,
    TenantNotFoundError,
    TenantStatus,
    get_platform_tenant_id,
    get_tenant,
    is_accessible_to_principals,
    list_open_tenant_ids,
)

from crm_app.domains.membership import ACTIVE


@dataclass(frozen=True)
class Entry:
    id: uuid.UUID
    name: str


def _platform_tenant() -> uuid.UUID | None:
    """SaaS-OS's own platform tenant is not a CRM workspace."""
    try:
        return get_platform_tenant_id()
    except PlatformTenantNotConfiguredError:
        return None


def list_workspaces(user_id: uuid.UUID) -> list[Entry]:
    """The workspaces where `user_id` is an active member, by name."""
    platform = _platform_tenant()
    entries: list[Entry] = []
    for tenant_id in list_open_tenant_ids():
        if tenant_id == platform:
            continue
        membership = get_membership(tenant_id, user_id)
        if membership is None or membership.status != ACTIVE:
            continue
        try:
            tenant = get_tenant(tenant_id)
        except TenantNotFoundError:
            continue  # gone between the two reads
        if not is_accessible_to_principals(TenantStatus(tenant.status)):
            continue
        entries.append(Entry(id=tenant.id, name=tenant.name))
    return sorted(entries, key=lambda entry: (entry.name.casefold(), str(entry.id)))

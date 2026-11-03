"""Member display names (decision M-P1, PHASE2-PLAN.md §6.5).

SaaS-OS's `core.users` stores no name, so the product keeps one display
name per member and workspace in `crm_app.member_profile` (forced RLS).

- A member sets or clears only their own name; nobody sets another
  member's name.
- Names are read for the members the caller may already see (the member
  list's visibility rules); this module adds no visibility of its own.
- The name is personal data: it is not written to logs or audit metadata,
  and the workspace purge removes it.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from datetime import UTC, datetime

from saas_os.core.audit_log import record_in_transaction
from saas_os.core.authority import UserCaller
from saas_os.infra.db import select, tenant_session_scope

from crm_app.models import MemberProfile

RESOURCE = "crm_app.member_profile"


def names(workspace: uuid.UUID, user_ids: Iterable[uuid.UUID]) -> dict[uuid.UUID, str]:
    """The display names of those of `user_ids` who chose one."""
    wanted = list(set(user_ids))
    if not wanted:
        return {}
    with tenant_session_scope(workspace) as session:
        rows = session.execute(
            select(MemberProfile.user_id, MemberProfile.display_name).where(
                MemberProfile.tenant_id == workspace, MemberProfile.user_id.in_(wanted)
            )
        )
        return dict(rows.tuples().all())


def own(workspace: uuid.UUID, user_id: uuid.UUID) -> str | None:
    return names(workspace, [user_id]).get(user_id)


def set_own(workspace: uuid.UUID, user_id: uuid.UUID, display_name: str | None) -> str | None:
    """Set (or, with None, clear) the caller's own display name; audited
    without the name itself. Returns the name now stored."""
    now = datetime.now(UTC)
    with tenant_session_scope(workspace) as session:
        row = session.get(MemberProfile, (workspace, user_id))
        if display_name is None:
            if row is None:
                return None
            session.delete(row)
        elif row is None:
            session.add(
                MemberProfile(
                    tenant_id=workspace,
                    user_id=user_id,
                    display_name=display_name,
                    updated_at=now,
                )
            )
        elif row.display_name == display_name:
            return display_name
        else:
            row.display_name = display_name
            row.updated_at = now
        record_in_transaction(
            session,
            caller=UserCaller(user_id),
            tenant_id=workspace,
            action=f"{RESOURCE}.{'cleared' if display_name is None else 'updated'}",
            resource_type=RESOURCE,
            resource_id=str(user_id),
            metadata={},
        )
    return display_name

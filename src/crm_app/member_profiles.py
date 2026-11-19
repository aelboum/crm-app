"""Member display names (decision M-P1, PHASE2-PLAN.md §6.5).

SaaS-OS's `core.users` stores no name, so the product keeps one display
name per member and workspace in `crm_app.member_profile` (forced RLS).

- A member sets or clears only their own name; nobody sets another
  member's name.
- Names are read for the members the caller may already see (the member
  list's visibility rules); this module adds no visibility of its own.
- The name is personal data: it is not written to logs or audit metadata,
  and the workspace purge removes it.
- An inviter may suggest a name (decision M-P2, `invitation_intent`): it is
  shown for the member who joined with that invitation until they set
  their own, which always wins. `shown` returns which one is shown.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Literal

from saas_os.core.audit_log import record_in_transaction
from saas_os.core.authority import UserCaller
from saas_os.core.identity import list_invitations_for_tenant
from saas_os.infra.db import select, tenant_session_scope

from crm_app.models import InvitationIntent, MemberProfile

RESOURCE = "crm_app.member_profile"
NameSource = Literal["own", "invitation"]


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


def _invited(workspace: uuid.UUID, user_ids: set[uuid.UUID]) -> dict[uuid.UUID, str]:
    """The names inviters suggested for those of `user_ids` who joined by
    invitation; the latest accepted invitation counts."""
    accepted = sorted(
        (
            invitation
            for invitation in list_invitations_for_tenant(workspace)
            if invitation.accepted_by_user_id in user_ids
        ),
        key=lambda invitation: invitation.created_at,
    )
    if not accepted:
        return {}
    with tenant_session_scope(workspace) as session:
        named = dict(
            session.execute(
                select(InvitationIntent.invitation_id, InvitationIntent.display_name).where(
                    InvitationIntent.tenant_id == workspace,
                    InvitationIntent.invitation_id.in_([i.id for i in accepted]),
                    InvitationIntent.display_name.is_not(None),
                )
            )
            .tuples()
            .all()
        )
    result: dict[uuid.UUID, str] = {}
    for invitation in accepted:
        name = named.get(invitation.id)
        if name and invitation.accepted_by_user_id is not None:
            result[invitation.accepted_by_user_id] = name
    return result


def shown(
    workspace: uuid.UUID, user_ids: Iterable[uuid.UUID]
) -> dict[uuid.UUID, tuple[str, NameSource]]:
    """For each of `user_ids` with a name: the name shown and where it
    comes from, `own` or `invitation` (decision M-P2)."""
    wanted = set(user_ids)
    result: dict[uuid.UUID, tuple[str, NameSource]] = {
        user: (name, "own") for user, name in names(workspace, wanted).items()
    }
    rest = wanted - result.keys()
    if rest:
        for user, name in _invited(workspace, rest).items():
            result[user] = (name, "invitation")
    return result


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

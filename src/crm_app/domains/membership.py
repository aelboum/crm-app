"""Which workspace memberships a member may see.

SaaS-OS memberships are `active`, `suspended` or `revoked`
(`saas_os.core.identity.MembershipStatus`; enforced by a database CHECK);
`revoked` is terminal. The member list shows:

- active memberships to every caller allowed to list members;
- suspended memberships only to callers who may act on them, that is who
  hold `membership:reactivate` (Owner and Admin, PHASE2-PLAN.md §5.2);
- revoked memberships to nobody: nothing can be done with them, and their
  history belongs in the audit log.

Kept free of SaaS-OS imports so the rule is testable without configuration;
`tests/unit/test_membership_visibility.py` checks the status values against
the pinned SaaS-OS source.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

ACTIVE = "active"
SUSPENDED = "suspended"
REVOKED = "revoked"

# The permission whose holders also see suspended memberships.
MANAGE_SUSPENDED = ("membership", "reactivate")


def visible_statuses(*, may_reactivate: bool) -> frozenset[str]:
    return frozenset({ACTIVE, SUSPENDED}) if may_reactivate else frozenset({ACTIVE})


class Refusal(StrEnum):
    """Why a membership or role change is refused (PHASE2-PLAN.md §5.4)."""

    SELF_CHANGE = "self_change"
    OWNER_ONLY = "owner_only"
    CONFIRMATION_REQUIRED = "confirmation_required"
    LAST_OWNER = "last_owner"


@dataclass(frozen=True)
class ChangeFacts:
    """What the backend knows about one requested change, read while the
    workspace's membership lock is held.

    `touches_owner`: the target holds the Owner role, or the change grants
    or removes it. `removes_active_owner`: afterwards the target would no
    longer be an active Owner. `active_owners`: active Owners before the
    change. `stepping_down`: the caller removes their own Owner role."""

    caller_is_owner: bool
    touches_owner: bool
    removes_active_owner: bool
    active_owners: int
    self_change: bool
    stepping_down: bool
    confirmed: bool


def refusal_for(facts: ChangeFacts) -> Refusal | None:
    """`None` when the change may proceed. Checked in this order: nobody
    changes their own membership or roles except an Owner stepping down;
    only an Owner touches an Owner; an Owner change must be re-confirmed;
    the last active Owner can never be removed, demoted or disabled."""
    if facts.self_change and not facts.stepping_down:
        return Refusal.SELF_CHANGE
    if facts.touches_owner and not facts.caller_is_owner:
        return Refusal.OWNER_ONLY
    if facts.touches_owner and not facts.confirmed:
        return Refusal.CONFIRMATION_REQUIRED
    if facts.removes_active_owner and facts.active_owners <= 1:
        return Refusal.LAST_OWNER
    return None

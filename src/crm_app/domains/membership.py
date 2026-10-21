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

ACTIVE = "active"
SUSPENDED = "suspended"
REVOKED = "revoked"

# The permission whose holders also see suspended memberships.
MANAGE_SUSPENDED = ("membership", "reactivate")


def visible_statuses(*, may_reactivate: bool) -> frozenset[str]:
    return frozenset({ACTIVE, SUSPENDED}) if may_reactivate else frozenset({ACTIVE})

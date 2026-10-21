"""The member list never shows revoked memberships and shows suspended ones
only to callers who may reactivate them (`crm_app.domains.membership`)."""

from __future__ import annotations

import re
from pathlib import Path

import saas_os

from crm_app.domains.membership import (
    ACTIVE,
    MANAGE_SUSPENDED,
    REVOKED,
    SUSPENDED,
    visible_statuses,
)
from crm_app.roles import ROLE_TEMPLATES, Role


def test_ordinary_members_see_active_memberships_only() -> None:
    assert visible_statuses(may_reactivate=False) == {ACTIVE}


def test_members_who_may_reactivate_also_see_suspended_ones() -> None:
    assert visible_statuses(may_reactivate=True) == {ACTIVE, SUSPENDED}


def test_revoked_memberships_are_never_visible() -> None:
    assert REVOKED not in visible_statuses(may_reactivate=True)
    assert REVOKED not in visible_statuses(may_reactivate=False)


def test_the_statuses_match_the_pinned_saas_os_enum() -> None:
    """Read from source: importing `saas_os.core.identity` resolves
    configuration at import time."""
    models = Path(saas_os.__file__).parent / "core" / "identity" / "models.py"
    body = models.read_text(encoding="utf-8").split("class MembershipStatus", 1)[1]
    body = body.split("\nclass ", 1)[0]
    values = set(re.findall(r'^\s+[A-Z]+ = "([a-z_]+)"$', body, re.MULTILINE))
    assert values == {ACTIVE, SUSPENDED, REVOKED}


def test_only_owner_and_admin_see_suspended_memberships() -> None:
    """The deciding permission follows the approved matrix (PHASE2-PLAN.md §5.2)."""
    holders = {role for role, template in ROLE_TEMPLATES.items() if MANAGE_SUSPENDED in template}
    assert holders == {Role.OWNER, Role.ADMIN}

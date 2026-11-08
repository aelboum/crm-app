"""A workspace's first steps, for the Home page's setup checklist (decision P4-S).

Each step is a yes or no read from what the workspace already stores: are
business hours set, does it have a contact, a deal, a form, a booking page
and an automation, and does it have more than one active member. Only
whether something exists is read, never what it holds, so every role may
see the list. Read-only, bounded: each record step reads at most one row.
"""

from __future__ import annotations

from typing import Any

from saas_os.core.identity import list_tenant_members
from saas_os.infra.db import select, set_local_statement_timeout, tenant_session_scope

from crm_app.domains.membership import ACTIVE
from crm_app.models import (
    Automation,
    BookingPage,
    Contact,
    Form,
    Opportunity,
    WorkspaceSettings,
)
from crm_app.records import Scope

# In the order the checklist shows them.
STEPS: tuple[str, ...] = (
    "business_hours",
    "contact",
    "deal",
    "form",
    "booking_page",
    "automation",
    "teammate",
)
_TIMEOUT_MS = 5_000
_TABLES: dict[str, Any] = {
    "contact": Contact,
    "deal": Opportunity,
    "form": Form,
    "booking_page": BookingPage,
    "automation": Automation,
}


def steps(scope: Scope) -> list[dict[str, Any]]:
    """Each step with whether it is done."""
    done: dict[str, bool] = {}
    with tenant_session_scope(scope.workspace) as session:
        set_local_statement_timeout(session, _TIMEOUT_MS)
        hours = session.execute(
            select(WorkspaceSettings.business_hours).where(
                WorkspaceSettings.tenant_id == scope.workspace
            )
        ).scalar_one_or_none()
        done["business_hours"] = hours is not None
        for step, table in _TABLES.items():
            done[step] = (
                session.execute(
                    select(table.id).where(table.tenant_id == scope.workspace).limit(1)
                ).first()
                is not None
            )
    active = sum(1 for member in list_tenant_members(scope.workspace) if member.status == ACTIVE)
    done["teammate"] = active > 1
    return [{"key": step, "done": done[step]} for step in STEPS]

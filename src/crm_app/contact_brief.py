"""The facts one contact brief may send, read from the database (decisions
P9-P, P9-B).

Reads exactly the allowlisted `ai_brief.ContactFacts` for one contact in
the caller's workspace, under its row security: the lifecycle stage, the
source, tag names, the creation day, the kinds and days of the last
history entries, its deals' stage names and outcomes, and counts of open
and overdue tasks and upcoming appointments. Never a name, address,
phone number, note, message, custom-field value, title or member.
Nothing is written.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from saas_os.infra.db import select, tenant_session_scope

from crm_app.domains import ai_brief
from crm_app.domains.settings import DEFAULT_TIME_ZONE
from crm_app.models import (
    Activity,
    Appointment,
    Contact,
    ContactTag,
    Opportunity,
    PipelineStage,
    Tag,
    Task,
    WorkspaceSettings,
)
from crm_app.records import Scope

# Statuses of an appointment that will not take place.
_NOT_HAPPENING = ("cancelled", "no_show", "completed")


def _zone(name: str | None) -> ZoneInfo:
    try:
        return ZoneInfo(name or DEFAULT_TIME_ZONE)
    except ZoneInfoNotFoundError:
        return ZoneInfo(DEFAULT_TIME_ZONE)


def facts(scope: Scope, contact_id: uuid.UUID) -> tuple[ai_brief.ContactFacts, date] | None:
    """The contact's facts and today's day in the workspace's time zone, or
    None when the contact is not in the workspace."""
    now = datetime.now(UTC)
    workspace = scope.workspace
    with tenant_session_scope(workspace) as session:
        contact = session.execute(
            select(Contact.lifecycle_stage, Contact.source, Contact.created_at).where(
                Contact.tenant_id == workspace, Contact.id == contact_id
            )
        ).first()
        if contact is None:
            return None
        zone = _zone(
            session.execute(
                select(WorkspaceSettings.time_zone).where(WorkspaceSettings.tenant_id == workspace)
            ).scalar_one_or_none()
        )
        tags = session.execute(
            select(Tag.name)
            .join(
                ContactTag, (ContactTag.tenant_id == Tag.tenant_id) & (ContactTag.tag_id == Tag.id)
            )
            .where(ContactTag.tenant_id == workspace, ContactTag.contact_id == contact_id)
            .order_by(Tag.name)
            .limit(ai_brief.MAX_TAGS)
        ).scalars()
        tag_names = tuple(tags)
        history = session.execute(
            select(Activity.kind, Activity.occurred_at)
            .where(Activity.tenant_id == workspace, Activity.contact_id == contact_id)
            .order_by(Activity.occurred_at.desc(), Activity.id)
            .limit(ai_brief.MAX_HISTORY)
        ).all()
        deals = session.execute(
            select(PipelineStage.name, Opportunity.outcome)
            .join(
                PipelineStage,
                (PipelineStage.tenant_id == Opportunity.tenant_id)
                & (PipelineStage.id == Opportunity.stage_id),
            )
            .where(Opportunity.tenant_id == workspace, Opportunity.contact_id == contact_id)
            .order_by(Opportunity.created_at.desc(), Opportunity.id)
            .limit(ai_brief.MAX_DEALS)
        ).all()
        due = list(
            session.execute(
                select(Task.due_at).where(
                    Task.tenant_id == workspace,
                    Task.contact_id == contact_id,
                    Task.completed_at.is_(None),
                )
            ).scalars()
        )
        upcoming = session.execute(
            select(Appointment.id).where(
                Appointment.tenant_id == workspace,
                Appointment.contact_id == contact_id,
                Appointment.starts_at >= now,
                Appointment.status.not_in(_NOT_HAPPENING),
            )
        ).all()
    found = ai_brief.ContactFacts(
        lifecycle_stage=contact.lifecycle_stage,
        source=contact.source,
        tag_names=tag_names,
        created_on=contact.created_at.astimezone(zone).date(),
        history=tuple(
            ai_brief.HistoryFact(kind=kind, day=at.astimezone(zone).date()) for kind, at in history
        ),
        deals=tuple(ai_brief.DealFact(stage=stage, outcome=outcome) for stage, outcome in deals),
        open_tasks=len(due),
        overdue_tasks=sum(1 for at in due if at is not None and at < now),
        upcoming_appointments=len(upcoming),
    )
    return found, now.astimezone(zone).date()

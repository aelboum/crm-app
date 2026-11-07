"""In-app reminders of upcoming appointments for their hosts (decision N-2).

`LEAD` before an appointment starts, its host gets an `appointment_upcoming`
notification in the app (`crm_app.notifications`). The email maintenance
run (`crm_app.email_maintenance`) calls `run_due`: it finds the workspaces
with an appointment starting up to a known time through the global
`member_reminder_workspace`, and in each one's own tenant session notifies
the host of every appointment that starts within `LEAD`, is pending or
confirmed, and was made before its reminder time. The row in
`appointment_member_reminder` and the notification are written in the
same transaction; its primary key (workspace, appointment, start time)
makes a retried or concurrent run notify nobody twice, and a rescheduled
appointment is reminded of again for its new time.

`register` is called when an appointment is made or moved. It records the
latest start time per workspace in its own transaction, before the
caller's commits: a rolled-back change leaves a later time than needed,
which only makes a run look at a workspace with nothing due.

Nothing leaves the product: no email, no push. A host notified about
their own appointment is still notified, since nobody acted.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta

from saas_os.core.tenancy import TenantClosedError, TenantNotFoundError, lock_open_tenant
from saas_os.infra.db import (
    IntegrityError,
    OperationalError,
    delete,
    select,
    session_scope,
    tenant_session_scope,
)

from crm_app import notifications
from crm_app.domains import reminders as rules
from crm_app.models import Appointment, AppointmentMemberReminder, MemberReminderWorkspace

logger = logging.getLogger(__name__)
LEAD = timedelta(minutes=30)
# Appointments looked at per workspace per run; the rest wait for the next.
PER_WORKSPACE = 200


def _now() -> datetime:
    return datetime.now(UTC)


def register(workspace: uuid.UUID, starts_at: datetime) -> None:
    """Note that `workspace` has an appointment starting at `starts_at`."""
    with session_scope() as session:
        row = session.get(MemberReminderWorkspace, workspace, with_for_update=True)
        if row is None:
            session.add(MemberReminderWorkspace(workspace_id=workspace, until=starts_at))
        elif row.until < starts_at:
            row.until = starts_at


def forget_workspace(tenant_id: uuid.UUID) -> bool:
    """Remove a purged workspace's registry row; True when none remains."""
    with session_scope() as session:
        session.execute(
            delete(MemberReminderWorkspace).where(MemberReminderWorkspace.workspace_id == tenant_id)
        )
    with session_scope() as session:
        return session.get(MemberReminderWorkspace, tenant_id) is None


def _remind_workspace(workspace: uuid.UUID, now: datetime) -> int:
    reminded = (
        (AppointmentMemberReminder.tenant_id == Appointment.tenant_id)
        & (AppointmentMemberReminder.appointment_id == Appointment.id)
        & (AppointmentMemberReminder.starts_at == Appointment.starts_at)
    )
    with tenant_session_scope(workspace) as session:
        lock_open_tenant(session, workspace)
        # Appointments already reminded of for this start time are left out
        # before the limit, so they never crowd out the rest.
        due = session.execute(
            select(Appointment)
            .outerjoin(AppointmentMemberReminder, reminded)
            .where(
                Appointment.tenant_id == workspace,
                Appointment.cancelled_at.is_(None),
                Appointment.status.in_(rules.REMINDED_STATUSES),
                Appointment.starts_at > now,
                Appointment.starts_at <= now + LEAD,
                # Made before its reminder time: a host who books something
                # a few minutes ahead already knows about it.
                Appointment.created_at < Appointment.starts_at - LEAD,
                AppointmentMemberReminder.appointment_id.is_(None),
            )
            .order_by(Appointment.starts_at, Appointment.id)
            .limit(PER_WORKSPACE)
        ).scalars()
        count = 0
        for appointment in due:
            session.add(
                AppointmentMemberReminder(
                    tenant_id=workspace,
                    appointment_id=appointment.id,
                    starts_at=appointment.starts_at,
                    created_at=now,
                )
            )
            notifications.notify(
                session,
                workspace,
                appointment.host_user_id,
                "appointment_upcoming",
                appointment.id,
                actor=None,
            )
            count += 1
        session.flush()
    return count


def _registered(now: datetime, limit: int) -> list[uuid.UUID]:
    """The registered workspaces to look at; rows whose last known
    appointment has started are removed first (nothing more to remind of)."""
    with session_scope() as session:
        session.execute(delete(MemberReminderWorkspace).where(MemberReminderWorkspace.until <= now))
    with session_scope() as session:
        return list(
            session.execute(
                select(MemberReminderWorkspace.workspace_id)
                .order_by(MemberReminderWorkspace.workspace_id)
                .limit(limit)
            ).scalars()
        )


def run_due(now: datetime | None = None, *, limit: int = 500) -> dict[str, int]:
    """Notify every host whose appointment starts within `LEAD`. A
    workspace that fails (closed, or a concurrent run got there first) is
    left for the next run."""
    now = now or _now()
    totals = {"notified": 0, "workspaces": 0, "failed": 0}
    for workspace in _registered(now, limit):
        try:
            count = _remind_workspace(workspace, now)
        except (TenantClosedError, TenantNotFoundError, IntegrityError, OperationalError):
            totals["failed"] += 1
            continue
        except Exception as exc:  # noqa: BLE001 - one workspace never stops the run
            # The workspace id and the error's type only: never its data.
            logger.warning(
                "member reminders: workspace %s failed (%s)", workspace, type(exc).__name__
            )
            totals["failed"] += 1
            continue
        totals["workspaces"] += 1
        totals["notified"] += count
    return totals

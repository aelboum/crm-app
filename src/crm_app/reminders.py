"""Appointment reminder emails (decision P5-D).

A workspace's settings say how long before an appointment its contact is
emailed a reminder (`reminder_lead_minutes`, off by default). The email
maintenance run (`crm_app.email_maintenance`) finds the workspaces that
have reminders on through the global `reminder_workspace`, re-reads each
one's setting in its own tenant session, and queues one transactional
email per appointment and start time that is due (`domains.reminders.due`):
the unique automatic row makes a retried or concurrent run remind nobody
twice. A rescheduled appointment is reminded about again for its new
time. Appointments without a contact, or whose contact has no usable
address or is archived, get a `skipped` row with the reason, so the
appointment says why nobody was reminded.

A member who may update appointments can send a reminder at once, at most
once an hour per appointment. Emails go through `crm_app.emails`: nothing
reaches a provider while sending is off (P6-E 3), and suppressed addresses
are never sent to.

The email acts as the appointment's host, as booking confirmations do
(P5-C 9); a member's reminder acts as that member.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from saas_os.core.tenancy import TenantClosedError, TenantNotFoundError, lock_open_tenant
from saas_os.infra.db import (
    IntegrityError,
    OperationalError,
    Session,
    delete,
    is_transaction_conflict,
    select,
    session_scope,
    tenant_session_scope,
)

from crm_app import emails
from crm_app.domains import reminders as rules
from crm_app.domains import settings as setting_values
from crm_app.domains.records import InvalidValue
from crm_app.models import (
    Appointment,
    AppointmentReminder,
    Contact,
    ReminderWorkspace,
    WorkspaceSettings,
)
from crm_app.records import (
    RecordError,
    RecordNotFoundError,
    Scope,
    TransactionConflictError,
)

Item = dict[str, Any]
logger = logging.getLogger(__name__)
HISTORY_MAX = 10
# Appointments looked at per workspace per run; the rest wait for the next.
PER_WORKSPACE = 200


class ReminderUnavailableError(RecordError):
    """Nobody can be reminded: the appointment is over, cancelled or
    completed, or has no contact with a usable address."""

    status, code = 422, "reminder_unavailable"

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class ReminderTooSoonError(RecordError):
    """A reminder was sent for this appointment within the last hour."""

    status, code = 409, "reminder_too_soon"


def _now() -> datetime:
    return datetime.now(UTC)


# --- Workspace registry -------------------------------------------------------------------


def register_workspace(workspace: uuid.UUID, lead: int | None) -> None:
    """Record whether the workspace has reminders on (after its settings
    commit); the maintenance run finds it by this row."""
    with session_scope() as session:
        row = session.get(ReminderWorkspace, workspace)
        if lead is None:
            if row is not None:
                session.delete(row)
        elif row is None:
            session.add(
                ReminderWorkspace(workspace_id=workspace, lead_minutes=lead, updated_at=_now())
            )
        else:
            row.lead_minutes, row.updated_at = lead, _now()


def forget_workspace(tenant_id: uuid.UUID) -> bool:
    """Remove a purged workspace's registry row; True when none remains."""
    with session_scope() as session:
        session.execute(
            delete(ReminderWorkspace).where(ReminderWorkspace.workspace_id == tenant_id)
        )
    with session_scope() as session:
        return session.get(ReminderWorkspace, tenant_id) is None


# --- Making a reminder ----------------------------------------------------------------------


@dataclass(frozen=True)
class _Workspace:
    lead: int | None
    time_zone: str


def _settings(session: Session, workspace: uuid.UUID) -> _Workspace:
    row = session.execute(
        select(WorkspaceSettings).where(WorkspaceSettings.tenant_id == workspace)
    ).scalar_one_or_none()
    if row is None:
        return _Workspace(lead=None, time_zone=setting_values.DEFAULT_TIME_ZONE)
    return _Workspace(lead=row.reminder_lead_minutes, time_zone=row.time_zone)


def _recipient(session: Session, appointment: Appointment) -> tuple[Contact | None, str | None]:
    """The contact and why they cannot be reminded, if they cannot."""
    if appointment.contact_id is None:
        return None, "no_contact"
    contact = session.execute(
        select(Contact).where(
            Contact.tenant_id == appointment.tenant_id, Contact.id == appointment.contact_id
        )
    ).scalar_one_or_none()
    if contact is None:
        return None, "no_contact"
    if contact.archived_at is not None:
        return contact, "contact_archived"
    if not contact.email:
        return contact, "no_email"
    return contact, None


def _make(  # noqa: PLR0913 - one reminder: where, what, who and how
    session: Session,
    appointment: Appointment,
    settings: _Workspace,
    *,
    kind: str,
    actor: uuid.UUID,
    now: datetime,
) -> AppointmentReminder:
    contact, reason = _recipient(session, appointment)
    email_id: uuid.UUID | None = None
    if reason is None and contact is not None and contact.email:
        subject, body = rules.text(
            contact.first_name,
            appointment.title,
            starts_at=appointment.starts_at,
            ends_at=appointment.ends_at,
            time_zone=settings.time_zone,
            kind=appointment.kind,
            location=appointment.location,
        )
        try:
            email_id = emails.queue(
                session,
                Scope(workspace=appointment.tenant_id, actor=actor),
                purpose="appointment_reminder",
                to_email=contact.email,
                subject=subject,
                text_body=body,
                contact_id=contact.id,
            )
        except InvalidValue:
            reason = "invalid_email"
    row = AppointmentReminder(
        id=uuid.uuid4(),
        tenant_id=appointment.tenant_id,
        appointment_id=appointment.id,
        starts_at=appointment.starts_at,
        kind=kind,
        outcome="queued" if email_id else "skipped",
        skip_reason=None if email_id else reason,
        email_message_id=email_id,
        created_by_user_id=actor if kind == "manual" else None,
        created_at=now,
    )
    session.add(row)
    session.flush()
    return row


# --- The maintenance run -----------------------------------------------------------------


def _remind_workspace(workspace: uuid.UUID, now: datetime) -> dict[str, int]:
    counts = {"queued": 0, "skipped": 0}
    with tenant_session_scope(workspace) as session:
        lock_open_tenant(session, workspace)
        settings = _settings(session, workspace)
        if settings.lead is None:
            register_workspace(workspace, None)
            return counts
        window_end = now + timedelta(minutes=settings.lead)
        # Appointments already reminded for this start time are left out
        # before the limit, so they never crowd out the rest (13-H5).
        reminded = (
            (AppointmentReminder.tenant_id == Appointment.tenant_id)
            & (AppointmentReminder.appointment_id == Appointment.id)
            & (AppointmentReminder.starts_at == Appointment.starts_at)
            & (AppointmentReminder.kind == "automatic")
        )
        candidates = session.execute(
            select(Appointment)
            .outerjoin(AppointmentReminder, reminded)
            .where(
                Appointment.tenant_id == workspace,
                Appointment.cancelled_at.is_(None),
                Appointment.status.in_(rules.REMINDED_STATUSES),
                Appointment.starts_at > now,
                Appointment.starts_at <= window_end,
                AppointmentReminder.id.is_(None),
            )
            .order_by(Appointment.starts_at, Appointment.id)
            .limit(PER_WORKSPACE)
        ).scalars()
        due = [
            row
            for row in candidates
            if rules.due(
                starts_at=row.starts_at,
                created_at=row.created_at,
                status=row.status,
                cancelled=row.cancelled_at is not None,
                lead=settings.lead,
                now=now,
            )
        ]
        if not due:
            return counts
        # A contact emailed within `MANUAL_GAP` (an appointment rescheduled
        # again and again) is not reminded once more (13-H5).
        recent = set(
            session.execute(
                select(AppointmentReminder.appointment_id).where(
                    AppointmentReminder.tenant_id == workspace,
                    AppointmentReminder.outcome == "queued",
                    AppointmentReminder.created_at > now - rules.MANUAL_GAP,
                    AppointmentReminder.appointment_id.in_([row.id for row in due]),
                )
            ).scalars()
        )
        for appointment in due:
            if appointment.id in recent:
                continue
            made = _make(
                session,
                appointment,
                settings,
                kind="automatic",
                actor=appointment.host_user_id,
                now=now,
            )
            counts[made.outcome] += 1
    return counts


def run_due(now: datetime | None = None, *, limit: int = 500) -> dict[str, int]:
    """Queue every reminder due now, across the workspaces with reminders on.
    A workspace that fails (closed, or a concurrent run got there first) is
    left for the next run."""
    now = now or _now()
    with session_scope() as session:
        workspaces = list(
            session.execute(
                select(ReminderWorkspace.workspace_id)
                .order_by(ReminderWorkspace.workspace_id)
                .limit(limit)
            ).scalars()
        )
    totals = {"queued": 0, "skipped": 0, "workspaces": 0, "failed": 0}
    for workspace in workspaces:
        try:
            counts = _remind_workspace(workspace, now)
        except (TenantClosedError, TenantNotFoundError, IntegrityError, OperationalError):
            totals["failed"] += 1
            continue
        except Exception as exc:  # noqa: BLE001 - one workspace never stops the run (13-H5)
            # The workspace id and the error's type only: never its data.
            logger.warning("reminders: workspace %s failed (%s)", workspace, type(exc).__name__)
            totals["failed"] += 1
            continue
        totals["workspaces"] += 1
        totals["queued"] += counts["queued"]
        totals["skipped"] += counts["skipped"]
    return totals


# --- Members ---------------------------------------------------------------------------------


def _transaction[T](scope: Scope, fn: Callable[[Session], T]) -> T:
    try:
        with tenant_session_scope(scope.workspace) as session:
            lock_open_tenant(session, scope.workspace)
            return fn(session)
    except (TenantClosedError, TenantNotFoundError):
        raise RecordNotFoundError from None
    except OperationalError as exc:
        if is_transaction_conflict(exc):
            raise TransactionConflictError from None
        raise


def _load(session: Session, scope: Scope, appointment_id: uuid.UUID, *, lock: bool) -> Appointment:
    query = select(Appointment).where(
        Appointment.tenant_id == scope.workspace, Appointment.id == appointment_id
    )
    row = session.execute(query.with_for_update() if lock else query).scalar_one_or_none()
    if row is None:
        raise RecordNotFoundError
    return row


def _item(row: AppointmentReminder) -> Item:
    return {
        "id": row.id,
        "kind": row.kind,
        "outcome": row.outcome,
        "skip_reason": row.skip_reason,
        "starts_at": row.starts_at,
        "created_at": row.created_at,
        "created_by_user_id": row.created_by_user_id,
    }


def _history(session: Session, scope: Scope, appointment_id: uuid.UUID) -> list[Item]:
    rows = session.execute(
        select(AppointmentReminder)
        .where(
            AppointmentReminder.tenant_id == scope.workspace,
            AppointmentReminder.appointment_id == appointment_id,
        )
        .order_by(AppointmentReminder.created_at.desc(), AppointmentReminder.id.desc())
        .limit(HISTORY_MAX)
    ).scalars()
    return [_item(row) for row in rows]


def status(scope: Scope, appointment_id: uuid.UUID) -> Item:
    """The workspace's reminder setting, when this appointment's automatic
    reminder is due (if it will be), and the latest reminders made."""

    def read(session: Session) -> Item:
        row = _load(session, scope, appointment_id, lock=False)
        settings = _settings(session, scope.workspace)
        history = _history(session, scope, appointment_id)
        next_at = None
        if settings.lead is not None:
            remind_at = row.starts_at - timedelta(minutes=settings.lead)
            already = any(
                item["kind"] == "automatic" and item["starts_at"] == row.starts_at
                for item in history
            )
            if (
                not already
                and row.cancelled_at is None
                and row.status in rules.REMINDED_STATUSES
                and row.created_at < remind_at
                and row.starts_at > _now()
            ):
                next_at = max(remind_at, _now())
        _, reason = _recipient(session, row)
        return {
            "lead_minutes": settings.lead,
            "next_at": next_at,
            "recipient_problem": reason,
            "items": history,
        }

    return _transaction(scope, read)


def send_now(scope: Scope, appointment_id: uuid.UUID) -> Item:
    """Queue a reminder for this appointment now, as the acting member."""

    def apply(session: Session) -> Item:
        row = _load(session, scope, appointment_id, lock=True)
        now = _now()
        if row.cancelled_at is not None or row.status not in rules.REMINDED_STATUSES:
            raise ReminderUnavailableError("not_open")
        if row.starts_at <= now:
            raise ReminderUnavailableError("started")
        _, reason = _recipient(session, row)
        if reason is not None:
            raise ReminderUnavailableError(reason)
        last = session.execute(
            select(AppointmentReminder.created_at)
            .where(
                AppointmentReminder.tenant_id == scope.workspace,
                AppointmentReminder.appointment_id == appointment_id,
                AppointmentReminder.outcome == "queued",
            )
            .order_by(AppointmentReminder.created_at.desc())
            .limit(1)
        ).scalar_one_or_none()
        if last is not None and now - last < rules.MANUAL_GAP:
            raise ReminderTooSoonError
        made = _make(
            session,
            row,
            _settings(session, scope.workspace),
            kind="manual",
            actor=scope.actor,
            now=now,
        )
        if made.outcome != "queued":
            raise ReminderUnavailableError(made.skip_reason or "invalid_email")
        return _item(made)

    return _transaction(scope, apply)

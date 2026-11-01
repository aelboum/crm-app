"""Reports over contacts, deals, tasks and appointments (decision P10-A).

Every figure is counted from rows as they are stored now, in one workspace
under its row security, for a period of whole days in the workspace's time
zone and the same number of days before it. Deleted records are gone and
not counted; a reopened deal counts as open, not as won or lost. Each read
takes at most `ROW_CAP` rows and says when it stopped there (`capped`), and
runs under a statement timeout so a large report cannot hold a connection.
Amounts are summed per currency as exact decimals, never converted.

SaaS-OS's public database surface offers no `count` or `group by`, so rows
are counted here; the cap and the indexes on `created_at`, `closed_at`,
`completed_at` and `starts_at` keep that bounded.
"""

from __future__ import annotations

import uuid
from collections import Counter
from collections.abc import Iterable, Sequence
from datetime import datetime
from decimal import Decimal
from typing import Any

from saas_os.infra.db import (
    Session,
    select,
    set_local_statement_timeout,
    tenant_session_scope,
)

from crm_app.domains import opportunities as deal_rules
from crm_app.domains import reports as rules
from crm_app.domains.settings import DEFAULT_TIME_ZONE
from crm_app.models import Appointment, Contact, Opportunity, Task, WorkspaceSettings
from crm_app.records import Scope

ROW_CAP = 20_000
_TIMEOUT_MS = 5_000

Item = dict[str, Any]


def _start(session: Session) -> None:
    set_local_statement_timeout(session, _TIMEOUT_MS)


def resolve(scope: Scope, start: Any, end: Any) -> rules.Period:
    """The period in the workspace's time zone (refuses with `InvalidPeriod`)."""
    with tenant_session_scope(scope.workspace) as session:
        zone = session.execute(
            select(WorkspaceSettings.time_zone).where(
                WorkspaceSettings.tenant_id == scope.workspace
            )
        ).scalar_one_or_none()
    return rules.period(start, end, zone or DEFAULT_TIME_ZONE)


def _capped[T](rows: Sequence[T]) -> tuple[list[T], bool]:
    return list(rows[:ROW_CAP]), len(rows) > ROW_CAP


def _period(chosen: rules.Period) -> Item:
    return {
        "start": chosen.start.isoformat(),
        "end": chosen.end.isoformat(),
        "days": chosen.days,
    }


def _sums(pairs: Iterable[tuple[str, Decimal | None]]) -> list[Item]:
    totals: dict[str, Decimal] = {}
    for currency, amount in pairs:
        if amount is not None:
            totals[currency] = totals.get(currency, Decimal(0)) + amount
    return [
        {"currency": currency, "amount": deal_rules.amount_text(amount, currency)}
        for currency, amount in sorted(totals.items())
    ]


def _people(counts: Counter[uuid.UUID | None]) -> list[Item]:
    return [
        {"user_id": user, "count": count}
        for user, count in sorted(counts.items(), key=lambda item: (-item[1], str(item[0])))
    ]


def contacts(scope: Scope, chosen: rules.Period) -> Item:
    """Contacts created in the period, archived ones included, by source."""
    with tenant_session_scope(scope.workspace) as session:
        _start(session)
        rows, capped = _capped(
            session.execute(
                select(Contact.created_at, Contact.source)
                .where(
                    Contact.tenant_id == scope.workspace,
                    Contact.created_at >= chosen.previous_since,
                    Contact.created_at < chosen.until,
                )
                .limit(ROW_CAP + 1)
            ).all()
        )
    created: Counter[str] = Counter()
    sources: Counter[str] = Counter()
    for created_at, source in rows:
        side = rules.where(created_at, chosen)
        if side is None:
            continue
        created[side] += 1
        if side == "current":
            sources[source] += 1
    return {
        "period": _period(chosen),
        "capped": capped,
        "created": created["current"],
        "created_before": created["previous"],
        "sources": [
            {"source": s, "count": n}
            for s, n in sorted(sources.items(), key=lambda i: (-i[1], i[0]))
        ],
    }


def deals(scope: Scope, chosen: rules.Period) -> Item:
    """Deals created in the period, and deals won or lost in it (by their
    current outcome and close time), with values per currency and owner."""
    with tenant_session_scope(scope.workspace) as session:
        _start(session)
        rows, capped = _capped(
            session.execute(
                select(
                    Opportunity.created_at,
                    Opportunity.closed_at,
                    Opportunity.outcome,
                    Opportunity.amount,
                    Opportunity.currency,
                    Opportunity.owner_user_id,
                )
                .where(
                    Opportunity.tenant_id == scope.workspace,
                    (
                        (Opportunity.created_at >= chosen.previous_since)
                        & (Opportunity.created_at < chosen.until)
                    )
                    | (
                        (Opportunity.closed_at >= chosen.previous_since)
                        & (Opportunity.closed_at < chosen.until)
                    ),
                )
                .limit(ROW_CAP + 1)
            ).all()
        )
    created: Counter[str] = Counter()
    closed: Counter[tuple[str, str]] = Counter()
    won_values: list[tuple[str, Decimal | None]] = []
    lost_values: list[tuple[str, Decimal | None]] = []
    owners: dict[uuid.UUID | None, list[tuple[str, Decimal | None]]] = {}
    for created_at, closed_at, outcome, amount, currency, owner in rows:
        side = rules.where(created_at, chosen)
        if side is not None:
            created[side] += 1
        side = rules.where(closed_at, chosen)
        if side is None or outcome == deal_rules.OPEN:
            continue
        closed[(side, outcome)] += 1
        if side != "current":
            continue
        if outcome == deal_rules.WON:
            won_values.append((currency, amount))
            owners.setdefault(owner, []).append((currency, amount))
        else:
            lost_values.append((currency, amount))
    won, lost = closed[("current", deal_rules.WON)], closed[("current", deal_rules.LOST)]
    won_before = closed[("previous", deal_rules.WON)]
    lost_before = closed[("previous", deal_rules.LOST)]
    return {
        "period": _period(chosen),
        "capped": capped,
        "created": created["current"],
        "created_before": created["previous"],
        "won": won,
        "won_before": won_before,
        "lost": lost,
        "lost_before": lost_before,
        # Percent of the deals closed in the period that were won; none when none closed.
        "win_rate": round(100 * won / (won + lost)) if won + lost else None,
        "win_rate_before": (
            round(100 * won_before / (won_before + lost_before))
            if won_before + lost_before
            else None
        ),
        "won_value": _sums(won_values),
        "lost_value": _sums(lost_values),
        "owners": [
            {"user_id": owner, "won": len(values), "won_value": _sums(values)}
            for owner, values in sorted(
                owners.items(), key=lambda item: (-len(item[1]), str(item[0]))
            )
        ],
    }


def tasks(scope: Scope, chosen: rules.Period, now: datetime) -> Item:
    """Tasks created and completed in the period, completed tasks against
    their due time, and the open tasks overdue now."""
    with tenant_session_scope(scope.workspace) as session:
        _start(session)
        rows, capped = _capped(
            session.execute(
                select(Task.created_at, Task.completed_at, Task.due_at, Task.completed_by_user_id)
                .where(
                    Task.tenant_id == scope.workspace,
                    ((Task.created_at >= chosen.previous_since) & (Task.created_at < chosen.until))
                    | (
                        (Task.completed_at >= chosen.previous_since)
                        & (Task.completed_at < chosen.until)
                    ),
                )
                .limit(ROW_CAP + 1)
            ).all()
        )
        overdue_rows, overdue_capped = _capped(
            session.execute(
                select(Task.id)
                .where(
                    Task.tenant_id == scope.workspace,
                    Task.completed_at.is_(None),
                    Task.due_at < now,
                )
                .limit(ROW_CAP + 1)
            ).all()
        )
    created: Counter[str] = Counter()
    completed: Counter[str] = Counter()
    timing: Counter[str] = Counter()
    people: Counter[uuid.UUID | None] = Counter()
    for created_at, completed_at, due_at, completed_by in rows:
        side = rules.where(created_at, chosen)
        if side is not None:
            created[side] += 1
        side = rules.where(completed_at, chosen)
        if side is None:
            continue
        completed[side] += 1
        if side != "current" or completed_at is None:
            continue
        people[completed_by] += 1
        if due_at is None:
            timing["no_due"] += 1
        elif completed_at <= due_at:
            timing["on_time"] += 1
        else:
            timing["late"] += 1
    return {
        "period": _period(chosen),
        "capped": capped or overdue_capped,
        "created": created["current"],
        "created_before": created["previous"],
        "completed": completed["current"],
        "completed_before": completed["previous"],
        "on_time": timing["on_time"],
        "late": timing["late"],
        "no_due": timing["no_due"],
        "overdue_now": len(overdue_rows),
        "completed_by": _people(people),
    }


def appointments(scope: Scope, chosen: rules.Period) -> Item:
    """Appointments starting in the period by status, the no-show rate and
    each host's appointments."""
    with tenant_session_scope(scope.workspace) as session:
        _start(session)
        rows, capped = _capped(
            session.execute(
                select(Appointment.starts_at, Appointment.status, Appointment.host_user_id)
                .where(
                    Appointment.tenant_id == scope.workspace,
                    Appointment.starts_at >= chosen.previous_since,
                    Appointment.starts_at < chosen.until,
                )
                .limit(ROW_CAP + 1)
            ).all()
        )
    statuses: Counter[str] = Counter()
    total: Counter[str] = Counter()
    hosts: Counter[uuid.UUID | None] = Counter()
    for starts_at, status, host in rows:
        side = rules.where(starts_at, chosen)
        if side is None:
            continue
        if status != "cancelled":
            total[side] += 1
        if side == "current":
            statuses[status] += 1
            if status != "cancelled":
                hosts[host] += 1
    attended = statuses["completed"] + statuses["no_show"]
    return {
        "period": _period(chosen),
        "capped": capped,
        # Not cancelled: what actually took up the calendar.
        "held": total["current"],
        "held_before": total["previous"],
        "statuses": [{"status": s, "count": statuses[s]} for s in sorted(statuses)],
        # Of the appointments marked completed or no-show; none when none are marked.
        "no_show_rate": round(100 * statuses["no_show"] / attended) if attended else None,
        "hosts": _people(hosts),
    }

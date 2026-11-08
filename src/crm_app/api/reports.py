"""Report routes (decision P10-A, slice 10A).

    GET /v1/workspaces/{tenant_id}/reports/contacts      crm_app.contact:read
    GET /v1/workspaces/{tenant_id}/reports/deals         crm_app.opportunity:read
    GET /v1/workspaces/{tenant_id}/reports/tasks         crm_app.task:read
    GET /v1/workspaces/{tenant_id}/reports/appointments  crm_app.appointment:read
    GET /v1/workspaces/{tenant_id}/reports/funnel        crm_app.contact:read, and
                                                         appointment and deal read
    GET /v1/workspaces/{tenant_id}/reports/contact-trend crm_app.contact:read, and
                                                         deal read (decision P10-F)

and each as CSV at `.../reports/<name>/export.csv` with the same
permission (decision P10-B).

Each report is guarded by the read permission of the records it counts,
so a member sees exactly the figures for records they may read, and a card
whose permission is missing fails alone. `start` and `end` are calendar
days in the workspace's time zone, both included, at most 366 days apart.
The funnel and the trend also follow deals (and the funnel appointments),
so their handlers check those read permissions too and answer 403
`permission_denied` without them; a route policy names one permission.
The path's `tenant_id` is only the request; handlers use
`context.tenant_id` alone. A report that runs out of time answers 503
`report_timeout` instead of holding a connection.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import UTC, date, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, ConfigDict, Field
from saas_os.api.context import RequestContext
from saas_os.api.dependencies import require_permission
from saas_os.core.rbac import can
from saas_os.infra.db import OperationalError, is_statement_timeout

from crm_app import reports
from crm_app.domains import export as csv_export
from crm_app.domains import reports as rules
from crm_app.records import Scope

router = APIRouter(prefix="/v1/workspaces", tags=["reports"])

ReadContacts = Annotated[RequestContext, Depends(require_permission("crm_app.contact", "read"))]
ReadDeals = Annotated[RequestContext, Depends(require_permission("crm_app.opportunity", "read"))]
ReadTasks = Annotated[RequestContext, Depends(require_permission("crm_app.task", "read"))]
ReadAppointments = Annotated[
    RequestContext, Depends(require_permission("crm_app.appointment", "read"))
]


class PeriodParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start: date
    end: date


class TrendParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    weeks: int = Field(
        default=rules.TREND_WEEKS, ge=rules.TREND_MIN_WEEKS, le=rules.TREND_MAX_WEEKS
    )


class PeriodOut(BaseModel):
    start: date
    end: date
    days: int


class Amount(BaseModel):
    currency: str
    amount: str


class Count(BaseModel):
    user_id: uuid.UUID | None
    count: int


class SourceCount(BaseModel):
    source: str
    count: int


class ContactReport(BaseModel):
    period: PeriodOut
    capped: bool
    created: int
    created_before: int
    sources: list[SourceCount]


class OwnerWins(BaseModel):
    user_id: uuid.UUID | None
    won: int
    won_value: list[Amount]


class DealReport(BaseModel):
    period: PeriodOut
    capped: bool
    created: int
    created_before: int
    won: int
    won_before: int
    lost: int
    lost_before: int
    win_rate: int | None
    win_rate_before: int | None
    won_value: list[Amount]
    lost_value: list[Amount]
    owners: list[OwnerWins]


class TaskReport(BaseModel):
    period: PeriodOut
    capped: bool
    created: int
    created_before: int
    completed: int
    completed_before: int
    on_time: int
    late: int
    no_due: int
    overdue_now: int
    completed_by: list[Count]


class StatusCount(BaseModel):
    status: str
    count: int


class AppointmentReport(BaseModel):
    period: PeriodOut
    capped: bool
    held: int
    held_before: int
    statuses: list[StatusCount]
    no_show_rate: int | None
    hosts: list[Count]


class FunnelReport(BaseModel):
    """Of the contacts created in the period (and the one before): how many
    have a live appointment, a linked deal and a won deal by now."""

    period: PeriodOut
    capped: bool
    created: int
    created_before: int
    booked: int
    booked_before: int
    with_deal: int
    with_deal_before: int
    won: int
    won_before: int


class TrendWeek(BaseModel):
    start: date
    created: int
    won: int


class ContactTrend(BaseModel):
    capped: bool
    weeks: list[TrendWeek]


async def _also(context: RequestContext, *resources: str) -> None:
    """Refuse unless the member may also read each of `resources`."""
    for resource in resources:
        if not await run_in_threadpool(
            can,
            actor_id=context.actor_id,
            tenant_id=context.tenant_id,
            action="read",
            resource=resource,
        ):
            raise HTTPException(403, detail={"code": "permission_denied"})


async def _report(
    context: RequestContext, params: PeriodParams, build: Callable[[Scope, rules.Period], Any]
) -> Any:
    scope = Scope(workspace=context.tenant_id, actor=context.actor_id)

    def run() -> Any:
        return build(scope, reports.resolve(scope, params.start, params.end))

    try:
        return await run_in_threadpool(run)
    except rules.InvalidPeriod:
        raise HTTPException(422, detail={"code": "invalid_period"}) from None
    except OperationalError as exc:
        if is_statement_timeout(exc):
            raise HTTPException(503, detail={"code": "report_timeout"}) from None
        raise


Params = Annotated[PeriodParams, Query()]


@router.get("/{tenant_id}/reports/contacts", response_model=ContactReport, name="report_contacts")
async def report_contacts(context: ReadContacts, params: Params) -> Any:
    return await _report(context, params, reports.contacts)


@router.get("/{tenant_id}/reports/deals", response_model=DealReport, name="report_deals")
async def report_deals(context: ReadDeals, params: Params) -> Any:
    return await _report(context, params, reports.deals)


@router.get("/{tenant_id}/reports/tasks", response_model=TaskReport, name="report_tasks")
async def report_tasks(context: ReadTasks, params: Params) -> Any:
    now = datetime.now(UTC)
    return await _report(context, params, lambda scope, chosen: reports.tasks(scope, chosen, now))


@router.get(
    "/{tenant_id}/reports/appointments",
    response_model=AppointmentReport,
    name="report_appointments",
)
async def report_appointments(context: ReadAppointments, params: Params) -> Any:
    return await _report(context, params, reports.appointments)


@router.get("/{tenant_id}/reports/funnel", response_model=FunnelReport, name="report_funnel")
async def report_funnel(context: ReadContacts, params: Params) -> Any:
    await _also(context, "crm_app.opportunity", "crm_app.appointment")
    return await _report(context, params, reports.funnel)


@router.get(
    "/{tenant_id}/reports/contact-trend", response_model=ContactTrend, name="report_contact_trend"
)
async def report_contact_trend(
    context: ReadContacts, params: Annotated[TrendParams, Query()]
) -> Any:
    await _also(context, "crm_app.opportunity")
    scope = Scope(workspace=context.tenant_id, actor=context.actor_id)
    now = datetime.now(UTC)
    try:
        return await run_in_threadpool(reports.trend, scope, now, params.weeks)
    except OperationalError as exc:
        if is_statement_timeout(exc):
            raise HTTPException(503, detail={"code": "report_timeout"}) from None
        raise


# --- CSV (decision P10-B) ----------------------------------------------------------------
# The same figures as the card, as rows; the same permission. Only counts,
# rates, amounts and member ids: never a record's contents.

_CSV: dict[int | str, dict[str, Any]] = {
    200: {"content": {"text/csv": {"schema": {"type": "string", "format": "binary"}}}}
}


async def _csv(context: RequestContext, params: PeriodParams, name: str, build: Any) -> Response:
    report = await _report(context, params, build)
    content = await run_in_threadpool(csv_export.to_csv, rules.CSV_COLUMNS, rules.csv_rows(report))
    file_name = csv_export.filename(f"report-{name}", datetime.now(UTC).date())
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{file_name}"',
            "Cache-Control": "no-store",
        },
    )


@router.get(
    "/{tenant_id}/reports/contacts/export.csv",
    response_class=Response,
    responses=_CSV,
    name="export_report_contacts",
)
async def export_report_contacts(context: ReadContacts, params: Params) -> Response:
    return await _csv(context, params, "contacts", reports.contacts)


@router.get(
    "/{tenant_id}/reports/deals/export.csv",
    response_class=Response,
    responses=_CSV,
    name="export_report_deals",
)
async def export_report_deals(context: ReadDeals, params: Params) -> Response:
    return await _csv(context, params, "deals", reports.deals)


@router.get(
    "/{tenant_id}/reports/tasks/export.csv",
    response_class=Response,
    responses=_CSV,
    name="export_report_tasks",
)
async def export_report_tasks(context: ReadTasks, params: Params) -> Response:
    now = datetime.now(UTC)
    return await _csv(
        context, params, "tasks", lambda scope, chosen: reports.tasks(scope, chosen, now)
    )


@router.get(
    "/{tenant_id}/reports/appointments/export.csv",
    response_class=Response,
    responses=_CSV,
    name="export_report_appointments",
)
async def export_report_appointments(context: ReadAppointments, params: Params) -> Response:
    return await _csv(context, params, "appointments", reports.appointments)


@router.get(
    "/{tenant_id}/reports/funnel/export.csv",
    response_class=Response,
    responses=_CSV,
    name="export_report_funnel",
)
async def export_report_funnel(context: ReadContacts, params: Params) -> Response:
    await _also(context, "crm_app.opportunity", "crm_app.appointment")
    return await _csv(context, params, "funnel", reports.funnel)

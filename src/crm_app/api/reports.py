"""Report routes (decision P10-A, slice 10A).

    GET /v1/workspaces/{tenant_id}/reports/contacts      crm_app.contact:read
    GET /v1/workspaces/{tenant_id}/reports/deals         crm_app.opportunity:read
    GET /v1/workspaces/{tenant_id}/reports/tasks         crm_app.task:read
    GET /v1/workspaces/{tenant_id}/reports/appointments  crm_app.appointment:read

Each report is guarded by the read permission of the records it counts,
so a member sees exactly the figures for records they may read, and a card
whose permission is missing fails alone. `start` and `end` are calendar
days in the workspace's time zone, both included, at most 366 days apart.
The path's `tenant_id` is only the request; handlers use
`context.tenant_id` alone. A report that runs out of time answers 503
`report_timeout` instead of holding a connection.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import UTC, date, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, ConfigDict
from saas_os.api.context import RequestContext
from saas_os.api.dependencies import require_permission
from saas_os.infra.db import OperationalError, is_statement_timeout

from crm_app import reports
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

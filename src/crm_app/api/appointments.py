"""Appointment routes (decisions P5-A and P5-B).

    GET    /v1/workspaces/{tenant_id}/appointments                   crm_app.appointment:read
    GET    /v1/workspaces/{tenant_id}/appointments/upcoming          crm_app.appointment:read
    GET    /v1/workspaces/{tenant_id}/appointments/conflicts         crm_app.appointment:read
    GET    /v1/workspaces/{tenant_id}/appointments/availability      crm_app.appointment:read
    POST   /v1/workspaces/{tenant_id}/appointments                   crm_app.appointment:create
    GET    /v1/workspaces/{tenant_id}/appointments/{appointment_id}  crm_app.appointment:read
    PATCH  /v1/workspaces/{tenant_id}/appointments/{appointment_id}  crm_app.appointment:update
    DELETE /v1/workspaces/{tenant_id}/appointments/{appointment_id}  crm_app.appointment:delete

Each declares exactly one `require_permission` from the existing catalogue
(P5-A 6: every role reads; Owner, Admin and Member book, change and cancel;
Owner and Admin delete). The path's `tenant_id` is only the request;
handlers use `context.tenant_id` alone, and another workspace's
appointment, member or contact is the same 404 or refusal as an unknown one.

Times must carry a time zone. Bodies forbid unknown fields; text is
normalised once and never echoed in an error. `PATCH` needs `If-Match`
(also to change the status or cancel); `POST` accepts an `Idempotency-Key`.
A conflict is 409 `appointment_conflict` with the host's conflicting
appointments unless the body sets `allow_conflict` (P5-A 4).
"""

import uuid
from datetime import datetime
from typing import Annotated, Any, Literal, Self

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)
from saas_os.api.context import RequestContext
from saas_os.api.dependencies import require_permission
from saas_os.core.idempotency import IdempotencyInProgressError, IdempotencyKeyReusedError

from crm_app import appointments
from crm_app.api.inputs import Instant
from crm_app.api.records import IdempotencyKey, IfMatch, _http, _owners, _version
from crm_app.domains import appointments as rules
from crm_app.records import RecordError, Scope

router = APIRouter(prefix="/v1/workspaces", tags=["appointments"])

RESOURCE = "crm_app.appointment"
Read = Annotated[RequestContext, Depends(require_permission(RESOURCE, "read"))]
Create = Annotated[RequestContext, Depends(require_permission(RESOURCE, "create"))]
Change = Annotated[RequestContext, Depends(require_permission(RESOURCE, "update"))]
Remove = Annotated[RequestContext, Depends(require_permission(RESOURCE, "delete"))]

_TITLE_RAW = 4 * rules.TITLE_MAX
_LOCATION_RAW = 4 * rules.LOCATION_MAX
_NOTE_RAW = 4 * rules.NOTE_MAX
Kind = Literal["in_person", "video", "phone"]
Status = Literal["pending", "confirmed", "completed", "no_show", "cancelled"]
# A new appointment is never booked as cancelled.
NewStatus = Literal["pending", "confirmed", "completed", "no_show"]
_MAX_VALUES = 20


class AppointmentIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(max_length=_TITLE_RAW)
    starts_at: Instant
    ends_at: Instant
    kind: Kind = "in_person"
    location: str | None = Field(default=None, max_length=_LOCATION_RAW)
    note: str | None = Field(default=None, max_length=_NOTE_RAW)
    status: NewStatus = "confirmed"
    host_user_id: uuid.UUID
    contact_id: uuid.UUID | None = None
    allow_conflict: Annotated[bool, Field(strict=True)] = False

    @field_validator("title")
    @classmethod
    def _title(cls, value: str) -> str:
        return rules.title(value)

    @field_validator("location")
    @classmethod
    def _location(cls, value: str | None) -> str | None:
        return rules.location(value)

    @field_validator("note")
    @classmethod
    def _note(cls, value: str | None) -> str | None:
        return rules.note(value)


class AppointmentPatch(BaseModel):
    """Only the fields sent change; `null` clears an optional one."""

    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, max_length=_TITLE_RAW)
    starts_at: Instant | None = None
    ends_at: Instant | None = None
    kind: Kind | None = None
    location: str | None = Field(default=None, max_length=_LOCATION_RAW)
    note: str | None = Field(default=None, max_length=_NOTE_RAW)
    status: Status | None = None
    host_user_id: uuid.UUID | None = None
    contact_id: uuid.UUID | None = None
    allow_conflict: Annotated[bool, Field(strict=True)] = False

    @field_validator("title")
    @classmethod
    def _title(cls, value: str | None) -> str:
        if value is None:
            raise ValueError("title cannot be cleared")
        return rules.title(value)

    @field_validator("location")
    @classmethod
    def _location(cls, value: str | None) -> str | None:
        return rules.location(value)

    @field_validator("note")
    @classmethod
    def _note(cls, value: str | None) -> str | None:
        return rules.note(value)

    @field_validator("starts_at", "ends_at", "kind", "status", "host_user_id")
    @classmethod
    def _required(cls, value: object) -> object:
        if value is None:
            raise ValueError("cannot be cleared")
        return value


class ContactRef(BaseModel):
    id: uuid.UUID
    name: str
    archived: bool


class BookingRef(BaseModel):
    """How an appointment booked online was booked (P5-C 10); the page is
    `null` once deleted."""

    page_id: uuid.UUID | None
    page_name: str | None
    cancelled_by_visitor: bool


class AppointmentOut(BaseModel):
    id: uuid.UUID
    title: str
    starts_at: datetime
    ends_at: datetime
    kind: Kind
    location: str | None
    note: str | None
    status: Status
    host_user_id: uuid.UUID
    contact_id: uuid.UUID | None
    contact: ContactRef | None
    booking: BookingRef | None
    cancelled_at: datetime | None
    cancelled_by_user_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime
    created_by_user_id: uuid.UUID | None
    updated_by_user_id: uuid.UUID | None
    version: int


class AppointmentRange(BaseModel):
    items: list[AppointmentOut]
    truncated: bool


class AppointmentList(BaseModel):
    items: list[AppointmentOut]


class Conflict(BaseModel):
    id: uuid.UUID
    title: str
    starts_at: datetime
    ends_at: datetime


class ConflictList(BaseModel):
    conflicts: list[Conflict]
    # Whether the time falls outside the business hours (P5-B 6, 7): a
    # warning, never a refusal; false while no hours are set.
    outside_hours: bool


class OpenInterval(BaseModel):
    starts_at: datetime
    ends_at: datetime


class Availability(BaseModel):
    hours_set: bool
    time_zone: str
    open: list[OpenInterval]


class WindowParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start: Instant
    end: Instant

    @model_validator(mode="after")
    def _range(self) -> Self:
        if not self.start < self.end <= self.start + rules.RANGE_MAX:
            raise ValueError("the range must end after it starts and span at most 42 days")
        return self


class RangeParams(WindowParams):
    host: list[str] = Field(default_factory=list, max_length=_MAX_VALUES)
    contact_id: list[uuid.UUID] = Field(default_factory=list, max_length=_MAX_VALUES)
    include_cancelled: bool = False


class UpcomingParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    host: list[str] = Field(default_factory=list, max_length=_MAX_VALUES)
    contact_id: list[uuid.UUID] = Field(default_factory=list, max_length=_MAX_VALUES)
    limit: int = Field(default=10, ge=1, le=appointments.UPCOMING_MAX)


class ConflictParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    host_user_id: uuid.UUID
    starts_at: Instant
    ends_at: Instant
    exclude_id: uuid.UUID | None = None


def _scope(context: RequestContext) -> Scope:
    return Scope(workspace=context.tenant_id, actor=context.actor_id)


def _etag(response: Response, item: dict[str, Any]) -> dict[str, Any]:
    response.headers["ETag"] = f'"{item["version"]}"'
    return item


def _refused(exc: RecordError) -> HTTPException:
    """`_http`, plus the conflicting appointments of a conflict."""
    if isinstance(exc, appointments.AppointmentConflictError):
        return HTTPException(
            exc.status,
            detail={
                "code": exc.code,
                "conflicts": [
                    {
                        "id": str(found["id"]),
                        "title": found["title"],
                        "starts_at": found["starts_at"].isoformat(),
                        "ends_at": found["ends_at"].isoformat(),
                    }
                    for found in exc.conflicts
                ],
            },
        )
    return _http(exc)


_APPOINTMENTS = "/{tenant_id}/appointments"
_APPOINTMENT = f"{_APPOINTMENTS}/{{appointment_id}}"


@router.get(_APPOINTMENTS, response_model=AppointmentRange, name="list_appointments")
def list_appointments(context: Read, params: Annotated[RangeParams, Query()]) -> Any:
    query = appointments.RangeQuery(
        starts=params.start,
        ends=params.end,
        hosts=_owners(params.host, context),
        contacts=tuple(params.contact_id),
        include_cancelled=params.include_cancelled,
    )
    return appointments.in_range(_scope(context), query)


@router.get(
    f"{_APPOINTMENTS}/upcoming", response_model=AppointmentList, name="upcoming_appointments"
)
def upcoming_appointments(context: Read, params: Annotated[UpcomingParams, Query()]) -> Any:
    items = appointments.upcoming(
        _scope(context),
        hosts=_owners(params.host, context),
        contacts=tuple(params.contact_id),
        limit=params.limit,
    )
    return {"items": items}


@router.get(f"{_APPOINTMENTS}/conflicts", response_model=ConflictList, name="appointment_conflicts")
def appointment_conflicts(context: Read, params: Annotated[ConflictParams, Query()]) -> Any:
    try:
        found = appointments.conflicts(
            _scope(context),
            params.host_user_id,
            params.starts_at,
            params.ends_at,
            exclude=params.exclude_id,
        )
    except RecordError as exc:
        raise _refused(exc) from None
    return found


@router.get(
    f"{_APPOINTMENTS}/availability", response_model=Availability, name="appointment_availability"
)
def appointment_availability(context: Read, params: Annotated[WindowParams, Query()]) -> Any:
    return appointments.availability(_scope(context), params.start, params.end)


@router.post(
    _APPOINTMENTS, status_code=201, response_model=AppointmentOut, name="create_appointment"
)
def create_appointment(
    body: AppointmentIn, context: Create, response: Response, idempotency_key: IdempotencyKey
) -> Any:
    values = body.model_dump(exclude={"allow_conflict"})
    try:
        item, replay = appointments.create(
            _scope(context),
            values,
            allow_conflict=body.allow_conflict,
            idempotency_key=idempotency_key,
        )
    except RecordError as exc:
        raise _refused(exc) from None
    except IdempotencyKeyReusedError:
        raise HTTPException(422, detail={"code": "idempotency_key_reused"}) from None
    except IdempotencyInProgressError:
        raise HTTPException(409, detail={"code": "idempotency_in_progress"}) from None
    if replay:
        response.headers["Idempotent-Replayed"] = "true"
    return _etag(response, item)


@router.get(_APPOINTMENT, response_model=AppointmentOut, name="get_appointment")
def get_appointment(appointment_id: uuid.UUID, context: Read, response: Response) -> Any:
    try:
        return _etag(response, appointments.get(_scope(context), appointment_id))
    except RecordError as exc:
        raise _refused(exc) from None


@router.patch(_APPOINTMENT, response_model=AppointmentOut, name="update_appointment")
def update_appointment(
    appointment_id: uuid.UUID,
    body: AppointmentPatch,
    context: Change,
    response: Response,
    if_match: IfMatch = None,
) -> Any:
    expected = _version(if_match)
    changes = body.model_dump(include=body.model_fields_set - {"allow_conflict"})
    try:
        item = appointments.update(
            _scope(context),
            appointment_id,
            changes,
            expected_version=expected,
            allow_conflict=body.allow_conflict,
        )
    except RecordError as exc:
        raise _refused(exc) from None
    return _etag(response, item)


@router.delete(_APPOINTMENT, status_code=204, name="delete_appointment")
def delete_appointment(appointment_id: uuid.UUID, context: Remove) -> Response:
    try:
        appointments.remove(_scope(context), appointment_id)
    except RecordError as exc:
        raise _refused(exc) from None
    return Response(status_code=204)

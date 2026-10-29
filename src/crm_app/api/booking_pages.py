"""Booking page routes (decision P5-C, slice 5C).

Members, under `/v1/workspaces/{tenant_id}`:

    GET    /booking-pages            crm_app.booking_page:read
    POST   /booking-pages            crm_app.booking_page:manage
    GET    /booking-pages/{page_id}  crm_app.booking_page:read
    PATCH  /booking-pages/{page_id}  crm_app.booking_page:manage
    DELETE /booking-pages/{page_id}  crm_app.booking_page:manage

The path's `tenant_id` is only the request; handlers use `context.tenant_id`
alone. `PATCH` needs `If-Match` (publishing is a change of `status`); `POST`
accepts an `Idempotency-Key`.

Public, for the hosted booking page (SaaS-OS `public_route`, P5-C 5):

    GET    /v1/public/booking-pages/{workspace_id}/{key}
    GET    /v1/public/booking-pages/{workspace_id}/{key}/times
    POST   /v1/public/booking-pages/{workspace_id}/{key}
    POST   /v1/public/bookings/{workspace_id}/view
    POST   /v1/public/bookings/{workspace_id}/cancel

Every one is limited per client address, and the booking also per page,
with the SaaS-OS limiter, which fails closed (503). An unknown workspace or
key, a draft page and a closed or suspended workspace are the same 404, as
is an unknown token. The visitor's token travels in a body, never in an
address. A booking needs an `Idempotency-Key`, is read only after the
limits and at most 8 KiB, and a filled honeypot field is answered like a
time that is no longer free, storing nothing. Errors name fields and rules,
never what the visitor typed.
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime
from typing import Annotated, Any, Literal, Self

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.concurrency import run_in_threadpool
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from saas_os.api.auth.config import get_auth_http_config, resolve_client_address
from saas_os.api.context import RequestContext
from saas_os.api.dependencies import require_permission
from saas_os.api.errors import route_not_found
from saas_os.api.route_policy import public_route
from saas_os.core.idempotency import IdempotencyInProgressError, IdempotencyKeyReusedError

from crm_app import booking_pages
from crm_app.api.forms import _idempotency_key, _limited
from crm_app.api.inputs import Instant, json_body
from crm_app.api.records import IdempotencyKey, IfMatch, _http, _version
from crm_app.domains import appointments as appointment_rules
from crm_app.domains import booking_pages as rules
from crm_app.records import RecordError, Scope

router = APIRouter(prefix="/v1/workspaces", tags=["booking pages"])
public_router = APIRouter(prefix="/v1/public", tags=["public booking pages"])

RESOURCE = "crm_app.booking_page"
Read = Annotated[RequestContext, Depends(require_permission(RESOURCE, "read"))]
Manage = Annotated[RequestContext, Depends(require_permission(RESOURCE, "manage"))]

Kind = Literal["in_person", "video", "phone"]
Status = Literal["draft", "published"]
# Raw lengths are bounded generously; the service applies the real limits
# after trimming, without echoing the text.
_RAW = 4


class BookingPageIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(max_length=_RAW * rules.NAME_MAX)
    description: str | None = Field(default=None, max_length=_RAW * rules.DESCRIPTION_MAX)
    host_user_id: uuid.UUID | None = None
    length_minutes: int = rules.DEFAULT_LENGTH
    step_minutes: int = rules.DEFAULT_STEP
    kind: Kind = "video"
    location: str | None = Field(default=None, max_length=_RAW * appointment_rules.LOCATION_MAX)
    notice_minutes: int = rules.DEFAULT_NOTICE
    horizon_days: int = rules.DEFAULT_HORIZON


class BookingPagePatch(BaseModel):
    """Only the fields sent change; `null` clears the description or the
    location."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, max_length=_RAW * rules.NAME_MAX)
    description: str | None = Field(default=None, max_length=_RAW * rules.DESCRIPTION_MAX)
    host_user_id: uuid.UUID | None = None
    length_minutes: int | None = None
    step_minutes: int | None = None
    kind: Kind | None = None
    location: str | None = Field(default=None, max_length=_RAW * appointment_rules.LOCATION_MAX)
    notice_minutes: int | None = None
    horizon_days: int | None = None
    status: Status | None = None


class BookingPageOut(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    status: Status
    public_key: str
    host_user_id: uuid.UUID
    length_minutes: int
    step_minutes: int
    kind: Kind
    location: str | None
    notice_minutes: int
    horizon_days: int
    booking_count: int
    last_booked_at: datetime | None
    created_at: datetime
    updated_at: datetime
    created_by_user_id: uuid.UUID | None
    updated_by_user_id: uuid.UUID | None
    version: int


class BookingPageList(BaseModel):
    items: list[BookingPageOut]


def _scope(context: RequestContext) -> Scope:
    return Scope(workspace=context.tenant_id, actor=context.actor_id)


def _refusal(exc: RecordError) -> HTTPException:
    if isinstance(exc, booking_pages.VisitorError):
        return HTTPException(422, detail={"code": exc.code, "fields": exc.errors})
    if isinstance(exc, booking_pages.BookingPageRuleError):
        return HTTPException(422, detail={"code": exc.code})
    return _http(exc)


def _etag(response: Response, item: dict[str, Any]) -> dict[str, Any]:
    response.headers["ETag"] = f'"{item["version"]}"'
    return item


_PAGES = "/{tenant_id}/booking-pages"
_PAGE = f"{_PAGES}/{{page_id}}"


@router.get(_PAGES, response_model=BookingPageList, name="list_booking_pages")
def list_pages(context: Read) -> Any:
    return {"items": booking_pages.list_pages(_scope(context))}


@router.post(_PAGES, status_code=201, response_model=BookingPageOut, name="create_booking_page")
def create_page(
    body: BookingPageIn, context: Manage, response: Response, idempotency_key: IdempotencyKey
) -> Any:
    values = body.model_dump(exclude_none=True)
    try:
        item, replay = booking_pages.create(
            _scope(context), values, idempotency_key=idempotency_key
        )
    except RecordError as exc:
        raise _refusal(exc) from None
    except IdempotencyKeyReusedError:
        raise HTTPException(422, detail={"code": "idempotency_key_reused"}) from None
    except IdempotencyInProgressError:
        raise HTTPException(409, detail={"code": "idempotency_in_progress"}) from None
    if replay:
        response.headers["Idempotent-Replayed"] = "true"
    return _etag(response, item)


@router.get(_PAGE, response_model=BookingPageOut, name="get_booking_page")
def get_page(page_id: uuid.UUID, context: Read, response: Response) -> Any:
    try:
        return _etag(response, booking_pages.get(_scope(context), page_id))
    except RecordError as exc:
        raise _refusal(exc) from None


_REQUIRED = (
    "name",
    "host_user_id",
    "length_minutes",
    "step_minutes",
    "kind",
    "notice_minutes",
    "horizon_days",
    "status",
)


@router.patch(_PAGE, response_model=BookingPageOut, name="update_booking_page")
def update_page(
    page_id: uuid.UUID,
    body: BookingPagePatch,
    context: Manage,
    response: Response,
    if_match: IfMatch = None,
) -> Any:
    expected = _version(if_match)
    changes = body.model_dump(include=body.model_fields_set)
    for name in _REQUIRED:
        if name in changes and changes[name] is None:
            raise HTTPException(422, detail={"code": f"{name}_required"})
    try:
        item = booking_pages.update(_scope(context), page_id, changes, expected_version=expected)
    except RecordError as exc:
        raise _refusal(exc) from None
    return _etag(response, item)


@router.delete(_PAGE, status_code=204, name="delete_booking_page")
def delete_page(page_id: uuid.UUID, context: Manage) -> Response:
    try:
        booking_pages.remove(_scope(context), page_id)
    except RecordError as exc:
        raise _refusal(exc) from None
    return Response(status_code=204)


# --- Public ----------------------------------------------------------------------------

_KEY = re.compile(r"[A-Za-z0-9_-]{22}")
_MAX_BODY_BYTES = 8 * 1024
_IDEMPOTENCY_KEY = "Idempotency-Key"
_TOKEN_MAX = 64


class PublicBookingPage(BaseModel):
    name: str
    description: str | None
    length_minutes: int
    kind: Kind
    time_zone: str
    horizon_days: int


class FreeTimesParams(BaseModel):
    """At most 14 days of free times at once (P5-C 4)."""

    model_config = ConfigDict(extra="forbid")

    start: Instant
    end: Instant

    @model_validator(mode="after")
    def _bounded(self) -> Self:
        if self.end <= self.start:
            raise ValueError("end must come after start")
        if self.end - self.start > rules.TIMES_RANGE_MAX:
            raise ValueError("the range must be at most 14 days")
        return self


class FreeTimes(BaseModel):
    times: list[datetime]


class BookingIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    starts_at: Instant
    first_name: str = Field(max_length=_RAW * 200)
    last_name: str | None = Field(default=None, max_length=_RAW * 200)
    email: str = Field(max_length=_RAW * 320)
    phone: str | None = Field(default=None, max_length=_RAW * 32)
    message: str | None = Field(default=None, max_length=_RAW * rules.VISITOR_MESSAGE_MAX)
    # The honeypot (P5-C 5): the hosted page leaves it empty and hidden.
    website: str = Field(default="", max_length=200)


class BookingView(BaseModel):
    page_name: str | None
    starts_at: datetime
    ends_at: datetime
    kind: Kind
    location: str | None
    cancelled: bool
    cancelled_by_visitor: bool
    can_cancel: bool


class Booked(BaseModel):
    """The booking and the visitor's link token, which only the first
    answer carries (`null` on a replay)."""

    booking: BookingView
    token: str | None


class TokenIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    token: str = Field(max_length=_TOKEN_MAX)


async def _address_limit(request: Request) -> None:
    address = resolve_client_address(
        request, trust_proxy_headers=get_auth_http_config().trust_proxy_headers
    )
    await _limited(f"booking:client:{address}")


def _known_key(key: str) -> None:
    """A malformed key is the same 404 as an unknown one, before any lookup."""
    if not _KEY.fullmatch(key):
        raise route_not_found()


async def _body[M: BaseModel](request: Request, model: type[M]) -> M:
    payload = await json_body(request, _MAX_BODY_BYTES)
    try:
        return model.model_validate(payload)
    except ValidationError as exc:
        raise RequestValidationError(exc.errors(include_input=False)) from None


def _body_schema(model: type[BaseModel]) -> dict[str, Any]:
    return {
        "requestBody": {
            "required": True,
            "content": {"application/json": {"schema": model.model_json_schema()}},
        }
    }


_public = Depends(
    public_route(
        "a published booking page, its free times and a booking, and the visitor's own"
        " booking by its token: anyone with the link may book"
    )
)
_PAGE_PUBLIC = "/booking-pages/{workspace_id}/{key}"
_BOOKINGS_PUBLIC = "/bookings/{workspace_id}"


@public_router.get(
    _PAGE_PUBLIC,
    response_model=PublicBookingPage,
    dependencies=[_public],
    name="public_booking_page",
)
async def read_public_page(workspace_id: uuid.UUID, key: str, request: Request) -> Any:
    _known_key(key)
    await _address_limit(request)
    try:
        return await run_in_threadpool(booking_pages.public_page, workspace_id, key)
    except booking_pages.BookingPageNotFoundError:
        raise route_not_found() from None


@public_router.get(
    f"{_PAGE_PUBLIC}/times",
    response_model=FreeTimes,
    dependencies=[_public],
    name="public_booking_times",
)
async def read_free_times(
    workspace_id: uuid.UUID,
    key: str,
    request: Request,
    params: Annotated[FreeTimesParams, Query()],
) -> Any:
    _known_key(key)
    await _address_limit(request)
    try:
        times = await run_in_threadpool(
            booking_pages.free_times, workspace_id, key, params.start, params.end
        )
    except booking_pages.BookingPageNotFoundError:
        raise route_not_found() from None
    return {"times": times}


@public_router.post(
    _PAGE_PUBLIC,
    status_code=201,
    response_model=Booked,
    dependencies=[_public],
    name="book_public_page",
    openapi_extra={
        "parameters": [
            {
                "name": _IDEMPOTENCY_KEY,
                "in": "header",
                "required": True,
                "schema": {"type": "string", "maxLength": 255},
            }
        ],
        **_body_schema(BookingIn),
    },
)
async def book(workspace_id: uuid.UUID, key: str, request: Request) -> Any:
    _known_key(key)
    await _address_limit(request)
    await _limited(f"booking:page:{workspace_id}:{key}")
    idempotency_key = _idempotency_key(request)
    body = await _body(request, BookingIn)
    try:
        if body.website.strip():
            # A bot filled the hidden field: a refusal, nothing stored.
            await run_in_threadpool(booking_pages.public_page, workspace_id, key)
            raise booking_pages.TimeUnavailableError
        booking = booking_pages.BookingRequest(
            starts_at=body.starts_at,
            first_name=body.first_name,
            last_name=body.last_name,
            email=body.email,
            phone=body.phone,
            message=body.message,
        )
        view, token = await run_in_threadpool(
            lambda: booking_pages.book(workspace_id, key, booking, idempotency_key=idempotency_key)
        )
    except booking_pages.BookingPageNotFoundError:
        raise route_not_found() from None
    except RecordError as exc:
        raise _refusal(exc) from None
    except IdempotencyKeyReusedError:
        raise HTTPException(422, detail={"code": "idempotency_key_reused"}) from None
    except IdempotencyInProgressError:
        raise HTTPException(409, detail={"code": "idempotency_in_progress"}) from None
    return {"booking": view, "token": token}


@public_router.post(
    f"{_BOOKINGS_PUBLIC}/view",
    response_model=BookingView,
    dependencies=[_public],
    name="view_public_booking",
    openapi_extra=_body_schema(TokenIn),
)
async def view_booking(workspace_id: uuid.UUID, request: Request) -> Any:
    await _address_limit(request)
    body = await _body(request, TokenIn)
    try:
        return await run_in_threadpool(booking_pages.view, workspace_id, body.token)
    except booking_pages.BookingNotFoundError:
        raise route_not_found() from None


@public_router.post(
    f"{_BOOKINGS_PUBLIC}/cancel",
    response_model=BookingView,
    dependencies=[_public],
    name="cancel_public_booking",
    openapi_extra=_body_schema(TokenIn),
)
async def cancel_booking(workspace_id: uuid.UUID, request: Request) -> Any:
    await _address_limit(request)
    body = await _body(request, TokenIn)
    try:
        return await run_in_threadpool(booking_pages.cancel, workspace_id, body.token)
    except booking_pages.BookingNotFoundError:
        raise route_not_found() from None
    except RecordError as exc:
        raise _refusal(exc) from None

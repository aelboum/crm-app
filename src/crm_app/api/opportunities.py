"""Deal routes (decision P4-B, slice 4B).

    GET    /v1/workspaces/{tenant_id}/opportunities                     opportunity:read
    GET    /v1/workspaces/{tenant_id}/opportunities/summary             opportunity:read
    POST   /v1/workspaces/{tenant_id}/opportunities                     opportunity:create
    GET    /v1/workspaces/{tenant_id}/opportunities/{deal_id}           opportunity:read
    PATCH  /v1/workspaces/{tenant_id}/opportunities/{deal_id}           opportunity:update
    POST   /v1/workspaces/{tenant_id}/opportunities/{deal_id}/outcome   opportunity:update
    DELETE /v1/workspaces/{tenant_id}/opportunities/{deal_id}           opportunity:delete
    GET    /v1/workspaces/{tenant_id}/opportunities/{deal_id}/history   opportunity:read

Each declares exactly one `require_permission` from the existing catalogue
(Q6: every role reads; Owner, Admin and Member create and update, which
covers stages and outcomes; Owner and Admin delete). The path's
`tenant_id` is only the request; handlers use `context.tenant_id` alone,
and another workspace's deal, stage, contact or company is the same 404 or
refusal as an unknown one.

Amounts travel as decimal strings, never JSON numbers (P4-B 2); their
currency's digits are checked by the service, which knows the currency.
Bodies forbid unknown fields; text is normalised once and never echoed in
an error. `PATCH` and `outcome` need `If-Match`; `POST` accepts an
`Idempotency-Key`.
"""

import uuid
from datetime import date, datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator
from saas_os.api.context import RequestContext
from saas_os.api.dependencies import require_permission
from saas_os.core.idempotency import IdempotencyInProgressError, IdempotencyKeyReusedError

from crm_app import opportunities
from crm_app.api.records import (
    DEFAULT_LIMIT,
    MAX_LIMIT,
    IdempotencyKey,
    IfMatch,
    _http,
    _owners,
    _version,
)
from crm_app.domains import opportunities as rules
from crm_app.domains import paging
from crm_app.records import RecordError, Scope

router = APIRouter(prefix="/v1/workspaces", tags=["opportunities"])

RESOURCE = "crm_app.opportunity"
Read = Annotated[RequestContext, Depends(require_permission(RESOURCE, "read"))]
Create = Annotated[RequestContext, Depends(require_permission(RESOURCE, "create"))]
Change = Annotated[RequestContext, Depends(require_permission(RESOURCE, "update"))]
Remove = Annotated[RequestContext, Depends(require_permission(RESOURCE, "delete"))]

# Ceilings before normalisation, so oversized input is refused early.
_TITLE_RAW = 4 * rules.TITLE_MAX
_REASON_RAW = 4 * rules.LOST_REASON_MAX
# An amount as text: digits and one point, checked fully by the service.
Amount = Annotated[str, Field(max_length=24, pattern=r"^[0-9]+(\.[0-9]+)?$")]
Outcome = Literal["open", "won", "lost"]
_NO_NUL = r"^[^\x00]*$"


class DealIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(max_length=_TITLE_RAW)
    amount: Amount | None = None
    stage_id: uuid.UUID | None = None
    owner_user_id: uuid.UUID | None = None
    expected_close_date: date | None = None
    contact_id: uuid.UUID | None = None
    company_id: uuid.UUID | None = None

    @field_validator("title")
    @classmethod
    def _title(cls, value: str) -> str:
        return rules.title(value)


class DealPatch(BaseModel):
    """Only the fields sent change; `null` clears an optional one."""

    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, max_length=_TITLE_RAW)
    amount: Amount | None = None
    stage_id: uuid.UUID | None = None
    owner_user_id: uuid.UUID | None = None
    expected_close_date: date | None = None
    contact_id: uuid.UUID | None = None
    company_id: uuid.UUID | None = None

    @field_validator("title")
    @classmethod
    def _title(cls, value: str | None) -> str:
        if value is None:
            raise ValueError("title cannot be cleared")
        return rules.title(value)

    @field_validator("stage_id")
    @classmethod
    def _stage(cls, value: uuid.UUID | None) -> uuid.UUID:
        if value is None:
            raise ValueError("a deal always has a stage")
        return value


class OutcomeIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    outcome: Outcome
    lost_reason: str | None = Field(default=None, max_length=_REASON_RAW)

    @field_validator("lost_reason")
    @classmethod
    def _reason(cls, value: str | None) -> str | None:
        return None if value is None else rules.lost_reason(value)


class StageRef(BaseModel):
    id: uuid.UUID
    name: str
    probability: int
    position: int


class LinkRef(BaseModel):
    id: uuid.UUID
    name: str
    archived: bool


class DealOut(BaseModel):
    id: uuid.UUID
    title: str
    amount: str | None
    currency: str
    weighted_amount: str | None
    pipeline_id: uuid.UUID
    stage_id: uuid.UUID
    stage: StageRef
    stage_entered_at: datetime
    owner_user_id: uuid.UUID | None
    expected_close_date: date | None
    contact_id: uuid.UUID | None
    contact: LinkRef | None
    company_id: uuid.UUID | None
    company: LinkRef | None
    outcome: Outcome
    lost_reason: str | None
    closed_at: datetime | None
    created_at: datetime
    updated_at: datetime
    created_by_user_id: uuid.UUID | None
    updated_by_user_id: uuid.UUID | None
    version: int


class DealPage(BaseModel):
    items: list[DealOut]
    next_cursor: str | None
    total: int
    total_capped: bool


class StageTotal(BaseModel):
    currency: str
    amount: str
    weighted_amount: str


class StageSummary(BaseModel):
    stage_id: uuid.UUID
    count: int
    totals: list[StageTotal]


class DealSummary(BaseModel):
    stages: list[StageSummary]
    total_capped: bool


class DealEvent(BaseModel):
    id: uuid.UUID
    kind: str
    actor_user_id: uuid.UUID | None
    occurred_at: datetime
    fields: list[str] | None
    stage_from: uuid.UUID | None
    stage_to: uuid.UUID | None
    stage_from_name: str | None
    stage_to_name: str | None
    stage_cause: str | None
    owner_from: uuid.UUID | None
    owner_to: uuid.UUID | None
    outcome_from: str | None
    outcome_to: str | None


class DealHistory(BaseModel):
    items: list[DealEvent]
    next_cursor: str | None


_MAX_VALUES = 20  # per repeatable filter


class DealFilters(BaseModel):
    """The filters both the list and the summary take (P4-B 10), so the
    board and the table agree; unknown parameters are refused."""

    model_config = ConfigDict(extra="forbid")

    q: str | None = Field(default=None, max_length=100, pattern=_NO_NUL)
    outcome: list[Outcome] = Field(default_factory=list, max_length=3)
    stage_id: list[uuid.UUID] = Field(default_factory=list, max_length=_MAX_VALUES)
    owner: list[str] = Field(default_factory=list, max_length=_MAX_VALUES)
    contact_id: list[uuid.UUID] = Field(default_factory=list, max_length=_MAX_VALUES)
    company_id: list[uuid.UUID] = Field(default_factory=list, max_length=_MAX_VALUES)
    idle: bool = False


class DealListParams(DealFilters):
    sort: Literal["updated_at", "created_at", "title", "amount", "expected_close_date"] = (
        "updated_at"
    )
    direction: Literal["asc", "desc"] = "desc"
    limit: int = Field(default=DEFAULT_LIMIT, ge=1, le=MAX_LIMIT)
    cursor: str | None = Field(default=None, max_length=paging.CURSOR_MAX)


class HistoryParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    limit: int = Field(default=DEFAULT_LIMIT, ge=1, le=MAX_LIMIT)
    cursor: str | None = Field(default=None, max_length=paging.CURSOR_MAX)


def _scope(context: RequestContext) -> Scope:
    return Scope(workspace=context.tenant_id, actor=context.actor_id)


def _etag(response: Response, deal: dict[str, Any]) -> dict[str, Any]:
    response.headers["ETag"] = f'"{deal["version"]}"'
    return deal


def _query(params: DealFilters, context: RequestContext) -> opportunities.ListQuery:
    q = params.q.strip() if params.q else ""
    paged = isinstance(params, DealListParams)
    return opportunities.ListQuery(
        order=params.sort if paged else "updated_at",
        direction=params.direction if paged else "desc",
        limit=params.limit if paged else DEFAULT_LIMIT,
        cursor=params.cursor if paged else None,
        q=q or None,
        outcomes=tuple(params.outcome),
        stages=tuple(params.stage_id),
        owners=_owners(params.owner, context),
        contacts=tuple(params.contact_id),
        companies=tuple(params.company_id),
        idle=params.idle,
    )


_DEALS = "/{tenant_id}/opportunities"
_DEAL = f"{_DEALS}/{{deal_id}}"


@router.get(_DEALS, response_model=DealPage, name="list_opportunities")
def list_opportunities(context: Read, params: Annotated[DealListParams, Query()]) -> Any:
    try:
        return opportunities.list_deals(_scope(context), _query(params, context))
    except paging.InvalidCursor:
        raise HTTPException(400, detail={"code": "invalid_cursor"}) from None


@router.get(f"{_DEALS}/summary", response_model=DealSummary, name="summarize_opportunities")
def summarize_opportunities(context: Read, params: Annotated[DealFilters, Query()]) -> Any:
    return opportunities.summary(_scope(context), _query(params, context))


@router.post(_DEALS, status_code=201, response_model=DealOut, name="create_opportunity")
def create_opportunity(
    body: DealIn, context: Create, response: Response, idempotency_key: IdempotencyKey
) -> Any:
    try:
        deal, replay = opportunities.create(
            _scope(context), body.model_dump(), idempotency_key=idempotency_key
        )
    except RecordError as exc:
        raise _http(exc) from None
    except IdempotencyKeyReusedError:
        raise HTTPException(422, detail={"code": "idempotency_key_reused"}) from None
    except IdempotencyInProgressError:
        raise HTTPException(409, detail={"code": "idempotency_in_progress"}) from None
    if replay:
        response.headers["Idempotent-Replayed"] = "true"
    return _etag(response, deal)


@router.get(_DEAL, response_model=DealOut, name="get_opportunity")
def get_opportunity(deal_id: uuid.UUID, context: Read, response: Response) -> Any:
    try:
        return _etag(response, opportunities.get(_scope(context), deal_id))
    except RecordError as exc:
        raise _http(exc) from None


@router.patch(_DEAL, response_model=DealOut, name="update_opportunity")
def update_opportunity(
    deal_id: uuid.UUID,
    body: DealPatch,
    context: Change,
    response: Response,
    if_match: IfMatch = None,
) -> Any:
    expected = _version(if_match)
    changes = body.model_dump(include=body.model_fields_set)
    try:
        deal = opportunities.update(_scope(context), deal_id, changes, expected_version=expected)
    except RecordError as exc:
        raise _http(exc) from None
    return _etag(response, deal)


@router.post(f"{_DEAL}/outcome", response_model=DealOut, name="set_opportunity_outcome")
def set_opportunity_outcome(
    deal_id: uuid.UUID,
    body: OutcomeIn,
    context: Change,
    response: Response,
    if_match: IfMatch = None,
) -> Any:
    expected = _version(if_match)
    try:
        deal = opportunities.set_outcome(
            _scope(context), deal_id, body.outcome, body.lost_reason, expected_version=expected
        )
    except RecordError as exc:
        raise _http(exc) from None
    return _etag(response, deal)


@router.delete(_DEAL, status_code=204, name="delete_opportunity")
def delete_opportunity(deal_id: uuid.UUID, context: Remove) -> Response:
    try:
        opportunities.remove(_scope(context), deal_id)
    except RecordError as exc:
        raise _http(exc) from None
    return Response(status_code=204)


@router.get(f"{_DEAL}/history", response_model=DealHistory, name="opportunity_history")
def opportunity_history(
    deal_id: uuid.UUID, context: Read, params: Annotated[HistoryParams, Query()]
) -> Any:
    try:
        return opportunities.history(
            _scope(context), deal_id, cursor=params.cursor, limit=params.limit
        )
    except RecordError as exc:
        raise _http(exc) from None
    except paging.InvalidCursor:
        raise HTTPException(400, detail={"code": "invalid_cursor"}) from None

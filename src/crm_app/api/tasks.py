"""Task routes (decision P4-C, slice 4C).

    GET    /v1/workspaces/{tenant_id}/tasks             crm_app.task:read
    GET    /v1/workspaces/{tenant_id}/tasks/counts      crm_app.task:read
    POST   /v1/workspaces/{tenant_id}/tasks             crm_app.task:create
    GET    /v1/workspaces/{tenant_id}/tasks/{task_id}   crm_app.task:read
    PATCH  /v1/workspaces/{tenant_id}/tasks/{task_id}   crm_app.task:update
    DELETE /v1/workspaces/{tenant_id}/tasks/{task_id}   crm_app.task:delete

Each declares exactly one `require_permission` from the existing catalogue
(Q6: every role reads; Owner, Admin and Member create, update and delete).
The path's `tenant_id` is only the request; handlers use
`context.tenant_id` alone, and another workspace's task, contact, company or
deal is the same 404 or refusal as an unknown one.

Times must carry a time zone. Bodies forbid unknown fields; titles are
normalised once and never echoed in an error. `PATCH` needs `If-Match`
(also to complete or reopen, with `done`); `POST` accepts an
`Idempotency-Key`.
"""

import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator
from saas_os.api.context import RequestContext
from saas_os.api.dependencies import require_permission
from saas_os.core.idempotency import IdempotencyInProgressError, IdempotencyKeyReusedError

from crm_app import tasks
from crm_app.api.records import (
    DEFAULT_LIMIT,
    MAX_LIMIT,
    IdempotencyKey,
    IfMatch,
    _http,
    _owners,
    _version,
)
from crm_app.domains import paging
from crm_app.domains import tasks as rules
from crm_app.records import RecordError, Scope

router = APIRouter(prefix="/v1/workspaces", tags=["tasks"])

RESOURCE = "crm_app.task"
Read = Annotated[RequestContext, Depends(require_permission(RESOURCE, "read"))]
Create = Annotated[RequestContext, Depends(require_permission(RESOURCE, "create"))]
Change = Annotated[RequestContext, Depends(require_permission(RESOURCE, "update"))]
Remove = Annotated[RequestContext, Depends(require_permission(RESOURCE, "delete"))]

_TITLE_RAW = 4 * rules.TITLE_MAX
Priority = Literal["high", "medium", "low"]
_MAX_VALUES = 20


class TaskIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(max_length=_TITLE_RAW)
    priority: Priority = "medium"
    due_at: AwareDatetime | None = None
    assignee_user_id: uuid.UUID | None = None
    contact_id: uuid.UUID | None = None
    company_id: uuid.UUID | None = None
    opportunity_id: uuid.UUID | None = None

    @field_validator("title")
    @classmethod
    def _title(cls, value: str) -> str:
        return rules.title(value)


class TaskPatch(BaseModel):
    """Only the fields sent change; `null` clears an optional one."""

    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, max_length=_TITLE_RAW)
    priority: Priority | None = None
    due_at: AwareDatetime | None = None
    assignee_user_id: uuid.UUID | None = None
    contact_id: uuid.UUID | None = None
    company_id: uuid.UUID | None = None
    opportunity_id: uuid.UUID | None = None
    done: Annotated[bool, Field(strict=True)] | None = None

    @field_validator("title")
    @classmethod
    def _title(cls, value: str | None) -> str:
        if value is None:
            raise ValueError("title cannot be cleared")
        return rules.title(value)

    @field_validator("priority", "done")
    @classmethod
    def _required(cls, value: object) -> object:
        if value is None:
            raise ValueError("cannot be cleared")
        return value


class LinkRef(BaseModel):
    id: uuid.UUID
    name: str
    archived: bool


class TaskOut(BaseModel):
    id: uuid.UUID
    title: str
    priority: Priority
    due_at: datetime | None
    assignee_user_id: uuid.UUID | None
    contact_id: uuid.UUID | None
    contact: LinkRef | None
    company_id: uuid.UUID | None
    company: LinkRef | None
    opportunity_id: uuid.UUID | None
    opportunity: LinkRef | None
    done: bool
    completed_at: datetime | None
    completed_by_user_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime
    created_by_user_id: uuid.UUID | None
    updated_by_user_id: uuid.UUID | None
    version: int


class TaskPage(BaseModel):
    items: list[TaskOut]
    next_cursor: str | None
    total: int
    total_capped: bool


class TaskCounts(BaseModel):
    open: int
    mine: int
    overdue: int
    done: int


class CountParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    assignee: list[str] = Field(default_factory=list, max_length=_MAX_VALUES)


class TaskListParams(CountParams):
    status: Literal["open", "done", "all"] = "open"
    overdue: bool = False
    due_from: AwareDatetime | None = None
    due_to: AwareDatetime | None = None
    contact_id: list[uuid.UUID] = Field(default_factory=list, max_length=_MAX_VALUES)
    company_id: list[uuid.UUID] = Field(default_factory=list, max_length=_MAX_VALUES)
    opportunity_id: list[uuid.UUID] = Field(default_factory=list, max_length=_MAX_VALUES)
    sort: Literal["due_at", "completed_at", "created_at", "updated_at"] = "due_at"
    direction: Literal["asc", "desc"] = "asc"
    limit: int = Field(default=DEFAULT_LIMIT, ge=1, le=MAX_LIMIT)
    cursor: str | None = Field(default=None, max_length=paging.CURSOR_MAX)


def _scope(context: RequestContext) -> Scope:
    return Scope(workspace=context.tenant_id, actor=context.actor_id)


def _etag(response: Response, item: dict[str, Any]) -> dict[str, Any]:
    response.headers["ETag"] = f'"{item["version"]}"'
    return item


_TASKS = "/{tenant_id}/tasks"
_TASK = f"{_TASKS}/{{task_id}}"


@router.get(_TASKS, response_model=TaskPage, name="list_tasks")
def list_tasks(context: Read, params: Annotated[TaskListParams, Query()]) -> Any:
    query = tasks.ListQuery(
        order=params.sort,
        direction=params.direction,
        limit=params.limit,
        cursor=params.cursor,
        status=params.status,
        assignees=_owners(params.assignee, context),
        overdue=params.overdue,
        due_from=params.due_from,
        due_to=params.due_to,
        contacts=tuple(params.contact_id),
        companies=tuple(params.company_id),
        opportunities=tuple(params.opportunity_id),
    )
    try:
        return tasks.list_tasks(_scope(context), query)
    except paging.InvalidCursor:
        raise HTTPException(400, detail={"code": "invalid_cursor"}) from None


@router.get(f"{_TASKS}/counts", response_model=TaskCounts, name="count_tasks")
def count_tasks(context: Read, params: Annotated[CountParams, Query()]) -> Any:
    return tasks.counts(_scope(context), _owners(params.assignee, context))


@router.post(_TASKS, status_code=201, response_model=TaskOut, name="create_task")
def create_task(
    body: TaskIn, context: Create, response: Response, idempotency_key: IdempotencyKey
) -> Any:
    try:
        item, replay = tasks.create(
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
    return _etag(response, item)


@router.get(_TASK, response_model=TaskOut, name="get_task")
def get_task(task_id: uuid.UUID, context: Read, response: Response) -> Any:
    try:
        return _etag(response, tasks.get(_scope(context), task_id))
    except RecordError as exc:
        raise _http(exc) from None


@router.patch(_TASK, response_model=TaskOut, name="update_task")
def update_task(
    task_id: uuid.UUID,
    body: TaskPatch,
    context: Change,
    response: Response,
    if_match: IfMatch = None,
) -> Any:
    expected = _version(if_match)
    changes = body.model_dump(include=body.model_fields_set)
    try:
        item = tasks.update(_scope(context), task_id, changes, expected_version=expected)
    except RecordError as exc:
        raise _http(exc) from None
    return _etag(response, item)


@router.delete(_TASK, status_code=204, name="delete_task")
def delete_task(task_id: uuid.UUID, context: Remove) -> Response:
    try:
        tasks.remove(_scope(context), task_id)
    except RecordError as exc:
        raise _http(exc) from None
    return Response(status_code=204)

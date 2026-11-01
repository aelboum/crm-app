"""Automation routes (decision P8-A, slice 8A).

    GET    /v1/workspaces/{tenant_id}/automations                crm_app.automation:read
    POST   /v1/workspaces/{tenant_id}/automations                crm_app.automation:manage
    GET    /v1/workspaces/{tenant_id}/automations/{id}           crm_app.automation:read
    PATCH  /v1/workspaces/{tenant_id}/automations/{id}           crm_app.automation:manage
    POST   /v1/workspaces/{tenant_id}/automations/{id}/activate  crm_app.automation:manage
    POST   /v1/workspaces/{tenant_id}/automations/{id}/pause     crm_app.automation:manage
    DELETE /v1/workspaces/{tenant_id}/automations/{id}           crm_app.automation:manage
    GET    /v1/workspaces/{tenant_id}/automations/{id}/runs      crm_app.automation:read

The path's `tenant_id` is only the request; handlers use `context.tenant_id`
alone. Changes need `If-Match`. A refused definition answers 422
`invalid_automation` with the rule it breaks, never the value sent.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field
from saas_os.api.context import RequestContext
from saas_os.api.dependencies import require_permission

from crm_app import automations
from crm_app.api.records import IfMatch, _http, _version
from crm_app.domains import automations as rules
from crm_app.records import RecordError, Scope

router = APIRouter(prefix="/v1/workspaces", tags=["automations"])

RESOURCE = "crm_app.automation"
Read = Annotated[RequestContext, Depends(require_permission(RESOURCE, "read"))]
Manage = Annotated[RequestContext, Depends(require_permission(RESOURCE, "manage"))]

Status = Literal["draft", "active", "paused"]


class AutomationIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(max_length=4 * rules.NAME_MAX)
    definition: dict[str, Any]


class AutomationPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, max_length=4 * rules.NAME_MAX)
    definition: dict[str, Any] | None = None


class AutomationOut(BaseModel):
    id: uuid.UUID
    name: str
    status: Status
    trigger_type: Literal["contact_created"]
    definition: dict[str, Any]
    active_version: int | None
    created_at: datetime
    updated_at: datetime
    version: int


class AutomationList(BaseModel):
    items: list[AutomationOut]


class StepOut(BaseModel):
    branch: Literal["yes", "no"]
    position: int
    action: Literal["add_tag", "assign_owner", "create_task", "wait"]
    outcome: Literal["done", "skipped"]
    detail: str | None
    executed_at: datetime


class RunOut(BaseModel):
    id: uuid.UUID
    contact_id: uuid.UUID | None
    version: int
    branch: Literal["yes", "no"] | None
    status: Literal["running", "waiting", "completed", "failed", "cancelled"]
    resume_at: datetime | None
    attempts: int
    last_error: str | None
    created_at: datetime
    finished_at: datetime | None
    steps: list[StepOut]


class RunList(BaseModel):
    items: list[RunOut]


def _scope(context: RequestContext) -> Scope:
    return Scope(workspace=context.tenant_id, actor=context.actor_id)


def _refusal(exc: RecordError) -> HTTPException:
    if isinstance(exc, automations.AutomationRuleError):
        return HTTPException(422, detail={"code": exc.code, "rule": exc.detail})
    return _http(exc)


def _etag(response: Response, item: dict[str, Any]) -> dict[str, Any]:
    response.headers["ETag"] = f'"{item["version"]}"'
    return item


_LIST = "/{tenant_id}/automations"
_ONE = f"{_LIST}/{{automation_id}}"


@router.get(_LIST, response_model=AutomationList, name="list_automations")
def list_automations(context: Read) -> Any:
    return {"items": automations.list_automations(_scope(context))}


@router.post(_LIST, status_code=201, response_model=AutomationOut, name="create_automation")
def create_automation(body: AutomationIn, context: Manage, response: Response) -> Any:
    try:
        item = automations.create(_scope(context), body.name, body.definition)
    except RecordError as exc:
        raise _refusal(exc) from None
    return _etag(response, item)


@router.get(_ONE, response_model=AutomationOut, name="get_automation")
def get_automation(automation_id: uuid.UUID, context: Read, response: Response) -> Any:
    try:
        return _etag(response, automations.get(_scope(context), automation_id))
    except RecordError as exc:
        raise _refusal(exc) from None


@router.patch(_ONE, response_model=AutomationOut, name="update_automation")
def update_automation(
    automation_id: uuid.UUID,
    body: AutomationPatch,
    context: Manage,
    response: Response,
    if_match: IfMatch = None,
) -> Any:
    expected = _version(if_match)
    changes = body.model_dump(include=body.model_fields_set)
    if any(value is None for value in changes.values()):
        raise HTTPException(422, detail={"code": "value_required"})
    try:
        item = automations.update(
            _scope(context), automation_id, changes, expected_version=expected
        )
    except RecordError as exc:
        raise _refusal(exc) from None
    return _etag(response, item)


@router.post(f"{_ONE}/activate", response_model=AutomationOut, name="activate_automation")
def activate_automation(
    automation_id: uuid.UUID, context: Manage, response: Response, if_match: IfMatch = None
) -> Any:
    expected = _version(if_match)
    try:
        item = automations.activate(_scope(context), automation_id, expected_version=expected)
    except RecordError as exc:
        raise _refusal(exc) from None
    return _etag(response, item)


@router.post(f"{_ONE}/pause", response_model=AutomationOut, name="pause_automation")
def pause_automation(
    automation_id: uuid.UUID, context: Manage, response: Response, if_match: IfMatch = None
) -> Any:
    expected = _version(if_match)
    try:
        item = automations.pause(_scope(context), automation_id, expected_version=expected)
    except RecordError as exc:
        raise _refusal(exc) from None
    return _etag(response, item)


@router.delete(_ONE, status_code=204, name="delete_automation")
def delete_automation(automation_id: uuid.UUID, context: Manage) -> Response:
    try:
        automations.remove(_scope(context), automation_id)
    except RecordError as exc:
        raise _refusal(exc) from None
    return Response(status_code=204)


@router.get(f"{_ONE}/runs", response_model=RunList, name="list_automation_runs")
def list_runs(automation_id: uuid.UUID, context: Read) -> Any:
    try:
        return {"items": automations.runs(_scope(context), automation_id)}
    except RecordError as exc:
        raise _refusal(exc) from None

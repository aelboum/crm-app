"""Saved view routes (decision P3-SV).

Per list (`contacts`, `opportunities`), under /v1/workspaces/{tenant_id}:

    GET    /saved-views/{list}             the member's own views
    POST   /saved-views/{list}             save the current filters
    PATCH  /saved-views/{list}/{id}        rename, or save new filters
    DELETE /saved-views/{list}/{id}        delete

Each needs the list's own read permission (`crm_app.contact:read`,
`crm_app.opportunity:read`) and a member's session. The filters are the
list's own, checked here against an allow-list; nothing else is stored.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field
from saas_os.api.context import RequestContext
from saas_os.api.dependencies import require_permission

from crm_app import saved_views
from crm_app.records import RecordError, Scope

router = APIRouter(prefix="/v1/workspaces", tags=["saved views"])

_MAX = 20
_NO_NUL = r"^[^\x00]*$"


class ContactViewFilters(BaseModel):
    """What the contacts list filters by (its own parameters)."""

    model_config = ConfigDict(extra="forbid")
    q: str | None = Field(default=None, max_length=100, pattern=_NO_NUL)
    lifecycle_stage: list[Literal["lead", "prospect", "customer", "inactive"]] = Field(
        default_factory=list, max_length=_MAX
    )
    owner: list[str] = Field(default_factory=list, max_length=_MAX)
    tag_id: list[uuid.UUID] = Field(default_factory=list, max_length=_MAX)
    archived: Literal["false", "true", "all"] = "false"
    sort: Literal["name", "created_at", "updated_at"] = "name"
    direction: Literal["asc", "desc"] = "asc"


class DealViewFilters(BaseModel):
    """What the deals list filters by (its own parameters)."""

    model_config = ConfigDict(extra="forbid")
    q: str | None = Field(default=None, max_length=100, pattern=_NO_NUL)
    owner: list[str] = Field(default_factory=list, max_length=_MAX)
    outcome: list[Literal["open", "won", "lost"]] = Field(default_factory=list, max_length=3)
    idle: bool = False
    sort: Literal["updated_at", "created_at", "title", "amount", "expected_close_date"] = (
        "updated_at"
    )
    direction: Literal["asc", "desc"] = "desc"


class ContactViewIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(max_length=4 * saved_views.NAME_MAX)
    filters: ContactViewFilters


class ContactViewPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(default=None, max_length=4 * saved_views.NAME_MAX)
    filters: ContactViewFilters | None = None


class DealViewIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(max_length=4 * saved_views.NAME_MAX)
    filters: DealViewFilters


class DealViewPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(default=None, max_length=4 * saved_views.NAME_MAX)
    filters: DealViewFilters | None = None


class ContactViewOut(BaseModel):
    id: uuid.UUID
    name: str
    filters: ContactViewFilters
    created_at: datetime
    updated_at: datetime


class DealViewOut(BaseModel):
    id: uuid.UUID
    name: str
    filters: DealViewFilters
    created_at: datetime
    updated_at: datetime


class ContactViewList(BaseModel):
    items: list[ContactViewOut]


class DealViewList(BaseModel):
    items: list[DealViewOut]


def _scope(context: RequestContext) -> Scope:
    return Scope(workspace=context.tenant_id, actor=context.actor_id)


def _http(exc: RecordError) -> HTTPException:
    return HTTPException(status_code=exc.status, detail={"code": exc.code})


Contacts = Annotated[RequestContext, Depends(require_permission("crm_app.contact", "read"))]
Deals = Annotated[RequestContext, Depends(require_permission("crm_app.opportunity", "read"))]
_C = "/{tenant_id}/saved-views/contacts"
_D = "/{tenant_id}/saved-views/opportunities"


@router.get(_C, response_model=ContactViewList, name="list_contact_views")
def list_contact_views(context: Contacts) -> dict[str, Any]:
    return {"items": saved_views.list_views(_scope(context), "contacts")}


@router.post(_C, status_code=201, response_model=ContactViewOut, name="save_contact_view")
def save_contact_view(body: ContactViewIn, context: Contacts) -> Any:
    try:
        return saved_views.create(
            _scope(context), "contacts", body.name, body.filters.model_dump(mode="json")
        )
    except RecordError as exc:
        raise _http(exc) from None


@router.patch(f"{_C}/{{view_id}}", response_model=ContactViewOut, name="change_contact_view")
def change_contact_view(view_id: uuid.UUID, body: ContactViewPatch, context: Contacts) -> Any:
    filters = None if body.filters is None else body.filters.model_dump(mode="json")
    try:
        return saved_views.update(
            _scope(context), "contacts", view_id, name=body.name, filters=filters
        )
    except RecordError as exc:
        raise _http(exc) from None


@router.delete(f"{_C}/{{view_id}}", status_code=204, name="delete_contact_view")
def delete_contact_view(view_id: uuid.UUID, context: Contacts) -> Response:
    try:
        saved_views.remove(_scope(context), "contacts", view_id)
    except RecordError as exc:
        raise _http(exc) from None
    return Response(status_code=204)


@router.get(_D, response_model=DealViewList, name="list_deal_views")
def list_deal_views(context: Deals) -> dict[str, Any]:
    return {"items": saved_views.list_views(_scope(context), "opportunities")}


@router.post(_D, status_code=201, response_model=DealViewOut, name="save_deal_view")
def save_deal_view(body: DealViewIn, context: Deals) -> Any:
    try:
        return saved_views.create(
            _scope(context), "opportunities", body.name, body.filters.model_dump(mode="json")
        )
    except RecordError as exc:
        raise _http(exc) from None


@router.patch(f"{_D}/{{view_id}}", response_model=DealViewOut, name="change_deal_view")
def change_deal_view(view_id: uuid.UUID, body: DealViewPatch, context: Deals) -> Any:
    filters = None if body.filters is None else body.filters.model_dump(mode="json")
    try:
        return saved_views.update(
            _scope(context), "opportunities", view_id, name=body.name, filters=filters
        )
    except RecordError as exc:
        raise _http(exc) from None


@router.delete(f"{_D}/{{view_id}}", status_code=204, name="delete_deal_view")
def delete_deal_view(view_id: uuid.UUID, context: Deals) -> Response:
    try:
        saved_views.remove(_scope(context), "opportunities", view_id)
    except RecordError as exc:
        raise _http(exc) from None
    return Response(status_code=204)

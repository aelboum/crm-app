"""Workspace settings routes (`PHASE2-PLAN.md` S10, decision P2-F 1).

    GET   /v1/workspaces/{tenant_id}/settings   crm_app.workspace:read (every role)
    PATCH /v1/workspaces/{tenant_id}/settings   crm_app.workspace:update (Owner, Admin)

The path's `tenant_id` is only the request: `require_permission` admits
an active member of an open workspace, and the handlers use
`context.tenant_id` alone. `PATCH` needs `If-Match: <version>` (version 0
before the first save) and accepts only the four fields, each validated
and normalised by `crm_app.domains.settings`; unknown fields are refused,
and refusals never echo the value sent. `business_hours: null` clears the
hours (P5-B 3); `null` for the other fields means "unchanged".
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator
from saas_os.api.context import RequestContext
from saas_os.api.dependencies import require_permission

from crm_app import workspace_settings
from crm_app.api.records import IfMatch, _http, _version
from crm_app.domains import settings as values
from crm_app.records import RecordError, Scope

router = APIRouter(prefix="/v1/workspaces", tags=["workspaces"])

ReadWorkspace = Annotated[RequestContext, Depends(require_permission("crm_app.workspace", "read"))]
UpdateWorkspace = Annotated[
    RequestContext, Depends(require_permission("crm_app.workspace", "update"))
]


class DayHours(BaseModel):
    """One open day (P5-B 2): `HH:MM` wall-clock times in the workspace's zone."""

    model_config = ConfigDict(extra="forbid")

    opens: str = Field(max_length=5)
    closes: str = Field(max_length=5)


# Seven days, Monday first; `null` is a closed day.
Week = Annotated[list[DayHours | None], Field(max_length=values.DAYS)]


class SettingsOut(BaseModel):
    locale: str
    time_zone: str
    currency: str
    # `null` until the hours are first saved (P5-B 3).
    business_hours: Week | None
    # 0 until the first save: the product defaults.
    version: int
    updated_at: datetime | None
    updated_by_user_id: uuid.UUID | None


class SettingsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    locale: str | None = Field(default=None, max_length=64)
    time_zone: str | None = Field(default=None, max_length=64)
    currency: str | None = Field(default=None, max_length=64)
    business_hours: Week | None = None

    @field_validator("locale")
    @classmethod
    def _locale(cls, value: str | None) -> str | None:
        return None if value is None else values.locale(value)

    @field_validator("time_zone")
    @classmethod
    def _time_zone(cls, value: str | None) -> str | None:
        return None if value is None else values.time_zone(value)

    @field_validator("currency")
    @classmethod
    def _currency(cls, value: str | None) -> str | None:
        return None if value is None else values.currency(value)

    @field_validator("business_hours")
    @classmethod
    def _business_hours(cls, value: list[DayHours | None] | None) -> list[DayHours | None] | None:
        if value is None:
            return None
        week = values.business_hours([None if day is None else day.model_dump() for day in value])
        return [None if day is None else DayHours(**day) for day in week or []]


def _scope(context: RequestContext) -> Scope:
    return Scope(workspace=context.tenant_id, actor=context.actor_id)


def _respond(response: Response, settings: dict[str, Any]) -> dict[str, Any]:
    response.headers["ETag"] = f'"{settings["version"]}"'
    return settings


@router.get("/{tenant_id}/settings", response_model=SettingsOut)
def get_settings(tenant_id: uuid.UUID, context: ReadWorkspace, response: Response) -> Any:
    return _respond(response, workspace_settings.get(_scope(context)))


@router.patch("/{tenant_id}/settings", response_model=SettingsOut)
def update_settings(
    tenant_id: uuid.UUID,
    body: SettingsUpdate,
    context: UpdateWorkspace,
    response: Response,
    if_match: IfMatch = None,
) -> Any:
    expected = _version(if_match)
    changes = {
        name: value
        for name, value in body.model_dump(exclude_unset=True).items()
        if value is not None or name == "business_hours"
    }
    try:
        settings = workspace_settings.update(_scope(context), changes, expected_version=expected)
    except RecordError as exc:
        raise _http(exc) from None
    return _respond(response, settings)

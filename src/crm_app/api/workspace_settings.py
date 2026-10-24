"""Workspace settings routes (`PHASE2-PLAN.md` S10, decision P2-F 1).

    GET   /v1/workspaces/{tenant_id}/settings   crm_app.workspace:read (every role)
    PATCH /v1/workspaces/{tenant_id}/settings   crm_app.workspace:update (Owner, Admin)

The path's `tenant_id` is only the request: `require_permission` admits
an active member of an open workspace, and the handlers use
`context.tenant_id` alone. `PATCH` needs `If-Match: <version>` (version 0
before the first save) and accepts only the three fields, each validated
and normalised by `crm_app.domains.settings`; unknown fields are refused,
and refusals never echo the value sent.
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


class SettingsOut(BaseModel):
    locale: str
    time_zone: str
    currency: str
    # 0 until the first save: the product defaults.
    version: int
    updated_at: datetime | None
    updated_by_user_id: uuid.UUID | None


class SettingsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    locale: str | None = Field(default=None, max_length=64)
    time_zone: str | None = Field(default=None, max_length=64)
    currency: str | None = Field(default=None, max_length=64)

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
    changes = {name: value for name, value in body.model_dump().items() if value is not None}
    try:
        settings = workspace_settings.update(_scope(context), changes, expected_version=expected)
    except RecordError as exc:
        raise _http(exc) from None
    return _respond(response, settings)

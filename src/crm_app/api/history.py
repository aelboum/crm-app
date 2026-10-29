"""Record history routes (`PHASE3-PLAN.md` §21.2, decision P3-B).

    GET /v1/workspaces/{tenant_id}/contacts/{record_id}/activity
    GET /v1/workspaces/{tenant_id}/companies/{record_id}/activity
    GET /v1/workspaces/{tenant_id}/activity     (P4-D 4: the Home page's feed)

Each declares `crm_app.activity:read` (every role, Q6). The path's
`tenant_id` is only the request; handlers use `context.tenant_id` alone, and
a record from another workspace is the same 404 as an unknown one.
Newest first, keyset-paged; a cursor is bound to its record.

No `from __future__ import annotations`, for the reason in
`crm_app.api.records`: routes are built per kind.
"""

import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from saas_os.api.context import RequestContext
from saas_os.api.dependencies import require_permission

from crm_app import history
from crm_app.domains import paging
from crm_app.records import COMPANY, CONTACT, Kind, RecordError, Scope

router = APIRouter(prefix="/v1/workspaces")

ACTIVITY = "crm_app.activity"
DEFAULT_LIMIT = 20
MAX_LIMIT = 100

EntryKind = Literal[
    "created",
    "updated",
    "archived",
    "restored",
    "stage_changed",
    "owner_changed",
    "company_linked",
    "company_unlinked",
    "note_added",
    "note_deleted",
]


class ActivityOut(BaseModel):
    """One history entry. Field names only, never values (D5)."""

    id: uuid.UUID
    kind: EntryKind
    occurred_at: datetime
    actor_user_id: uuid.UUID | None
    fields: list[str] | None
    stage_from: str | None
    stage_to: str | None
    owner_from: uuid.UUID | None
    owner_to: uuid.UUID | None
    company_id: uuid.UUID | None
    company_name: str | None
    note_id: uuid.UUID | None
    note_excerpt: str | None
    note_truncated: bool


class RecentActivityOut(ActivityOut):
    """An entry of the workspace's feed, with the record it belongs to; a
    record deleted since has no name."""

    record_type: Literal["contact", "company"]
    record_id: uuid.UUID
    record_name: str | None


class RecentActivity(BaseModel):
    items: list[RecentActivityOut]


class RecentParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    limit: int = Field(default=10, ge=1, le=20)


class ActivityPage(BaseModel):
    items: list[ActivityOut]
    next_cursor: str | None


class HistoryParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    limit: int = Field(default=DEFAULT_LIMIT, ge=1, le=MAX_LIMIT)
    cursor: str | None = Field(default=None, max_length=paging.CURSOR_MAX)


Read = Annotated[RequestContext, Depends(require_permission(ACTIVITY, "read"))]


def _add_route(kind: Kind, path: str) -> None:
    @router.get(
        f"/{{tenant_id}}/{path}/{{record_id}}/activity",
        response_model=ActivityPage,
        name=f"list_{kind.name}_activity",
        tags=[path],
    )
    def list_activity(
        record_id: uuid.UUID,
        context: Read,
        params: Annotated[HistoryParams, Query()],
    ) -> Any:
        scope = Scope(workspace=context.tenant_id, actor=context.actor_id)
        try:
            page = history.list_history(
                kind, scope, record_id, limit=params.limit, cursor=params.cursor
            )
        except paging.InvalidCursor:
            raise HTTPException(400, detail={"code": "invalid_cursor"}) from None
        except RecordError as exc:
            raise HTTPException(exc.status, detail={"code": exc.code}) from None
        return {"items": page.items, "next_cursor": page.next_cursor}


_add_route(CONTACT, "contacts")
_add_route(COMPANY, "companies")


@router.get(
    "/{tenant_id}/activity",
    response_model=RecentActivity,
    name="list_recent_activity",
    tags=["activity"],
)
def list_recent_activity(context: Read, params: Annotated[RecentParams, Query()]) -> Any:
    scope = Scope(workspace=context.tenant_id, actor=context.actor_id)
    return {"items": history.recent(scope, limit=params.limit)}

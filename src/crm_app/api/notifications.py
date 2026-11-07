"""The signed-in member's own notifications (decision N-1).

    GET  /v1/workspaces/{tenant_id}/me/notifications                     crm_app.workspace:read
    POST /v1/workspaces/{tenant_id}/me/notifications/read-all            crm_app.workspace:read
    POST /v1/workspaces/{tenant_id}/me/notifications/{notification_id}/read
                                                                         crm_app.workspace:read

Every role holds `crm_app.workspace:read`, which proves membership. The
recipient is always `context.actor_id`: no route takes a member ID, so a
member reads and marks only their own notifications, and another member's
(or another workspace's) notification is the same 404 as an unknown one.
Marking read is routine and not audited.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict, Field
from saas_os.api.context import RequestContext
from saas_os.api.dependencies import require_permission

from crm_app import notifications
from crm_app.domains import paging

router = APIRouter(prefix="/v1/workspaces", tags=["notifications"])

Member = Annotated[RequestContext, Depends(require_permission("crm_app.workspace", "read"))]

Kind = Literal[
    "task_assigned",
    "conversation_assigned",
    "appointment_assigned",
    "booking_received",
    "booking_cancelled",
    "appointment_upcoming",
]
SubjectType = Literal["task", "conversation", "appointment"]


class NotificationOut(BaseModel):
    id: uuid.UUID
    kind: Kind
    subject_type: SubjectType
    subject_id: uuid.UUID
    # The record's current name; null when it was deleted or the reader may
    # not read that kind of record.
    subject_label: str | None
    # The member who acted; null for a visitor or an automation.
    actor_user_id: uuid.UUID | None
    created_at: datetime
    read_at: datetime | None


class NotificationPage(BaseModel):
    items: list[NotificationOut]
    next_cursor: str | None
    unread: int
    unread_capped: bool


class ListParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    unread: bool = False
    limit: int = Field(default=notifications.DEFAULT_LIMIT, ge=1, le=notifications.MAX_LIMIT)
    cursor: str | None = Field(default=None, max_length=paging.CURSOR_MAX)


class MarkedAll(BaseModel):
    marked: int


_LIST = "/{tenant_id}/me/notifications"


@router.get(_LIST, response_model=NotificationPage, name="list_own_notifications")
def list_own_notifications(context: Member, params: Annotated[ListParams, Query()]) -> Any:
    try:
        page = notifications.list_own(
            context.tenant_id,
            context.actor_id,
            unread_only=params.unread,
            limit=params.limit,
            cursor=params.cursor,
        )
    except paging.InvalidCursor:
        raise HTTPException(400, detail={"code": "invalid_cursor"}) from None
    return {
        "items": page.items,
        "next_cursor": page.next_cursor,
        "unread": page.unread,
        "unread_capped": page.unread_capped,
    }


@router.post(f"{_LIST}/read-all", response_model=MarkedAll, name="mark_all_notifications_read")
def mark_all_notifications_read(context: Member) -> Any:
    return {"marked": notifications.mark_all_read(context.tenant_id, context.actor_id)}


@router.post(f"{_LIST}/{{notification_id}}/read", status_code=204, name="mark_notification_read")
def mark_notification_read(notification_id: uuid.UUID, context: Member) -> Response:
    if not notifications.mark_read(context.tenant_id, context.actor_id, notification_id):
        raise HTTPException(404, detail={"code": "not_found"})
    return Response(status_code=204)

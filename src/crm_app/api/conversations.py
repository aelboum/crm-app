"""Conversation routes (decision P6-C, slice 6C).

    GET    /v1/workspaces/{tenant_id}/conversations                 crm_app.conversation:read
    POST   /v1/workspaces/{tenant_id}/conversations                 crm_app.conversation:reply
    GET    /v1/workspaces/{tenant_id}/conversations/{id}            crm_app.conversation:read
    PATCH  /v1/workspaces/{tenant_id}/conversations/{id}            crm_app.conversation:reply
    POST   /v1/workspaces/{tenant_id}/conversations/{id}/messages   crm_app.conversation:reply
    POST   /v1/workspaces/{tenant_id}/conversations/{id}/read       crm_app.conversation:read

The path's `tenant_id` is only the request; handlers use `context.tenant_id`
alone. `PATCH` needs `If-Match`. Creating a thread and adding a message
accept an `Idempotency-Key`, so a retried reply never queues a second
email. An email reply is queued, not sent: the worker sends it only when
email sending is enabled, and the message shows the email's status.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict, Field
from saas_os.api.context import RequestContext
from saas_os.api.dependencies import require_permission
from saas_os.core.idempotency import IdempotencyInProgressError, IdempotencyKeyReusedError
from starlette.concurrency import run_in_threadpool

from crm_app import conversations, emails
from crm_app.api.records import IdempotencyKey, IfMatch, _http, _version
from crm_app.domains import paging
from crm_app.records import RecordError, Scope

router = APIRouter(prefix="/v1/workspaces", tags=["conversations"])

RESOURCE = "crm_app.conversation"
Read = Annotated[RequestContext, Depends(require_permission(RESOURCE, "read"))]
Reply = Annotated[RequestContext, Depends(require_permission(RESOURCE, "reply"))]

Channel = Literal["email", "other"]
Kind = Literal["inbound", "outbound", "note"]


class ConversationIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contact_id: uuid.UUID
    channel: Channel
    subject: str = Field(max_length=4 * conversations.SUBJECT_MAX)
    kind: Kind
    body: str = Field(max_length=2 * conversations.BODY_MAX)


class MessageIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Kind
    body: str = Field(max_length=2 * conversations.BODY_MAX)


class ConversationPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["open", "closed"] | None = None
    assignee_user_id: uuid.UUID | None = None


class ListParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["open", "closed", "all"] = "open"
    assigned: Literal["all", "mine", "unassigned"] = "all"
    contact_id: uuid.UUID | None = None
    # Searched literally: no wildcard or query syntax (decision P6-C1).
    q: str = Field(default="", max_length=conversations.SEARCH_MAX, pattern=r"^[^\x00]*$")
    limit: int = Field(default=conversations.PAGE_DEFAULT, ge=1, le=conversations.LIST_LIMIT)
    cursor: str | None = Field(default=None, max_length=paging.CURSOR_MAX)


class ConversationSummary(BaseModel):
    id: uuid.UUID
    contact_id: uuid.UUID | None
    contact_name: str | None
    channel: Channel
    subject: str
    status: Literal["open", "closed"]
    assignee_user_id: uuid.UUID | None
    last_message_at: datetime
    unread: bool
    created_at: datetime
    version: int


class ConversationList(BaseModel):
    items: list[ConversationSummary]
    next_cursor: str | None


class MessageOut(BaseModel):
    id: uuid.UUID
    kind: Kind
    body: str
    author_user_id: uuid.UUID | None
    created_at: datetime
    delivery: str | None


class ConversationOut(ConversationSummary):
    contact_email: str | None
    messages: list[MessageOut]


def _scope(context: RequestContext) -> Scope:
    return Scope(workspace=context.tenant_id, actor=context.actor_id)


def _refusal(exc: RecordError) -> HTTPException:
    if isinstance(exc, conversations.ConversationRuleError):
        return HTTPException(422, detail={"code": exc.code, "rule": exc.detail})
    return _http(exc)


def _idempotency(exc: Exception) -> HTTPException:
    if isinstance(exc, IdempotencyKeyReusedError):
        return HTTPException(422, detail={"code": "idempotency_key_reused"})
    return HTTPException(409, detail={"code": "idempotency_in_progress"})


def _etag(response: Response, item: dict[str, Any]) -> dict[str, Any]:
    response.headers["ETag"] = f'"{item["version"]}"'
    return item


_LIST = "/{tenant_id}/conversations"
_ONE = f"{_LIST}/{{conversation_id}}"


@router.get(_LIST, response_model=ConversationList, name="list_conversations")
def list_conversations(context: Read, params: Annotated[ListParams, Query()]) -> Any:
    try:
        return conversations.list_conversations(
            _scope(context), conversations.InboxQuery(**params.model_dump())
        )
    except paging.InvalidCursor:
        raise HTTPException(400, detail={"code": "invalid_cursor"}) from None


@router.post(_LIST, status_code=201, response_model=ConversationOut, name="create_conversation")
async def create_conversation(
    body: ConversationIn, context: Reply, response: Response, idempotency_key: IdempotencyKey
) -> Any:
    try:
        item, email_id, replay = await run_in_threadpool(
            lambda: conversations.create(
                _scope(context),
                contact_id=body.contact_id,
                channel=body.channel,
                subject=body.subject,
                kind=body.kind,
                body=body.body,
                idempotency_key=idempotency_key,
            )
        )
    except RecordError as exc:
        raise _refusal(exc) from None
    except (IdempotencyKeyReusedError, IdempotencyInProgressError) as exc:
        raise _idempotency(exc) from None
    if email_id is not None:
        # Best effort: a lost job is found again by `email_maintenance`.
        await emails.enqueue(context.tenant_id, email_id)
    if replay:
        response.headers["Idempotent-Replayed"] = "true"
    return _etag(response, item)


@router.get(_ONE, response_model=ConversationOut, name="get_conversation")
def get_conversation(conversation_id: uuid.UUID, context: Read, response: Response) -> Any:
    try:
        return _etag(response, conversations.get(_scope(context), conversation_id))
    except RecordError as exc:
        raise _refusal(exc) from None


@router.patch(_ONE, response_model=ConversationOut, name="update_conversation")
def update_conversation(
    conversation_id: uuid.UUID,
    body: ConversationPatch,
    context: Reply,
    response: Response,
    if_match: IfMatch = None,
) -> Any:
    expected = _version(if_match)
    changes = body.model_dump(include=body.model_fields_set)
    if "status" in changes and changes["status"] is None:
        raise HTTPException(422, detail={"code": "value_required"})
    try:
        item = conversations.update(
            _scope(context), conversation_id, changes, expected_version=expected
        )
    except RecordError as exc:
        raise _refusal(exc) from None
    return _etag(response, item)


@router.post(
    f"{_ONE}/messages",
    status_code=201,
    response_model=ConversationOut,
    name="add_conversation_message",
)
async def add_message(
    conversation_id: uuid.UUID,
    body: MessageIn,
    context: Reply,
    response: Response,
    idempotency_key: IdempotencyKey,
) -> Any:
    try:
        item, email_id, replay = await run_in_threadpool(
            lambda: conversations.add_message(
                _scope(context),
                conversation_id,
                kind=body.kind,
                body=body.body,
                idempotency_key=idempotency_key,
            )
        )
    except RecordError as exc:
        raise _refusal(exc) from None
    except (IdempotencyKeyReusedError, IdempotencyInProgressError) as exc:
        raise _idempotency(exc) from None
    if email_id is not None:
        await emails.enqueue(context.tenant_id, email_id)
    if replay:
        response.headers["Idempotent-Replayed"] = "true"
    return _etag(response, item)


@router.post(f"{_ONE}/read", status_code=204, name="mark_conversation_read")
def mark_read(conversation_id: uuid.UUID, context: Read) -> Response:
    try:
        conversations.mark_read(_scope(context), conversation_id)
    except RecordError as exc:
        raise _refusal(exc) from None
    return Response(status_code=204)

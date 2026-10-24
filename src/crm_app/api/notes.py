"""Note routes (`PHASE3-PLAN.md` §21.2, decision P3-B).

    GET  /v1/workspaces/{tenant_id}/contacts/{record_id}/notes    activity:read
    POST /v1/workspaces/{tenant_id}/contacts/{record_id}/notes    activity:create
    (the same two under /companies)
    PATCH  /v1/workspaces/{tenant_id}/notes/{note_id}             activity:create
    DELETE /v1/workspaces/{tenant_id}/notes/{note_id}             activity:create

Each declares exactly one `require_permission`. Editing and deleting are
declared with `activity:create` (Owner, Admin, Member); `crm_app.notes`
then allows the note's author, or a caller holding `activity:update` /
`activity:delete` (Owner, Admin), read here with SaaS-OS `can()` for this
request (D3). The path's `tenant_id` is only the request; handlers use
`context.tenant_id` alone, and an ID from another workspace is the same 404
as an unknown one.

Bodies forbid unknown fields; the text is normalised once
(`crm_app.domains.records.note_body`) and never echoed in an error. `POST`
accepts an `Idempotency-Key`; `PATCH` needs `If-Match: <version>`.

No `from __future__ import annotations`, for the reason in
`crm_app.api.records`: routes are built per kind.
"""

import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator
from saas_os.api.context import RequestContext
from saas_os.api.dependencies import require_permission
from saas_os.core.idempotency import IdempotencyInProgressError, IdempotencyKeyReusedError
from saas_os.core.rbac import can

from crm_app import notes
from crm_app.api.records import IdempotencyKey, IfMatch, _http, _version
from crm_app.domains import paging
from crm_app.domains import records as values
from crm_app.records import COMPANY, CONTACT, Kind, RecordError, Scope

router = APIRouter(prefix="/v1/workspaces")

ACTIVITY = "crm_app.activity"
DEFAULT_LIMIT = 20
MAX_LIMIT = 100
# A ceiling before normalisation (CR LF pairs and surrounding blanks may
# shrink it), so oversized input is refused early.
_RAW_MAX = 2 * values.NOTE_MAX

Read = Annotated[RequestContext, Depends(require_permission(ACTIVITY, "read"))]
Write = Annotated[RequestContext, Depends(require_permission(ACTIVITY, "create"))]


class NoteIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    body: str = Field(max_length=_RAW_MAX)

    @field_validator("body")
    @classmethod
    def _body(cls, value: str) -> str:
        return values.note_body(value)


class NoteOut(BaseModel):
    id: uuid.UUID
    contact_id: uuid.UUID | None
    company_id: uuid.UUID | None
    body: str
    author_user_id: uuid.UUID
    created_at: datetime
    updated_at: datetime
    updated_by_user_id: uuid.UUID
    edited: bool
    version: int
    can_edit: bool
    can_delete: bool


class NotePage(BaseModel):
    items: list[NoteOut]
    next_cursor: str | None
    # The record is archived: no note can be added or edited (D8).
    record_archived: bool


class NoteListParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    limit: int = Field(default=DEFAULT_LIMIT, ge=1, le=MAX_LIMIT)
    cursor: str | None = Field(default=None, max_length=paging.CURSOR_MAX)


def _scope(context: RequestContext) -> Scope:
    return Scope(workspace=context.tenant_id, actor=context.actor_id)


def _rights(context: RequestContext) -> notes.NoteRights | None:
    """The caller's note rights, or `None` when they may not add notes and
    so may change none, not even their own (a Member turned Read-only)."""

    def holds(action: str) -> bool:
        return can(
            actor_id=context.actor_id, tenant_id=context.tenant_id, action=action, resource=ACTIVITY
        )

    if not holds("create"):
        return None
    return notes.NoteRights(edit_any=holds("update"), delete_any=holds("delete"))


def _write_rights(context: RequestContext) -> notes.NoteRights:
    """Rights for a route already gated by `activity:create`."""
    return _rights(context) or notes.NoteRights()


def _etag(response: Response, note: dict[str, Any]) -> None:
    response.headers["ETag"] = f'"{note["version"]}"'


def _add_routes(kind: Kind, path: str) -> None:
    collection = f"/{{tenant_id}}/{path}/{{record_id}}/notes"
    tags: list[Any] = [path]

    @router.get(collection, response_model=NotePage, name=f"list_{kind.name}_notes", tags=tags)
    def list_notes(
        record_id: uuid.UUID,
        context: Read,
        params: Annotated[NoteListParams, Query()],
    ) -> Any:
        try:
            page = notes.list_notes(
                kind,
                _scope(context),
                record_id,
                notes.PageRequest(limit=params.limit, cursor=params.cursor),
                _rights(context),
            )
        except paging.InvalidCursor:
            raise HTTPException(400, detail={"code": "invalid_cursor"}) from None
        except RecordError as exc:
            raise _http(exc) from None
        return {
            "items": page.items,
            "next_cursor": page.next_cursor,
            "record_archived": page.archived,
        }

    @router.post(
        collection,
        status_code=201,
        response_model=NoteOut,
        name=f"create_{kind.name}_note",
        tags=tags,
    )
    def create_note(
        record_id: uuid.UUID,
        body: NoteIn,
        context: Write,
        response: Response,
        idempotency_key: IdempotencyKey,
    ) -> Any:
        scope = _scope(context)
        try:
            note_id, replay = notes.create_note(
                kind, scope, record_id, body.body, idempotency_key=idempotency_key
            )
            note = notes.get_note(scope, note_id, _write_rights(context))
        except RecordError as exc:
            raise _http(exc) from None
        except IdempotencyKeyReusedError:
            raise HTTPException(422, detail={"code": "idempotency_key_reused"}) from None
        except IdempotencyInProgressError:
            raise HTTPException(409, detail={"code": "idempotency_in_progress"}) from None
        if replay:
            response.headers["Idempotent-Replayed"] = "true"
        _etag(response, note)
        return note


_add_routes(CONTACT, "contacts")
_add_routes(COMPANY, "companies")

_NOTE = "/{tenant_id}/notes/{note_id}"


@router.patch(_NOTE, response_model=NoteOut, name="update_note", tags=["notes"])
def update_note(
    note_id: uuid.UUID,
    body: NoteIn,
    context: Write,
    response: Response,
    if_match: IfMatch = None,
) -> Any:
    expected = _version(if_match)
    try:
        note = notes.update_note(
            _scope(context),
            note_id,
            body.body,
            expected_version=expected,
            rights=_write_rights(context),
        )
    except RecordError as exc:
        raise _http(exc) from None
    _etag(response, note)
    return note


@router.delete(_NOTE, status_code=204, name="delete_note", tags=["notes"])
def delete_note(note_id: uuid.UUID, context: Write) -> Response:
    try:
        notes.delete_note(_scope(context), note_id, rights=_write_rights(context))
    except RecordError as exc:
        raise _http(exc) from None
    return Response(status_code=204)

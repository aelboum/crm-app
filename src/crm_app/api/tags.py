"""Tag vocabulary routes (decision P3-C, `PHASE3-PLAN.md` §6.1).

    GET    /v1/workspaces/{tenant_id}/tags             crm_app.contact:read
    POST   /v1/workspaces/{tenant_id}/tags             crm_app.workspace:update
    PATCH  /v1/workspaces/{tenant_id}/tags/{tag_id}    crm_app.workspace:update
    DELETE /v1/workspaces/{tenant_id}/tags/{tag_id}    crm_app.workspace:update

Each declares exactly one `require_permission` from the existing catalogue:
every role reads; the vocabulary is workspace configuration, so changing it
is for Owner and Admin (P3-C 4). The path's `tenant_id` is only the
request; handlers use `context.tenant_id` alone, and a tag ID from another
workspace is the same 404 as an unknown one.

Bodies forbid unknown fields; names are normalised once
(`crm_app.domains.records.tag_name`) and never echoed in an error. `PATCH`
needs `If-Match: <version>`. `POST` takes no `Idempotency-Key`: names are
unique, so a repeated request is refused with `duplicate_tag` and the
existing tag's ID, which a client can use as the result.
"""

import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator
from saas_os.api.context import RequestContext
from saas_os.api.dependencies import require_permission

from crm_app import tags
from crm_app.api.records import IfMatch, _http, _version
from crm_app.domains import records as values
from crm_app.records import RecordError, Scope

router = APIRouter(prefix="/v1/workspaces", tags=["tags"])

# A ceiling before trimming, so oversized input is refused early.
_RAW_MAX = 4 * values.TAG_NAME_MAX

Read = Annotated[RequestContext, Depends(require_permission("crm_app.contact", "read"))]
Configure = Annotated[RequestContext, Depends(require_permission("crm_app.workspace", "update"))]


class TagIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(max_length=_RAW_MAX)

    @field_validator("name")
    @classmethod
    def _name(cls, value: str) -> str:
        return values.tag_name(value)


class TagOut(BaseModel):
    id: uuid.UUID
    name: str
    version: int
    created_at: datetime
    updated_at: datetime


class TagList(BaseModel):
    items: list[TagOut]
    max_tags: int


def _scope(context: RequestContext) -> Scope:
    return Scope(workspace=context.tenant_id, actor=context.actor_id)


def _error(exc: RecordError) -> HTTPException:
    if isinstance(exc, tags.DuplicateTagError):
        detail: dict[str, object] = {"code": exc.code}
        if exc.existing_id is not None:
            detail["existing_id"] = str(exc.existing_id)
        return HTTPException(exc.status, detail=detail)
    return _http(exc)


def _etag(response: Response, tag: dict[str, Any]) -> None:
    response.headers["ETag"] = f'"{tag["version"]}"'


_TAGS = "/{tenant_id}/tags"
_TAG = f"{_TAGS}/{{tag_id}}"


@router.get(_TAGS, response_model=TagList, name="list_tags")
def list_tags(context: Read) -> Any:
    return {"items": tags.list_tags(_scope(context)), "max_tags": tags.MAX_TAGS}


@router.post(_TAGS, status_code=201, response_model=TagOut, name="create_tag")
def create_tag(body: TagIn, context: Configure, response: Response) -> Any:
    try:
        tag = tags.create_tag(_scope(context), body.name)
    except RecordError as exc:
        raise _error(exc) from None
    _etag(response, tag)
    return tag


@router.patch(_TAG, response_model=TagOut, name="rename_tag")
def rename_tag(
    tag_id: uuid.UUID,
    body: TagIn,
    context: Configure,
    response: Response,
    if_match: IfMatch = None,
) -> Any:
    expected = _version(if_match)
    try:
        tag = tags.rename_tag(_scope(context), tag_id, body.name, expected_version=expected)
    except RecordError as exc:
        raise _error(exc) from None
    _etag(response, tag)
    return tag


@router.delete(_TAG, status_code=204, name="delete_tag")
def delete_tag(tag_id: uuid.UUID, context: Configure) -> Response:
    try:
        tags.delete_tag(_scope(context), tag_id)
    except RecordError as exc:
        raise _error(exc) from None
    return Response(status_code=204)

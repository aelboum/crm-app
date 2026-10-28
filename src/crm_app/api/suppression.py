"""Suppression and consent routes (decision P7-B, slice 7B).

Under `/v1/workspaces/{tenant_id}`:

    GET    /suppressions                          crm_app.suppression:read
    POST   /suppressions                          crm_app.suppression:manage
    DELETE /suppressions/{suppression_id}         crm_app.suppression:manage
    GET    /contacts/{record_id}/email-status     crm_app.contact:read
    POST   /contacts/{record_id}/consent          crm_app.contact:update
    POST   /contacts/{record_id}/consent/withdraw crm_app.contact:update

The path's `tenant_id` is only the request; handlers use `context.tenant_id`
alone. Refusals name positions and rules, never an address or wording.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict, Field
from saas_os.api.context import RequestContext
from saas_os.api.dependencies import require_permission

from crm_app import suppression
from crm_app.api.records import DEFAULT_LIMIT, MAX_LIMIT, _http
from crm_app.domains import paging
from crm_app.domains import suppression as rules
from crm_app.domains.records import InvalidValue
from crm_app.records import RecordError, Scope

router = APIRouter(prefix="/v1/workspaces", tags=["consent and suppression"])

RESOURCE = "crm_app.suppression"
Read = Annotated[RequestContext, Depends(require_permission(RESOURCE, "read"))]
Manage = Annotated[RequestContext, Depends(require_permission(RESOURCE, "manage"))]
ReadContacts = Annotated[RequestContext, Depends(require_permission("crm_app.contact", "read"))]
UpdateContacts = Annotated[RequestContext, Depends(require_permission("crm_app.contact", "update"))]

Reason = Literal["unsubscribed", "bounced", "complained", "manual"]
# Raw lengths are bounded generously; the rules apply the real limits after
# trimming, without echoing the text.
_RAW = 4


class SuppressionOut(BaseModel):
    id: uuid.UUID
    email: str
    reason: Reason
    origin: Literal["manual", "consent_withdrawn"]
    note: str | None
    created_by_user_id: uuid.UUID | None
    created_at: datetime


class SuppressionPage(BaseModel):
    items: list[SuppressionOut]
    next_cursor: str | None
    total: int
    total_capped: bool


class ListParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    limit: int = Field(default=DEFAULT_LIMIT, ge=1, le=MAX_LIMIT)
    cursor: str | None = Field(default=None, max_length=paging.CURSOR_MAX)
    search: str | None = Field(default=None, max_length=_RAW * rules.SEARCH_MAX)


class SuppressionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    emails: list[Annotated[str, Field(max_length=_RAW * 320)]] = Field(
        min_length=1, max_length=rules.ADD_MAX
    )
    reason: Reason = "manual"
    note: str | None = Field(default=None, max_length=_RAW * rules.NOTE_MAX)


class Added(BaseModel):
    added: int
    already_suppressed: int


class SuppressionRef(BaseModel):
    id: uuid.UUID
    reason: Reason
    created_at: datetime


class EmailStatus(BaseModel):
    """A contact's email status (P7-B 6, 10)."""

    has_email: bool
    consent: Literal["granted", "withdrawn", "none"]
    suppression: SuppressionRef | None
    marketing_allowed: bool


class ConsentIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    wording: str = Field(max_length=_RAW * 500)


class WithdrawIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    note: str | None = Field(default=None, max_length=_RAW * rules.NOTE_MAX)


def _scope(context: RequestContext) -> Scope:
    return Scope(workspace=context.tenant_id, actor=context.actor_id)


def _invalid(code: str, **detail: Any) -> HTTPException:
    return HTTPException(422, detail={"code": code, **detail})


@router.get("/{tenant_id}/suppressions", response_model=SuppressionPage, name="list_suppressions")
def list_suppressions(context: Read, params: Annotated[ListParams, Query()]) -> Any:
    try:
        term = rules.search(params.search)
    except InvalidValue:
        raise _invalid("invalid_search") from None
    query = suppression.ListQuery(limit=params.limit, cursor=params.cursor, search=term)
    try:
        return suppression.list_suppressions(_scope(context), query)
    except paging.InvalidCursor:
        raise HTTPException(400, detail={"code": "invalid_cursor"}) from None


@router.post(
    "/{tenant_id}/suppressions", status_code=201, response_model=Added, name="add_suppressions"
)
def add_suppressions(body: SuppressionIn, context: Manage) -> Any:
    try:
        emails = rules.addresses(body.emails)
    except rules.InvalidAddresses as exc:
        raise _invalid("invalid_emails", positions=exc.positions[:50]) from None
    try:
        note = rules.note(body.note)
    except InvalidValue:
        raise _invalid("invalid_note") from None
    try:
        return suppression.add(_scope(context), emails, reason=body.reason, note=note)
    except RecordError as exc:
        raise _http(exc) from None


@router.delete(
    "/{tenant_id}/suppressions/{suppression_id}", status_code=204, name="remove_suppression"
)
def remove_suppression(suppression_id: uuid.UUID, context: Manage) -> Response:
    try:
        suppression.remove(_scope(context), suppression_id)
    except RecordError as exc:
        raise _http(exc) from None
    return Response(status_code=204)


_CONTACT = "/{tenant_id}/contacts/{record_id}"


@router.get(f"{_CONTACT}/email-status", response_model=EmailStatus, name="contact_email_status")
def contact_email_status(record_id: uuid.UUID, context: ReadContacts) -> Any:
    try:
        return suppression.contact_email_status(_scope(context), record_id)
    except RecordError as exc:
        raise _http(exc) from None


@router.post(f"{_CONTACT}/consent", response_model=EmailStatus, name="record_contact_consent")
def record_consent(record_id: uuid.UUID, body: ConsentIn, context: UpdateContacts) -> Any:
    try:
        wording = rules.wording(body.wording)
    except InvalidValue:
        raise _invalid("invalid_wording") from None
    try:
        return suppression.record_consent(_scope(context), record_id, wording)
    except RecordError as exc:
        raise _http(exc) from None


@router.post(
    f"{_CONTACT}/consent/withdraw", response_model=EmailStatus, name="withdraw_contact_consent"
)
def withdraw_consent(record_id: uuid.UUID, body: WithdrawIn, context: UpdateContacts) -> Any:
    try:
        note = rules.note(body.note)
    except InvalidValue:
        raise _invalid("invalid_note") from None
    try:
        return suppression.withdraw_consent(_scope(context), record_id, note)
    except RecordError as exc:
        raise _http(exc) from None

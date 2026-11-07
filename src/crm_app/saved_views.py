"""Saved views of the contacts and deals lists (decision P3-SV).

A saved view is one member's named set of list filters. Only that member
lists, renames, changes or deletes it: every query names the member from
the validated request, so another member's view is the same as an unknown
one. Filters are checked against the list's allow-list by the API before
they reach this module; a view never holds anything else. At most
`MAX_PER_LIST` per member and list.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from saas_os.infra.db import IntegrityError, delete, select, tenant_session_scope

from crm_app.models import SavedView
from crm_app.records import RecordError, RecordNotFoundError, Scope

KINDS = ("contacts", "opportunities")
MAX_PER_LIST = 20
NAME_MAX = 60

Item = dict[str, Any]


class SavedViewError(RecordError):
    status, code = 422, "invalid_saved_view"


class DuplicateSavedViewError(RecordError):
    status, code = 409, "duplicate_saved_view"


class SavedViewLimitError(RecordError):
    status, code = 409, "saved_view_limit"


def _name(value: str) -> str:
    text = " ".join(value.split())
    if not 1 <= len(text) <= NAME_MAX:
        raise SavedViewError
    return text


def _item(row: SavedView) -> Item:
    return {
        "id": row.id,
        "name": row.name,
        "filters": row.filters,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def list_views(scope: Scope, kind: str) -> list[Item]:
    with tenant_session_scope(scope.workspace) as session:
        rows = session.execute(
            select(SavedView)
            .where(
                SavedView.tenant_id == scope.workspace,
                SavedView.user_id == scope.actor,
                SavedView.kind == kind,
            )
            .order_by(SavedView.name, SavedView.id)
        ).scalars()
        return [_item(row) for row in rows]


def create(scope: Scope, kind: str, name: str, filters: Mapping[str, Any]) -> Item:
    clean = _name(name)
    now = datetime.now(UTC)
    try:
        with tenant_session_scope(scope.workspace) as session:
            count = len(
                session.execute(
                    select(SavedView.id).where(
                        SavedView.tenant_id == scope.workspace,
                        SavedView.user_id == scope.actor,
                        SavedView.kind == kind,
                    )
                ).all()
            )
            if count >= MAX_PER_LIST:
                raise SavedViewLimitError
            row = SavedView(
                tenant_id=scope.workspace,
                id=uuid.uuid4(),
                user_id=scope.actor,
                kind=kind,
                name=clean,
                filters=dict(filters),
                created_at=now,
                updated_at=now,
            )
            session.add(row)
            session.flush()
            return _item(row)
    except IntegrityError:
        raise DuplicateSavedViewError from None


def update(
    scope: Scope,
    kind: str,
    view_id: uuid.UUID,
    *,
    name: str | None = None,
    filters: Mapping[str, Any] | None = None,
) -> Item:
    clean = None if name is None else _name(name)
    try:
        with tenant_session_scope(scope.workspace) as session:
            row = session.execute(
                select(SavedView)
                .where(
                    SavedView.tenant_id == scope.workspace,
                    SavedView.user_id == scope.actor,
                    SavedView.kind == kind,
                    SavedView.id == view_id,
                )
                .with_for_update()
            ).scalar_one_or_none()
            if row is None:
                raise RecordNotFoundError
            if clean is not None:
                row.name = clean
            if filters is not None:
                row.filters = dict(filters)
            row.updated_at = datetime.now(UTC)
            session.flush()
            return _item(row)
    except IntegrityError:
        raise DuplicateSavedViewError from None


def remove(scope: Scope, kind: str, view_id: uuid.UUID) -> None:
    with tenant_session_scope(scope.workspace) as session:
        gone = session.execute(
            delete(SavedView).where(
                SavedView.tenant_id == scope.workspace,
                SavedView.user_id == scope.actor,
                SavedView.kind == kind,
                SavedView.id == view_id,
            )
        )
        if not getattr(gone, "rowcount", 0):
            raise RecordNotFoundError

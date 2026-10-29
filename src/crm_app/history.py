"""A record's user-visible history (`PHASE3-PLAN.md` §21.2, decision P3-B).

Entries are written by `crm_app.records` (and `crm_app.notes`) in the same
transaction as the change they describe; this module only reads them. An
entry holds field names, the fixed stages, member user IDs and company or
note references; never field values (D5). A `note_added` entry shows the
start of its note, read from `note` at request time, so a deleted note's
text is never shown (its entry is gone with it, D4).

Reads run in `tenant_session_scope(workspace)` with an explicit workspace
predicate. The record is loaded first, so an unknown record, or one from
another workspace, is the same 404 as for the record itself.

SaaS-OS resolves configuration at import time; only code that runs after
validation imports this module.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from saas_os.infra.db import Session, select, tenant_session_scope

from crm_app.domains import paging
from crm_app.models import Activity, Company, Contact, Note
from crm_app.records import CONTACT, Kind, Scope, load_record

ORDER, DIRECTION = "occurred_at", "desc"
EXCERPT = 280  # characters of a note shown in its `note_added` entry


@dataclass(frozen=True)
class HistoryPage:
    items: list[dict[str, Any]]
    next_cursor: str | None


def _filters(kind: Kind, record_id: uuid.UUID) -> str:
    """Binds a cursor to the record it was issued for."""
    return paging.filter_hash({"record": f"{kind.name}:{record_id}"})


def list_history(
    kind: Kind, scope: Scope, record_id: uuid.UUID, *, limit: int, cursor: str | None
) -> HistoryPage:
    """Newest first, `limit` entries, in a total order (`id` breaks ties).
    Raises `paging.InvalidCursor` for a cursor issued for another record."""
    filters = _filters(kind, record_id)
    after = paging.decode(cursor, "activity", ORDER, DIRECTION, filters) if cursor else None
    parent = Activity.contact_id if kind is CONTACT else Activity.company_id
    with tenant_session_scope(scope.workspace) as session:
        load_record(session, kind, scope, record_id)
        statement = (
            select(Activity, Note.body)
            .outerjoin(Note, (Note.tenant_id == Activity.tenant_id) & (Note.id == Activity.note_id))
            .where(Activity.tenant_id == scope.workspace, parent == record_id)
        )
        if after is not None:
            occurred, last_id = after
            statement = statement.where(
                (Activity.occurred_at < occurred)
                | ((Activity.occurred_at == occurred) & (Activity.id < last_id))
            )
        statement = statement.order_by(Activity.occurred_at.desc(), Activity.id.desc()).limit(
            limit + 1
        )
        rows = list(session.execute(statement).tuples())
        more = len(rows) > limit
        rows = rows[:limit]
        names = _company_names(session, scope, {entry.company_ref_id for entry, _ in rows})
        items = [_item(entry, body, names) for entry, body in rows]
        last_key = (rows[-1][0].occurred_at, rows[-1][0].id) if rows else None
    next_cursor = None
    if more and last_key is not None:
        next_cursor = paging.encode("activity", ORDER, DIRECTION, filters, last_key)
    return HistoryPage(items=items, next_cursor=next_cursor)


def recent(scope: Scope, *, limit: int) -> list[dict[str, Any]]:
    """The workspace's newest `limit` entries across contacts and companies
    (decision P4-D 4), each with its record's kind, ID and current name. No
    note text: the Home page names what happened, the record shows the rest."""
    with tenant_session_scope(scope.workspace) as session:
        rows = list(
            session.execute(
                select(Activity)
                .where(Activity.tenant_id == scope.workspace)
                .order_by(Activity.occurred_at.desc(), Activity.id.desc())
                .limit(limit)
            ).scalars()
        )
        contacts = {entry.contact_id for entry in rows if entry.contact_id is not None}
        people: dict[uuid.UUID, str] = {}
        if contacts:
            query = select(Contact.id, Contact.first_name, Contact.last_name).where(
                Contact.tenant_id == scope.workspace, Contact.id.in_(contacts)
            )
            people = {
                row_id: " ".join(part for part in (first, last) if part)
                for row_id, first, last in session.execute(query).tuples()
            }
        companies = _company_names(
            session,
            scope,
            {entry.company_id for entry in rows} | {entry.company_ref_id for entry in rows},
        )
        return [
            {
                **_item(entry, None, companies),
                "record_type": "contact" if entry.contact_id is not None else "company",
                "record_id": entry.contact_id or entry.company_id,
                "record_name": (
                    people.get(entry.contact_id)
                    if entry.contact_id is not None
                    else companies.get(entry.company_id)
                    if entry.company_id is not None
                    else None
                ),
            }
            for entry in rows
        ]


def _company_names(
    session: Session, scope: Scope, ids: set[uuid.UUID | None]
) -> dict[uuid.UUID, str]:
    """Current names of the companies linked or unlinked; a deleted company
    has none."""
    wanted = {i for i in ids if i is not None}
    if not wanted:
        return {}
    query = select(Company.id, Company.name).where(
        Company.tenant_id == scope.workspace, Company.id.in_(wanted)
    )
    # `.all()`: a result object has `keys()`, so `dict()` would read it as a
    # mapping instead of as pairs.
    return dict(session.execute(query).tuples().all())


def _item(entry: Activity, body: str | None, names: dict[uuid.UUID, str]) -> dict[str, Any]:
    return {
        "id": entry.id,
        "kind": entry.kind,
        "occurred_at": entry.occurred_at,
        "actor_user_id": entry.actor_user_id,
        "fields": entry.fields,
        "stage_from": entry.stage_from,
        "stage_to": entry.stage_to,
        "owner_from": entry.owner_from,
        "owner_to": entry.owner_to,
        "company_id": entry.company_ref_id,
        "company_name": names.get(entry.company_ref_id) if entry.company_ref_id else None,
        "note_id": entry.note_id,
        "note_excerpt": None if body is None else body[:EXCERPT],
        "note_truncated": body is not None and len(body) > EXCERPT,
    }

"""Deals: the service layer (decision P4-B, slice 4B).

Every function takes a `Scope` from SaaS-OS's validated request context.
Every query runs in `tenant_session_scope(workspace)` and also names the
workspace, so Row-Level Security and the predicate both confine it.

Every write takes `lock_open_tenant`, then a share lock on the pipeline's
row (P4-B 9), then, for an existing deal, its row lock. Pipeline changes
take the pipeline's row lock (`crm_app.pipelines`), so a stage removal and
a deal write never interleave, and the lock order is always the same. The
write, its history entries (`opportunity_event`, P4-B 7) and its audit
entry commit or roll back together. History and audit carry IDs, field
names, stage names and outcomes only; never amounts, titles or the lost
reason.

A contact or company is linked only when it is an active record of the
same workspace; an owner only when an active member (P4-B 4). A stage is
one of the workspace's pipeline. Amounts are exact decimals in the
workspace's currency at creation (P4-B 2).

SaaS-OS resolves configuration at import time; only code that runs after
validation imports this module.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from saas_os.core.audit_log import record_in_transaction
from saas_os.core.authority import UserCaller
from saas_os.core.idempotency import run_idempotent
from saas_os.core.tenancy import TenantClosedError, TenantNotFoundError, lock_open_tenant
from saas_os.infra.db import (
    IntegrityError,
    OperationalError,
    Session,
    is_transaction_conflict,
    select,
    tenant_session_scope,
)

from crm_app import pipelines
from crm_app.domains import opportunities as rules
from crm_app.domains import paging
from crm_app.domains.records import InvalidValue
from crm_app.domains.settings import DEFAULT_CURRENCY
from crm_app.models import (
    Company,
    Contact,
    Opportunity,
    OpportunityEvent,
    Pipeline,
    PipelineStage,
    WorkspaceSettings,
)
from crm_app.records import (
    ORDER_COLLATION,
    TOTAL_CAP,
    ConstraintViolationError,
    InvalidReferenceError,
    RecordError,
    RecordNotFoundError,
    Scope,
    StaleVersionError,
    TransactionConflictError,
    _after,
    _OrderKey,
    check_owner,
)

RESOURCE = "crm_app.opportunity"
# The fields a create or an update may set (outcomes have their own call).
FIELDS = (
    "title",
    "amount",
    "stage_id",
    "owner_user_id",
    "expected_close_date",
    "contact_id",
    "company_id",
)
_PLAIN = ("title", "amount", "expected_close_date", "contact_id", "company_id")
_CONSTRAINT_REFERENCES = {
    "opportunity_stage_fkey": "stage_not_found",
    "opportunity_contact_fkey": "contact_not_found",
    "opportunity_company_fkey": "company_not_found",
}
_EVENT_FIELDS = (
    "id",
    "kind",
    "actor_user_id",
    "occurred_at",
    "fields",
    "stage_from",
    "stage_to",
    "stage_from_name",
    "stage_to_name",
    "stage_cause",
    "owner_from",
    "owner_to",
    "outcome_from",
    "outcome_to",
)


class OpportunityNotFoundError(RecordError):
    status, code = 404, "opportunity_not_found"


class InvalidAmountError(RecordError):
    status, code = 422, "invalid_amount"


class DealClosedError(RecordError):
    """A won or lost deal's stage cannot change; reopen it first."""

    status, code = 409, "deal_closed"


class InvalidTransitionError(RecordError):
    status, code = 409, "invalid_outcome_transition"


class LostReasonError(RecordError):
    """Lost needs a reason."""

    status, code = 422, "lost_reason_required"


class LostReasonNotAllowedError(RecordError):
    """Open and won take no reason."""

    status, code = 422, "lost_reason_not_allowed"


Deal = dict[str, Any]


def _now() -> datetime:
    return datetime.now(UTC)


# --- Transactions, locks and references ------------------------------------------------


def _refusal(exc: IntegrityError) -> Exception:
    """A reference that vanished between the check and the write is the same
    refusal the check gives; anything else is `ConstraintViolationError`,
    never the driver error (whose detail would quote the row)."""
    constraint = getattr(getattr(exc.orig, "diag", None), "constraint_name", None)
    code = _CONSTRAINT_REFERENCES.get(constraint or "")
    return InvalidReferenceError(code) if code else ConstraintViolationError()


def _transaction[T](scope: Scope, fn: Callable[[Session], T]) -> T:
    """Run `fn` in one locked, workspace-scoped transaction."""
    try:
        with tenant_session_scope(scope.workspace) as session:
            lock_open_tenant(session, scope.workspace)
            return fn(session)
    except (TenantClosedError, TenantNotFoundError):
        raise RecordNotFoundError from None
    except IntegrityError as exc:
        raise _refusal(exc) from None
    except OperationalError as exc:
        if is_transaction_conflict(exc):
            raise TransactionConflictError from None
        raise


def _first_pipeline(session: Session, scope: Scope, *, share: bool) -> Pipeline | None:
    query = (
        select(Pipeline)
        .where(Pipeline.tenant_id == scope.workspace)
        .order_by(Pipeline.created_at, Pipeline.id)
        .limit(1)
    )
    return session.execute(
        query.with_for_update(read=True) if share else query
    ).scalar_one_or_none()


def _pipeline(session: Session, scope: Scope) -> Pipeline:
    """The workspace's pipeline, share-locked against concurrent pipeline
    changes (P4-B 9)."""
    pipeline = _first_pipeline(session, scope, share=True)
    if pipeline is None:
        raise InvalidReferenceError("stage_not_found")
    return pipeline


def _stages(session: Session, scope: Scope, pipeline_id: uuid.UUID) -> list[PipelineStage]:
    return list(
        session.execute(
            select(PipelineStage)
            .where(
                PipelineStage.tenant_id == scope.workspace,
                PipelineStage.pipeline_id == pipeline_id,
            )
            .order_by(PipelineStage.position, PipelineStage.id)
        ).scalars()
    )


def _stage(stages: Sequence[PipelineStage], stage_id: uuid.UUID) -> PipelineStage:
    found = next((stage for stage in stages if stage.id == stage_id), None)
    if found is None:
        raise InvalidReferenceError("stage_not_found")
    return found


def _check_link(
    session: Session, scope: Scope, model: type[Contact] | type[Company], record_id: Any
) -> None:
    """A deal links only to an active record of its own workspace."""
    if record_id is None:
        return
    found = session.execute(
        select(model.id).where(
            model.tenant_id == scope.workspace,
            model.id == record_id,
            model.archived_at.is_(None),
        )
    ).scalar_one_or_none()
    if found is None:
        raise InvalidReferenceError(f"{model.__tablename__}_not_found")


def _currency(session: Session, scope: Scope) -> str:
    stored = session.execute(
        select(WorkspaceSettings.currency).where(WorkspaceSettings.tenant_id == scope.workspace)
    ).scalar_one_or_none()
    return stored or DEFAULT_CURRENCY


def _amount(raw: str | None, currency: str) -> Decimal | None:
    if raw is None:
        return None
    try:
        return rules.amount(raw, currency)
    except InvalidValue:
        raise InvalidAmountError from None


def _load(session: Session, scope: Scope, deal_id: uuid.UUID, *, lock: bool) -> Opportunity:
    query = select(Opportunity).where(
        Opportunity.tenant_id == scope.workspace, Opportunity.id == deal_id
    )
    row = session.execute(query.with_for_update() if lock else query).scalar_one_or_none()
    if row is None:
        raise OpportunityNotFoundError
    return row


def _event(scope: Scope, deal_id: uuid.UUID, kind: str, **payload: Any) -> OpportunityEvent:
    return OpportunityEvent(
        id=uuid.uuid4(),
        tenant_id=scope.workspace,
        opportunity_id=deal_id,
        kind=kind,
        actor_user_id=scope.actor,
        occurred_at=_now(),
        **payload,
    )


def _audit(session: Session, scope: Scope, verb: str, deal_id: uuid.UUID, **metadata: Any) -> None:
    record_in_transaction(
        session,
        caller=UserCaller(scope.actor),
        tenant_id=scope.workspace,
        action=f"{RESOURCE}.{verb}",
        resource_type=RESOURCE,
        resource_id=str(deal_id),
        metadata=metadata,
    )


def _touch(row: Opportunity, scope: Scope, now: datetime) -> None:
    row.version += 1
    row.updated_at = now
    row.updated_by_user_id = scope.actor


def move_to_stage(
    scope: Scope, row: Opportunity, before: PipelineStage, to: PipelineStage, cause: str
) -> OpportunityEvent:
    """Move `row` from stage `before` to `to` and return the history entry
    for it. Used by updates and by a stage removal (`crm_app.pipelines`),
    each in its own locked transaction."""
    now = _now()
    row.stage_id = to.id
    row.stage_entered_at = now
    _touch(row, scope, now)
    return _event(
        scope,
        row.id,
        "stage_changed",
        stage_from=before.id,
        stage_from_name=before.name,
        stage_to=to.id,
        stage_to_name=to.name,
        stage_cause=cause,
    )


# --- Reads ---------------------------------------------------------------------------


def _to_unit(value: Decimal, currency: str) -> Decimal:
    """`value` to the currency's minor unit, half up: for weighted figures,
    which are shown, never stored."""
    unit = Decimal(1).scaleb(-rules.minor_digits(currency))
    return value.quantize(unit, rounding=ROUND_HALF_UP)


def _weighted(row: Opportunity, probability: int) -> str | None:
    """The open deal's amount times its stage's probability."""
    if row.amount is None or row.outcome != rules.OPEN:
        return None
    value = _to_unit(row.amount * probability / 100, row.currency)
    return rules.amount_text(value, row.currency)


def _links(
    session: Session, scope: Scope, rows: Sequence[Opportunity]
) -> tuple[dict[uuid.UUID, dict[str, Any]], dict[uuid.UUID, dict[str, Any]]]:
    """The linked contacts' and companies' names, for a page at once."""
    contacts: dict[uuid.UUID, dict[str, Any]] = {}
    contact_ids = {row.contact_id for row in rows if row.contact_id}
    if contact_ids:
        for contact_id, first, last, archived in session.execute(
            select(Contact.id, Contact.first_name, Contact.last_name, Contact.archived_at).where(
                Contact.tenant_id == scope.workspace, Contact.id.in_(contact_ids)
            )
        ):
            name = " ".join(part for part in (first, last) if part)
            contacts[contact_id] = {
                "id": contact_id,
                "name": name,
                "archived": archived is not None,
            }
    companies: dict[uuid.UUID, dict[str, Any]] = {}
    company_ids = {row.company_id for row in rows if row.company_id}
    if company_ids:
        for company_id, name, archived in session.execute(
            select(Company.id, Company.name, Company.archived_at).where(
                Company.tenant_id == scope.workspace, Company.id.in_(company_ids)
            )
        ):
            companies[company_id] = {
                "id": company_id,
                "name": name,
                "archived": archived is not None,
            }
    return contacts, companies


def _deals(session: Session, scope: Scope, rows: Sequence[Opportunity]) -> list[Deal]:
    """Rows as API records, with their stage, contact and company."""
    if not rows:
        return []
    stages = {
        stage.id: stage
        for stage in session.execute(
            select(PipelineStage).where(
                PipelineStage.tenant_id == scope.workspace,
                PipelineStage.id.in_({row.stage_id for row in rows}),
            )
        ).scalars()
    }
    contacts, companies = _links(session, scope, rows)
    deals = []
    for row in rows:
        stage = stages[row.stage_id]
        deals.append(
            {
                "id": row.id,
                "title": row.title,
                "amount": None
                if row.amount is None
                else rules.amount_text(row.amount, row.currency),
                "currency": row.currency,
                "weighted_amount": _weighted(row, stage.probability),
                "pipeline_id": row.pipeline_id,
                "stage_id": row.stage_id,
                "stage": {
                    "id": stage.id,
                    "name": stage.name,
                    "probability": stage.probability,
                    "position": stage.position,
                },
                "stage_entered_at": row.stage_entered_at,
                "owner_user_id": row.owner_user_id,
                "expected_close_date": row.expected_close_date,
                "contact_id": row.contact_id,
                "contact": contacts.get(row.contact_id) if row.contact_id else None,
                "company_id": row.company_id,
                "company": companies.get(row.company_id) if row.company_id else None,
                "outcome": row.outcome,
                "lost_reason": row.lost_reason,
                "closed_at": row.closed_at,
                "created_at": row.created_at,
                "updated_at": row.updated_at,
                "created_by_user_id": row.created_by_user_id,
                "updated_by_user_id": row.updated_by_user_id,
                "version": row.version,
            }
        )
    return deals


def get(scope: Scope, deal_id: uuid.UUID) -> Deal:
    with tenant_session_scope(scope.workspace) as session:
        row = _load(session, scope, deal_id, lock=False)
        return _deals(session, scope, [row])[0]


@dataclass(frozen=True)
class ListQuery:
    """A validated list request; the API has checked every value."""

    order: str = "updated_at"
    direction: str = "desc"
    limit: int = 50
    cursor: str | None = None
    q: str | None = None
    outcomes: tuple[str, ...] = ()
    stages: tuple[uuid.UUID, ...] = ()
    owners: tuple[uuid.UUID, ...] = ()
    contacts: tuple[uuid.UUID, ...] = ()
    companies: tuple[uuid.UUID, ...] = ()
    idle: bool = False

    def filters(self) -> dict[str, object]:
        return {
            "q": self.q,
            "outcomes": sorted(self.outcomes),
            "stages": sorted(str(x) for x in self.stages),
            "owners": sorted(str(x) for x in self.owners),
            "contacts": sorted(str(x) for x in self.contacts),
            "companies": sorted(str(x) for x in self.companies),
            "idle": self.idle,
        }


@dataclass(frozen=True)
class Page:
    items: list[Deal]
    next_cursor: str | None
    total: int
    total_capped: bool


def _order(order: str) -> list[_OrderKey]:
    identity = _OrderKey(Opportunity.id, Opportunity.id, "id")
    if order == "title":
        expression = Opportunity.title.collate(ORDER_COLLATION)
        return [_OrderKey(expression, Opportunity.title, "title"), identity]
    column = getattr(Opportunity, order)
    nullable = order in {"amount", "expected_close_date"}
    return [_OrderKey(column, column, order, nullable), identity]


def _conditions(scope: Scope, query: ListQuery) -> list[Any]:
    conditions: list[Any] = [Opportunity.tenant_id == scope.workspace]
    if query.q:
        conditions.append(Opportunity.title.icontains(query.q, autoescape=True))
    if query.outcomes:
        conditions.append(Opportunity.outcome.in_(query.outcomes))
    if query.stages:
        conditions.append(Opportunity.stage_id.in_(query.stages))
    if query.owners:
        conditions.append(Opportunity.owner_user_id.in_(query.owners))
    if query.contacts:
        conditions.append(Opportunity.contact_id.in_(query.contacts))
    if query.companies:
        conditions.append(Opportunity.company_id.in_(query.companies))
    if query.idle:
        idle_since = _now() - timedelta(days=rules.IDLE_DAYS)
        conditions.append(Opportunity.outcome == rules.OPEN)
        conditions.append(Opportunity.stage_entered_at <= idle_since)
    return conditions


def list_deals(scope: Scope, query: ListQuery) -> Page:
    """One page in a total, deterministic order (the ID breaks ties). Raises
    `paging.InvalidCursor` for a cursor issued for another order, direction
    or filter set."""
    filters = paging.filter_hash(query.filters())
    after = (
        paging.decode(query.cursor, "opportunity", query.order, query.direction, filters)
        if query.cursor
        else None
    )
    keys = _order(query.order)
    ascending = query.direction == "asc"
    with tenant_session_scope(scope.workspace) as session:
        conditions = _conditions(scope, query)
        counted = session.execute(
            select(Opportunity.id).where(*conditions).limit(TOTAL_CAP + 1)
        ).all()
        statement = select(Opportunity).where(*conditions)
        if after is not None:
            statement = statement.where(_after(keys, after, ascending=ascending))
        statement = statement.order_by(
            *(key.expression.asc() if ascending else key.expression.desc() for key in keys)
        ).limit(query.limit + 1)
        rows = list(session.execute(statement).scalars())
        more = len(rows) > query.limit
        rows = rows[: query.limit]
        items = _deals(session, scope, rows)
        last_key = tuple(getattr(rows[-1], key.attribute) for key in keys) if rows else None
    next_cursor = None
    if more and last_key is not None:
        next_cursor = paging.encode("opportunity", query.order, query.direction, filters, last_key)
    return Page(
        items=items,
        next_cursor=next_cursor,
        total=min(len(counted), TOTAL_CAP),
        total_capped=len(counted) > TOTAL_CAP,
    )


def summary(scope: Scope, query: ListQuery) -> dict[str, Any]:
    """For the list's filters: each stage's deal count and, per currency,
    total and weighted total of open deals, summed as exact decimals
    (P4-B 10). Reads at most `TOTAL_CAP` deals."""
    with tenant_session_scope(scope.workspace) as session:
        pipeline = _first_pipeline(session, scope, share=False)
        # Plain values, read while the session is open.
        probability = {
            stage.id: stage.probability
            for stage in (_stages(session, scope, pipeline.id) if pipeline else [])
        }
        rows = session.execute(
            select(
                Opportunity.stage_id,
                Opportunity.currency,
                Opportunity.amount,
                Opportunity.outcome,
            )
            .where(*_conditions(scope, query))
            .limit(TOTAL_CAP + 1)
        ).all()
    counts: dict[uuid.UUID, int] = dict.fromkeys(probability, 0)
    sums: dict[uuid.UUID, dict[str, list[Decimal]]] = {stage_id: {} for stage_id in probability}
    for stage_id, currency, amount, outcome in rows[:TOTAL_CAP]:
        if stage_id not in counts:
            continue
        counts[stage_id] += 1
        if amount is None:
            continue
        total = sums[stage_id].setdefault(currency, [Decimal(0), Decimal(0)])
        total[0] += amount
        if outcome == rules.OPEN:
            total[1] += amount * probability[stage_id] / 100
    return {
        "stages": [
            {
                "stage_id": stage_id,
                "count": counts[stage_id],
                "totals": [
                    {
                        "currency": currency,
                        "amount": rules.amount_text(amount, currency),
                        "weighted_amount": rules.amount_text(
                            _to_unit(weighted, currency), currency
                        ),
                    }
                    for currency, (amount, weighted) in sorted(sums[stage_id].items())
                ],
            }
            for stage_id in probability
        ],
        "total_capped": len(rows) > TOTAL_CAP,
    }


def history(scope: Scope, deal_id: uuid.UUID, *, cursor: str | None, limit: int) -> dict[str, Any]:
    """The deal's history, newest first."""
    after = paging.decode(cursor, "opportunity_event", "seq", "desc", "") if cursor else None
    with tenant_session_scope(scope.workspace) as session:
        _load(session, scope, deal_id, lock=False)
        statement = select(OpportunityEvent).where(
            OpportunityEvent.tenant_id == scope.workspace,
            OpportunityEvent.opportunity_id == deal_id,
        )
        if after is not None:
            statement = statement.where(OpportunityEvent.seq < after[0])
        rows = list(
            session.execute(
                statement.order_by(OpportunityEvent.seq.desc()).limit(limit + 1)
            ).scalars()
        )
        more = len(rows) > limit
        rows = rows[:limit]
        items = [{name: getattr(row, name) for name in _EVENT_FIELDS} for row in rows]
        last = rows[-1].seq if rows else None
    next_cursor = None
    if more and last is not None:
        next_cursor = paging.encode("opportunity_event", "seq", "desc", "", (last,))
    return {"items": items, "next_cursor": next_cursor}


# --- Writes ----------------------------------------------------------------------------


def _insert(session: Session, scope: Scope, deal_id: uuid.UUID, values: Mapping[str, Any]) -> None:
    """Insert one deal with its `created` history and audit entries, in the
    caller's locked transaction."""
    pipeline = _pipeline(session, scope)
    stages = _stages(session, scope, pipeline.id)
    stage_id = values.get("stage_id")
    stage = _stage(stages, stage_id) if stage_id is not None else stages[0]
    currency = _currency(session, scope)
    _check_link(session, scope, Contact, values.get("contact_id"))
    _check_link(session, scope, Company, values.get("company_id"))
    now = _now()
    session.add(
        Opportunity(
            id=deal_id,
            tenant_id=scope.workspace,
            title=values["title"],
            amount=_amount(values.get("amount"), currency),
            currency=currency,
            pipeline_id=pipeline.id,
            stage_id=stage.id,
            stage_entered_at=now,
            owner_user_id=values.get("owner_user_id"),
            expected_close_date=values.get("expected_close_date"),
            contact_id=values.get("contact_id"),
            company_id=values.get("company_id"),
            outcome=rules.OPEN,
            lost_reason=None,
            closed_at=None,
            created_by_user_id=scope.actor,
            updated_by_user_id=scope.actor,
            created_at=now,
            updated_at=now,
            version=1,
        )
    )
    session.flush()
    session.add(_event(scope, deal_id, "created", stage_to=stage.id, stage_to_name=stage.name))
    given = sorted(name for name in FIELDS if values.get(name) is not None)
    _audit(session, scope, "created", deal_id, fields=given)


def create(
    scope: Scope, values: Mapping[str, Any], *, idempotency_key: str | None = None
) -> tuple[Deal, bool]:
    """Create a deal; returns it and whether this was an idempotent replay.
    The key is scoped to the workspace and the acting member; the stored
    result is the new ID only, and a replay returns the deal as it is now."""
    check_owner(scope, values.get("owner_user_id"))
    pipelines.list_pipelines(scope)  # the default pipeline exists from here on
    deal_id = uuid.uuid4()

    def business(session: Session) -> dict[str, object]:
        lock_open_tenant(session, scope.workspace)
        _insert(session, scope, deal_id, values)
        return {"id": str(deal_id)}

    replay = False
    if idempotency_key is None:
        result = _transaction(scope, business)
    else:
        fingerprint = {
            name: None if values.get(name) is None else str(values[name]) for name in FIELDS
        }
        try:
            replay, result = run_idempotent(
                scope.workspace,
                f"{RESOURCE}.create:{scope.actor}",
                idempotency_key,
                fingerprint,
                business,
            )
        except (TenantClosedError, TenantNotFoundError):
            raise RecordNotFoundError from None
        except IntegrityError as exc:
            raise _refusal(exc) from None
        except OperationalError as exc:
            if is_transaction_conflict(exc):
                raise TransactionConflictError from None
            raise
    return get(scope, uuid.UUID(str(result["id"]))), replay


def update(
    scope: Scope, deal_id: uuid.UUID, changes: Mapping[str, Any], *, expected_version: int
) -> Deal:
    """Apply `changes` if the deal is still at `expected_version`. A change
    that alters nothing is a no-op: no new version, no audit entry."""
    if changes.get("owner_user_id") is not None:
        check_owner(scope, changes["owner_user_id"])

    def apply(session: Session) -> None:
        pipeline = _pipeline(session, scope)
        row = _load(session, scope, deal_id, lock=True)
        if row.version != expected_version:
            raise StaleVersionError(row.version)
        wanted: dict[str, Any] = {
            name: _amount(value, row.currency) if name == "amount" else value
            for name, value in changes.items()
        }
        changed = sorted(name for name, value in wanted.items() if getattr(row, name) != value)
        if not changed:
            return
        if "contact_id" in changed:
            _check_link(session, scope, Contact, wanted["contact_id"])
        if "company_id" in changed:
            _check_link(session, scope, Company, wanted["company_id"])
        entries: list[OpportunityEvent] = []
        plain = [name for name in changed if name in _PLAIN]
        if plain:
            entries.append(_event(scope, row.id, "updated", fields=plain))
        if "stage_id" in changed:
            if row.outcome != rules.OPEN:
                raise DealClosedError
            stages = _stages(session, scope, pipeline.id)
            to = _stage(stages, wanted["stage_id"])
            entries.append(move_to_stage(scope, row, _stage(stages, row.stage_id), to, "moved"))
        else:
            _touch(row, scope, _now())
        if "owner_user_id" in changed:
            entries.append(
                _event(
                    scope,
                    row.id,
                    "owner_changed",
                    owner_from=row.owner_user_id,
                    owner_to=wanted["owner_user_id"],
                )
            )
        for name in changed:
            if name != "stage_id":
                setattr(row, name, wanted[name])
        session.flush()
        for entry in entries:  # one at a time, so `seq` keeps this order
            session.add(entry)
            session.flush()
        _audit(session, scope, "updated", row.id, fields=changed)

    _transaction(scope, apply)
    return get(scope, deal_id)


def set_outcome(
    scope: Scope,
    deal_id: uuid.UUID,
    outcome: str,
    lost_reason: str | None,
    *,
    expected_version: int,
) -> Deal:
    """Mark the deal won or lost, or reopen it (P4-B 5). Lost needs a
    reason; reopening clears it. Asking for the outcome the deal already has
    (with the same reason) is a no-op."""
    if outcome == rules.LOST and lost_reason is None:
        raise LostReasonError
    if outcome != rules.LOST and lost_reason is not None:
        raise LostReasonNotAllowedError

    def apply(session: Session) -> None:
        _pipeline(session, scope)
        row = _load(session, scope, deal_id, lock=True)
        if row.version != expected_version:
            raise StaleVersionError(row.version)
        if row.outcome == outcome and row.lost_reason == lost_reason:
            return
        if (row.outcome, outcome) not in rules.TRANSITIONS:
            raise InvalidTransitionError
        before = row.outcome
        now = _now()
        row.outcome = outcome
        row.lost_reason = lost_reason
        row.closed_at = None if outcome == rules.OPEN else now
        _touch(row, scope, now)
        session.flush()
        session.add(
            _event(scope, row.id, "outcome_changed", outcome_from=before, outcome_to=outcome)
        )
        _audit(session, scope, "outcome_changed", row.id, outcome_from=before, outcome_to=outcome)

    _transaction(scope, apply)
    return get(scope, deal_id)


def remove(scope: Scope, deal_id: uuid.UUID) -> None:
    """Delete the deal and, by cascade, its history (Owner and Admin, Q6)."""

    def apply(session: Session) -> None:
        _pipeline(session, scope)
        row = _load(session, scope, deal_id, lock=True)
        session.delete(row)
        session.flush()
        _audit(session, scope, "deleted", deal_id)

    _transaction(scope, apply)

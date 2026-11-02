"""Automations (decision P8-A): definitions, activation, runs and steps.

- **Definitions** are edited as drafts (`create`, `update`) and checked by
  `crm_app.domains.automations`. `activate` checks them again, plus every
  tag and member they name, and freezes them as an immutable version; runs
  follow the version they began with. `pause` stops new runs; running ones
  finish. At most `MAX_AUTOMATIONS` per workspace.
- **Trigger:** `on_contact_created` runs inside the transaction that
  creates the contact (`records.insert_record`): one run per active
  automation it matches, at most once per automation and contact, indexed
  as due now in the global `automation_due`.
- **Execution:** `advance` takes a run under a row lock and executes its
  steps in order. Each step's effect and its `automation_step` row commit
  together, so a retried job finds the step done and never acts twice. A
  `wait` sets the run waiting until its time; the sweeper
  (`crm_app.automation_maintenance`) enqueues due runs. A missing tag or a
  member who left skips the step with a code; a deleted contact cancels
  the run; anything unexpected raises, the job queue retries, and after
  `MAX_ATTEMPTS` the run fails. Steps act as the member who activated the
  automation: SaaS-OS has no system caller for this.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Mapping
from datetime import UTC, datetime, timedelta
from typing import Any

from saas_os.core.audit_log import record_in_transaction
from saas_os.core.authority import UserCaller
from saas_os.core.identity import get_membership
from saas_os.core.tenancy import lock_open_tenant
from saas_os.infra.db import (
    IntegrityError,
    OperationalError,
    Session,
    acquire_tenant_advisory_lock,
    delete,
    is_transaction_conflict,
    select,
    session_scope,
    tenant_session_scope,
)

from crm_app import records, tasks
from crm_app.domains import automations as rules
from crm_app.domains.records import InvalidValue
from crm_app.models import (
    Automation,
    AutomationDue,
    AutomationRun,
    AutomationStep,
    AutomationVersion,
    BookingPage,
    Contact,
    ContactTag,
    Form,
    PipelineStage,
    Tag,
)
from crm_app.records import (
    RecordError,
    RecordNotFoundError,
    Scope,
    StaleVersionError,
    TransactionConflictError,
)

# The record a trigger may be limited to (P8-B), by trigger.
_SUBJECT_MODELS: dict[str, Any] = {
    "form_submitted": Form,
    "appointment_booked": BookingPage,
    "deal_stage_changed": PipelineStage,
}
RESOURCE = "crm_app.automation"
JOB_NAME = "crm_app_automation_run"
MAX_ATTEMPTS = 5
RETRY_DELAY = timedelta(minutes=5)
RUN_PAGE = 50

Item = dict[str, Any]


class AutomationRuleError(RecordError):
    """A definition or change the rules refuse; `detail` names the rule."""

    status, code = 422, "invalid_automation"

    def __init__(self, detail: str) -> None:
        super().__init__(self.code)
        self.detail = detail


class AutomationLimitError(RecordError):
    status, code = 409, "automation_limit"


class AutomationStateError(RecordError):
    """Only a draft or paused automation's definition may change."""

    status, code = 409, "automation_active"


def _now() -> datetime:
    return datetime.now(UTC)


def _transaction[T](scope: Scope, fn: Callable[[Session], T]) -> T:
    try:
        with tenant_session_scope(scope.workspace) as session:
            lock_open_tenant(session, scope.workspace)
            return fn(session)
    except OperationalError as exc:
        if is_transaction_conflict(exc):
            raise TransactionConflictError from None
        raise


def _audit(
    session: Session, scope: Scope, verb: str, automation_id: uuid.UUID, **meta: Any
) -> None:
    record_in_transaction(
        session,
        caller=UserCaller(scope.actor),
        tenant_id=scope.workspace,
        action=f"{RESOURCE}.{verb}",
        resource_type=RESOURCE,
        resource_id=str(automation_id),
        metadata=meta,
    )


def _definition(raw: object) -> rules.Definition:
    try:
        return rules.definition(raw)
    except InvalidValue as exc:
        raise AutomationRuleError(str(exc)) from None


def _stored(raw: object) -> rules.Definition | None:
    """A stored active definition, or None when it no longer passes the
    rules: it then simply matches nothing, and never breaks the request that
    raised the event (a contact create, a public form or booking; 13-H5)."""
    try:
        return rules.definition(raw)
    except InvalidValue:
        return None


def _item(row: Automation) -> Item:
    return {
        "id": row.id,
        "name": row.name,
        "status": row.status,
        "trigger_type": row.trigger_type,
        "definition": row.definition,
        "active_version": row.active_version,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
        "version": row.version,
    }


def _load(session: Session, scope: Scope, automation_id: uuid.UUID, *, lock: bool) -> Automation:
    query = select(Automation).where(
        Automation.tenant_id == scope.workspace, Automation.id == automation_id
    )
    row = session.execute(query.with_for_update() if lock else query).scalar_one_or_none()
    if row is None:
        raise RecordNotFoundError
    return row


# --- Definitions ----------------------------------------------------------------------------


def list_automations(scope: Scope) -> list[Item]:
    with tenant_session_scope(scope.workspace) as session:
        rows = session.execute(
            select(Automation)
            .where(Automation.tenant_id == scope.workspace)
            .order_by(Automation.created_at, Automation.id)
        ).scalars()
        return [_item(row) for row in rows]


def get(scope: Scope, automation_id: uuid.UUID) -> Item:
    with tenant_session_scope(scope.workspace) as session:
        return _item(_load(session, scope, automation_id, lock=False))


def create(scope: Scope, name: str, definition: object) -> Item:
    try:
        clean_name = rules.name(name)
    except InvalidValue as exc:
        raise AutomationRuleError(str(exc)) from None
    given = _definition(definition)
    automation_id = uuid.uuid4()

    def apply(session: Session) -> Item:
        acquire_tenant_advisory_lock(session, scope.workspace, f"{RESOURCE}.create")
        count = len(
            session.execute(
                select(Automation.id)
                .where(Automation.tenant_id == scope.workspace)
                .limit(rules.MAX_AUTOMATIONS)
            ).all()
        )
        if count >= rules.MAX_AUTOMATIONS:
            raise AutomationLimitError
        now = _now()
        row = Automation(
            id=automation_id,
            tenant_id=scope.workspace,
            name=clean_name,
            status="draft",
            trigger_type=given.trigger,
            definition=given.as_json(),
            active_version=None,
            activated_by_user_id=None,
            created_by_user_id=scope.actor,
            updated_by_user_id=scope.actor,
            created_at=now,
            updated_at=now,
            version=1,
        )
        session.add(row)
        session.flush()
        _audit(session, scope, "created", automation_id)
        return _item(row)

    return _transaction(scope, apply)


def update(
    scope: Scope,
    automation_id: uuid.UUID,
    changes: Mapping[str, Any],
    *,
    expected_version: int,
) -> Item:
    """Rename, or replace the draft definition. The definition of an active
    automation is frozen: pause it first."""
    values: dict[str, Any] = {}
    if "name" in changes:
        try:
            values["name"] = rules.name(str(changes["name"]))
        except InvalidValue as exc:
            raise AutomationRuleError(str(exc)) from None
    if "definition" in changes:
        values["definition"] = _definition(changes["definition"]).as_json()

    def apply(session: Session) -> Item:
        row = _load(session, scope, automation_id, lock=True)
        if row.version != expected_version:
            raise StaleVersionError(row.version)
        if "definition" in values and row.status == "active":
            raise AutomationStateError
        changed = sorted(k for k, v in values.items() if getattr(row, k) != v)
        if changed:
            for name in changed:
                setattr(row, name, values[name])
            if "definition" in changed:
                # Kept with the row so an event looks up only its automations.
                row.trigger_type = values["definition"]["trigger"]["type"]
            row.updated_by_user_id, row.updated_at = scope.actor, _now()
            row.version += 1
            session.flush()
            _audit(session, scope, "updated", automation_id, fields=changed)
        return _item(row)

    return _transaction(scope, apply)


def _active_member(workspace: uuid.UUID, user_id: uuid.UUID) -> bool:
    membership = get_membership(workspace, user_id)
    return membership is not None and membership.status == "active"


def _check_references(session: Session, scope: Scope, given: rules.Definition) -> None:
    tags, users = rules.referenced(given)
    if tags:
        wanted = {uuid.UUID(t) for t in tags}
        found = set(
            session.execute(
                select(Tag.id).where(Tag.tenant_id == scope.workspace, Tag.id.in_(wanted))
            ).scalars()
        )
        if found != wanted:
            raise AutomationRuleError("a tag it names no longer exists")
    for user in users:
        if not _active_member(scope.workspace, uuid.UUID(user)):
            raise AutomationRuleError("a member it names is not an active member")
    model = _SUBJECT_MODELS.get(given.trigger)
    if model is not None and given.subject_id is not None:
        found_subject = session.execute(
            select(model.id).where(
                model.tenant_id == scope.workspace, model.id == uuid.UUID(given.subject_id)
            )
        ).first()
        if found_subject is None:
            raise AutomationRuleError("the form, booking page or stage it names no longer exists")


def activate(scope: Scope, automation_id: uuid.UUID, *, expected_version: int) -> Item:
    """Freeze the draft as a new version and start matching new contacts."""

    def apply(session: Session) -> Item:
        row = _load(session, scope, automation_id, lock=True)
        if row.version != expected_version:
            raise StaleVersionError(row.version)
        given = _definition(row.definition)
        try:
            rules.activatable(given)
        except InvalidValue as exc:
            raise AutomationRuleError(str(exc)) from None
        _check_references(session, scope, given)
        latest = session.execute(
            select(AutomationVersion.number)
            .where(
                AutomationVersion.tenant_id == scope.workspace,
                AutomationVersion.automation_id == automation_id,
            )
            .order_by(AutomationVersion.number.desc())
            .limit(1)
        ).scalar_one_or_none()
        number = (latest or 0) + 1
        now = _now()
        session.add(
            AutomationVersion(
                tenant_id=scope.workspace,
                automation_id=automation_id,
                number=number,
                definition=given.as_json(),
                created_by_user_id=scope.actor,
                created_at=now,
            )
        )
        row.status, row.active_version, row.activated_by_user_id = "active", number, scope.actor
        row.updated_by_user_id, row.updated_at = scope.actor, now
        row.version += 1
        session.flush()
        _audit(session, scope, "activated", automation_id, version=number)
        return _item(row)

    return _transaction(scope, apply)


def pause(scope: Scope, automation_id: uuid.UUID, *, expected_version: int) -> Item:
    """Stop starting runs; runs already started finish."""

    def apply(session: Session) -> Item:
        row = _load(session, scope, automation_id, lock=True)
        if row.version != expected_version:
            raise StaleVersionError(row.version)
        if row.status != "active":
            return _item(row)
        row.status, row.updated_by_user_id, row.updated_at = "paused", scope.actor, _now()
        row.version += 1
        session.flush()
        _audit(session, scope, "paused", automation_id)
        return _item(row)

    return _transaction(scope, apply)


def remove(scope: Scope, automation_id: uuid.UUID) -> None:
    """Delete an automation with its versions, runs and steps."""

    def apply(session: Session) -> list[uuid.UUID]:
        row = _load(session, scope, automation_id, lock=True)
        run_ids = list(
            session.execute(
                select(AutomationRun.id).where(
                    AutomationRun.tenant_id == scope.workspace,
                    AutomationRun.automation_id == automation_id,
                )
            ).scalars()
        )
        session.delete(row)
        session.flush()
        _audit(session, scope, "deleted", automation_id, runs=len(run_ids))
        return run_ids

    _forget(_transaction(scope, apply))


# --- Trigger -------------------------------------------------------------------------------


def _active(session: Session, workspace: uuid.UUID, trigger: str) -> list[Any]:
    return list(
        session.execute(
            select(Automation.id, Automation.active_version, AutomationVersion.definition)
            .join(
                AutomationVersion,
                (AutomationVersion.tenant_id == Automation.tenant_id)
                & (AutomationVersion.automation_id == Automation.id)
                & (AutomationVersion.number == Automation.active_version),
            )
            .where(
                Automation.tenant_id == workspace,
                Automation.status == "active",
                Automation.trigger_type == trigger,
            )
        ).all()
    )


def on_event(
    session: Session,
    scope: Scope,
    trigger: str,
    contact_id: uuid.UUID,
    subject_id: uuid.UUID | None = None,
) -> int:
    """Start the active automations an event about a contact matches (a tag
    added, a form submitted, an appointment booked, a deal moved into a
    stage; decision P8-B), in the event's transaction. An automation that
    already ran for this contact is not started again, so automations that
    trigger one another always stop. Returns how many runs started."""
    rows = _active(session, scope.workspace, trigger)
    if not rows:
        return 0
    subject = None if subject_id is None else str(subject_id)
    wanted = [
        (automation_id, version)
        for automation_id, version, definition in rows
        if version is not None
        and (parsed := _stored(definition)) is not None
        and rules.matches(parsed, trigger, subject)
    ]
    if not wanted:
        return 0
    ran = set(
        session.execute(
            select(AutomationRun.automation_id).where(
                AutomationRun.tenant_id == scope.workspace,
                AutomationRun.contact_id == contact_id,
                AutomationRun.automation_id.in_([automation_id for automation_id, _ in wanted]),
            )
        ).scalars()
    )
    started: list[uuid.UUID] = []
    now = _now()
    for automation_id, version in wanted:
        if automation_id in ran:
            continue
        run_id = uuid.uuid4()
        try:
            # A concurrent event for the same contact may start it first:
            # then this one simply does not, and the caller's change stands.
            with session.begin_nested():
                session.add(
                    _new_run(scope.workspace, automation_id, version, contact_id, run_id, now)
                )
                session.flush()
        except IntegrityError:
            continue
        started.append(run_id)
    _index_runs(scope.workspace, started, now)
    return len(started)


def _new_run(  # noqa: PLR0913, PLR0917 - one run's identity
    workspace: uuid.UUID,
    automation_id: uuid.UUID,
    version: int,
    contact_id: uuid.UUID,
    run_id: uuid.UUID,
    now: datetime,
) -> AutomationRun:
    return AutomationRun(
        id=run_id,
        tenant_id=workspace,
        automation_id=automation_id,
        version_number=version,
        contact_id=contact_id,
        branch=None,
        next_step=0,
        status="running",
        resume_at=None,
        attempts=0,
        last_error=None,
        created_at=now,
        updated_at=now,
        finished_at=None,
    )


def _index_runs(workspace: uuid.UUID, started: list[uuid.UUID], now: datetime) -> None:
    if not started:
        return
    # Indexed in its own transaction: if the event's rolls back, the
    # sweeper finds no run and drops the entry.
    with session_scope() as global_session:
        global_session.add_all(
            AutomationDue(run_id=run_id, workspace_id=workspace, due_at=now) for run_id in started
        )


def on_contact_created(session: Session, scope: Scope, contact_id: uuid.UUID, source: str) -> int:
    """Start the active automations a new contact matches, in the creating
    transaction; returns how many runs started."""
    started: list[uuid.UUID] = []
    now = _now()
    for automation_id, version, definition in _active(session, scope.workspace, "contact_created"):
        parsed = _stored(definition)
        if version is None or parsed is None or not rules.triggered_by(parsed, source):
            continue
        run_id = uuid.uuid4()
        session.add(_new_run(scope.workspace, automation_id, version, contact_id, run_id, now))
        started.append(run_id)
    if started:
        session.flush()
    _index_runs(scope.workspace, started, now)
    return len(started)


# --- Execution -----------------------------------------------------------------------------


def _facts(session: Session, workspace: uuid.UUID, contact: Contact) -> rules.Facts:
    tag_ids = frozenset(
        str(tag)
        for tag in session.execute(
            select(ContactTag.tag_id).where(
                ContactTag.tenant_id == workspace, ContactTag.contact_id == contact.id
            )
        ).scalars()
    )
    return rules.Facts(
        source=contact.source,
        lifecycle_stage=contact.lifecycle_stage,
        has_email=bool(contact.email),
        tag_ids=tag_ids,
    )


def _act(  # noqa: PLR0911 - one answer per action
    session: Session, scope: Scope, contact: Contact, action: rules.Action, run: AutomationRun
) -> tuple[str, str | None]:
    """One action's effect in the run's transaction: (outcome, detail)."""
    args = action.args
    if action.type == "add_tag":
        result = records.add_tag_in(session, scope, contact.id, uuid.UUID(args["tag_id"]))
        return ("done", None) if result in ("added", "present") else ("skipped", result)
    if action.type == "remove_tag":
        records.remove_tag_in(session, scope, contact.id, uuid.UUID(args["tag_id"]))
        return "done", None
    if action.type == "set_lifecycle_stage":
        records.set_stage_in(session, scope, contact.id, args["stage"])
        return "done", None
    if action.type == "assign_owner":
        owner = uuid.UUID(args["user_id"])
        if not _active_member(scope.workspace, owner):
            return "skipped", "member_gone"
        records.assign_owner_in(session, scope, contact.id, owner)
        return "done", None
    if action.type == "create_task":
        assignee: uuid.UUID | None
        if args["assignee"] == "none":
            assignee = None
        elif args["assignee"] == "contact_owner":
            assignee = contact.owner_user_id
        else:
            assignee = uuid.UUID(args["assignee"])
        if assignee is not None and not _active_member(scope.workspace, assignee):
            assignee = None
        minutes = args["due_minutes"]
        values = {
            "title": args["title"],
            "priority": args["priority"],
            "due_at": None if minutes is None else _now() + timedelta(minutes=minutes),
            "assignee_user_id": assignee,
            "contact_id": contact.id,
        }
        tasks.create_in(session, scope, values, automation_id=str(run.automation_id))
        return "done", None
    # wait: the caller sets the run waiting.
    return "done", None


def advance(workspace: uuid.UUID, run_id: uuid.UUID) -> str:
    """Execute a run's due steps; returns its status afterwards."""
    while True:
        status, more = _step(workspace, run_id)
        if not more:
            return status


def _load_run(session: Session, workspace: uuid.UUID, run_id: uuid.UUID) -> AutomationRun | None:
    return session.execute(
        select(AutomationRun)
        .where(AutomationRun.tenant_id == workspace, AutomationRun.id == run_id)
        .with_for_update()
    ).scalar_one_or_none()


def _version(session: Session, workspace: uuid.UUID, run: AutomationRun) -> rules.Definition:
    return _definition(
        session.execute(
            select(AutomationVersion.definition).where(
                AutomationVersion.tenant_id == workspace,
                AutomationVersion.automation_id == run.automation_id,
                AutomationVersion.number == run.version_number,
            )
        ).scalar_one()
    )


def _step(workspace: uuid.UUID, run_id: uuid.UUID) -> tuple[str, bool]:  # noqa: PLR0911 - one exit per state
    """At most one step, in one transaction: (status, whether to go on)."""
    with tenant_session_scope(workspace) as session:
        run = _load_run(session, workspace, run_id)
        if run is None:
            _forget([run_id])
            return "missing", False
        now = _now()
        if run.status in ("completed", "failed", "cancelled"):
            _forget([run_id])
            return run.status, False
        if run.status == "waiting":
            if run.resume_at is not None and run.resume_at > now:
                return "waiting", False
            run.status, run.resume_at = "running", None
        actor = session.execute(
            select(Automation.activated_by_user_id).where(
                Automation.tenant_id == workspace, Automation.id == run.automation_id
            )
        ).scalar_one()
        definition = _version(session, workspace, run)
        contact = None
        if run.contact_id is not None:
            contact = session.execute(
                select(Contact).where(Contact.tenant_id == workspace, Contact.id == run.contact_id)
            ).scalar_one_or_none()
        if contact is None or actor is None or not _active_member(workspace, actor):
            # The member who activated it left or was suspended: it stops
            # acting in their name (13-H5).
            _finish(run, "cancelled", now, "contact_gone" if contact is None else "not_active")
            _forget([run_id])
            return run.status, False
        if run.branch is None:
            run.branch = rules.branch_for(definition.condition, _facts(session, workspace, contact))
        steps = definition.branch(run.branch)
        if run.next_step >= len(steps):
            _finish(run, "completed", now, None)
            _forget([run_id])
            return run.status, False
        position = run.next_step
        action = steps[position]
        done = session.execute(
            select(AutomationStep.outcome).where(
                AutomationStep.tenant_id == workspace,
                AutomationStep.run_id == run_id,
                AutomationStep.branch == run.branch,
                AutomationStep.position == position,
            )
        ).first()
        if done is None:
            scope = Scope(workspace=workspace, actor=actor)
            outcome, detail = _act(session, scope, contact, action, run)
            session.add(
                AutomationStep(
                    tenant_id=workspace,
                    run_id=run_id,
                    branch=run.branch,
                    position=position,
                    action=action.type,
                    outcome=outcome,
                    detail=detail,
                    executed_at=now,
                )
            )
        # A step that succeeded resets the failure count: five unrelated
        # transient errors over a long run do not fail it (13-H5).
        run.next_step, run.updated_at, run.last_error = position + 1, now, None
        run.attempts = 0
        if action.type == "wait":
            run.status = "waiting"
            resume_at = now + timedelta(minutes=action.args["minutes"])
            run.resume_at = resume_at
            session.flush()
            _schedule(run_id, workspace, resume_at)
            return "waiting", False
        session.flush()
        return "running", True


def _finish(run: AutomationRun, status: str, now: datetime, error: str | None) -> None:
    run.status, run.finished_at, run.updated_at, run.resume_at = status, now, now, None
    if error is not None:
        run.last_error = error


def record_failure(workspace: uuid.UUID, run_id: uuid.UUID, code: str) -> str:
    """Count a failed try; after `MAX_ATTEMPTS` the run fails. Returns the
    run's status."""
    with tenant_session_scope(workspace) as session:
        run = _load_run(session, workspace, run_id)
        if run is None:
            return "missing"
        if run.status in ("completed", "failed", "cancelled"):
            return run.status
        now = _now()
        run.attempts += 1
        run.last_error = code
        run.updated_at = now
        status = run.status
        if run.attempts >= MAX_ATTEMPTS:
            _finish(run, "failed", now, code)
            status = "failed"
    if status == "failed":
        _forget([run_id])
    else:
        _schedule(run_id, workspace, now + RETRY_DELAY)
    return status


# --- The global index and the sweeper ------------------------------------------------------


def _schedule(run_id: uuid.UUID, workspace: uuid.UUID, due_at: datetime) -> None:
    with session_scope() as session:
        row = session.get(AutomationDue, run_id)
        if row is None:
            session.add(AutomationDue(run_id=run_id, workspace_id=workspace, due_at=due_at))
        else:
            row.due_at = due_at


def _forget(run_ids: list[uuid.UUID]) -> None:
    if not run_ids:
        return
    with session_scope() as session:
        session.execute(delete(AutomationDue).where(AutomationDue.run_id.in_(run_ids)))


def due(limit: int = 500) -> list[tuple[uuid.UUID, uuid.UUID]]:
    """Runs due now, as (workspace, run) pairs, oldest first; each is pushed
    back by `RETRY_DELAY` so a lost job is tried again."""
    now = _now()
    with session_scope() as session:
        rows = session.execute(
            select(AutomationDue)
            .where(AutomationDue.due_at <= now)
            .order_by(AutomationDue.due_at)
            .limit(limit)
            .with_for_update(skip_locked=True)
        ).scalars()
        pairs: list[tuple[uuid.UUID, uuid.UUID]] = []
        for row in rows:
            pairs.append((row.workspace_id, row.run_id))
            row.due_at = now + RETRY_DELAY
    return pairs


async def enqueue(workspace: uuid.UUID, run_id: uuid.UUID) -> bool:
    from saas_os.infra.jobs import TenantJobPayload, enqueue_job  # noqa: PLC0415

    payload = TenantJobPayload(tenant_id=str(workspace), data={"run_id": str(run_id)})
    try:
        await enqueue_job(JOB_NAME, payload)
    except Exception:  # noqa: BLE001 - any queue failure leaves it to the next sweep
        return False
    return True


# --- History --------------------------------------------------------------------------------


def _steps_of(
    session: Session, workspace: uuid.UUID, run_ids: list[uuid.UUID]
) -> dict[uuid.UUID, list[Item]]:
    steps: dict[uuid.UUID, list[Item]] = {run_id: [] for run_id in run_ids}
    if not run_ids:
        return steps
    for step in session.execute(
        select(AutomationStep)
        .where(AutomationStep.tenant_id == workspace, AutomationStep.run_id.in_(run_ids))
        .order_by(AutomationStep.executed_at, AutomationStep.position)
    ).scalars():
        steps[step.run_id].append(
            {
                "branch": step.branch,
                "position": step.position,
                "action": step.action,
                "outcome": step.outcome,
                "detail": step.detail,
                "executed_at": step.executed_at,
            }
        )
    return steps


def runs(scope: Scope, automation_id: uuid.UUID) -> list[Item]:
    """The automation's latest `RUN_PAGE` runs with their steps, newest first."""
    with tenant_session_scope(scope.workspace) as session:
        _load(session, scope, automation_id, lock=False)
        rows = list(
            session.execute(
                select(AutomationRun)
                .where(
                    AutomationRun.tenant_id == scope.workspace,
                    AutomationRun.automation_id == automation_id,
                )
                .order_by(AutomationRun.created_at.desc(), AutomationRun.id.desc())
                .limit(RUN_PAGE)
            ).scalars()
        )
        steps = _steps_of(session, scope.workspace, [row.id for row in rows])
        return [
            {
                "id": row.id,
                "contact_id": row.contact_id,
                "version": row.version_number,
                "branch": row.branch,
                "status": row.status,
                "resume_at": row.resume_at,
                "attempts": row.attempts,
                "last_error": row.last_error,
                "created_at": row.created_at,
                "finished_at": row.finished_at,
                "steps": steps[row.id],
            }
            for row in rows
        ]

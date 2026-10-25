"""Self-service signup: a verified person creates a workspace and becomes its
Owner (decisions S-1, S-1.1; `docs/project/SIGNUP-PLAN.md` §3, §4, §4b).

**Who.** The person is always the server-side session's user, passed in by
the route; nothing in a request names a user, a parent workspace, a role or
any authority. Every read and write of `crm_app.signup` runs in a
transaction that first sets `crm_app.signup_user_id` to that person,
transaction-locally (`_as_user`), and the table's forced RLS limits it to
that person's rows (migration 0006). A session-level setting would outlive
the transaction on a pooled connection, so `_set_local` is the only place
that sets either setting, and always with `is_local = true`
(`tests/unit/test_signup_rules.py` checks this).

**Limits.** `record_attempt()` counts the request against the
platform-wide rolling 24-hour cap under one global advisory lock, so the
check and the increment are atomic; a request refused by the cap is not
counted, and if the counter cannot be read the request is refused
(`CounterUnavailableError`). `start()` checks the per-person workspace
limit under a per-person advisory lock, with the one-open-signup index as a
backstop.

**Provisioning** (`run()`) is a sequence of find-or-create steps, each
recorded on the row before the next starts, so a run that is interrupted
resumes where it stopped. One runner at a time per signup (a session-level
advisory lock held on its own connection for the run). The workspace is
activated last, only after the Owner passes `can()` for
`provisioning.OWNER_CHECKS`. SaaS-OS cannot create a tenant and record it
on this row in one transaction; if a run stops between the two, the next
run adopts the workspace it created: a `pending` workspace of the recorded
name, created within the step's window, with no members, that no other
signup has claimed (`signup_workspace_unique`).

**Maintenance** (`maintain()`, run by `python -m crm_app.signup_maintenance`)
resumes stale signups, expires those older than 7 days and removes old
records. It may *read* every row with `crm_app.signup_maintenance = 'on'`,
then acts on each row as that row's own person; the flag never permits a
write. Nothing here creates or deletes an identity in ZITADEL.

Logs carry identifiers and outcome codes only: never an email, a name, a
token or a workspace name.

SaaS-OS resolves configuration at import time; only code that runs after
validation imports this module.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

# Registers the RBAC tables in the shared ORM metadata before
# `create_tenant` flushes its audit row (its foreign keys name them).
import saas_os.core.rbac  # noqa: F401
from saas_os.core.authority import SystemAuthority, SystemCaller
from saas_os.core.identity import get_membership, list_tenant_members
from saas_os.core.tenancy import (
    TenantNotFoundError,
    TenantStatus,
    create_tenant,
    find_tenants_by_name,
    get_tenant,
    is_closed,
    transition_tenant_status,
)
from saas_os.infra.db import (
    IntegrityError,
    Session,
    delete,
    get_engine,
    select,
    session_scope,
    update,
)

from crm_app import provisioning
from crm_app.domains.signup import request_fingerprint
from crm_app.models import Signup

logger = logging.getLogger(__name__)

OPEN_STATES = ("started", "provisioning")
EXPIRY = timedelta(days=7)
MAX_RUNS = 5
STALE_AFTER = timedelta(minutes=2)
RETENTION = timedelta(days=90)
ADOPTION_WINDOW = timedelta(minutes=10)
ADOPTION_SKEW = timedelta(minutes=1)

USER_SETTING = "crm_app.signup_user_id"
MAINTENANCE_SETTING = "crm_app.signup_maintenance"

# Advisory-lock namespaces (two-key form, so they never meet SaaS-OS's
# one-key locks).
_NS_USER = 727_001
_NS_CAP = 727_002
_NS_RUN = 727_003


class SignupRefusedError(Exception):
    """The request is refused; `code` is a fixed literal for the response."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class CounterUnavailableError(Exception):
    """The attempt counter could not be read or written: refuse (fail closed)."""


class _StepFailedError(Exception):
    """A step found a state it must not continue from: needs an operator."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class SignupView:
    id: uuid.UUID
    state: str
    workspace_id: uuid.UUID | None
    created_at: datetime
    error_code: str | None


@dataclass(frozen=True)
class _Row:
    id: uuid.UUID
    user_id: uuid.UUID
    state: str
    step: str
    workspace_name: str | None
    workspace_id: uuid.UUID | None
    step_started_at: datetime | None
    attempts: int
    expires_at: datetime


def _now() -> datetime:
    return datetime.now(UTC)


def _provisioning_caller() -> Any:
    return SystemCaller(SystemAuthority.PROVISIONING)


def _set_local(session: Session, name: str, value: str) -> None:
    # Always transaction-local: see the module docstring.
    session.connection().exec_driver_sql(
        "SELECT set_config(%(name)s, %(value)s, true)", {"name": name, "value": value}
    )


@contextmanager
def _as_user(user_id: uuid.UUID) -> Iterator[Session]:
    """A transaction limited by RLS to this person's signup rows."""
    with session_scope() as session:
        _set_local(session, USER_SETTING, str(user_id))
        yield session


@contextmanager
def _maintenance_reader() -> Iterator[Session]:
    """A transaction that may read every signup row and write none."""
    with session_scope() as session:
        _set_local(session, MAINTENANCE_SETTING, "on")
        yield session


def _view(row: Signup) -> SignupView:
    return SignupView(
        id=row.id,
        state=row.state,
        workspace_id=row.workspace_id,
        created_at=row.created_at,
        error_code=row.last_error_code,
    )


def _snapshot(row: Signup) -> _Row:
    return _Row(
        id=row.id,
        user_id=row.user_id,
        state=row.state,
        step=row.step,
        workspace_name=row.workspace_name,
        workspace_id=row.workspace_id,
        step_started_at=row.step_started_at,
        attempts=row.attempts,
        expires_at=row.expires_at,
    )


# --- The platform-wide attempt cap -------------------------------------------


def record_attempt(cap: int) -> None:
    """Count one attempt against the rolling 24-hour cap, atomically: refused
    (and not counted) when `cap` attempts are already in the window."""
    try:
        with session_scope() as session:
            connection = session.connection()
            connection.exec_driver_sql("SELECT pg_advisory_xact_lock(%(ns)s, 0)", {"ns": _NS_CAP})
            counted = connection.exec_driver_sql(
                "SELECT count(*) FROM crm_app.signup_attempt"
                " WHERE attempted_at > now() - interval '24 hours'"
            ).scalar_one()
            if counted >= cap:
                raise SignupRefusedError("signup_capacity_reached")
            connection.exec_driver_sql("INSERT INTO crm_app.signup_attempt DEFAULT VALUES")
    except SignupRefusedError:
        raise
    except Exception:  # noqa: BLE001 - any failure of the counter refuses the request
        raise CounterUnavailableError from None


# --- Starting and reading ----------------------------------------------------


def _workspace_open(workspace_id: uuid.UUID) -> bool:
    try:
        return not is_closed(TenantStatus(get_tenant(workspace_id).status))
    except TenantNotFoundError:
        return False


def _workspaces_held(session: Session, user_id: uuid.UUID) -> int:
    """Workspaces this person created through signup that still exist (in
    any signup state: a failed signup's pending workspace counts too)."""
    held = session.execute(
        select(Signup.workspace_id).where(
            Signup.user_id == user_id, Signup.workspace_id.is_not(None)
        )
    ).scalars()
    return sum(1 for workspace_id in held if workspace_id and _workspace_open(workspace_id))


def start(
    user_id: uuid.UUID, idempotency_key: str, name: str, *, max_workspaces: int
) -> tuple[SignupView, bool]:
    """This person's signup for `idempotency_key`: the existing one (same
    key, same request), the open one (another key while one is unfinished),
    or a new one if the per-person limit allows. `True` when new."""
    request = request_fingerprint(name)
    with _as_user(user_id) as session:
        session.connection().exec_driver_sql(
            "SELECT pg_advisory_xact_lock(%(ns)s, hashtext(%(key)s))",
            {"ns": _NS_USER, "key": str(user_id)},
        )
        same_key = session.execute(
            select(Signup).where(
                Signup.user_id == user_id, Signup.idempotency_key == idempotency_key
            )
        ).scalar_one_or_none()
        if same_key is not None:
            if same_key.request_fingerprint != request:
                raise SignupRefusedError("idempotency_key_reused")
            return _view(same_key), False
        open_signup = session.execute(
            select(Signup).where(Signup.user_id == user_id, Signup.state.in_(OPEN_STATES))
        ).scalar_one_or_none()
        if open_signup is not None:
            return _view(open_signup), False
        if _workspaces_held(session, user_id) >= max_workspaces:
            raise SignupRefusedError("workspace_limit_reached")
        now = _now()
        row = Signup(
            id=uuid.uuid4(),
            user_id=user_id,
            idempotency_key=idempotency_key,
            request_fingerprint=request,
            state="started",
            step="none",
            workspace_name=name,
            attempts=0,
            created_at=now,
            updated_at=now,
            expires_at=now + EXPIRY,
        )
        session.add(row)
        session.flush()
        view = _view(row)
    logger.info("signup_started", extra={"signup_id": str(view.id), "signup_user_id": str(user_id)})
    return view, True


def current(user_id: uuid.UUID) -> SignupView | None:
    """This person's unfinished signup, else their most recent one."""
    with _as_user(user_id) as session:
        row = session.execute(
            select(Signup)
            .where(Signup.user_id == user_id)
            .order_by(Signup.state.in_(OPEN_STATES).desc(), Signup.created_at.desc())
            .limit(1)
        ).scalar_one_or_none()
        return _view(row) if row is not None else None


def _load(signup_id: uuid.UUID, user_id: uuid.UUID) -> _Row:
    with _as_user(user_id) as session:
        row = session.execute(
            select(Signup).where(Signup.id == signup_id, Signup.user_id == user_id)
        ).scalar_one()
        return _snapshot(row)


def view(signup_id: uuid.UUID, user_id: uuid.UUID) -> SignupView:
    with _as_user(user_id) as session:
        row = session.execute(
            select(Signup).where(Signup.id == signup_id, Signup.user_id == user_id)
        ).scalar_one()
        return _view(row)


def _set(signup_id: uuid.UUID, user_id: uuid.UUID, **values: Any) -> None:
    with _as_user(user_id) as session:
        changed = session.execute(
            update(Signup)
            .where(Signup.id == signup_id, Signup.user_id == user_id)
            .values(**values, updated_at=_now())
            .returning(Signup.id)
        ).all()
        if len(changed) != 1:
            raise _StepFailedError("signup_row_missing")


# --- Provisioning ------------------------------------------------------------


@contextmanager
def _lease(signup_id: uuid.UUID) -> Iterator[bool]:
    """Whether this process may run the signup now: a session-level advisory
    lock on a connection of its own, released at the end (or when the
    connection ends)."""
    key = {"ns": _NS_RUN, "key": str(signup_id)}
    with get_engine().connect() as connection:
        held = bool(
            connection.exec_driver_sql(
                "SELECT pg_try_advisory_lock(%(ns)s, hashtext(%(key)s))", key
            ).scalar_one()
        )
        connection.commit()
        try:
            yield held
        finally:
            if held:
                connection.exec_driver_sql(
                    "SELECT pg_advisory_unlock(%(ns)s, hashtext(%(key)s))", key
                )
                connection.commit()


def run(signup_id: uuid.UUID, user_id: uuid.UUID) -> SignupView:
    """Advance the signup as far as it goes; another runner holding it means
    it is already advancing. Returns its state afterwards."""
    with _lease(signup_id) as held:
        if held:
            _advance(signup_id, user_id)
    return view(signup_id, user_id)


def _claim(row: _Row, workspace_id: uuid.UUID) -> bool:
    try:
        _set(row.id, row.user_id, workspace_id=workspace_id, step="workspace", workspace_name=None)
    except IntegrityError:
        return False
    return True


def _adopt(row: _Row) -> uuid.UUID | None:
    """The workspace an interrupted run created, if it can be identified."""
    if row.step_started_at is None or row.workspace_name is None:
        return None
    earliest = row.step_started_at - ADOPTION_SKEW
    latest = row.step_started_at + ADOPTION_WINDOW
    for tenant in find_tenants_by_name(row.workspace_name):
        if (
            tenant.status == TenantStatus.PENDING.value
            and earliest <= tenant.created_at <= latest
            and not list_tenant_members(tenant.id)
            and _claim(row, tenant.id)
        ):
            logger.info("signup_workspace_adopted", extra={"signup_id": str(row.id)})
            return tenant.id
    return None


def _create_workspace(row: _Row) -> None:
    if row.workspace_id is not None:
        _set(row.id, row.user_id, step="workspace", workspace_name=None)
        return
    if row.step == "creating" and _adopt(row) is not None:
        return
    if row.workspace_name is None:
        raise _StepFailedError("workspace_name_missing")
    _set(row.id, row.user_id, step="creating", step_started_at=_now())
    tenant = create_tenant(row.workspace_name, caller=_provisioning_caller())
    if not _claim(row, tenant.id):
        raise _StepFailedError("workspace_claim_failed")


def _activate(workspace_id: uuid.UUID) -> None:
    status = get_tenant(workspace_id).status
    if status == TenantStatus.PENDING.value:
        transition_tenant_status(workspace_id, TenantStatus.ACTIVE, caller=_provisioning_caller())
    elif status != TenantStatus.ACTIVE.value:
        raise _StepFailedError("workspace_not_open")


def _step(row: _Row) -> bool:
    """Perform the row's next step; `False` once complete."""
    workspace, user = row.workspace_id, row.user_id
    if row.step in ("none", "creating"):
        _create_workspace(row)
        return True
    if workspace is None:  # every later step has recorded it
        raise _StepFailedError("workspace_missing")
    performed: list[str] = []
    if row.step == "workspace":
        members = list_tenant_members(workspace)
        if any(m.user_id != user for m in members):
            raise _StepFailedError("workspace_has_other_members")
        provisioning.seed_roles(workspace, performed)
        _set(row.id, user, step="roles")
    elif row.step == "roles":
        provisioning.ensure_membership(workspace, user, performed)
        _set(row.id, user, step="membership")
    elif row.step == "membership":
        membership = get_membership(workspace, user)
        if membership is None:
            raise _StepFailedError("membership_missing")
        provisioning.assign_owner(
            workspace, membership.id, provisioning.roles_by_name(workspace), performed
        )
        _set(row.id, user, step="owner")
    elif row.step == "owner":
        if not provisioning.owner_verified(workspace, user):
            raise _StepFailedError("owner_check_failed")
        _set(row.id, user, step="verified")
    elif row.step == "verified":
        _activate(workspace)
        _set(row.id, user, step="active")
    else:  # "active"
        _set(row.id, user, state="complete", last_error_code=None)
        logger.info("signup_completed", extra={"signup_id": str(row.id)})
        return False
    return True


def _advance(signup_id: uuid.UUID, user_id: uuid.UUID) -> None:
    row = _load(signup_id, user_id)
    if row.state not in OPEN_STATES:
        return
    if row.expires_at <= _now():
        _set(signup_id, user_id, state="expired", last_error_code="expired")
        logger.info("signup_expired", extra={"signup_id": str(signup_id)})
        return
    attempts = row.attempts + 1
    _set(signup_id, user_id, state="provisioning", attempts=attempts)
    try:
        while _step(_load(signup_id, user_id)):
            pass
    except Exception as exc:  # noqa: BLE001 - recorded on the row, resumed or reviewed later
        code = exc.code if isinstance(exc, _StepFailedError) else type(exc).__name__
        final = isinstance(exc, _StepFailedError) or attempts >= MAX_RUNS
        _set(
            signup_id,
            user_id,
            state="failed" if final else "provisioning",
            last_error_code=code[:64],
        )
        logger.warning(
            "signup_step_failed",
            extra={"signup_id": str(signup_id), "signup_error": code[:64], "final": final},
        )


# --- Purge and maintenance ---------------------------------------------------


def forget_workspace(workspace_id: uuid.UUID) -> int:
    """Remove the signup rows naming a purged workspace (`crm_app.purge`):
    read through the maintenance flag, deleted as each row's own person."""
    with _maintenance_reader() as session:
        rows = session.execute(
            select(Signup.id, Signup.user_id).where(Signup.workspace_id == workspace_id)
        ).all()
    for signup_id, user_id in rows:
        with _as_user(user_id) as session:
            session.execute(delete(Signup).where(Signup.id == signup_id, Signup.user_id == user_id))
    return len(rows)


def remaining_for_workspace(workspace_id: uuid.UUID) -> int:
    with _maintenance_reader() as session:
        return len(
            session.execute(select(Signup.id).where(Signup.workspace_id == workspace_id)).all()
        )


@dataclass
class MaintenanceReport:
    resumed: int = 0
    completed: int = 0
    expired: int = 0
    failed: int = 0
    removed: int = 0
    attempts_removed: int = 0


def maintain(now: datetime | None = None) -> MaintenanceReport:
    """Resume stale signups, expire old ones, remove old records."""
    now = now or _now()
    report = MaintenanceReport()
    with _maintenance_reader() as session:
        due = session.execute(
            select(Signup.id, Signup.user_id).where(
                Signup.state.in_(OPEN_STATES), Signup.updated_at < now - STALE_AFTER
            )
        ).all()
        old = session.execute(
            select(Signup.id, Signup.user_id).where(
                Signup.state.in_(("failed", "expired")), Signup.updated_at < now - RETENTION
            )
        ).all()
    for signup_id, user_id in due:
        report.resumed += 1
        state = run(signup_id, user_id).state
        if state == "complete":
            report.completed += 1
        elif state == "expired":
            report.expired += 1
        elif state == "failed":
            report.failed += 1
    for signup_id, user_id in old:
        with _as_user(user_id) as session:
            session.execute(delete(Signup).where(Signup.id == signup_id, Signup.user_id == user_id))
        report.removed += 1
    with session_scope() as session:
        report.attempts_removed = (
            session.connection()
            .exec_driver_sql(
                "DELETE FROM crm_app.signup_attempt"
                " WHERE attempted_at < now() - interval '48 hours'"
            )
            .rowcount
        )
    return report

"""Membership and role changes (PHASE2-PLAN.md §5.4, gate G-LOCK).

Every change runs while the workspace's membership lock is held: a
PostgreSQL transaction-scoped advisory lock
(`saas_os.infra.db.acquire_tenant_advisory_lock`) taken in an outer
transaction that stays open until the change has committed. The SaaS-OS
functions that make the change open their own transactions, so the lock
cannot share theirs; instead every product path that can change a
membership or a role takes the same lock first and reads the facts only
after acquiring it. Under READ COMMITTED a waiting request therefore sees
the previous change before deciding. A bounded wait
(`set_local_statement_timeout`) turns a stalled wait into a 409 instead of
holding a connection indefinitely.

The decision itself is `crm_app.domains.membership.refusal_for`. SaaS-OS's
own membership routers are not mounted: they could not enforce these
product rules.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from saas_os.api.context import RequestContext
from saas_os.api.dependencies import require_permission
from saas_os.core.authority import UserCaller
from saas_os.core.identity import (
    InvalidMembershipTransitionError,
    LastTenantAdministratorError,
    list_tenant_members,
    reactivate_membership,
    revoke_membership,
    suspend_membership,
)
from saas_os.core.rbac import (
    RoleAssignmentNotAuthorizedError,
    assign_role,
    can,
    list_membership_roles,
    list_roles,
    remove_role,
)
from saas_os.infra.db import (
    acquire_tenant_advisory_lock,
    is_statement_timeout,
    session_scope,
    set_local_statement_timeout,
)

from crm_app.api.workspaces import Member
from crm_app.domains.membership import ACTIVE, ChangeFacts, Refusal, refusal_for
from crm_app.roles import Role

router = APIRouter(prefix="/v1/workspaces", tags=["memberships"])

AssignRole = Annotated[RequestContext, Depends(require_permission("membership_role", "create"))]
RemoveRole = Annotated[RequestContext, Depends(require_permission("membership_role", "delete"))]
Suspend = Annotated[RequestContext, Depends(require_permission("membership", "suspend"))]
Reactivate = Annotated[RequestContext, Depends(require_permission("membership", "reactivate"))]
Revoke = Annotated[RequestContext, Depends(require_permission("membership", "revoke"))]

LOCK_KEY = "crm_app.memberships"
LOCK_WAIT_MILLISECONDS = 5_000
OWNER_CHECK = ("crm_app.owner", "manage")

_STATUS = {
    Refusal.SELF_CHANGE: 403,
    Refusal.OWNER_ONLY: 403,
    Refusal.CONFIRMATION_REQUIRED: 409,
    Refusal.LAST_OWNER: 409,
}


class RoleChange(BaseModel):
    role: Role
    confirm_owner_change: bool = False


class StatusChange(BaseModel):
    confirm_owner_change: bool = False


@dataclass(frozen=True)
class _Snapshot:
    target_id: uuid.UUID
    target_user_id: uuid.UUID
    target_status: str
    target_roles: frozenset[str]
    role_ids: dict[str, uuid.UUID]
    active_owners: int


def _refuse(status: int, code: str) -> HTTPException:
    return HTTPException(status_code=status, detail={"code": code})


@contextmanager
def _membership_lock(workspace: uuid.UUID) -> Iterator[None]:
    with session_scope() as session:
        set_local_statement_timeout(session, LOCK_WAIT_MILLISECONDS)
        try:
            acquire_tenant_advisory_lock(session, workspace, LOCK_KEY)
        except Exception as exc:
            if is_statement_timeout(exc):
                raise _refuse(409, "busy") from exc
            raise
        yield


def _snapshot(workspace: uuid.UUID, membership_id: uuid.UUID) -> _Snapshot:
    role_ids = {role.name: role.id for role in list_roles(workspace)}
    names = {role_id: name for name, role_id in role_ids.items()}

    def roles_of(member_id: uuid.UUID) -> frozenset[str]:
        return frozenset(
            names[a.role_id]
            for a in list_membership_roles(workspace, member_id)
            if a.role_id in names
        )

    members = list_tenant_members(workspace)
    target = next((m for m in members if m.id == membership_id), None)
    if target is None:
        raise _refuse(404, "membership_not_found")
    active_owners = sum(
        1 for m in members if m.status == ACTIVE and Role.OWNER.value in roles_of(m.id)
    )
    return _Snapshot(
        target_id=target.id,
        target_user_id=target.user_id,
        target_status=target.status,
        target_roles=roles_of(target.id),
        role_ids=role_ids,
        active_owners=active_owners,
    )


def _check(  # noqa: PLR0913 - each keyword is one named fact of the decision
    context: RequestContext,
    snap: _Snapshot,
    *,
    grants_or_removes_owner: bool,
    removes_active_owner: bool,
    stepping_down: bool,
    confirmed: bool,
) -> None:
    resource, action = OWNER_CHECK
    facts = ChangeFacts(
        caller_is_owner=can(
            actor_id=context.actor_id,
            tenant_id=context.tenant_id,
            action=action,
            resource=resource,
        ),
        touches_owner=grants_or_removes_owner or Role.OWNER.value in snap.target_roles,
        removes_active_owner=removes_active_owner,
        active_owners=snap.active_owners,
        self_change=snap.target_id == context.membership_id,
        stepping_down=stepping_down,
        confirmed=confirmed,
    )
    refusal = refusal_for(facts)
    if refusal is not None:
        raise _refuse(_STATUS[refusal], refusal.value)


def _view(workspace: uuid.UUID, membership_id: uuid.UUID) -> Member:
    snap = _snapshot(workspace, membership_id)
    return Member(
        membership_id=snap.target_id,
        user_id=snap.target_user_id,
        status=snap.target_status,
        roles=sorted(snap.target_roles),
    )


@router.post("/{tenant_id}/members/{membership_id}/roles", response_model=Member)
def add_role(
    tenant_id: uuid.UUID, membership_id: uuid.UUID, change: RoleChange, context: AssignRole
) -> Member:
    workspace = context.tenant_id
    with _membership_lock(workspace):
        snap = _snapshot(workspace, membership_id)
        if snap.target_status != ACTIVE:
            raise _refuse(409, "membership_not_active")
        _check(
            context,
            snap,
            grants_or_removes_owner=change.role is Role.OWNER,
            removes_active_owner=False,
            stepping_down=False,
            confirmed=change.confirm_owner_change,
        )
        if change.role.value in snap.target_roles:
            raise _refuse(409, "role_already_assigned")
        try:
            assign_role(
                workspace,
                snap.target_id,
                snap.role_ids[change.role.value],
                caller=UserCaller(context.actor_id),
            )
        except RoleAssignmentNotAuthorizedError as exc:
            raise _refuse(403, "not_authorized") from exc
    return _view(workspace, membership_id)


@router.delete("/{tenant_id}/members/{membership_id}/roles/{role}", response_model=Member)
def drop_role(
    tenant_id: uuid.UUID,
    membership_id: uuid.UUID,
    role: Role,
    context: RemoveRole,
    confirm_owner_change: Annotated[bool, Query()] = False,
) -> Member:
    workspace = context.tenant_id
    with _membership_lock(workspace):
        snap = _snapshot(workspace, membership_id)
        if role.value not in snap.target_roles:
            raise _refuse(404, "role_not_assigned")
        removes_owner = role is Role.OWNER
        _check(
            context,
            snap,
            grants_or_removes_owner=removes_owner,
            removes_active_owner=removes_owner and snap.target_status == ACTIVE,
            stepping_down=removes_owner and snap.target_id == context.membership_id,
            confirmed=confirm_owner_change,
        )
        try:
            remove_role(
                workspace,
                snap.target_id,
                snap.role_ids[role.value],
                caller=UserCaller(context.actor_id),
            )
        except LastTenantAdministratorError as exc:
            raise _refuse(409, "last_administrator") from exc
    return _view(workspace, membership_id)


def _status_change(
    context: RequestContext, membership_id: uuid.UUID, change: StatusChange, operation: str
) -> Member:
    workspace = context.tenant_id
    transitions = {
        "suspend": suspend_membership,
        "reactivate": reactivate_membership,
        "revoke": revoke_membership,
    }
    with _membership_lock(workspace):
        snap = _snapshot(workspace, membership_id)
        disables = operation in ("suspend", "revoke")
        _check(
            context,
            snap,
            grants_or_removes_owner=False,
            removes_active_owner=disables
            and snap.target_status == ACTIVE
            and Role.OWNER.value in snap.target_roles,
            stepping_down=False,
            confirmed=change.confirm_owner_change,
        )
        try:
            transitions[operation](workspace, snap.target_id, caller=UserCaller(context.actor_id))
        except InvalidMembershipTransitionError as exc:
            raise _refuse(409, "invalid_transition") from exc
        except LastTenantAdministratorError as exc:
            raise _refuse(409, "last_administrator") from exc
    return _view(workspace, membership_id)


@router.post("/{tenant_id}/members/{membership_id}/suspend", response_model=Member)
def suspend(
    tenant_id: uuid.UUID, membership_id: uuid.UUID, change: StatusChange, context: Suspend
) -> Member:
    return _status_change(context, membership_id, change, "suspend")


@router.post("/{tenant_id}/members/{membership_id}/reactivate", response_model=Member)
def reactivate(
    tenant_id: uuid.UUID, membership_id: uuid.UUID, change: StatusChange, context: Reactivate
) -> Member:
    return _status_change(context, membership_id, change, "reactivate")


@router.post("/{tenant_id}/members/{membership_id}/revoke", response_model=Member)
def revoke(
    tenant_id: uuid.UUID, membership_id: uuid.UUID, change: StatusChange, context: Revoke
) -> Member:
    return _status_change(context, membership_id, change, "revoke")

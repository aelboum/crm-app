"""Integrations and their API keys (decision P12-K).

An integration is a SaaS-OS service account of the workspace, with one of
the product roles Member or Read-only (never Admin or Owner, so a leaked key
cannot administer the workspace), and up to `MAX_KEYS` live API keys. A key
is shown once when issued; SaaS-OS keeps only its hash. A request that
carries it in `X-API-Key` acts as the integration, with that role's
permissions, on the routes that accept a key: reading, creating and
updating contacts, companies, deals and tasks (`crm_app.api.records`,
`.opportunities`, `.tasks`). Nothing that changes members, roles, keys or
billing ever accepts one (SaaS-OS ADR-0047).

Every change goes through SaaS-OS with the member as `UserCaller`, so
SaaS-OS checks its own permissions (`service_account:create`,
`service_account_role:create`, `api_key:create` and `:revoke`,
`service_account:disable`) and audits each one. A workspace created before
those permissions were added to the templates has none of them
(`crm_app.permission_grants.OWNER_GRANTED_ADDITIONS`): every change then
answers `IntegrationsUnavailableError`.

Disabling an integration revokes its keys first, then disables it; it is
final (no route enables it again). Prints, logs and returns no key except
the one response that issues it.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import Any

from saas_os.core.api_keys import (
    ApiKey,
    InvalidApiKeyNameError,
    create_service_account_api_key,
    list_api_keys,
    revoke_service_account_api_key,
)
from saas_os.core.authority import UserCaller
from saas_os.core.identity import (
    DuplicateServiceAccountNameError,
    InvalidServiceAccountNameError,
    ServiceAccount,
    create_service_account,
    disable_service_account,
    get_service_account,
    list_service_accounts,
)
from saas_os.core.rbac import assign_service_account_role, list_service_account_roles

from crm_app.domains.records import InvalidValue, visible_text
from crm_app.provisioning import roles_by_name
from crm_app.records import RecordError, RecordNotFoundError, Scope
from crm_app.roles import Role

# The roles an integration may hold (P12-K decision B).
ROLES = (Role.MEMBER, Role.READ_ONLY)
NAME_MAX = 100
MAX_INTEGRATIONS = 20
# Two, so a key can be replaced without a gap.
MAX_KEYS = 2
EXPIRY_DAYS = (30, 90, 365)

Item = dict[str, Any]


class IntegrationError(RecordError):
    status, code = 422, "invalid_integration"

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


class IntegrationsUnavailableError(RecordError):
    """The member, or this workspace's roles, lack SaaS-OS's integration
    permissions (a workspace created before P12-K)."""

    status, code = 403, "integrations_unavailable"


class IntegrationLimitError(RecordError):
    status, code = 409, "integration_limit"


class DuplicateIntegrationError(RecordError):
    status, code = 409, "duplicate_integration"


def name(value: str) -> str:
    text = " ".join(value.split())
    if not 1 <= len(text) <= NAME_MAX or not visible_text(text):
        raise InvalidValue(f"name: 1 to {NAME_MAX} visible characters")
    return text


def _caller(scope: Scope) -> UserCaller:
    return UserCaller(scope.actor)


def _key_item(key: ApiKey) -> Item:
    return {
        "id": key.id,
        "name": key.name,
        "created_at": key.created_at,
        "expires_at": key.expires_at,
        "revoked_at": key.revoked_at,
    }


def _role_names(workspace: uuid.UUID) -> Mapping[uuid.UUID, str]:
    return {role.id: name for name, role in roles_by_name(workspace).items()}


def _item(
    account: ServiceAccount,
    roles: Mapping[uuid.UUID, str],
    keys: list[ApiKey],
    workspace: uuid.UUID,
) -> Item:
    held = [
        roles.get(assignment.role_id)
        for assignment in list_service_account_roles(workspace, account.id)
    ]
    return {
        "id": account.id,
        "name": account.name,
        "status": account.status,
        "role": next((r for r in held if r is not None), None),
        "created_at": account.created_at,
        "keys": [_key_item(k) for k in keys if k.service_account_id == account.id],
    }


def list_integrations(scope: Scope) -> list[Item]:
    roles = _role_names(scope.workspace)
    keys = list_api_keys(scope.workspace)
    accounts = sorted(list_service_accounts(scope.workspace), key=lambda a: a.created_at)
    return [_item(account, roles, keys, scope.workspace) for account in accounts]


def _account(scope: Scope, integration_id: uuid.UUID) -> ServiceAccount:
    account = get_service_account(scope.workspace, integration_id)
    if account is None:
        raise RecordNotFoundError
    return account


def get(scope: Scope, integration_id: uuid.UUID) -> Item:
    account = _account(scope, integration_id)
    return _item(
        account, _role_names(scope.workspace), list_api_keys(scope.workspace), scope.workspace
    )


def create(scope: Scope, given_name: str, role: str) -> Item:
    """A new integration with `role` (Member or Read-only) and no key yet."""
    try:
        clean = name(given_name)
    except InvalidValue as exc:
        raise IntegrationError(str(exc)) from None
    if role not in {r.value for r in ROLES}:
        raise IntegrationError("role: Member or Read-only")
    if len(list_service_accounts(scope.workspace)) >= MAX_INTEGRATIONS:
        raise IntegrationLimitError
    target = roles_by_name(scope.workspace).get(role)
    if target is None:
        raise IntegrationsUnavailableError
    try:
        account = create_service_account(scope.workspace, clean, caller=_caller(scope))
    except DuplicateServiceAccountNameError:
        raise DuplicateIntegrationError from None
    except InvalidServiceAccountNameError:
        raise IntegrationError("name: no control characters") from None
    except PermissionError:
        raise IntegrationsUnavailableError from None
    try:
        assign_service_account_role(
            caller=_caller(scope),
            tenant_id=scope.workspace,
            service_account_id=account.id,
            role_id=target.id,
        )
    except PermissionError:
        # Without its role it can do nothing; disable it so it is not left
        # half-made, and say why.
        disable_service_account(scope.workspace, account.id, caller=_caller(scope))
        raise IntegrationsUnavailableError from None
    return get(scope, account.id)


def disable(scope: Scope, integration_id: uuid.UUID) -> Item:
    """Revoke every key, then disable the integration. Final; repeating it
    changes nothing."""
    account = _account(scope, integration_id)
    try:
        for key in list_api_keys(scope.workspace):
            if key.service_account_id == account.id and key.revoked_at is None:
                revoke_service_account_api_key(
                    caller=_caller(scope), tenant_id=scope.workspace, key_id=key.id
                )
        if account.status != "disabled":
            disable_service_account(scope.workspace, account.id, caller=_caller(scope))
    except PermissionError:
        raise IntegrationsUnavailableError from None
    return get(scope, account.id)


def _live(key: ApiKey, now: datetime) -> bool:
    return key.revoked_at is None and (key.expires_at is None or key.expires_at > now)


def create_key(
    scope: Scope, integration_id: uuid.UUID, given_name: str, expires_in_days: int | None
) -> tuple[Item, str]:
    """A new key for an active integration: its record and, once, the key."""
    account = _account(scope, integration_id)
    if account.status != "active":
        raise IntegrationError("the integration is disabled")
    try:
        clean = name(given_name)
    except InvalidValue as exc:
        raise IntegrationError(str(exc)) from None
    if expires_in_days is not None and expires_in_days not in EXPIRY_DAYS:
        raise IntegrationError("expires_in_days: 30, 90, 365 or none")
    now = datetime.now(UTC)
    live = [
        k
        for k in list_api_keys(scope.workspace)
        if k.service_account_id == account.id and _live(k, now)
    ]
    if len(live) >= MAX_KEYS:
        raise IntegrationLimitError
    expires_at = None if expires_in_days is None else now + timedelta(days=expires_in_days)
    try:
        key, raw = create_service_account_api_key(
            caller=_caller(scope),
            tenant_id=scope.workspace,
            service_account_id=account.id,
            name=clean,
            expires_at=expires_at,
        )
    except InvalidApiKeyNameError:
        raise IntegrationError("name: not accepted for a key") from None
    except PermissionError:
        raise IntegrationsUnavailableError from None
    return _key_item(key), raw


def revoke_key(scope: Scope, integration_id: uuid.UUID, key_id: uuid.UUID) -> None:
    """Revoke one of the integration's keys; at once, and repeatable."""
    account = _account(scope, integration_id)
    key = next(
        (
            k
            for k in list_api_keys(scope.workspace)
            if k.id == key_id and k.service_account_id == account.id
        ),
        None,
    )
    if key is None:
        raise RecordNotFoundError
    if key.revoked_at is not None:
        return
    try:
        revoke_service_account_api_key(
            caller=_caller(scope), tenant_id=scope.workspace, key_id=key.id
        )
    except PermissionError:
        raise IntegrationsUnavailableError from None
